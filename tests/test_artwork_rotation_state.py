"""Behaviour test for artwork rotation across repeated UI renders."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ArtworkRotationStateTests(unittest.TestCase):
    def test_rotates_once_per_playing_frame_and_holds_while_stopped(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artwork-rotation-") as directory:
            executable = Path(directory) / "probe.exe"
            subprocess.run(
                [
                    "mcs",
                    "-langversion:7.2",
                    f"-out:{executable}",
                    str(ROOT / "plugin/ArtworkRotationState.cs"),
                    str(ROOT / "tests/ArtworkRotationStateProbe.cs"),
                ],
                check=True,
            )
            subprocess.run(["mono", str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
