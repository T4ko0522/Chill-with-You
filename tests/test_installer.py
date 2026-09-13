"""Behavioural contract for the filesystem installer.

The tests use a temporary fake game directory.  They deliberately exercise the
installer's public Python seam so that the Nix app can remain a thin wrapper
around the same operation.
"""

from __future__ import annotations

import tempfile
import unittest
import hashlib
import json
import stat
from pathlib import Path

from installer import InstallError, install


class InstallPayloadTests(unittest.TestCase):
    def test_legacy_chirarism_manifest_entries_are_forgotten_without_touching_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game_directory = root / "game"
            payload_directory = root / "payload"
            game_directory.mkdir()

            chirarism_file = game_directory / "BepInEx/plugins/ChillWithYouMod.dll"
            chirarism_file.parent.mkdir(parents=True)
            chirarism_file.write_bytes(b"manually replaced mod")
            preserved_bundle = (
                game_directory / "BepInEx/plugins/ChillWithYouMod/existing.bundle"
            )
            preserved_bundle.parent.mkdir(parents=True)
            preserved_bundle.write_bytes(b"previous managed bundle")
            missing_chirarism = "BepInEx/plugins/ChillWithYouMod/missing.bundle"
            manifest_path = game_directory / ".chill-with-you-mod-manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": {
                            "BepInEx/plugins/ChillWithYouMod.dll": hashlib.sha256(
                                b"previous managed mod"
                            ).hexdigest(),
                            "BepInEx/plugins/ChillWithYouMod/existing.bundle": hashlib.sha256(
                                b"previous managed bundle"
                            ).hexdigest(),
                            missing_chirarism: hashlib.sha256(b"missing").hexdigest(),
                        },
                    }
                ),
                encoding="utf-8",
            )

            spotify_file = payload_directory / "BepInEx/plugins/ChillSpotify.dll"
            spotify_file.parent.mkdir(parents=True)
            spotify_file.write_bytes(b"spotify plugin")

            install(game_directory, payload_directory)

            self.assertEqual(chirarism_file.read_bytes(), b"manually replaced mod")
            self.assertEqual(preserved_bundle.read_bytes(), b"previous managed bundle")
            self.assertFalse((game_directory / missing_chirarism).exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest,
                {
                    "version": 1,
                    "files": {
                        "BepInEx/plugins/ChillSpotify.dll": hashlib.sha256(
                            b"spotify plugin"
                        ).hexdigest()
                    },
                },
            )

    def test_chirarism_file_in_new_payload_is_rejected_before_any_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game_directory = root / "game"
            payload_directory = root / "payload"
            game_directory.mkdir()

            chirarism_file = payload_directory / "BepInEx/plugins/ChillWithYouMod.dll"
            chirarism_file.parent.mkdir(parents=True)
            chirarism_file.write_bytes(b"procedurally installed mod")
            core_file = payload_directory / "BepInEx/core/loader.dll"
            core_file.parent.mkdir(parents=True)
            core_file.write_bytes(b"loader")

            with self.assertRaises(InstallError):
                install(game_directory, payload_directory)

            self.assertEqual(list(game_directory.iterdir()), [])

    def test_legacy_manifest_still_rejects_invalid_entries_before_any_change(self) -> None:
        invalid_entries = (
            {
                "BepInEx/plugins/OtherMod.dll": hashlib.sha256(
                    b"unrelated mod"
                ).hexdigest()
            },
            {"BepInEx/plugins/ChillWithYouMod.dll": "not-a-sha256"},
        )
        for entries in invalid_entries:
            with (
                self.subTest(entries=entries),
                tempfile.TemporaryDirectory() as temporary_directory,
            ):
                root = Path(temporary_directory)
                game_directory = root / "game"
                payload_directory = root / "payload"
                game_directory.mkdir()
                manifest_path = game_directory / ".chill-with-you-mod-manifest.json"
                manifest_path.write_text(
                    json.dumps({"version": 1, "files": entries}), encoding="utf-8"
                )
                manifest_before = manifest_path.read_bytes()
                core_file = payload_directory / "BepInEx/core/loader.dll"
                core_file.parent.mkdir(parents=True)
                core_file.write_bytes(b"loader")

                with self.assertRaises(InstallError):
                    install(game_directory, payload_directory)

                self.assertFalse((game_directory / "BepInEx").exists())
                self.assertEqual(manifest_path.read_bytes(), manifest_before)

    def test_install_copies_payload_into_game_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game_directory = root / "game"
            payload_directory = root / "payload"
            game_directory.mkdir()

            expected_files = {
                Path("BepInEx/core/loader.dll"): b"loader",
                Path("BepInEx/core/resources/body.bundle"): b"body",
                Path("BepInEx/plugins/ChillSpotify.dll"): b"spotify mod",
                Path("winhttp.dll"): b"override",
                Path("doorstop_config.ini"): b"enabled = true\n",
                Path(".doorstop_version"): b"5\n",
            }
            for relative_path, contents in expected_files.items():
                source = payload_directory / relative_path
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(contents)
                source.chmod(0o444)

            install(game_directory, payload_directory)

            for relative_path, contents in expected_files.items():
                self.assertEqual(
                    (game_directory / relative_path).read_bytes(), contents
                )
                self.assertTrue(
                    (game_directory / relative_path).stat().st_mode & stat.S_IWUSR,
                    relative_path,
                )

    def test_reinstall_preserves_runtime_files_and_other_mods(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game_directory = root / "game"
            payload_directory = root / "payload"
            game_directory.mkdir()

            payload_file = payload_directory / "BepInEx/plugins/ChillSpotify.dll"
            payload_file.parent.mkdir(parents=True)
            payload_file.write_bytes(b"managed mod")

            runtime_files = {
                Path("BepInEx/config/runtime.cfg"): b"user setting\n",
                Path("BepInEx/logs/LogOutput.log"): b"previous run\n",
                Path("BepInEx/plugins/OtherMod.dll"): b"another mod",
            }
            for relative_path, contents in runtime_files.items():
                destination = game_directory / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(contents)

            install(game_directory, payload_directory)
            install(game_directory, payload_directory)

            for relative_path, contents in runtime_files.items():
                self.assertEqual(
                    (game_directory / relative_path).read_bytes(), contents
                )
            self.assertEqual(
                (game_directory / "BepInEx/plugins/ChillSpotify.dll").read_bytes(),
                b"managed mod",
            )

    def test_conflicting_existing_file_rejects_install_before_any_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game_directory = root / "game"
            payload_directory = root / "payload"
            game_directory.mkdir()

            first_payload = payload_directory / "BepInEx/plugins/ChillSpotify.dll"
            first_payload.parent.mkdir(parents=True)
            first_payload.write_bytes(b"desired mod")
            second_payload = payload_directory / "winhttp.dll"
            second_payload.parent.mkdir(parents=True, exist_ok=True)
            second_payload.write_bytes(b"another desired file")

            conflicting_file = game_directory / "winhttp.dll"
            conflicting_file.parent.mkdir(parents=True, exist_ok=True)
            conflicting_file.write_bytes(b"user-owned file")
            existing_target = game_directory / "BepInEx/plugins/ChillSpotify.dll"
            before = {
                path.relative_to(game_directory): path.read_bytes()
                for path in game_directory.rglob("*")
                if path.is_file()
            }

            with self.assertRaises(InstallError):
                install(game_directory, payload_directory)

            after = {
                path.relative_to(game_directory): path.read_bytes()
                for path in game_directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertFalse(existing_target.exists())
            self.assertFalse(
                (game_directory / ".chill-with-you-mod-manifest.json").exists()
            )

    def test_manifest_allows_unchanged_managed_update_and_obsolete_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game_directory = root / "game"
            first_payload = root / "payload-v1"
            second_payload = root / "payload-v2"
            game_directory.mkdir()

            old_file = Path("BepInEx/plugins/ChillSpotify.dll")
            obsolete_file = Path("BepInEx/core/obsolete.bundle")
            for payload, relative_path, contents in (
                (first_payload, old_file, b"version one"),
                (first_payload, obsolete_file, b"remove me"),
                (second_payload, old_file, b"version two"),
            ):
                source = payload / relative_path
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(contents)

            runtime_file = game_directory / "BepInEx/config/runtime.cfg"
            other_mod = game_directory / "BepInEx/plugins/OtherMod.dll"
            runtime_file.parent.mkdir(parents=True)
            other_mod.parent.mkdir(parents=True, exist_ok=True)
            runtime_file.write_bytes(b"keep this setting")
            other_mod.write_bytes(b"keep this mod")

            install(game_directory, first_payload)
            install(game_directory, second_payload)

            self.assertEqual((game_directory / old_file).read_bytes(), b"version two")
            self.assertFalse((game_directory / obsolete_file).exists())
            self.assertEqual(runtime_file.read_bytes(), b"keep this setting")
            self.assertEqual(other_mod.read_bytes(), b"keep this mod")

            manifest = json.loads(
                (game_directory / ".chill-with-you-mod-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            expected_hash = hashlib.sha256(b"version two").hexdigest()
            self.assertEqual(manifest, {"version": 1, "files": {old_file.as_posix(): expected_hash}})

    def test_modified_managed_file_is_rejected_without_partial_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game_directory = root / "game"
            first_payload = root / "payload-v1"
            second_payload = root / "payload-v2"
            game_directory.mkdir()

            managed_file = Path("BepInEx/plugins/ChillSpotify.dll")
            first_source = first_payload / managed_file
            first_source.parent.mkdir(parents=True)
            first_source.write_bytes(b"version one")
            second_source = second_payload / managed_file
            second_source.parent.mkdir(parents=True)
            second_source.write_bytes(b"version two")
            new_source = second_payload / "BepInEx/core/new.dll"
            new_source.parent.mkdir(parents=True)
            new_source.write_bytes(b"new file")

            install(game_directory, first_payload)
            destination = game_directory / managed_file
            destination.write_bytes(b"edited by user")
            manifest_path = game_directory / ".chill-with-you-mod-manifest.json"
            manifest_before = manifest_path.read_bytes()

            with self.assertRaises(InstallError):
                install(game_directory, second_payload)

            self.assertEqual(destination.read_bytes(), b"edited by user")
            self.assertFalse((game_directory / "BepInEx/core/new.dll").exists())
            self.assertEqual(manifest_path.read_bytes(), manifest_before)

    def test_symlinked_managed_parent_is_rejected_without_writing_outside_game(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            game_directory = root / "game"
            payload_directory = root / "payload"
            outside_directory = root / "outside"
            game_directory.mkdir()
            outside_directory.mkdir()

            source = payload_directory / "BepInEx/plugins/ChillSpotify.dll"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"managed mod")
            (game_directory / "BepInEx").symlink_to(outside_directory, target_is_directory=True)

            with self.assertRaises(InstallError):
                install(game_directory, payload_directory)

            self.assertFalse(
                (outside_directory / "plugins/ChillSpotify.dll").exists()
            )
            self.assertFalse(
                (game_directory / ".chill-with-you-mod-manifest.json").exists()
            )

if __name__ == "__main__":
    unittest.main()
