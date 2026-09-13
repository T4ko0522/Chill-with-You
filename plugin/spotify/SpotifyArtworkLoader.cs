using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

namespace ChillWithYou.Spotify
{
    internal sealed class SpotifyArtworkLoader : IDisposable
    {
        private readonly MonoBehaviour _owner;
        private readonly Action<Texture2D> _changed;
        private readonly HashSet<UnityWebRequest> _activeRequests = new HashSet<UnityWebRequest>();
        private Texture2D _texture;
        private string _trackId;
        private string _url;
        private int _generation;

        public Texture2D Texture { get { return _texture; } }

        public SpotifyArtworkLoader(MonoBehaviour owner, Action<Texture2D> changed)
        {
            _owner = owner;
            _changed = changed;
        }

        public void ApplyState(SpotifyState state)
        {
            string trackId = state == null ? null : state.trackId;
            string url = state == null ? null : state.artUrl;
            if (string.Equals(_trackId, trackId, StringComparison.Ordinal) &&
                string.Equals(_url, url, StringComparison.Ordinal))
            {
                return;
            }

            Clear();
            _trackId = trackId;
            _url = url;
            if (IsAllowedUrl(url))
            {
                int generation = _generation;
                _owner.StartCoroutine(Download(url, trackId, generation));
            }
        }

        public void Clear()
        {
            ++_generation;
            _trackId = null;
            _url = null;
            if (_texture != null)
            {
                UnityEngine.Object.Destroy(_texture);
                _texture = null;
            }
            _changed(null);
        }

        public void Dispose()
        {
            Reset();
        }

        public void Reset()
        {
            foreach (UnityWebRequest request in _activeRequests)
            {
                request.Abort();
                request.Dispose();
            }
            _activeRequests.Clear();
            Clear();
        }

        private IEnumerator Download(string url, string trackId, int generation)
        {
            UnityWebRequest request = UnityWebRequestTexture.GetTexture(url);
            _activeRequests.Add(request);
            request.timeout = 5;
            yield return request.SendWebRequest();

            if (request.result == UnityWebRequest.Result.Success && generation == _generation &&
                string.Equals(_trackId, trackId, StringComparison.Ordinal) &&
                string.Equals(_url, url, StringComparison.Ordinal))
            {
                Texture2D downloaded = DownloadHandlerTexture.GetContent(request);
                _texture = UnityEngine.Object.Instantiate(downloaded);
                _changed(_texture);
                UnityEngine.Object.Destroy(downloaded);
            }
            _activeRequests.Remove(request);
            request.Dispose();
        }

        private static bool IsAllowedUrl(string value)
        {
            Uri uri;
            return Uri.TryCreate(value, UriKind.Absolute, out uri) &&
                string.Equals(uri.Scheme, "https", StringComparison.OrdinalIgnoreCase) &&
                string.Equals(uri.Host, "i.scdn.co", StringComparison.OrdinalIgnoreCase);
        }
    }
}
