#!/usr/bin/env python3
"""Loopback HTTP bridge for Spotify's Linux MPRIS interface."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import math
import os
import socket
import sys
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol

from dbus_next import Message, MessageType, Variant
from dbus_next.aio import MessageBus


class SpotifyAdapter(Protocol):
    def get_state(self) -> dict[str, object]: ...

    def command(self, command: str, value: float | None = None) -> None: ...


MAX_BODY_BYTES = 4096
ALLOWED_COMMANDS = {"play", "pause", "playpause", "next", "previous", "volume"}
MPRIS_NAME = "org.mpris.MediaPlayer2.spotify"
MPRIS_PATH = "/org/mpris/MediaPlayer2"
MPRIS_PLAYER = "org.mpris.MediaPlayer2.Player"
DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"
COMMAND_MEMBERS = {
    "play": "Play",
    "pause": "Pause",
    "playpause": "PlayPause",
    "next": "Next",
    "previous": "Previous",
}


def _empty_state(revision: int = 0) -> dict[str, object]:
    return {
        "connected": False,
        "playing": False,
        "title": "",
        "artist": "",
        "album": "",
        "artUrl": "",
        "trackId": "",
        "lengthUs": 0,
        "positionUs": 0,
        "canPlay": False,
        "canPause": False,
        "canGoNext": False,
        "canGoPrevious": False,
        "canSeek": False,
        "volume": 0.0,
        "canSetVolume": False,
        "revision": revision,
    }


class PlayerState:
    """Thread-safe MPRIS snapshot with monotonic position interpolation."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._state = _empty_state()
        self._has_volume = False
        self._can_control = False
        self._position_timestamp = clock()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            state = dict(self._state)
            self._advance_position(state, self._clock())
            return state

    def update(self, properties: dict[str, Any], *, replace: bool = False) -> None:
        values = {name: variant.value for name, variant in properties.items()}
        now = self._clock()
        with self._lock:
            if replace:
                state = _empty_state(int(self._state["revision"]))
                self._has_volume = False
                self._can_control = False
            else:
                state = dict(self._state)
                self._advance_position(state, now)
            old_track_id = str(state["trackId"])
            state["connected"] = True
            if "PlaybackStatus" in values:
                state["playing"] = values["PlaybackStatus"] == "Playing"
            if "Metadata" in values:
                metadata = values["Metadata"]
                state["title"] = self._metadata_value(metadata, "xesam:title")
                artists = self._variant_value(metadata.get("xesam:artist"), [])
                if isinstance(artists, (list, tuple)):
                    state["artist"] = ", ".join(str(artist) for artist in artists)
                else:
                    state["artist"] = str(artists)
                state["album"] = self._metadata_value(metadata, "xesam:album")
                state["artUrl"] = self._metadata_value(metadata, "mpris:artUrl")
                state["trackId"] = self._metadata_value(metadata, "mpris:trackid")
                state["lengthUs"] = int(
                    self._variant_value(metadata.get("mpris:length"), 0)
                )
                if state["trackId"] != old_track_id and "Position" not in values:
                    state["positionUs"] = 0
            property_map = {
                "Position": "positionUs",
                "CanPlay": "canPlay",
                "CanPause": "canPause",
                "CanGoNext": "canGoNext",
                "CanGoPrevious": "canGoPrevious",
                "CanSeek": "canSeek",
            }
            for property_name, state_name in property_map.items():
                if property_name in values:
                    state[state_name] = values[property_name]
            if "Volume" in values:
                self._has_volume = True
                state["volume"] = min(1.0, max(0.0, float(values["Volume"])))
            if "CanControl" in values:
                self._can_control = bool(values["CanControl"])
            state["canSetVolume"] = self._has_volume and self._can_control
            state["revision"] = int(state["revision"]) + 1
            self._state = state
            self._position_timestamp = now

    def seeked(self, position_us: int) -> None:
        with self._lock:
            state = dict(self._state)
            state["positionUs"] = max(0, position_us)
            state["revision"] = int(state["revision"]) + 1
            self._state = state
            self._position_timestamp = self._clock()

    def disconnect(self) -> None:
        with self._lock:
            if not self._state["connected"]:
                return
            revision = int(self._state["revision"]) + 1
            self._state = _empty_state(revision)
            self._has_volume = False
            self._can_control = False
            self._position_timestamp = self._clock()

    def _advance_position(self, state: dict[str, object], now: float) -> None:
        if not state["connected"] or not state["playing"]:
            return
        elapsed_us = int(max(0.0, now - self._position_timestamp) * 1_000_000)
        position = int(state["positionUs"]) + elapsed_us
        length = int(state["lengthUs"])
        state["positionUs"] = min(position, length) if length > 0 else position

    @classmethod
    def _metadata_value(cls, metadata: dict[str, Any], name: str) -> str:
        return str(cls._variant_value(metadata.get(name), ""))

    @staticmethod
    def _variant_value(value: Any, default: Any) -> Any:
        return default if value is None else getattr(value, "value", value)


