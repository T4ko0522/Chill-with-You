"""Regression tests for fail-safe Spotify mode activation."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SpotifyModeTransitionTests(unittest.TestCase):
    def test_activation_requires_a_binding_and_rolls_back_partial_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spotify-mode-transition-") as directory:
            executable = Path(directory) / "probe.exe"
            subprocess.run(
                [
                    "mcs",
                    "-langversion:7.2",
                    f"-out:{executable}",
                    str(ROOT / "plugin/SpotifyModeTransition.cs"),
                    str(ROOT / "tests/SpotifyModeTransitionProbe.cs"),
                ],
                check=True,
            )
            subprocess.run(["mono", str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
