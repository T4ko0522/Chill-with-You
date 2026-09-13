using System;
using System.Collections.Generic;
using System.Reflection;
using BepInEx;
using Bulbul;
using HarmonyLib;
using UnityEngine;

namespace ChillWithYou.Spotify
{
    [BepInPlugin(PluginGuid, PluginName, PluginVersion)]
    public sealed class SpotifyMusicPlugin : BaseUnityPlugin
    {
        public const string PluginGuid = "io.github.t4ko0522.chillwithyou.spotify";
        public const string PluginName = "Chill with You Spotify";
        public const string PluginVersion = "0.2.4";

        private const float UiSearchIntervalSeconds = 1f;
        private static SpotifyMusicPlugin _instance;

        private readonly List<MusicUiBinding> _bindings = new List<MusicUiBinding>();
        private readonly GameMusicMute _gameMusicMute = new GameMusicMute();
        private Harmony _harmony;
        private SpotifySession _session;
        private SpotifyArtworkLoader _artwork;
        private bool _spotifyMode;
        private bool _loggedFirstUpdate;
        private bool _loggedFirstUiScan;
        private bool _activationFailed;
        private float _nextUiSearchAt;

        private void Awake()
        {
            // The host was observed being destroyed after Awake and before Start. BepInEx uses
            // these flags for its HideManagerGameObject protection; apply the same protection
            // without requiring a machine-local BepInEx.cfg change.
            gameObject.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(gameObject);
            _instance = this;
            string token = Environment.GetEnvironmentVariable("CHILL_SPOTIFY_TOKEN");
            _session = new SpotifySession(
                this,
                Environment.GetEnvironmentVariable("CHILL_SPOTIFY_URL"),
                token,
                OnSessionStateChanged,
                message => Logger.LogWarning(message),
                message => Logger.LogDebug(message));
            _artwork = new SpotifyArtworkLoader(this, ApplyArtwork);

            _harmony = new Harmony(PluginGuid);
            _harmony.PatchAll(typeof(SpotifyMusicPlugin).Assembly);
            Logger.LogInfo(PluginName + " " + PluginVersion +
                " loaded on a protected plugin host. Spotify will attach to the music bar automatically.");
            if (string.IsNullOrEmpty(token))
            {
                Logger.LogWarning("CHILL_SPOTIFY_TOKEN is empty; the bridge will reject requests.");
            }
        }

        private void OnEnable()
        {
            Logger.LogInfo("Plugin component enabled; activeInHierarchy=" + gameObject.activeInHierarchy + ".");
        }

        private void Start()
        {
            Logger.LogInfo("Plugin Start reached.");
        }

        private void Update()
        {
            if (!_loggedFirstUpdate)
            {
                _loggedFirstUpdate = true;
                Logger.LogInfo("Plugin Update reached; enabled=" + enabled +
                    ", activeInHierarchy=" + gameObject.activeInHierarchy + ".");
            }
            if (Time.unscaledTime >= _nextUiSearchAt)
            {
                _nextUiSearchAt = Time.unscaledTime + UiSearchIntervalSeconds;
                if (_session.Configured)
                {
                    FindAndBindMusicUis();
                    TryEnableSpotifyMode();
                }
                RemoveDestroyedBindings();
            }
            if (!_spotifyMode) return;

            _gameMusicMute.Tick(Time.unscaledTime);
            RenderSpotifyState();
            _session.Tick(Time.unscaledTime);
        }

        private void OnDestroy()
        {
            DisableSpotifyMode();
            for (int i = _bindings.Count - 1; i >= 0; --i) _bindings[i].Dispose();
            _bindings.Clear();
            _session.Dispose();
            _artwork.Dispose();
            if (_harmony != null) _harmony.UnpatchSelf();
            if (_instance == this) _instance = null;
        }

        internal static void RenderAfterFacilityUpdate()
        {
            if (_instance != null && _instance._spotifyMode) _instance.RenderSpotifyState();
        }

        internal static void RenderAfterGameUiUpdate(MonoBehaviour ui)
        {
            if (_instance != null && _instance._spotifyMode) _instance.RenderSpotifyState(ui);
        }

        internal static void MarkFacilityReady(FacilityMusic facility)
        {
            if (_instance == null || facility == null) return;
            _instance.Logger.LogInfo("FacilityMusic Setup observed; id=" + facility.GetInstanceID() + ".");
            if (_instance._session.Configured)
            {
                _instance.FindAndBindMusicUis();
                _instance.TryEnableSpotifyMode();
            }
        }

        internal static bool ShouldSuppressFacilityAction(FacilityMusic facility)
        {
            if (_instance == null || !_instance._spotifyMode || facility == null) return false;
            for (int i = 0; i < _instance._bindings.Count; ++i)
            {
                MusicUiBinding binding = _instance._bindings[i];
                if (binding.IsInSpotifyMode && binding.Facility == facility) return true;
            }
            return false;
        }

