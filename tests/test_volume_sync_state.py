"""Behaviour tests for bidirectional Spotify volume synchronization."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VolumeSyncStateTests(unittest.TestCase):
    def test_local_intent_is_serialized_and_stale_remote_state_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spotify-volume-sync-") as directory:
            executable = Path(directory) / "probe.exe"
            subprocess.run(
                [
                    "mcs",
                    "-langversion:7.2",
                    f"-out:{executable}",
                    str(ROOT / "plugin/spotify/VolumeSyncState.cs"),
                    str(ROOT / "tests/VolumeSyncStateProbe.cs"),
                ],
                check=True,
            )
            subprocess.run(["mono", str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
