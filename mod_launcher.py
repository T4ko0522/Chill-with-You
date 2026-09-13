#!/usr/bin/env python3
"""Launch a Steam command with the BepInEx winhttp override."""

from __future__ import annotations

import os
import sys


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


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: chill-with-you-modded COMMAND [ARG ...]")
    environment = os.environ.copy()
    environment["WINEDLLOVERRIDES"] = merge_dll_overrides(
        environment.get("WINEDLLOVERRIDES")
    )
    os.execvpe(sys.argv[1], sys.argv[1:], environment)


if __name__ == "__main__":
    main()
