#!/usr/bin/env python3
"""Build and install BepInEx with the default outfit plugin."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from installer import DEFAULT_GAME_DIRECTORY, GAME_EXECUTABLE, InstallError, install
from plugin_build import build_plugin, stage_payload


def install_payload(game: Path, payload: Path, sources: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="chill-outfit-payload-") as directory:
        staged = Path(directory) / "payload"
        stage_payload(payload, staged)
        build_plugin(game, staged, sources, staged / "BepInEx/plugins/ChillDefaultOutfit.dll")
        install(game, staged)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_directory", nargs="?", type=Path, default=DEFAULT_GAME_DIRECTORY)
    parser.add_argument("--payload", type=Path, default=os.environ.get("CHILL_WITH_YOU_PAYLOAD"),
                        required="CHILL_WITH_YOU_PAYLOAD" not in os.environ)
    parser.add_argument("--build-only", type=Path, metavar="OUTPUT_DLL")
    arguments = parser.parse_args()
    game = arguments.game_directory.expanduser()
    sources = Path(__file__).parent / "plugin" / "outfit"
    try:
        if arguments.build_only:
            build_plugin(game, arguments.payload, sources, arguments.build_only)
            print(f"Built {arguments.build_only}")
            return
        if not (game / GAME_EXECUTABLE).is_file():
            raise InstallError(f"game executable not found: {game / GAME_EXECUTABLE}")
        install_payload(game, arguments.payload, sources)
    except (InstallError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Installed BepInEx and ChillDefaultOutfit into {game}")


if __name__ == "__main__":
    main()
