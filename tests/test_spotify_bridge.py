"""HTTP contract tests for the local Spotify MPRIS bridge."""

from __future__ import annotations

import json
import math
import threading
import unittest
from urllib import error, request

from dbus_next import Variant

from spotify_bridge import PlayerState, create_http_server


TOKEN = "test-secret"


class FakeSpotifyAdapter:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state
        self.commands: list[tuple[str, float | None]] = []

    def get_state(self) -> dict[str, object]:
        return dict(self.state)

    def command(self, command: str, value: float | None = None) -> None:
        self.commands.append((command, value))


class BridgeServer:
    def __init__(self, adapter: FakeSpotifyAdapter) -> None:
        self.server = create_http_server(adapter, TOKEN, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever)

    def __enter__(self) -> "BridgeServer":
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def fetch(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        all_headers = {"Authorization": f"Bearer {TOKEN}"}
        all_headers.update(headers or {})
        http_request = request.Request(
            self.url + path, data=body, method=method, headers=all_headers
        )
        try:
            response = request.urlopen(http_request, timeout=2)
        except error.HTTPError as failure:
            response = failure
        with response:
            response_body = response.read()
            return response.status, json.loads(response_body) if response_body else {}


class StateEndpointTests(unittest.TestCase):
    def test_authenticated_state_returns_the_complete_dto(self) -> None:
        expected = {
            "connected": True,
            "playing": True,
            "title": "Midnight Walk",
            "artist": "Satone",
            "album": "Chill",
            "artUrl": "https://example.invalid/cover.jpg",
            "trackId": "spotify:track:123",
            "lengthUs": 180_000_000,
            "positionUs": 12_000_000,
            "canPlay": True,
            "canPause": True,
            "canGoNext": True,
            "canGoPrevious": False,
            "canSeek": True,
            "volume": 0.25,
            "canSetVolume": True,
            "revision": 7,
        }
        with BridgeServer(FakeSpotifyAdapter(expected)) as bridge:
            status, payload = bridge.fetch("/state")

        self.assertEqual(status, 200)
        self.assertEqual(payload, expected)

    def test_all_endpoints_require_the_exact_bearer_token(self) -> None:
        adapter = FakeSpotifyAdapter({"connected": False})
        with BridgeServer(adapter) as bridge:
            for authorization in (None, "Bearer wrong", TOKEN):
                headers = (
                    {} if authorization is None else {"Authorization": authorization}
                )
                http_request = request.Request(bridge.url + "/state", headers=headers)
                with self.subTest(authorization=authorization):
                    with self.assertRaises(error.HTTPError) as failure:
                        request.urlopen(http_request, timeout=2)
                    with failure.exception as response:
                        self.assertEqual(response.code, 401)

    def test_browser_origin_requests_are_rejected(self) -> None:
        with BridgeServer(FakeSpotifyAdapter({"connected": False})) as bridge:
            status, payload = bridge.fetch(
                "/state", headers={"Origin": "https://example.invalid"}
            )

        self.assertEqual(status, 403)
        self.assertEqual(payload, {"error": "origin_forbidden"})


class PlayerStateTests(unittest.TestCase):
    def test_disconnected_snapshot_is_a_complete_empty_state(self) -> None:
        self.assertEqual(
            PlayerState().snapshot(),
            {
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
                "revision": 0,
            },
        )

    def test_position_advances_and_is_preserved_across_partial_updates(self) -> None:
        now = [10.0]
        state = PlayerState(clock=lambda: now[0])
        state.update(
            {
                "PlaybackStatus": Variant("s", "Playing"),
                "Position": Variant("x", 2_000_000),
                "Metadata": Variant(
                    "a{sv}",
                    {
                        "mpris:trackid": Variant("o", "/track/one"),
                        "mpris:length": Variant("x", 20_000_000),
                    },
                ),
            }
        )
        now[0] = 13.0

        state.update({"CanPause": Variant("b", True)})
        now[0] = 14.0

        self.assertEqual(state.snapshot()["positionUs"], 6_000_000)

    def test_new_track_without_position_starts_at_zero_and_seeked_rebases_it(self) -> None:
        now = [20.0]
        state = PlayerState(clock=lambda: now[0])
        state.update(
            {
                "PlaybackStatus": Variant("s", "Playing"),
                "Position": Variant("x", 8_000_000),
                "Metadata": Variant(
                    "a{sv}", {"mpris:trackid": Variant("o", "/track/one")}
                ),
            }
        )
        state.update(
            {
                "Metadata": Variant(
                    "a{sv}", {"mpris:trackid": Variant("o", "/track/two")}
                )
            }
        )
        self.assertEqual(state.snapshot()["positionUs"], 0)

        state.seeked(3_500_000)
        now[0] = 21.0
        self.assertEqual(state.snapshot()["positionUs"], 4_500_000)

    def test_volume_is_clamped_and_requires_volume_and_control_support(self) -> None:
        state = PlayerState()
        state.update(
            {
                "Volume": Variant("d", 1.5),
                "CanControl": Variant("b", True),
            }
        )
        self.assertEqual(state.snapshot()["volume"], 1.0)
        self.assertTrue(state.snapshot()["canSetVolume"])

        state.update({"CanControl": Variant("b", False)})
        self.assertFalse(state.snapshot()["canSetVolume"])


class CommandEndpointTests(unittest.TestCase):
    def test_allowed_commands_are_forwarded_to_the_adapter(self) -> None:
        adapter = FakeSpotifyAdapter({"connected": True})
        with BridgeServer(adapter) as bridge:
            statuses = []
            for command in ("play", "pause", "playpause", "next", "previous"):
                status, payload = bridge.fetch(
                    "/command",
                    method="POST",
                    body=json.dumps({"command": command}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                statuses.append((status, payload))

        self.assertEqual(
            adapter.commands,
            [
                ("play", None),
                ("pause", None),
                ("playpause", None),
                ("next", None),
                ("previous", None),
            ],
        )
        self.assertEqual(statuses, [(204, {})] * 5)

    def test_volume_command_forwards_a_normalized_finite_value(self) -> None:
        adapter = FakeSpotifyAdapter({"connected": True})
        with BridgeServer(adapter) as bridge:
            status, payload = bridge.fetch(
                "/command",
                method="POST",
                body=b'{"command":"volume","value":0.42}',
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual((status, payload), (204, {}))
        self.assertEqual(adapter.commands, [("volume", 0.42)])

    def test_volume_command_rejects_non_finite_out_of_range_and_boolean_values(self) -> None:
        adapter = FakeSpotifyAdapter({"connected": True})
        invalid_values: tuple[object, ...] = (
            -0.01,
            1.01,
            True,
            "0.5",
            math.nan,
            math.inf,
        )
        with BridgeServer(adapter) as bridge:
            for value in invalid_values:
                with self.subTest(value=value):
                    status, payload = bridge.fetch(
                        "/command",
                        method="POST",
                        body=json.dumps({"command": "volume", "value": value}).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(payload, {"error": "invalid_value"})

        self.assertEqual(adapter.commands, [])

    def test_unknown_command_is_rejected_without_forwarding(self) -> None:
        adapter = FakeSpotifyAdapter({"connected": True})
        with BridgeServer(adapter) as bridge:
            status, payload = bridge.fetch(
                "/command",
                method="POST",
                body=b'{"command":"seek"}',
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload, {"error": "invalid_command"})
        self.assertEqual(adapter.commands, [])

    def test_non_string_command_is_rejected_without_server_error(self) -> None:
        adapter = FakeSpotifyAdapter({"connected": True})
        with BridgeServer(adapter) as bridge:
            status, payload = bridge.fetch(
                "/command",
                method="POST",
                body=b'{"command":[]}',
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload, {"error": "invalid_command"})
        self.assertEqual(adapter.commands, [])

    def test_command_returns_service_unavailable_when_spotify_is_disconnected(self) -> None:
        adapter = FakeSpotifyAdapter({"connected": False})
        with BridgeServer(adapter) as bridge:
            status, payload = bridge.fetch(
                "/command",
                method="POST",
                body=b'{"command":"play"}',
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(status, 503)
        self.assertEqual(payload, {"error": "spotify_unavailable"})
        self.assertEqual(adapter.commands, [])

    def test_oversized_body_is_rejected(self) -> None:
        adapter = FakeSpotifyAdapter({"connected": True})
        with BridgeServer(adapter) as bridge:
            status, payload = bridge.fetch(
                "/command",
                method="POST",
                body=b" " * 4097,
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(status, 413)
        self.assertEqual(payload, {"error": "body_too_large"})
        self.assertEqual(adapter.commands, [])


if __name__ == "__main__":
    unittest.main()
