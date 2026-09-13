{
  description = "Declarative BepInEx and Spotify integration for Chill with You";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          settings = import ./settings.nix;
          outfitSources = pkgs.lib.fileset.toSource {
            root = ./.;
            fileset = pkgs.lib.fileset.unions [
              ./installer.py ./plugin_build.py ./install_outfit.py ./plugin/outfit
            ];
          };

          bepInExArchive = pkgs.fetchurl {
            url = "https://github.com/BepInEx/BepInEx/releases/download/v5.4.23.5/BepInEx_win_x64_5.4.23.5.zip";
            hash = "sha256-gvmHhVEDD1Rld5LAdA2dUaCVAO6uH7ohEGsMRB5nMsQ=";
          };

          payload = pkgs.runCommand "chill-with-you-mod-payload" {
            nativeBuildInputs = [ pkgs.unzip ];
            preferLocalBuild = true;
            allowSubstitutes = false;
          } ''
            mkdir -p "$out"
            unzip -q ${bepInExArchive} -d "$out"
            rm "$out/changelog.txt"
          '';

          installer = pkgs.writeShellApplication {
            name = "chill-with-you-install";
            runtimeInputs = pkgs.lib.optional settings.defaultOutfit pkgs.mono;
            text = ''
              export CHILL_WITH_YOU_PAYLOAD=${payload}
              exec ${pkgs.python3}/bin/python3 ${if settings.defaultOutfit then "${outfitSources}/install_outfit.py" else ./installer.py} "$@"
            '';
          };

          launcher = pkgs.writeShellApplication {
            name = "chill-with-you-modded";
            text = ''
              exec ${pkgs.python3}/bin/python3 ${./mod_launcher.py} "$@"
            '';
          };
          spotify = import ./spotify.nix { inherit pkgs payload; };
        in
        {
          default = launcher;
          inherit installer launcher payload;
          spotify-launcher = spotify.launcher;
          plugin-installer = spotify.installer;
        });

      apps = forAllSystems (system: {
        plugin-install = {
          type = "app";
          program = "${self.packages.${system}.plugin-installer}/bin/chill-with-you-plugin-install";
          meta.description = "Build and install the configured plugins with BepInEx";
        };
        spotify = {
          type = "app";
          program = "${self.packages.${system}.spotify-launcher}/bin/chill-with-you-spotify";
          meta.description = "Launch Chill with You with a private Spotify MPRIS bridge";
        };
        install = {
          type = "app";
          program = "${self.packages.${system}.installer}/bin/chill-with-you-install";
          meta.description = "Install the managed BepInEx payload";
        };
        default = {
          type = "app";
          program = "${self.packages.${system}.launcher}/bin/chill-with-you-modded";
          meta.description = "Launch Chill with You with the BepInEx DLL override";
        };
      });

      devShells = forAllSystems (system: {
        default = (import ./spotify.nix {
          pkgs = nixpkgs.legacyPackages.${system};
          payload = self.packages.${system}.payload;
        }).devShell;
      });

      checks = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          spotify = (import ./spotify.nix {
            inherit pkgs;
            payload = self.packages.${system}.payload;
          }).check;
          tests = pkgs.runCommand "chill-with-you-tests" {
            nativeBuildInputs = [ pkgs.python3 ];
          } ''
            cp ${./installer.py} installer.py
            cp ${./mod_launcher.py} mod_launcher.py
            mkdir tests
            cp ${./tests/test_installer.py} tests/test_installer.py
            cp ${./tests/test_mod_launcher.py} tests/test_mod_launcher.py
            PYTHONPATH="$PWD" python -m unittest \
              tests/test_installer.py tests/test_mod_launcher.py
            touch "$out"
          '';
        });
    };
}
