#!/usr/bin/env python3
"""Build the Spotify plugin against the installed game, then install the payload."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from installer import DEFAULT_GAME_DIRECTORY, GAME_EXECUTABLE, InstallError, install
from plugin_build import build_plugin, stage_payload



def main() -> None:
    parser = argparse.ArgumentParser(prog="chill-with-you-plugin-install", description=__doc__)
    parser.add_argument("game_directory", nargs="?", type=Path, default=DEFAULT_GAME_DIRECTORY)
    parser.add_argument("--payload", type=Path, default=os.environ.get("CHILL_WITH_YOU_PAYLOAD"),
                        required="CHILL_WITH_YOU_PAYLOAD" not in os.environ)
    parser.add_argument("--build-only", type=Path, metavar="OUTPUT_DLL")
    parser.add_argument("--default-outfit", action="store_true")
    arguments = parser.parse_args()
    game = arguments.game_directory.expanduser()
    sources = Path(__file__).parent / "plugin" / "spotify"
    try:
        if arguments.build_only:
            build_plugin(game, arguments.payload, sources, arguments.build_only)
            print(f"Built {arguments.build_only}")
            return
        if not (game / GAME_EXECUTABLE).is_file():
            raise InstallError(f"game executable not found: {game / GAME_EXECUTABLE}")
        with tempfile.TemporaryDirectory(prefix="chill-spotify-payload-") as directory:
            payload = Path(directory) / "payload"
            stage_payload(arguments.payload, payload)
            build_plugin(game, payload, sources, payload / "BepInEx/plugins/ChillSpotify.dll")
            if arguments.default_outfit:
                build_plugin(game, payload, Path(__file__).parent / "plugin" / "outfit",
                             payload / "BepInEx/plugins/ChillDefaultOutfit.dll")
            install(game, payload)
    except (InstallError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Installed managed files including ChillSpotify into {game}")


if __name__ == "__main__":
    main()
