"""Build local BepInEx plugins against the installed game assemblies."""

from pathlib import Path
import shutil
import stat
import subprocess

from installer import InstallError


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

