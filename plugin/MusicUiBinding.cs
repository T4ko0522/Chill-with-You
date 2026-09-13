using System;
using System.Reflection;
using Bulbul;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace ChillWithYou.Spotify
{
    internal sealed class MusicUiBinding : IDisposable
    {
        private const float ArtworkDegreesPerSecond = 18f;
        private const float ArtworkDiameter = 48f;
        private const float ArtworkGap = 8f;
        private const float ArtworkReservedWidth = ArtworkDiameter + ArtworkGap;

        private readonly Action<string> _sendCommand;
        private readonly Action<float> _setVolume;
        private readonly TextMeshProUGUI _title;
        private readonly TextMeshProUGUI _artist;
        private readonly Slider _progress;
        private readonly Slider _volume;
        private readonly Button _playPause;
        private readonly Button _next;
        private readonly Button _previous;
        private readonly Button _mute;
        private readonly Button _shuffle;
        private readonly Button _loop;
        private Button.ButtonClickedEvent _playPauseEvent;
        private Button.ButtonClickedEvent _nextEvent;
        private Button.ButtonClickedEvent _previousEvent;
        private Slider.SliderEvent _volumeEvent;
        private readonly Image _playPauseImage;
        private readonly Image _nextImage;
        private readonly Image _previousImage;
        private string _originalTitle;
        private string _originalArtist;
        private bool _progressInteractable;
        private bool _volumeInteractable;
        private bool _playPauseInteractable;
        private bool _nextInteractable;
        private bool _previousInteractable;
        private bool _muteInteractable;
        private bool _shuffleInteractable;
        private bool _loopInteractable;
        private float _progressValue;
        private float _volumeValue;
        private Sprite _playPauseSprite;
        private Sprite _nextSprite;
        private Sprite _previousSprite;
        private Vector2 _titleOffsetMin;
        private Vector2 _titleOffsetMax;
        private Vector2 _artistOffsetMin;
        private Vector2 _artistOffsetMax;
        private bool _titleWordWrapping;
        private bool _artistWordWrapping;
        private TextOverflowModes _titleOverflowMode;
        private TextOverflowModes _artistOverflowMode;

        private readonly GameObject _artworkHost;
        private readonly RawImage _artwork;
        private readonly Texture2D _maskTexture;
        private readonly Sprite _maskSprite;
        private readonly ArtworkRotationState _artworkRotation = new ArtworkRotationState();
        private Texture2D _artworkTexture;
        private SpotifyState _state;
        private bool _inSpotifyMode;

        public MonoBehaviour Ui { get; private set; }
        public FacilityMusic Facility { get; private set; }
        public bool IsAlive { get { return Ui != null; } }
        public bool IsInSpotifyMode { get { return _inSpotifyMode && IsAlive; } }

        public MusicUiBinding(
            MonoBehaviour ui,
            FacilityMusic facility,
            Action<string> sendCommand,
            Action<float> setVolume)
        {
            Ui = ui;
            Facility = facility;
            _sendCommand = sendCommand;
            _setVolume = setVolume;
            _title = GetField<TextMeshProUGUI>(ui, "_musicTitleText");
            _artist = GetField<TextMeshProUGUI>(ui, "_artistNameText");
            _progress = GetField<Slider>(ui, "musicProgressSlider");
            _volume = GetField<Slider>(ui, "_volumeSlider");
            _playPause = GetField<Button>(ui, "_playOrPauseButton");
            _next = GetField<Button>(ui, "_musicNextButton");
            _previous = GetField<Button>(ui, "_musicBackButton");
            _mute = GetField<Button>(ui, "_switchMuteButton");
            _shuffle = GetField<Button>(ui, "_shuffleButton");
            _loop = GetField<Button>(ui, "_loopButton");
            _playPauseImage = GetField<Image>(ui, "_playOrPauseButtonImage");
            _nextImage = GetField<Image>(ui, "_nextButtonImage");
            _previousImage = GetField<Image>(ui, "_backButtonImage");
            _artworkHost = BuildArtwork(
                _title.transform.parent,
                out _artwork,
                out _maskTexture,
                out _maskSprite);
        }

        public void EnterSpotifyMode()
        {
            if (_inSpotifyMode || !IsAlive)
            {
                return;
            }
            _inSpotifyMode = true;

            _originalTitle = _title.text;
            _originalArtist = _artist.text;
            _progressInteractable = _progress.interactable;
            _volumeInteractable = _volume != null && _volume.interactable;
            _playPauseInteractable = _playPause.interactable;
            _nextInteractable = _next.interactable;
            _previousInteractable = _previous.interactable;
            _muteInteractable = _mute.interactable;
            _shuffleInteractable = _shuffle.interactable;
            _loopInteractable = _loop.interactable;
            _progressValue = _progress.value;
            _playPauseSprite = _playPauseImage.sprite;
            _nextSprite = _nextImage.sprite;
            _previousSprite = _previousImage.sprite;
            RectTransform titleRect = _title.rectTransform;
            RectTransform artistRect = _artist.rectTransform;
            _titleOffsetMin = titleRect.offsetMin;
            _titleOffsetMax = titleRect.offsetMax;
            _artistOffsetMin = artistRect.offsetMin;
            _artistOffsetMax = artistRect.offsetMax;
            _titleWordWrapping = _title.enableWordWrapping;
            _artistWordWrapping = _artist.enableWordWrapping;
            _titleOverflowMode = _title.overflowMode;
            _artistOverflowMode = _artist.overflowMode;
            _playPauseEvent = _playPause.onClick;
            _nextEvent = _next.onClick;
            _previousEvent = _previous.onClick;
            if (_volume != null)
            {
                _volumeEvent = _volume.onValueChanged;
                _volumeValue = _volume.value;
            }

            _playPause.onClick = NewEvent(OnPlayPause);
            _next.onClick = NewEvent(OnNext);
            _previous.onClick = NewEvent(OnPrevious);
            if (_volume != null) _volume.onValueChanged = NewSliderEvent(OnVolumeChanged);

            _progress.interactable = false;
            if (_volume != null) _volume.interactable = false;
            _mute.interactable = false;
            _shuffle.interactable = false;
            _loop.interactable = false;
            ApplySpotifyLayout();
            _artworkHost.SetActive(true);
        }

        public void ExitSpotifyMode()
        {
            if (!_inSpotifyMode || !IsAlive)
            {
                return;
            }
            _inSpotifyMode = false;

            _playPause.onClick = _playPauseEvent;
            _next.onClick = _nextEvent;
            _previous.onClick = _previousEvent;
            if (_volume != null) _volume.onValueChanged = _volumeEvent;

            _progress.interactable = _progressInteractable;
            if (_volume != null)
            {
                _volume.interactable = _volumeInteractable;
                _volume.SetValueWithoutNotify(_volumeValue);
            }
            _playPause.interactable = _playPauseInteractable;
            _next.interactable = _nextInteractable;
            _previous.interactable = _previousInteractable;
            _mute.interactable = _muteInteractable;
            _shuffle.interactable = _shuffleInteractable;
            _loop.interactable = _loopInteractable;
            _progress.value = _progressValue;
            _playPauseImage.sprite = _playPauseSprite;
            _nextImage.sprite = _nextSprite;
            _previousImage.sprite = _previousSprite;
            RestoreTextLayout();
            _artworkHost.SetActive(false);
            _artwork.rectTransform.localRotation = Quaternion.identity;
            _artworkRotation.Reset();
            ClearArtwork();
            Render(null, false, false, false, 0f);
            RestoreCurrentGameState();
        }

        public void Render(
            SpotifyState state,
            bool bridgeConfigured,
            bool controlsBlocked,
            bool canSetVolume,
            float displayVolume)
        {
            if (!IsAlive || !_inSpotifyMode)
            {
                return;
            }
            _state = state;
            ApplySpotifyLayout();

            if (state == null)
            {
                _title.text = bridgeConfigured ? "Spotifyに接続できません" : "Spotify用の起動設定が必要です";
                _artist.text = bridgeConfigured
                    ? "Spotifyを起動してください"
                    : "CHILL_SPOTIFY_URLとTOKENを設定してください";
                _playPause.interactable = false;
                _next.interactable = false;
                _previous.interactable = false;
                ((IMusicPlayerUI)Ui).OnPauseMusic();
                _progress.interactable = false;
                if (_volume != null) _volume.interactable = false;
                return;
            }

            _title.text = string.IsNullOrEmpty(state.title) ? "Spotify" : state.title;
            _artist.text = FormatArtistAndAlbum(state.artist, state.album);
            bool controlsAvailable = !controlsBlocked;
            _playPause.interactable = controlsAvailable &&
                (state.playing ? state.canPause : state.canPlay);
            _next.interactable = controlsAvailable && state.canGoNext;
            _previous.interactable = controlsAvailable && state.canGoPrevious;

            if (state.playing)
            {
                ((IMusicPlayerUI)Ui).OnPlayMusic();
            }
            else
            {
                ((IMusicPlayerUI)Ui).OnPauseMusic();
            }
            _progress.interactable = false;
            _progress.value = state.lengthUs > 0.0
                ? Mathf.Clamp01((float)(state.positionUs / state.lengthUs))
                : 0f;
            if (_volume != null)
            {
                _volume.interactable = canSetVolume;
                _volume.SetValueWithoutNotify(Mathf.Lerp(
                    _volume.minValue,
                    _volume.maxValue,
                    displayVolume));
            }

            float artworkDelta = _artworkRotation.NextDelta(
                state.connected,
                state.playing,
                Time.frameCount,
                Time.unscaledDeltaTime,
                ArtworkDegreesPerSecond);
            if (artworkDelta != 0f)
            {
                _artwork.rectTransform.Rotate(0f, 0f, -artworkDelta);
            }
        }

        public void SetArtwork(Texture2D texture)
        {
            ClearArtwork();
            if (texture == null || !IsAlive)
            {
                return;
            }
            _artworkTexture = UnityEngine.Object.Instantiate(texture);
            _artwork.texture = _artworkTexture;
            _artwork.gameObject.SetActive(_inSpotifyMode);
        }

        public void ClearArtwork()
        {
            if (_artwork != null)
            {
                _artwork.texture = null;
                _artwork.gameObject.SetActive(false);
            }
            if (_artworkTexture != null)
            {
                UnityEngine.Object.Destroy(_artworkTexture);
                _artworkTexture = null;
            }
        }

        public void Dispose()
        {
            if (IsAlive)
            {
                ExitSpotifyMode();
            }
            ClearArtwork();
            if (_artworkHost != null)
            {
                UnityEngine.Object.Destroy(_artworkHost);
            }
            if (_maskSprite != null) UnityEngine.Object.Destroy(_maskSprite);
            if (_maskTexture != null) UnityEngine.Object.Destroy(_maskTexture);
            Ui = null;
            Facility = null;
        }

        private void OnPlayPause()
        {
            if (_state != null)
            {
                _sendCommand(_state.playing ? "pause" : "play");
            }
        }

        private void OnNext()
        {
            if (_state != null && _state.canGoNext)
            {
                _sendCommand("next");
            }
        }

        private void OnPrevious()
        {
            if (_state != null && _state.canGoPrevious)
            {
                _sendCommand("previous");
            }
        }

        private void OnVolumeChanged(float value)
        {
            if (_volume != null)
            {
                _setVolume(_volume.normalizedValue);
            }
        }

        private void RestoreCurrentGameState()
        {
            FacilityMusic facility = Facility;
            if (facility == null)
            {
                FacilityMusic[] facilities = Resources.FindObjectsOfTypeAll<FacilityMusic>();
                for (int i = 0; i < facilities.Length; ++i)
                {
                    if (facilities[i] != null && facilities[i].gameObject.scene.IsValid())
                    {
                        facility = facilities[i];
                        break;
                    }
                }
            }
            if (facility == null)
            {
                _title.text = _originalTitle;
                _artist.text = _originalArtist;
                return;
            }

            try
            {
                GameAudioInfo playing = facility.PlayingMusic;
                if (playing == null)
                {
                    _title.text = "No Music Selected";
                    _artist.text = "Unknown Artist";
                    ((IMusicPlayerUI)Ui).OnPlayEmptyMusic();
                }
                else
                {
                    _title.text = playing.Title ?? string.Empty;
                    _artist.text = playing.Credit ?? string.Empty;
                    if (facility.IsPaused)
                    {
                        ((IMusicPlayerUI)Ui).OnPauseMusic();
                    }
                    else
                    {
                        ((IMusicPlayerUI)Ui).OnPlayMusic();
                    }
                }
            }
            catch (Exception)
            {
                _title.text = _originalTitle;
                _artist.text = _originalArtist;
                _playPauseImage.sprite = _playPauseSprite;
            }
            finally
            {
                _progress.interactable = _progressInteractable;
            }
        }

        private static Button.ButtonClickedEvent NewEvent(UnityEngine.Events.UnityAction action)
        {
            Button.ButtonClickedEvent result = new Button.ButtonClickedEvent();
            result.AddListener(action);
            return result;
        }

        private static Slider.SliderEvent NewSliderEvent(UnityEngine.Events.UnityAction<float> action)
        {
            Slider.SliderEvent result = new Slider.SliderEvent();
            result.AddListener(action);
            return result;
        }

        private static string FormatArtistAndAlbum(string artist, string album)
        {
            if (string.IsNullOrEmpty(album))
            {
                return artist ?? string.Empty;
            }
            if (string.IsNullOrEmpty(artist))
            {
                return album;
            }
            return artist + "  ·  " + album;
        }

        private void ApplySpotifyLayout()
        {
            RectTransform titleRect = _title.rectTransform;
            RectTransform artistRect = _artist.rectTransform;
            titleRect.offsetMin = new Vector2(_titleOffsetMin.x + ArtworkReservedWidth, _titleOffsetMin.y);
            titleRect.offsetMax = _titleOffsetMax;
            artistRect.offsetMin = new Vector2(_artistOffsetMin.x + ArtworkReservedWidth, _artistOffsetMin.y);
            artistRect.offsetMax = _artistOffsetMax;
            _title.enableWordWrapping = false;
            _artist.enableWordWrapping = false;
            _title.overflowMode = TextOverflowModes.Ellipsis;
            _artist.overflowMode = TextOverflowModes.Ellipsis;
            UpdateArtworkPosition();
        }

        private void RestoreTextLayout()
        {
            _title.rectTransform.offsetMin = _titleOffsetMin;
            _title.rectTransform.offsetMax = _titleOffsetMax;
            _artist.rectTransform.offsetMin = _artistOffsetMin;
            _artist.rectTransform.offsetMax = _artistOffsetMax;
            _title.enableWordWrapping = _titleWordWrapping;
            _artist.enableWordWrapping = _artistWordWrapping;
            _title.overflowMode = _titleOverflowMode;
            _artist.overflowMode = _artistOverflowMode;
        }

        private void UpdateArtworkPosition()
        {
            RectTransform parent = _artworkHost.transform.parent as RectTransform;
            if (parent == null)
            {
                return;
            }

            Vector3[] titleCorners = new Vector3[4];
            Vector3[] artistCorners = new Vector3[4];
            _title.rectTransform.GetWorldCorners(titleCorners);
            _artist.rectTransform.GetWorldCorners(artistCorners);
            Vector3 titleBottomLeft = parent.InverseTransformPoint(titleCorners[0]);
            Vector3 titleTopLeft = parent.InverseTransformPoint(titleCorners[1]);
            Vector3 artistBottomLeft = parent.InverseTransformPoint(artistCorners[0]);
            Vector3 artistTopLeft = parent.InverseTransformPoint(artistCorners[1]);
            float shiftedLeft = Mathf.Min(titleBottomLeft.x, artistBottomLeft.x);
            float bottom = Mathf.Min(titleBottomLeft.y, artistBottomLeft.y);
            float top = Mathf.Max(titleTopLeft.y, artistTopLeft.y);
            RectTransform artworkRect = (RectTransform)_artworkHost.transform;
            artworkRect.localPosition = new Vector3(
                shiftedLeft - ArtworkGap - ArtworkDiameter * 0.5f,
                (bottom + top) * 0.5f,
                0f);
        }

        private static GameObject BuildArtwork(
            Transform anchor,
            out RawImage artwork,
            out Texture2D maskTexture,
            out Sprite maskSprite)
        {
            GameObject host = new GameObject("SpotifyArtwork", typeof(RectTransform));
            host.transform.SetParent(anchor, false);
            RectTransform hostRect = (RectTransform)host.transform;
            hostRect.anchorMin = new Vector2(0.5f, 0.5f);
            hostRect.anchorMax = new Vector2(0.5f, 0.5f);
            hostRect.pivot = new Vector2(0.5f, 0.5f);
            hostRect.sizeDelta = new Vector2(ArtworkDiameter, ArtworkDiameter);

            GameObject maskObject = new GameObject(
                "CircleMask",
                typeof(RectTransform),
                typeof(Image),
                typeof(Mask),
                typeof(AspectRatioFitter));
            maskObject.transform.SetParent(host.transform, false);
            RectTransform maskRect = (RectTransform)maskObject.transform;
            maskRect.anchorMin = Vector2.zero;
            maskRect.anchorMax = Vector2.one;
            maskRect.offsetMin = Vector2.zero;
            maskRect.offsetMax = Vector2.zero;
            AspectRatioFitter fitter = maskObject.GetComponent<AspectRatioFitter>();
            fitter.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
            fitter.aspectRatio = 1f;

            maskTexture = CreateCircleMaskTexture(64);
            maskSprite = Sprite.Create(
                maskTexture,
                new Rect(0f, 0f, maskTexture.width, maskTexture.height),
                new Vector2(0.5f, 0.5f),
                64f,
                0,
                SpriteMeshType.Tight);
            Image maskImage = maskObject.GetComponent<Image>();
            maskImage.sprite = maskSprite;
            maskImage.type = Image.Type.Simple;
            maskImage.raycastTarget = false;
            Mask mask = maskObject.GetComponent<Mask>();
            mask.showMaskGraphic = false;

            GameObject artworkObject = new GameObject(
                "ArtworkImage",
                typeof(RectTransform),
                typeof(RawImage));
            artworkObject.transform.SetParent(maskObject.transform, false);
            RectTransform artworkRect = (RectTransform)artworkObject.transform;
            artworkRect.anchorMin = Vector2.zero;
            artworkRect.anchorMax = Vector2.one;
            artworkRect.offsetMin = Vector2.zero;
            artworkRect.offsetMax = Vector2.zero;
            artwork = artworkObject.GetComponent<RawImage>();
            artwork.raycastTarget = false;
            artworkObject.SetActive(false);
            host.transform.SetAsLastSibling();
            host.SetActive(false);
            return host;
        }

        private static Texture2D CreateCircleMaskTexture(int size)
        {
            Texture2D texture = new Texture2D(size, size, TextureFormat.RGBA32, false);
            texture.name = "SpotifyArtworkCircleMask";
            Color32[] pixels = new Color32[size * size];
            float center = (size - 1) * 0.5f;
            float radiusSquared = center * center;
            for (int y = 0; y < size; ++y)
            {
                for (int x = 0; x < size; ++x)
                {
                    float dx = x - center;
                    float dy = y - center;
                    byte alpha = dx * dx + dy * dy <= radiusSquared ? (byte)255 : (byte)0;
                    pixels[y * size + x] = new Color32(255, 255, 255, alpha);
                }
            }
            texture.SetPixels32(pixels);
            texture.Apply(false, true);
            return texture;
        }

        private static T GetField<T>(object instance, string name) where T : class
        {
            FieldInfo field = instance.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null)
            {
                throw new MissingFieldException(instance.GetType().FullName, name);
            }
            T value = field.GetValue(instance) as T;
            if (value == null)
            {
                throw new InvalidOperationException(name + " is not assigned on " + instance.GetType().FullName);
            }
            return value;
        }
    }
}
