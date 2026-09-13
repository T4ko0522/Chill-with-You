"""Mono transport boundary tests for the local Spotify bridge."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


TOKEN = "bridge-transport-test-token"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROBE_SOURCE = Path(__file__).with_name("BridgeTransportProbe.cs")
BRIDGE_SOURCE = REPOSITORY_ROOT / "plugin" / "BridgeRequest.cs"
COMMAND_BODY = json.dumps({"command": "play"}, separators=(",", ":")).encode()


class _BridgeHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, bytes]] = []

    def do_GET(self) -> None:
        response_body = b""
        status = 404
        if self.path == "/state":
            status = 200
            response_body = b'{"connected":true}'
        elif self.path == "/state?error=1":
            status = 503
            response_body = b'{"error":"unavailable"}'
        self._record_and_respond(status, b"", response_body)

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        request_body = self.rfile.read(content_length)
        status = (
            204
            if self.path == "/command" and request_body == COMMAND_BODY
            else 400
        )
        self._record_and_respond(status, request_body, b"")

    def _record_and_respond(
        self, status: int, request_body: bytes, response_body: bytes
    ) -> None:
        self.requests.append(
            (self.command, self.headers.get("Authorization", ""), request_body)
        )
        self.send_response(status)
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if response_body:
            self.wfile.write(response_body)

    def log_message(self, format: str, *args: object) -> None:
        return


class _LocalBridge:
    def __init__(self) -> None:
        _BridgeHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _BridgeHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    @property
    def requests(self) -> list[tuple[str, str, bytes]]:
        return list(_BridgeHandler.requests)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise RuntimeError("local HTTP bridge did not stop")


class BridgeTransportTests(unittest.TestCase):
    def test_mono_probe_round_trips_http_and_reports_non_2xx(self) -> None:
        bridge = _LocalBridge()
        try:
            with tempfile.TemporaryDirectory() as directory:
                executable = Path(directory) / "bridge-transport-probe.exe"
                compile_result = subprocess.run(
                    [
                        "mcs",
                        f"-out:{executable}",
                        str(BRIDGE_SOURCE),
                        str(PROBE_SOURCE),
                    ],
                    cwd=REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(
                    compile_result.returncode,
                    0,
                    msg=compile_result.stdout + compile_result.stderr,
                )

                run_result = subprocess.run(
                    ["mono", str(executable), bridge.url, TOKEN],
                    cwd=REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(
                    run_result.returncode,
                    0,
                    msg=run_result.stdout + run_result.stderr,
                )

            self.assertEqual(
                bridge.requests,
                [
                    ("GET", f"Bearer {TOKEN}", b""),
                    ("POST", f"Bearer {TOKEN}", COMMAND_BODY),
                    ("GET", f"Bearer {TOKEN}", b""),
                ],
            )
        finally:
            bridge.close()


if __name__ == "__main__":
    unittest.main()
