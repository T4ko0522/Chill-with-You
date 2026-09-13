#!/usr/bin/env python3
"""Build the Spotify plugin against the installed game, then install the payload."""

import argparse
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

from installer import DEFAULT_GAME_DIRECTORY, GAME_EXECUTABLE, InstallError, install


def stage_payload(source: Path, destination: Path) -> None:
    """Copy a read-only store payload into a writable private staging tree."""
    shutil.copytree(source, destination)
    for directory in [destination, *destination.rglob("*")]:
        if directory.is_dir():
            directory.chmod(directory.stat().st_mode | stat.S_IWUSR)


def build_plugin(game: Path, payload: Path, sources: Path, output: Path) -> None:
    managed = game / "Chill With You_Data/Managed"
    if not (managed / "Assembly-CSharp.dll").is_file():
        raise InstallError(f"game managed assemblies not found: {managed}")
    references = sorted(managed.glob("*.dll"))
    references += [payload / "BepInEx/core" / name for name in ("BepInEx.dll", "0Harmony.dll")]
    source_files = sorted(sources.glob("*.cs"))
    if not source_files:
        raise InstallError(f"plugin sources not found: {sources}")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["mcs", "-target:library", "-langversion:7.2", "-nostdlib",
         f"-out:{output}", *[f"-r:{path}" for path in references],
         *map(str, source_files)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_directory", nargs="?", type=Path, default=DEFAULT_GAME_DIRECTORY)
    parser.add_argument("--payload", type=Path, default=os.environ.get("CHILL_WITH_YOU_PAYLOAD"),
                        required="CHILL_WITH_YOU_PAYLOAD" not in os.environ)
    parser.add_argument("--build-only", type=Path, metavar="OUTPUT_DLL")
    arguments = parser.parse_args()
    game = arguments.game_directory.expanduser()
    if not (game / GAME_EXECUTABLE).is_file():
        parser.exit(1, f"error: game executable not found: {game / GAME_EXECUTABLE}\n")
    sources = Path(__file__).parent / "plugin"
    try:
        if arguments.build_only:
            build_plugin(game, arguments.payload, sources, arguments.build_only)
            print(f"Built {arguments.build_only}")
            return
        with tempfile.TemporaryDirectory(prefix="chill-spotify-payload-") as directory:
            payload = Path(directory) / "payload"
            stage_payload(arguments.payload, payload)
            build_plugin(game, payload, sources, payload / "BepInEx/plugins/ChillSpotify.dll")
            install(game, payload)
    except (InstallError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Installed managed files including ChillSpotify into {game}")


if __name__ == "__main__":
    main()
