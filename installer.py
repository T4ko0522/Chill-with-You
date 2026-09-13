#!/usr/bin/env python3
"""Install the declaratively built BepInEx and mod payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath


MANIFEST_NAME = ".chill-with-you-mod-manifest.json"
DEFAULT_GAME_DIRECTORY = Path(
    "~/.local/share/Steam/steamapps/common/Chill with You Lo-Fi Story"
).expanduser()
ROOT_PAYLOAD_FILES = {
    ".doorstop_version",
    "doorstop_config.ini",
    "winhttp.dll",
}
GAME_EXECUTABLE = "Chill With You.exe"


class InstallError(RuntimeError):
    """Raised before installation when an existing file is unsafe to replace."""


def _is_chirarism_path(path: PurePosixPath) -> bool:
    return path.parts == (
        "BepInEx",
        "plugins",
        "ChillWithYouMod.dll",
    ) or (
        len(path.parts) >= 4
        and path.parts[:3] == ("BepInEx", "plugins", "ChillWithYouMod")
    )


def _validate_relative_path(value: str, *, allow_chirarism: bool = False) -> Path:
    if (
        not value
        or "\\" in value
        or "\0" in value
        or any(component in {"", ".", ".."} for component in value.split("/"))
    ):
        raise InstallError(f"invalid managed path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise InstallError(f"invalid managed path: {value!r}")
    is_core_file = len(path.parts) >= 3 and path.parts[:2] == ("BepInEx", "core")
    is_mod_file = path.parts == (
        "BepInEx",
        "plugins",
        "ChillSpotify.dll",
    ) or (allow_chirarism and _is_chirarism_path(path))
    if value not in ROOT_PAYLOAD_FILES and not is_core_file and not is_mod_file:
        raise InstallError(f"path is outside the managed payload: {value!r}")
    return Path(*path.parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _payload_files(payload_directory: Path) -> dict[str, tuple[Path, str]]:
    files: dict[str, tuple[Path, str]] = {}
    for source in sorted(payload_directory.rglob("*")):
        if source.is_symlink():
            raise InstallError(f"payload contains a symlink: {source}")
        if not source.is_file():
            continue
        relative = source.relative_to(payload_directory).as_posix()
        _validate_relative_path(relative)
        files[relative] = (source, _sha256(source))
    if not files:
        raise InstallError(f"payload contains no files: {payload_directory}")
    return files


def _load_manifest(path: Path) -> dict[str, str]:
    if path.is_symlink():
        raise InstallError(f"manifest is not a regular file: {path}")
    if not path.exists():
        return {}
    if not path.is_file():
        raise InstallError(f"manifest is not a regular file: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f"cannot read manifest {path}: {error}") from error
    if not isinstance(document, dict) or document.get("version") != 1:
        raise InstallError(f"unsupported manifest format: {path}")
    entries = document.get("files")
    if not isinstance(entries, dict):
        raise InstallError(f"invalid manifest file list: {path}")
    result: dict[str, str] = {}
    for relative, digest in entries.items():
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise InstallError(f"invalid manifest entry: {relative!r}")
        _validate_relative_path(relative, allow_chirarism=True)
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise InstallError(f"invalid manifest hash for {relative!r}")
        if _is_chirarism_path(PurePosixPath(relative)):
            continue
        result[relative] = digest
    return result


def _reject_symlink_parents(root: Path, relative: Path) -> None:
    current = root
    for component in relative.parts[:-1]:
        current /= component
        if current.is_symlink():
            raise InstallError(f"managed path traverses a symlink: {current}")
        if current.exists() and not current.is_dir():
            raise InstallError(f"managed path parent is not a directory: {current}")


def _preflight(
    game_directory: Path,
    payload: dict[str, tuple[Path, str]],
    previous: dict[str, str],
) -> None:
    for relative, (_, expected_hash) in payload.items():
        relative_path = _validate_relative_path(relative)
        _reject_symlink_parents(game_directory, relative_path)
        destination = game_directory / relative_path
        if not destination.exists():
            if destination.is_symlink():
                raise InstallError(f"refusing to replace a dangling symlink: {destination}")
            continue
        if not destination.is_file():
            raise InstallError(f"managed destination is not a file: {destination}")
        current_hash = _sha256(destination)
        if current_hash == expected_hash:
            continue
        if previous.get(relative) != current_hash:
            raise InstallError(f"refusing to overwrite unmanaged or modified file: {destination}")

    for relative, old_hash in previous.items():
        if relative in payload:
            continue
        relative_path = _validate_relative_path(relative)
        _reject_symlink_parents(game_directory, relative_path)
        destination = game_directory / relative_path
        if destination.is_symlink():
            raise InstallError(f"refusing to remove a symlink: {destination}")
        if destination.exists() and (
            not destination.is_file() or _sha256(destination) != old_hash
        ):
            raise InstallError(f"refusing to remove a modified managed file: {destination}")


def install(game_directory: Path, payload_directory: Path) -> None:
    """Copy payload files after verifying every affected existing path."""
    game_directory = Path(game_directory).expanduser()
    payload_directory = Path(payload_directory)
    if not game_directory.is_dir():
        raise InstallError(f"game directory does not exist: {game_directory}")
    if not payload_directory.is_dir():
        raise InstallError(f"payload directory does not exist: {payload_directory}")

    payload = _payload_files(payload_directory)
    manifest_path = game_directory / MANIFEST_NAME
    previous = _load_manifest(manifest_path)
    _preflight(game_directory, payload, previous)

    with tempfile.TemporaryDirectory(prefix=".chill-with-you-install-", dir=game_directory) as temporary:
        staging = Path(temporary)
        for relative, (source, _) in payload.items():
            staged = staging / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, staged)
            staged.chmod(staged.stat().st_mode | stat.S_IWUSR)

        for relative in sorted(payload):
            relative_path = _validate_relative_path(relative)
            _reject_symlink_parents(game_directory, relative_path)
            destination = game_directory / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative_path, destination)

        for relative in sorted(set(previous) - set(payload), reverse=True):
            destination = game_directory / _validate_relative_path(relative)
            if destination.exists():
                destination.unlink()

        manifest_staged = staging / MANIFEST_NAME
        hashes = {relative: digest for relative, (_, digest) in payload.items()}
        manifest_staged.write_text(
            json.dumps({"version": 1, "files": hashes}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(manifest_staged, manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(prog="chill-with-you-install", description=__doc__)
    parser.add_argument("game_directory", nargs="?", type=Path, default=DEFAULT_GAME_DIRECTORY)
    parser.add_argument(
        "--payload",
        type=Path,
        default=os.environ.get("CHILL_WITH_YOU_PAYLOAD"),
        required="CHILL_WITH_YOU_PAYLOAD" not in os.environ,
    )
    arguments = parser.parse_args()
    game_executable = arguments.game_directory.expanduser() / GAME_EXECUTABLE
    if not game_executable.is_file():
        parser.exit(1, f"error: game executable does not exist: {game_executable}\n")
    try:
        install(arguments.game_directory, arguments.payload)
    except InstallError as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Installed managed files into {arguments.game_directory.expanduser()}")


if __name__ == "__main__":
    main()
