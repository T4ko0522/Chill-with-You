#!/usr/bin/env python3
"""Launch a Steam command with the BepInEx winhttp override."""

from __future__ import annotations

import os
import json
from pathlib import Path
import secrets
import selectors
import signal
import subprocess
import sys
import time


def merge_dll_overrides(current: str | None) -> str:
    entries: list[str] = []
    for entry in (current or "").split(";"):
        if not entry:
            continue
        name = entry.partition("=")[0].strip().lower()
        if name in {"winhttp", "winhttp.dll"}:
            continue
        entries.append(entry)
    entries.append("winhttp.dll=n,b")
    return ";".join(entries)


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run(command: list[str], bridge_command: list[str] | None = None,
        *, startup_timeout: float = 10) -> int:
    """Keep one private Spotify bridge alive for the lifetime of the game."""
    environment = os.environ.copy()
    environment["WINEDLLOVERRIDES"] = merge_dll_overrides(
        environment.get("WINEDLLOVERRIDES")
    )
    environment["CHILL_SPOTIFY_TOKEN"] = secrets.token_urlsafe(32)
    if bridge_command is None:
        bridge_command = [sys.executable, str(Path(__file__).with_name("spotify_bridge.py"))]
    bridge = subprocess.Popen(bridge_command, env=environment, stdout=subprocess.PIPE)
    game = None
    previous_handler = signal.getsignal(signal.SIGTERM)

    def terminate(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(bridge.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + startup_timeout
            line = b""
            while b"\n" not in line:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(timeout=remaining):
                    raise RuntimeError("Spotify bridge did not start before the deadline")
                part = os.read(bridge.stdout.fileno(), 1024)
                if not part:
                    raise RuntimeError("Spotify bridge exited during startup")
                line += part
                if len(line) > 1024:
                    raise RuntimeError("Spotify bridge sent an invalid startup message")
        try:
            port = json.loads(line)["port"]
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("invalid port")
        except (ValueError, KeyError, TypeError) as error:
            raise RuntimeError("Spotify bridge failed to start; see its error above") from error
        environment["CHILL_SPOTIFY_URL"] = f"http://127.0.0.1:{port}"
        game = subprocess.Popen(command, env=environment)
        return game.wait()
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        if game is not None:
            _stop(game)
        _stop(bridge)
        bridge.stdout.close()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: chill-with-you-modded COMMAND [ARG ...]")
    try:
        code = run(sys.argv[1:])
    except KeyboardInterrupt:
        code = 130
    except (RuntimeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        code = 1
    raise SystemExit(code if code >= 0 else 128 - code)


if __name__ == "__main__":
    main()
