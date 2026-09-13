"""Behaviour tests for the default-outfit BepInEx plugin."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DefaultOutfitPluginTests(unittest.TestCase):
    def test_only_the_skin_passed_to_costume_rendering_is_forced_to_default(self) -> None:
        with tempfile.TemporaryDirectory(prefix="default-outfit-") as directory:
            executable = Path(directory) / "probe.exe"
            subprocess.run(
                [
                    "mcs",
                    "-langversion:7.2",
                    f"-out:{executable}",
                    str(ROOT / "plugin/outfit/DefaultOutfitPlugin.cs"),
                    str(ROOT / "tests/DefaultOutfitProbe.cs"),
                ],
                check=True,
            )
            subprocess.run(["mono", str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
