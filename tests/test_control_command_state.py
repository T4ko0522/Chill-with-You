"""Behaviour tests for serialized Spotify playback controls."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ControlCommandStateTests(unittest.TestCase):
    def test_only_current_command_completion_can_change_control_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spotify-control-command-") as directory:
            executable = Path(directory) / "probe.exe"
            subprocess.run(
                [
                    "mcs",
                    "-langversion:7.2",
                    f"-out:{executable}",
                    str(ROOT / "plugin/ControlCommandState.cs"),
                    str(ROOT / "tests/ControlCommandStateProbe.cs"),
                ],
                check=True,
            )
            subprocess.run(["mono", str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