class MprisSpotifyAdapter:
    """Maintain a thread-safe snapshot of Spotify's MPRIS player."""

    def __init__(self) -> None:
        self._state = PlayerState()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._owner = ""
        self._owner_generation = 0
        self._refresh_generation = 0
        self._refreshing = False
        self._refresh_again = False
        self._pending_events: list[tuple[str, object]] = []
        self._stopping = threading.Event()
        self._thread = threading.Thread(
            target=self._thread_main, name="spotify-mpris", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stopping.set()
        loop = self._loop
        bus = self._bus
        if loop is not None and bus is not None:
            try:
                loop.call_soon_threadsafe(bus.disconnect)
            except RuntimeError:
                pass
        if self._thread.is_alive():
            self._thread.join(timeout=3)

    def get_state(self) -> dict[str, object]:
        return self._state.snapshot()

    def command(self, command: str, value: float | None = None) -> None:
        if not isinstance(command, str) or command not in ALLOWED_COMMANDS:
            raise ValueError("unsupported command")
        if command == "volume":
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError("invalid volume")
        elif value is not None:
            raise ValueError("command does not accept a value")
        if command == "volume" and not self._state.snapshot()["canSetVolume"]:
            raise ConnectionError("Spotify volume control is unavailable")
        loop = self._loop
        if loop is None or self._bus is None or not self._owner:
            raise ConnectionError("Spotify is not connected")
        owner = self._owner
        future = asyncio.run_coroutine_threadsafe(
            self._send_command(
                owner, command, None if value is None else float(value)
            ),
            loop,
        )
        try:
            future.result(timeout=2)
        except TimeoutError:
            future.cancel()
            raise

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        logged_failure = False
        while not self._stopping.is_set():
            try:
                await self._connect_and_monitor()
                logged_failure = False
            except Exception as failure:
                self._set_disconnected()
                if not logged_failure:
                    logging.warning("Spotify MPRIS unavailable: %s", failure)
                    logged_failure = True
            finally:
                bus = self._bus
                if bus is not None:
                    try:
                        bus.disconnect()
                    except Exception:
                        pass
                self._bus = None
                self._owner = ""
                self._owner_generation += 1
                self._refresh_generation += 1
                self._refreshing = False
                self._refresh_again = False
                self._pending_events = []
            if not self._stopping.is_set():
                await asyncio.sleep(1)

    async def _connect_and_monitor(self) -> None:
        bus = await MessageBus().connect()
        self._bus = bus
        bus.add_message_handler(self._handle_message)
        await self._add_match(
            "type='signal',sender='org.freedesktop.DBus',"
            "interface='org.freedesktop.DBus',member='NameOwnerChanged',"
            f"arg0='{MPRIS_NAME}'"
        )
        await self._add_match(
            f"type='signal',path='{MPRIS_PATH}',interface='{DBUS_PROPERTIES}',"
            f"member='PropertiesChanged',arg0='{MPRIS_PLAYER}'"
        )
        await self._add_match(
            f"type='signal',path='{MPRIS_PATH}',interface='{MPRIS_PLAYER}',"
            "member='Seeked'"
        )
        owner_generation = self._owner_generation
        owner = await self._get_name_owner()
        if self._owner_generation == owner_generation:
            self._owner = owner
            if owner:
                self._start_refresh(owner)
            else:
                self._set_disconnected()
        await bus.wait_for_disconnect()
        self._set_disconnected()

    async def _add_match(self, rule: str) -> None:
        reply = await self._call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[rule],
            )
        )
        self._raise_for_error(reply)

    async def _get_name_owner(self) -> str:
        reply = await self._call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="GetNameOwner",
                signature="s",
                body=[MPRIS_NAME],
            )
        )
        if reply.message_type == MessageType.ERROR:
            if reply.error_name == "org.freedesktop.DBus.Error.NameHasNoOwner":
                return ""
            self._raise_for_error(reply)
        return str(reply.body[0])

    async def _fetch_properties(self, owner: str) -> dict[str, Any]:
        reply = await self._call(
            Message(
                destination=owner,
                path=MPRIS_PATH,
                interface=DBUS_PROPERTIES,
                member="GetAll",
                signature="s",
                body=[MPRIS_PLAYER],
            )
        )
        self._raise_for_error(reply)
        return reply.body[0]

    async def _send_command(
        self, owner: str, command: str, value: float | None
    ) -> None:
        if command == "volume":
            reply = await self._call(
                Message(
                    destination=owner,
                    path=MPRIS_PATH,
                    interface=DBUS_PROPERTIES,
                    member="Set",
                    signature="ssv",
                    body=[MPRIS_PLAYER, "Volume", Variant("d", value)],
                )
            )
        else:
            reply = await self._call(
                Message(
                    destination=owner,
                    path=MPRIS_PATH,
                    interface=MPRIS_PLAYER,
                    member=COMMAND_MEMBERS[command],
                )
            )
        self._raise_for_error(reply)

    async def _call(self, message: Message) -> Message:
        bus = self._bus
        if bus is None:
            raise ConnectionError("session bus is disconnected")
        reply = await bus.call(message)
        if reply is None:
            raise ConnectionError("D-Bus call returned no reply")
        return reply

    @staticmethod
    def _raise_for_error(reply: Message) -> None:
        if reply.message_type == MessageType.ERROR:
            detail = str(reply.body[0]) if reply.body else reply.error_name
            raise ConnectionError(detail)

    def _handle_message(self, message: Message) -> None:
        if (
            message.message_type == MessageType.SIGNAL
            and message.interface == "org.freedesktop.DBus"
            and message.member == "NameOwnerChanged"
            and message.body
            and message.body[0] == MPRIS_NAME
        ):
            self._owner_generation += 1
            self._owner = str(message.body[2])
            self._set_disconnected()
            if self._owner:
                self._start_refresh(self._owner)
            return
        if (
            message.message_type == MessageType.SIGNAL
            and message.sender == self._owner
            and message.interface == DBUS_PROPERTIES
            and message.member == "PropertiesChanged"
            and message.body
            and message.body[0] == MPRIS_PLAYER
        ):
            invalidated = message.body[2] if len(message.body) > 2 else []
            changes = message.body[1]
            if self._refreshing:
                if changes:
                    self._pending_events.append(("properties", changes))
                self._refresh_again = self._refresh_again or bool(invalidated)
            elif invalidated:
                self._start_refresh(self._owner)
                if changes:
                    self._pending_events.append(("properties", changes))
            else:
                self._state.update(changes)
            return
        if (
            message.message_type == MessageType.SIGNAL
            and message.sender == self._owner
            and message.interface == MPRIS_PLAYER
            and message.member == "Seeked"
            and message.body
        ):
            position_us = int(message.body[0])
            if self._refreshing:
                self._pending_events.append(("seeked", position_us))
            else:
                self._state.seeked(position_us)

    def _start_refresh(self, owner: str) -> None:
        self._refresh_generation += 1
        generation = self._refresh_generation
        self._refreshing = True
        self._refresh_again = False
        self._pending_events = []
        asyncio.create_task(self._refresh_owner(owner, generation))

    async def _refresh_owner(self, owner: str, generation: int) -> None:
        try:
            properties = await self._fetch_properties(owner)
        except Exception:
            if self._owner == owner and self._refresh_generation == generation:
                self._refreshing = False
                self._pending_events = []
                self._set_disconnected()
                asyncio.create_task(self._retry_refresh(owner, generation))
            return
        if self._owner != owner or self._refresh_generation != generation:
            return
        pending_events = self._pending_events
        refresh_again = self._refresh_again
        self._state.update(properties, replace=True)
        for event_name, payload in pending_events:
            if event_name == "properties":
                self._state.update(payload)
            else:
                self._state.seeked(int(payload))
        self._refreshing = False
        self._pending_events = []
        if refresh_again:
            self._start_refresh(owner)

    async def _retry_refresh(self, owner: str, generation: int) -> None:
        await asyncio.sleep(1)
        if (
            not self._stopping.is_set()
            and self._owner == owner
            and self._refresh_generation == generation
        ):
            self._start_refresh(owner)

    def _set_disconnected(self) -> None:
        self._state.disconnect()


