"""Behavioural contract for the standalone default-outfit installer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from installer import install
from install_outfit import install_payload, main


class DefaultOutfitInstallTests(unittest.TestCase):
    def test_build_only_does_not_require_the_game_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            payload = root / "payload"
            output = root / "ChillDefaultOutfit.dll"
            (game / "Chill With You_Data/Managed").mkdir(parents=True)

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "install_outfit.py",
                        str(game),
                        "--payload",
                        str(payload),
                        "--build-only",
                        str(output),
                    ],
                ),
                patch("install_outfit.build_plugin") as build_plugin,
            ):
                main()

            build_plugin.assert_called_once_with(
                game,
                payload,
                Path(__file__).parents[1] / "plugin/outfit",
                output,
            )

    @staticmethod
    def _fixture(root: Path) -> tuple[Path, Path, Path]:
        game = root / "game"
        payload = root / "payload"
        sources = root / "sources"
        game.mkdir()

        managed = game / "Chill With You_Data/Managed"
        managed.mkdir(parents=True)
        for name, contents in (
            ("Assembly-CSharp.dll", b"fake game assembly"),
            ("UnityEngine.CoreModule.dll", b"fake unity assembly"),
        ):
            (managed / name).write_bytes(contents)

        core = payload / "BepInEx/core"
        core.mkdir(parents=True)
        for name, contents in (
            ("BepInEx.dll", b"fake bepinex assembly"),
            ("0Harmony.dll", b"fake harmony assembly"),
        ):
            source = core / name
            source.write_bytes(contents)
            source.chmod(0o444)

        (sources / "DefaultOutfitPlugin.cs").parent.mkdir(parents=True)
        (sources / "DefaultOutfitPlugin.cs").write_text(
            "public sealed class DefaultOutfitPlugin {}\n",
            encoding="utf-8",
        )
        return game, payload, sources

    @staticmethod
    def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
        snapshot: dict[str, tuple[str, bytes | None]] = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                snapshot[relative] = ("directory", None)
            elif path.is_file():
                snapshot[relative] = ("file", path.read_bytes())
            else:
                snapshot[relative] = ("other", None)
        return snapshot

    def test_builds_default_outfit_in_staging_and_manages_the_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game, payload, sources = self._fixture(root)

            chirarism_dll = game / "BepInEx/plugins/ChillWithYouMod.dll"
            chirarism_dll.parent.mkdir(parents=True)
            chirarism_dll.write_bytes(b"manually installed Chirarism")
            chirarism_asset = game / "BepInEx/plugins/ChillWithYouMod/existing.bundle"
            chirarism_asset.parent.mkdir(parents=True)
            chirarism_asset.write_bytes(b"manually installed asset")

            compiler_commands: list[list[str]] = []

            def fake_compiler(command: list[str], check: bool = False, **_: object) -> None:
                self.assertTrue(check)
                compiler_commands.append(command)
                output_argument = next(
                    argument for argument in command if argument.startswith("-out:")
                )
                output = Path(output_argument.removeprefix("-out:"))
                staged_payload = output.parents[2]
                self.assertNotEqual(staged_payload, payload)
                self.assertEqual(
                    (staged_payload / "BepInEx/core/BepInEx.dll").read_bytes(),
                    b"fake bepinex assembly",
                )
                self.assertEqual(
                    (staged_payload / "BepInEx/core/0Harmony.dll").read_bytes(),
                    b"fake harmony assembly",
                )
                self.assertIn(f"-r:{game / 'Chill With You_Data/Managed/Assembly-CSharp.dll'}", command)
                self.assertIn(str(sources / "DefaultOutfitPlugin.cs"), command)
                self.assertTrue(output.parent.is_dir())
                output.write_bytes(b"compiled default outfit")

            with patch("plugin_build.subprocess.run", side_effect=fake_compiler):
                install_payload(game, payload, sources)

            self.assertEqual(len(compiler_commands), 1)
            installed_plugin = game / "BepInEx/plugins/ChillDefaultOutfit.dll"
            self.assertEqual(installed_plugin.read_bytes(), b"compiled default outfit")
            self.assertEqual(chirarism_dll.read_bytes(), b"manually installed Chirarism")
            self.assertEqual(chirarism_asset.read_bytes(), b"manually installed asset")

            manifest = json.loads(
                (game / ".chill-with-you-mod-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["version"], 1)
            self.assertEqual(
                manifest["files"]["BepInEx/plugins/ChillDefaultOutfit.dll"],
                hashlib.sha256(b"compiled default outfit").hexdigest(),
            )
            self.assertNotIn("BepInEx/plugins/ChillWithYouMod.dll", manifest["files"])

    def test_compiler_failure_leaves_the_game_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game, payload, sources = self._fixture(root)
            chirarism_dll = game / "BepInEx/plugins/ChillWithYouMod.dll"
            chirarism_dll.parent.mkdir(parents=True)
            chirarism_dll.write_bytes(b"manually installed Chirarism")
            before = self._tree_snapshot(game)

            def failing_compiler(command: list[str], **_: object) -> None:
                raise subprocess.CalledProcessError(returncode=1, cmd=command)

            with patch("plugin_build.subprocess.run", side_effect=failing_compiler):
                with self.assertRaises(subprocess.CalledProcessError):
                    install_payload(game, payload, sources)

            self.assertEqual(self._tree_snapshot(game), before)

    def test_reapplying_base_payload_removes_outfit_but_preserves_chirarism(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game, payload, sources = self._fixture(root)
            chirarism_dll = game / "BepInEx/plugins/ChillWithYouMod.dll"
            chirarism_dll.parent.mkdir(parents=True)
            chirarism_dll.write_bytes(b"manually installed Chirarism")
            chirarism_asset = game / "BepInEx/plugins/ChillWithYouMod/existing.bundle"
            chirarism_asset.parent.mkdir(parents=True)
            chirarism_asset.write_bytes(b"manually installed asset")

            def fake_compiler(command: list[str], **_: object) -> None:
                output_argument = next(
                    argument for argument in command if argument.startswith("-out:")
                )
                Path(output_argument.removeprefix("-out:")).write_bytes(
                    b"compiled default outfit"
                )

            with patch("plugin_build.subprocess.run", side_effect=fake_compiler):
                install_payload(game, payload, sources)

            installed_plugin = game / "BepInEx/plugins/ChillDefaultOutfit.dll"
            manifest_path = game / ".chill-with-you-mod-manifest.json"
            self.assertTrue(installed_plugin.is_file())
            self.assertIn(
                "BepInEx/plugins/ChillDefaultOutfit.dll",
                json.loads(manifest_path.read_text(encoding="utf-8"))["files"],
            )

            install(game, payload)

            self.assertFalse(installed_plugin.exists())
            self.assertEqual(chirarism_dll.read_bytes(), b"manually installed Chirarism")
            self.assertEqual(chirarism_asset.read_bytes(), b"manually installed asset")
            self.assertNotIn(
                "BepInEx/plugins/ChillDefaultOutfit.dll",
                json.loads(manifest_path.read_text(encoding="utf-8"))["files"],
            )


if __name__ == "__main__":
    unittest.main()
