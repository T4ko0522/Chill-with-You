from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from installer import install
from install_spotify import main, stage_payload


class SpotifyInstallTests(unittest.TestCase):
    def test_build_only_does_not_require_the_game_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            payload = root / "payload"
            output = root / "ChillSpotify.dll"
            (game / "Chill With You_Data/Managed").mkdir(parents=True)

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "chill-with-you-plugin-install",
                        str(game),
                        "--payload",
                        str(payload),
                        "--build-only",
                        str(output),
                    ],
                ),
                patch("install_spotify.build_plugin") as build_plugin,
            ):
                main()

            build_plugin.assert_called_once_with(
                game,
                payload,
                Path(__file__).parents[1] / "plugin/spotify",
                output,
            )

    def test_read_only_nix_payload_can_receive_the_built_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "store"
            plugins = source / "BepInEx/plugins"
            plugins.mkdir(parents=True)
            (plugins / "OtherMod.dll").write_bytes(b"original mod")
            plugins.chmod(0o555)
            try:
                destination = root / "staging"
                stage_payload(source, destination)
                (destination / "BepInEx/plugins/ChillSpotify.dll").write_bytes(b"new plugin")
                self.assertEqual((plugins / "OtherMod.dll").read_bytes(), b"original mod")
                self.assertEqual(plugins.stat().st_mode & 0o777, 0o555)
            finally:
                plugins.chmod(0o755)

    def test_spotify_plugin_is_managed_without_touching_other_mods(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game, payload = root / "game", root / "payload"
            plugins = game / "BepInEx/plugins"
            plugins.mkdir(parents=True)
            (plugins / "OtherMod.dll").write_bytes(b"user mod")
            source = payload / "BepInEx/plugins/ChillSpotify.dll"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"version one")
            install(game, payload)
            source.write_bytes(b"version two")
            install(game, payload)
            self.assertEqual((plugins / "ChillSpotify.dll").read_bytes(), b"version two")
            self.assertEqual((plugins / "OtherMod.dll").read_bytes(), b"user mod")