def create_http_server(
    adapter: SpotifyAdapter, token: str, *, port: int = 0
) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("token must not be empty")

    class BridgeHandler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(2)

        def do_GET(self) -> None:
            if not self._authorized():
                return
            if self.path != "/state":
                self._json(404, {"error": "not_found"})
                return
            self._json(200, adapter.get_state())

        def do_POST(self) -> None:
            if not self._authorized():
                return
            if self.path != "/command":
                self._json(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._json(400, {"error": "invalid_body"})
                return
            if length < 0:
                self._json(400, {"error": "invalid_body"})
                return
            if length > MAX_BODY_BYTES:
                self._json(413, {"error": "body_too_large"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except socket.timeout:
                self._json(408, {"error": "request_timeout"})
                return
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json(400, {"error": "invalid_body"})
                return
            command = payload.get("command") if isinstance(payload, dict) else None
            if not isinstance(command, str) or command not in ALLOWED_COMMANDS:
                self._json(400, {"error": "invalid_command"})
                return
            value = payload.get("value") if isinstance(payload, dict) else None
            if command == "volume":
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0.0 <= value <= 1.0
                ):
                    self._json(400, {"error": "invalid_value"})
                    return
                value = float(value)
            elif value is not None:
                self._json(400, {"error": "invalid_value"})
                return
            if not adapter.get_state().get("connected", False):
                self._json(503, {"error": "spotify_unavailable"})
                return
            try:
                adapter.command(command, value)
            except (ConnectionError, TimeoutError):
                self._json(503, {"error": "spotify_unavailable"})
                return
            self._json(204, {})

        def _authorized(self) -> bool:
            if self.headers.get("Origin") is not None:
                self._json(403, {"error": "origin_forbidden"})
                return False
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied, f"Bearer {token}"):
                self._json(401, {"error": "unauthorized"})
                return False
            return True

        def _json(self, status: int, payload: dict[str, object]) -> None:
            body = (
                b""
                if status == 204
                else json.dumps(payload, separators=(",", ":")).encode("utf-8")
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    class BridgeHttpServer(ThreadingHTTPServer):
        daemon_threads = True

    return BridgeHttpServer(("127.0.0.1", port), BridgeHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    arguments = parser.parse_args()
    token = os.environ.get("CHILL_SPOTIFY_TOKEN", "")
    if not token:
        parser.error("CHILL_SPOTIFY_TOKEN must be set")

    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    adapter = MprisSpotifyAdapter()
    adapter.start()
    server = create_http_server(adapter, token, port=arguments.port)
    print(json.dumps({"port": server.server_port}, separators=(",", ":")), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        adapter.close()


if __name__ == "__main__":
    main()
