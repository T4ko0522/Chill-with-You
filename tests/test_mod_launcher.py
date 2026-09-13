"""Behavioural tests for the Steam/Proton DLL-override wrapper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parents[1] / "mod_launcher.py"


class LauncherOverrideTests(unittest.TestCase):
    def test_launcher_replaces_winhttp_override_and_preserves_argv(self) -> None:
        child = (
            "import json, os, sys; "
            "print(json.dumps({'overrides': os.environ['WINEDLLOVERRIDES'], "
            "'argv': sys.argv[1:]}))"
        )
        environment = os.environ.copy()
        environment["WINEDLLOVERRIDES"] = "dinput8=n,b;winhttp=b;foo=n"

        result = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                sys.executable,
                "-c",
                child,
                "argument with spaces",
                "second-argument",
            ],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["argv"], ["argument with spaces", "second-argument"])
        self.assertEqual(observed["overrides"], "dinput8=n,b;foo=n;winhttp.dll=n,b")

    def test_launcher_forwards_child_exit_status(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                sys.executable,
                "-c",
                "import sys; sys.exit(17)",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 17, result.stderr)


if __name__ == "__main__":
    unittest.main()
