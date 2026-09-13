import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from launcher import run


class LauncherTests(unittest.TestCase):
    def test_game_gets_private_bridge_and_exit_status_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bridge = root / "bridge.py"
            bridge.write_text(
                "import os, time\n"
                "from pathlib import Path\n"
                f"Path({str(root / 'pid')!r}).write_text(str(os.getpid()))\n"
                "print('{\"port\":18473}', flush=True)\n"
                "time.sleep(60)\n"
            )
            output = root / "game.json"
            game = root / "game.py"
            game.write_text(
                "import os, json\nfrom pathlib import Path\n"
                f"Path({str(output)!r}).write_text(json.dumps(dict(os.environ)))\n"
                "raise SystemExit(7)\n"
            )
            code = run([sys.executable, str(game)], [sys.executable, str(bridge)])
            self.assertEqual(code, 7)
            environment = json.loads(output.read_text())
            self.assertEqual(environment["CHILL_SPOTIFY_URL"], "http://127.0.0.1:18473")
            self.assertGreaterEqual(len(environment["CHILL_SPOTIFY_TOKEN"]), 32)
            self.assertIn("winhttp.dll=n,b", environment["WINEDLLOVERRIDES"])
            with self.assertRaises(ProcessLookupError):
                os.kill(int((root / "pid").read_text()), 0)

    def test_failed_bridge_does_not_launch_game(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "started"
            with self.assertRaises(RuntimeError):
                run(
                    [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"],
                    [sys.executable, "-c", "raise SystemExit(1)"],
                )
            self.assertFalse(marker.exists())

    def test_partial_startup_message_has_a_deadline(self):
        with self.assertRaisesRegex(RuntimeError, "start"):
            run(
                [sys.executable, "-c", "raise SystemExit('must not launch')"],
                [sys.executable, "-c", "import sys,time; sys.stdout.write('{'); sys.stdout.flush(); time.sleep(60)"],
                startup_timeout=0.1,
            )