        private void TryEnableSpotifyMode()
        {
            if (_spotifyMode || _activationFailed) return;
            Exception transitionError;
            if (!SpotifyModeTransition.TryEnter(
                _bindings,
                binding => binding.EnterSpotifyMode(),
                binding => binding.ExitSpotifyMode(),
                out transitionError))
            {
                if (transitionError != null)
                {
                    _activationFailed = true;
                    Logger.LogError("Spotify injection failed and was rolled back: " + transitionError);
                }
                return;
            }

            _spotifyMode = true;
            try
            {
                _session.Activate();
                _gameMusicMute.Tick(Time.unscaledTime);
                RenderSpotifyState();
                Logger.LogInfo("Spotify injected into " + _bindings.Count + " music UI binding(s).");
            }
            catch (Exception exception)
            {
                _activationFailed = true;
                Logger.LogError("Spotify injection initialization failed; restoring game music: " + exception);
                DisableSpotifyMode();
            }
        }

        private void DisableSpotifyMode()
        {
            if (_spotifyMode)
            {
                // Fail open before touching UI: Harmony prefixes immediately stop suppressing game actions.
                _spotifyMode = false;
                for (int i = 0; i < _bindings.Count; ++i)
                {
                    try { _bindings[i].ExitSpotifyMode(); }
                    catch (Exception exception)
                    {
                        Logger.LogError("Could not restore a MusicUI binding: " + exception);
                    }
                }
            }
            _session.Reset();
            _artwork.Reset();
            StopAllCoroutines();
            _gameMusicMute.Restore();
            Logger.LogInfo("Spotify injection disabled.");
        }

        private void FindAndBindMusicUis()
        {
            MusicUI[] musicUis = Resources.FindObjectsOfTypeAll<MusicUI>();
            if (!_loggedFirstUiScan)
            {
                _loggedFirstUiScan = true;
                int sceneCount = 0;
                int initializedCount = 0;
                for (int i = 0; i < musicUis.Length; ++i)
                {
                    MusicUI candidate = musicUis[i];
                    FacilityMusic initializedFacility;
                    if (candidate != null && candidate.gameObject.scene.IsValid())
                    {
                        ++sceneCount;
                        if (TryGetField(candidate, "_facilityMusic", out initializedFacility) &&
                            initializedFacility != null) ++initializedCount;
                    }
                }
                Logger.LogInfo("First MusicUI scan: candidates=" + musicUis.Length +
                    ", live=" + sceneCount + ", initialized=" + initializedCount + ".");
            }
            for (int i = 0; i < musicUis.Length; ++i)
            {
                MusicUI musicUi = musicUis[i];
                FacilityMusic facility;
                if (musicUi == null || !musicUi.gameObject.scene.IsValid() || FindBinding(musicUi) != null ||
                    !TryGetField(musicUi, "_facilityMusic", out facility) || facility == null) continue;
                try { BindMusicUi(musicUi, facility); }
                catch (Exception exception) { Logger.LogError("Could not bind MusicUI: " + exception); }
            }
        }

        private void BindMusicUi(MonoBehaviour ui, FacilityMusic facility)
        {
            MusicUiBinding binding = new MusicUiBinding(
                ui,
                facility,
                command => _session.SendCommand(command),
                volume => _session.SetVolume(volume));
            _bindings.Add(binding);
            _activationFailed = false;
            Logger.LogInfo(ui.GetType().Name + " bound to FacilityMusic id=" + facility.GetInstanceID() + ".");
            if (!_spotifyMode) return;
            try
            {
                binding.EnterSpotifyMode();
                RenderSpotifyState(binding);
                if (_artwork.Texture != null) binding.SetArtwork(_artwork.Texture);
            }
            catch
            {
                _bindings.Remove(binding);
                binding.Dispose();
                throw;
            }
        }

        private void RemoveDestroyedBindings()
        {
            for (int i = _bindings.Count - 1; i >= 0; --i)
            {
                if (!_bindings[i].IsAlive)
                {
                    _bindings[i].Dispose();
                    _bindings.RemoveAt(i);
                }
            }
            if (_spotifyMode && _bindings.Count == 0)
            {
                Logger.LogWarning("All Spotify music UI bindings were destroyed; restoring game music.");
                DisableSpotifyMode();
            }
        }

        private MusicUiBinding FindBinding(MonoBehaviour ui)
        {
            for (int i = 0; i < _bindings.Count; ++i)
            {
                if (_bindings[i].Ui == ui) return _bindings[i];
            }
            return null;
        }

        private void OnSessionStateChanged()
        {
            if (!_spotifyMode) return;
            _artwork.ApplyState(_session.State);
            RenderSpotifyState();
        }

        private void ApplyArtwork(Texture2D texture)
        {
            for (int i = 0; i < _bindings.Count; ++i)
            {
                if (texture == null) _bindings[i].ClearArtwork();
                else _bindings[i].SetArtwork(texture);
            }
        }

        private void RenderSpotifyState()
        {
            for (int i = 0; i < _bindings.Count; ++i) RenderSpotifyState(_bindings[i]);
        }

        private void RenderSpotifyState(MonoBehaviour ui)
        {
            MusicUiBinding binding = FindBinding(ui);
            if (binding != null) RenderSpotifyState(binding);
        }

        private void RenderSpotifyState(MusicUiBinding binding)
        {
            binding.Render(
                _session.State,
                _session.Configured,
                _session.ControlsBlocked,
                _session.CanSetVolume,
                _session.DisplayVolume);
        }

        private static bool TryGetField<T>(object instance, string name, out T value) where T : class
        {
            value = null;
            FieldInfo field = instance.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null) return false;
            value = field.GetValue(instance) as T;
            return value != null;
        }
    }
}
