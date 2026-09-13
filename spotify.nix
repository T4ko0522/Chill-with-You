{ pkgs, payload }:
let
  python = pkgs.python3.withPackages (ps: [ ps.dbus-next ]);
  sources = pkgs.lib.fileset.toSource {
    root = ./.;
    fileset = pkgs.lib.fileset.unions [
      ./launcher.py ./spotify_bridge.py ./installer.py ./install_spotify.py ./plugin
    ];
  };
in
{
  launcher = pkgs.writeShellApplication {
    name = "chill-with-you-spotify";
    text = ''
      exec ${python}/bin/python3 ${sources}/launcher.py "$@"
    '';
  };

  installer = pkgs.writeShellApplication {
    name = "chill-with-you-spotify-install";
    runtimeInputs = [ pkgs.mono ];
    text = ''
      export CHILL_WITH_YOU_PAYLOAD=${payload}
      exec ${python}/bin/python3 ${sources}/install_spotify.py "$@"
    '';
  };

  devShell = pkgs.mkShell { packages = [ python pkgs.mono pkgs.dbus ]; };

  check = pkgs.runCommand "chill-spotify-tests" {
    nativeBuildInputs = [ python pkgs.dbus pkgs.mono ];
  } ''
    cp ${sources}/*.py .
    mkdir tests
    cp ${./tests/test_spotify_bridge.py} tests/test_spotify_bridge.py
    cp ${./tests/test_launcher.py} tests/test_launcher.py
    cp ${./tests/test_spotify_install.py} tests/test_spotify_install.py
    cp ${./tests/test_mpris_integration.py} tests/test_mpris_integration.py
    cp ${./tests/test_bridge_transport.py} tests/test_bridge_transport.py
    cp ${./tests/BridgeTransportProbe.cs} tests/BridgeTransportProbe.cs
    cp ${./tests/test_spotify_mode_transition.py} tests/test_spotify_mode_transition.py
    cp ${./tests/SpotifyModeTransitionProbe.cs} tests/SpotifyModeTransitionProbe.cs
    cp ${./tests/test_artwork_rotation_state.py} tests/test_artwork_rotation_state.py
    cp ${./tests/ArtworkRotationStateProbe.cs} tests/ArtworkRotationStateProbe.cs
    cp ${./tests/test_volume_sync_state.py} tests/test_volume_sync_state.py
    cp ${./tests/VolumeSyncStateProbe.cs} tests/VolumeSyncStateProbe.cs
    cp ${./tests/test_control_command_state.py} tests/test_control_command_state.py
    cp ${./tests/ControlCommandStateProbe.cs} tests/ControlCommandStateProbe.cs
    mkdir plugin
    cp ${sources}/plugin/BridgeRequest.cs plugin/BridgeRequest.cs
    cp ${sources}/plugin/SpotifyModeTransition.cs plugin/SpotifyModeTransition.cs
    cp ${sources}/plugin/ArtworkRotationState.cs plugin/ArtworkRotationState.cs
    cp ${sources}/plugin/VolumeSyncState.cs plugin/VolumeSyncState.cs
    cp ${sources}/plugin/ControlCommandState.cs plugin/ControlCommandState.cs
    python -m unittest discover -s tests -v
    touch "$out"
  '';
}
