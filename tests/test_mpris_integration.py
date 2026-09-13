"""Private-session-bus integration tests for the Spotify MPRIS bridge."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import json
import os
import selectors
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from typing import Any
from urllib import error, request

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess, RequestNameReply
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, dbus_property, method

from spotify_bridge import (
    MPRIS_NAME,
    MPRIS_PATH,
    MPRIS_PLAYER,
    MprisSpotifyAdapter,
    create_http_server,
)


TOKEN = "integration-test-secret"
TIMEOUT_SECONDS = 3.0
HTTP_TIMEOUT_SECONDS = 2.0
PRIVATE_BUS_CONFIG = """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
  "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir={tmpdir}</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*"/>
    <allow receive_sender="*"/>
    <allow own="*"/>
  </policy>
</busconfig>
"""


def _wait_until(
    predicate: Callable[[], bool], *, timeout: float = TIMEOUT_SECONDS
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not reached before the timeout")


def _readline_with_timeout(
    stream: Any, timeout: float, *, error_stream: Any = None
) -> str:
    selector = selectors.DefaultSelector()
    selector.register(stream, selectors.EVENT_READ)
    try:
        if not selector.select(timeout):
            raise TimeoutError("dbus-daemon did not publish an address")
        line = stream.readline().strip()
    finally:
        selector.close()
    if not line:
        detail = "" if error_stream is None else error_stream.read().strip()
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"dbus-daemon published an empty address{suffix}")
    return line


def _stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=TIMEOUT_SECONDS)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()


def _metadata(track_id: str, title: str) -> dict[str, Variant]:
    return {
        "mpris:trackid": Variant("o", f"/org/mpris/MediaPlayer2/{track_id}"),
        "mpris:length": Variant("x", 180_000_000),
        "mpris:artUrl": Variant("s", "https://example.invalid/cover.jpg"),
        "xesam:title": Variant("s", title),
        "xesam:artist": Variant("as", ["Satone"]),
        "xesam:album": Variant("s", "Chill"),
    }


class FakeMprisPlayer(ServiceInterface):
    """Small MPRIS Player service exported only on the private test bus."""

    def __init__(
        self,
        *,
        change_volume_during_first_snapshot: bool = False,
    ) -> None:
        self._lock = threading.Lock()
        self._commands: list[str] = []
        self._change_volume_during_first_snapshot = change_volume_during_first_snapshot
        self._fail_first_snapshot = False
        self._properties: dict[str, Any] = {
            "PlaybackStatus": "Paused",
            "Metadata": _metadata("track_one", "Midnight Walk"),
            "Position": 1_000_000,
            "CanPlay": True,
            "CanPause": True,
            "CanGoNext": True,
            "CanGoPrevious": True,
            "CanSeek": True,
            "CanControl": True,
            "Volume": 0.25,
        }
        super().__init__(MPRIS_PLAYER)

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":
        if self._fail_first_snapshot:
            self._fail_first_snapshot = False
            raise DBusError(
                "org.freedesktop.DBus.Error.Failed", "player is not ready"
            )
        return self._properties["PlaybackStatus"]

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":
        return self._properties["Metadata"]

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":
        return self._properties["Position"]

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":
        return self._properties["CanPlay"]

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":
        return self._properties["CanPause"]

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":
        return self._properties["CanGoNext"]

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":
        return self._properties["CanGoPrevious"]

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":
        return self._properties["CanSeek"]

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":
        return self._properties["CanControl"]

    @dbus_property(access=PropertyAccess.READWRITE)
    def Volume(self) -> "d":
        with self._lock:
            volume = self._properties["Volume"]
            should_change = self._change_volume_during_first_snapshot
            self._change_volume_during_first_snapshot = False
            if should_change:
                self._properties["Volume"] = 0.8
        if should_change:
            self.emit_properties_changed({"Volume": 0.8})
        return volume

    @Volume.setter
    def Volume(self, value: "d") -> None:
        self._record_and_update("volume", {"Volume": value})

    @method()
    def Play(self):
        self._record_and_update("play", {"PlaybackStatus": "Playing"})

    @method()
    def Pause(self):
        self._record_and_update("pause", {"PlaybackStatus": "Paused"})

    @method()
    def PlayPause(self):
        status = self._properties["PlaybackStatus"]
        next_status = "Paused" if status == "Playing" else "Playing"
        self._record_and_update("playpause", {"PlaybackStatus": next_status})

    @method()
    def Next(self):
        self._record_and_update(
            "next", {"Metadata": _metadata("track_two", "Afterglow")}
        )

    @method()
    def Previous(self):
        self._record_and_update(
            "previous", {"Metadata": _metadata("track_one", "Midnight Walk")}
        )

    def _record_and_update(self, command: str, changes: dict[str, Any]) -> None:
        with self._lock:
            self._commands.append(command)
            self._properties.update(changes)
        self.emit_properties_changed(changes)

    def set_properties(self, changes: dict[str, Any]) -> None:
        with self._lock:
            self._properties.update(changes)
        self.emit_properties_changed(changes)

    def commands(self) -> list[str]:
        with self._lock:
            return list(self._commands)

    def property_value(self, name: str) -> object:
        with self._lock:
            return self._properties[name]

    def arm_snapshot_failure(self) -> None:
        self._fail_first_snapshot = True


class FakeMprisBus:
    def __init__(
        self,
        *,
        change_volume_during_first_snapshot: bool = False,
        fail_first_snapshot: bool = False,
    ) -> None:
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._stopped = threading.Event()
        self._failure: BaseException | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._player: FakeMprisPlayer | None = None
        self._change_volume_during_first_snapshot = change_volume_during_first_snapshot
        self._fail_first_snapshot = fail_first_snapshot
        self._thread = threading.Thread(
            target=self._thread_main, name="fake-mpris", daemon=True
        )

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(TIMEOUT_SECONDS):
            self.close()
            raise TimeoutError("fake MPRIS service did not start")
        if self._failure is not None:
            failure = self._failure
            self.close()
            raise RuntimeError("fake MPRIS service failed to start") from failure

    def close(self) -> None:
        self._stopping.set()
        if self._thread.is_alive() and not self._stopped.wait(TIMEOUT_SECONDS):
            raise RuntimeError("fake MPRIS service did not stop")
        self._thread.join(timeout=0)

    @property
    def commands(self) -> list[str]:
        player = self._player
        return [] if player is None else player.commands()

    def property_value(self, name: str) -> object:
        player = self._player
        if player is None:
            raise RuntimeError("fake MPRIS service is not running")
        return player.property_value(name)

    def release_name(self) -> None:
        bus = self._bus
        loop = self._loop
        if bus is None or loop is None:
            raise RuntimeError("fake MPRIS service is not running")
        reply = asyncio.run_coroutine_threadsafe(
            bus.release_name(MPRIS_NAME), loop
        ).result(HTTP_TIMEOUT_SECONDS)
        self.assert_name_reply(reply, "RELEASED")

    def reacquire_name(self) -> None:
        bus = self._bus
        loop = self._loop
        if bus is None or loop is None:
            raise RuntimeError("fake MPRIS service is not running")
        reply = asyncio.run_coroutine_threadsafe(
            bus.request_name(MPRIS_NAME), loop
        ).result(HTTP_TIMEOUT_SECONDS)
        if reply is not RequestNameReply.PRIMARY_OWNER:
            raise RuntimeError(f"fake MPRIS service did not own its name: {reply}")

    def set_properties(self, changes: dict[str, Any]) -> None:
        player = self._player
        loop = self._loop
        if player is None or loop is None:
            raise RuntimeError("fake MPRIS service is not running")
        completion: concurrent.futures.Future[None] = concurrent.futures.Future()

        def update() -> None:
            try:
                player.set_properties(changes)
            except BaseException as failure:
                completion.set_exception(failure)
            else:
                completion.set_result(None)

        loop.call_soon_threadsafe(update)
        completion.result(HTTP_TIMEOUT_SECONDS)

    @staticmethod
    def assert_name_reply(reply: Any, expected_name: str) -> None:
        if getattr(reply, "name", None) != expected_name:
            raise RuntimeError(f"unexpected fake MPRIS name reply: {reply}")

    def _thread_main(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        try:
            self._loop = asyncio.get_running_loop()
            self._bus = await MessageBus().connect()
            self._player = FakeMprisPlayer(
                change_volume_during_first_snapshot=(
                    self._change_volume_during_first_snapshot
                ),
            )
            self._bus.export(MPRIS_PATH, self._player)
            await asyncio.sleep(0)
            if self._fail_first_snapshot:
                self._player.arm_snapshot_failure()
            reply = await self._bus.request_name(MPRIS_NAME)
            if reply is not RequestNameReply.PRIMARY_OWNER:
                raise RuntimeError(f"fake MPRIS name was not acquired: {reply}")
        except BaseException as failure:
            self._failure = failure
            self._ready.set()
        else:
            self._ready.set()
            while not self._stopping.is_set():
                await asyncio.sleep(0.01)
        finally:
            bus = self._bus
            if bus is not None:
                bus.disconnect()
            self._stopped.set()


class HttpBridge:
    def __init__(self, adapter: MprisSpotifyAdapter) -> None:
        self.server: ThreadingHTTPServer = create_http_server(
            adapter, TOKEN, port=0
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            name="test-http-bridge",
            daemon=True,
        )
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=TIMEOUT_SECONDS)
        if self.thread.is_alive():
            raise RuntimeError("HTTP bridge did not stop")

    def fetch(
        self,
        path: str,
        *,
        method_name: str = "GET",
        body: bytes | None = None,
    ) -> tuple[int, dict[str, object]]:
        http_request = request.Request(
            f"http://127.0.0.1:{self.server.server_port}{path}",
            data=body,
            method=method_name,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
        )
        try:
            response = request.urlopen(http_request, timeout=HTTP_TIMEOUT_SECONDS)
        except error.HTTPError as failure:
            response = failure
        with response:
            payload = response.read()
            return (
                response.status,
                json.loads(payload.decode("utf-8")) if payload else {},
            )

    def command(
        self, command_name: str, value: float | None = None
    ) -> tuple[int, dict[str, object]]:
        command: dict[str, object] = {"command": command_name}
        if value is not None:
            command["value"] = value
        return self.fetch(
            "/command",
            method_name="POST",
            body=json.dumps(command).encode("utf-8"),
        )


class PrivateBusFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._previous_bus_address = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        daemon = shutil.which("dbus-daemon") or "/run/current-system/sw/bin/dbus-daemon"
        process: subprocess.Popen[str] | None = None
        config_directory = tempfile.TemporaryDirectory(prefix="chill-with-you-dbus-")
        try:
            config_path = os.path.join(config_directory.name, "session.conf")
            with open(config_path, "w", encoding="utf-8") as config:
                config.write(PRIVATE_BUS_CONFIG.format(tmpdir=config_directory.name))
            daemon_environment = os.environ.copy()
            daemon_environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
            process = subprocess.Popen(
                [
                    daemon,
                    f"--config-file={config_path}",
                    "--nofork",
                    "--print-address=1",
                ],
                env=daemon_environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            address = _readline_with_timeout(
                process.stdout,
                TIMEOUT_SECONDS,
                error_stream=process.stderr,
            )
            cls._daemon = process
            cls._config_directory = config_directory
            cls._private_bus_address = address
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = address
        except BaseException:
            _stop_process(process)
            config_directory.cleanup()
            raise
        cls.addClassCleanup(cls._cleanup_private_bus)

    @classmethod
    def _cleanup_private_bus(cls) -> None:
        _stop_process(getattr(cls, "_daemon", None))
        config_directory = getattr(cls, "_config_directory", None)
        if config_directory is not None:
            config_directory.cleanup()
        previous = cls._previous_bus_address
        if previous is None:
            os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
        else:
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = previous


class MprisBridgeIntegrationTests(PrivateBusFixture):
    def test_initial_snapshot_failure_is_retried_without_an_owner_change(self) -> None:
        with contextlib.ExitStack() as cleanup:
            fake = FakeMprisBus(fail_first_snapshot=True)
            fake.start()
            cleanup.callback(fake.close)

            adapter = MprisSpotifyAdapter()
            adapter.start()
            cleanup.callback(adapter.close)

            _wait_until(
                lambda: bool(adapter.get_state()["connected"])
                and adapter.get_state()["title"] == "Midnight Walk"
            )

    def test_signal_received_during_initial_snapshot_wins_over_stale_snapshot(self) -> None:
        with contextlib.ExitStack() as cleanup:
            fake = FakeMprisBus(change_volume_during_first_snapshot=True)
            fake.start()
            cleanup.callback(fake.close)

            adapter = MprisSpotifyAdapter()
            adapter.start()
            cleanup.callback(adapter.close)

            _wait_until(lambda: bool(adapter.get_state()["connected"]))
            self.assertEqual(adapter.get_state()["volume"], 0.8)

    def test_adapter_started_before_spotify_connects_when_name_appears(self) -> None:
        with contextlib.ExitStack() as cleanup:
            adapter = MprisSpotifyAdapter()
            adapter.start()

            fake = FakeMprisBus()
            try:
                fake.start()
            except BaseException:
                adapter.close()
                raise
            cleanup.callback(fake.close)
            cleanup.callback(adapter.close)

            _wait_until(
                lambda: bool(adapter.get_state()["connected"])
                and adapter.get_state()["title"] == "Midnight Walk"
            )

            self.assertEqual(adapter.get_state()["volume"], 0.25)
            self.assertTrue(adapter.get_state()["canSetVolume"])

    def test_http_commands_and_name_re_registration_use_private_mpris(self) -> None:
        with contextlib.ExitStack() as cleanup:
            fake = FakeMprisBus()
            fake.start()
            cleanup.callback(fake.close)

            adapter = MprisSpotifyAdapter()
            adapter.start()
            cleanup.callback(adapter.close)

            _wait_until(
                lambda: bool(adapter.get_state()["connected"])
                and adapter.get_state()["title"] == "Midnight Walk"
            )
            bridge = HttpBridge(adapter)
            cleanup.callback(bridge.close)

            self.assertEqual(
                os.environ.get("DBUS_SESSION_BUS_ADDRESS"),
                self._private_bus_address,
            )
            status, state = bridge.fetch("/state")
            self.assertEqual(status, 200)
            self.assertTrue(state["connected"])
            self.assertEqual(state["title"], "Midnight Walk")
            self.assertEqual(state["artist"], "Satone")
            self.assertEqual(state["volume"], 0.25)
            self.assertTrue(state["canSetVolume"])

            fake.set_properties({"PlaybackStatus": "Playing"})
            _wait_until(lambda: adapter.get_state()["playing"] is True)
            fake.set_properties({"PlaybackStatus": "Paused"})
            _wait_until(lambda: adapter.get_state()["playing"] is False)

            command_expectations = (
                ("play", ("play",), lambda: adapter.get_state()["playing"] is True),
                ("pause", ("play", "pause"), lambda: adapter.get_state()["playing"] is False),
                (
                    "next",
                    ("play", "pause", "next"),
                    lambda: adapter.get_state()["title"] == "Afterglow",
                ),
                (
                    "previous",
                    ("play", "pause", "next", "previous"),
                    lambda: adapter.get_state()["title"] == "Midnight Walk",
                ),
            )
            for command_name, expected_commands, state_changed in command_expectations:
                with self.subTest(command=command_name):
                    status, payload = bridge.command(command_name)
                    self.assertEqual((status, payload), (204, {}))
                    _wait_until(lambda: fake.commands == list(expected_commands))
                    _wait_until(state_changed)

            status, payload = bridge.command("volume", 0.6)
            self.assertEqual((status, payload), (204, {}))
            _wait_until(lambda: fake.property_value("Volume") == 0.6)
            _wait_until(lambda: adapter.get_state()["volume"] == 0.6)

            fake.set_properties({"Volume": 0.4})
            _wait_until(lambda: adapter.get_state()["volume"] == 0.4)

            fake.set_properties({"CanControl": False})
            _wait_until(lambda: adapter.get_state()["canSetVolume"] is False)
            status, payload = bridge.command("volume", 0.7)
            self.assertEqual(
                (status, payload),
                (503, {"error": "spotify_unavailable"}),
            )
            self.assertEqual(fake.property_value("Volume"), 0.4)
            fake.set_properties({"CanControl": True})
            _wait_until(lambda: adapter.get_state()["canSetVolume"] is True)

            fake.release_name()
            _wait_until(lambda: adapter.get_state()["connected"] is False)

            fake.set_properties(
                {"Metadata": _metadata("track_three", "Reconnected")}
            )
            fake.reacquire_name()
            _wait_until(
                lambda: bool(adapter.get_state()["connected"])
                and adapter.get_state()["title"] == "Reconnected"
            )
            status, state = bridge.fetch("/state")
            self.assertEqual(status, 200)
            self.assertTrue(state["connected"])
            self.assertEqual(state["title"], "Reconnected")
            self.assertEqual(state["volume"], 0.4)


if __name__ == "__main__":
    unittest.main()
