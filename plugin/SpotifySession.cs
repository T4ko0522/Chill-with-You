using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace ChillWithYou.Spotify
{
    internal sealed class SpotifySession : IDisposable
    {
        private const float PollIntervalSeconds = 0.5f;

        private readonly MonoBehaviour _owner;
        private readonly string _bridgeUrl;
        private readonly string _bridgeToken;
        private readonly Action _stateChanged;
        private readonly Action<string> _logWarning;
        private readonly Action<string> _logDebug;
        private readonly HashSet<BridgeRequest> _activeRequests = new HashSet<BridgeRequest>();
        private readonly VolumeSyncState _volumeSync = new VolumeSyncState();
        private readonly ControlCommandState _controlCommands = new ControlCommandState();

        private bool _active;
        private bool _pollInFlight;
        private float _nextPollAt;

        public SpotifyState State { get; private set; }
        public bool Configured { get; private set; }
        public bool ControlsBlocked { get { return _controlCommands.ControlsBlocked; } }
        public bool CanSetVolume { get { return _volumeSync.CanSetVolume; } }
        public float DisplayVolume { get { return _volumeSync.DisplayVolume; } }

        public SpotifySession(
            MonoBehaviour owner,
            string bridgeUrl,
            string bridgeToken,
            Action stateChanged,
            Action<string> logWarning,
            Action<string> logDebug)
        {
            _owner = owner;
            _bridgeUrl = NormalizeBridgeUrl(bridgeUrl);
            _bridgeToken = bridgeToken ?? string.Empty;
            _stateChanged = stateChanged;
            _logWarning = logWarning;
            _logDebug = logDebug;
            Configured = !string.IsNullOrEmpty(_bridgeUrl) && !string.IsNullOrEmpty(_bridgeToken);
        }

        public void Activate()
        {
            _active = true;
            State = null;
            _nextPollAt = 0f;
        }

        public void Tick(float now)
        {
            if (!_active || !Configured || _pollInFlight || now < _nextPollAt)
            {
                return;
            }
            _nextPollAt = now + PollIntervalSeconds;
            _owner.StartCoroutine(PollState());
        }

        public void SendCommand(string command)
        {
            long commandId;
            if (!_active || State == null || !_controlCommands.TryBegin(out commandId))
            {
                return;
            }
            NotifyChanged();
            _owner.StartCoroutine(PostCommand(commandId, command));
        }

        public void SetVolume(float volume)
        {
            float commandVolume;
            long commandId;
            if (!_active || State == null ||
                !_volumeSync.TrySetLocal(volume, out commandId, out commandVolume))
            {
                NotifyChanged();
                return;
            }
            NotifyChanged();
            _owner.StartCoroutine(PostVolumeCommand(commandId, commandVolume));
        }

        public void Reset()
        {
            _active = false;
            foreach (BridgeRequest request in _activeRequests)
            {
                request.Dispose();
            }
            _activeRequests.Clear();
            _pollInFlight = false;
            State = null;
            _volumeSync.Reset();
            _controlCommands.Invalidate();
        }

        public void Dispose()
        {
            Reset();
        }

        private IEnumerator PollState()
        {
            _pollInFlight = true;
            long controlObservation = _controlCommands.CaptureObservation();
            BridgeRequest request = StartRequest(_bridgeUrl + "/state", null);
            while (!request.IsCompleted) yield return null;

            if (!_active)
            {
                FinishRequest(request);
                _pollInFlight = false;
                yield break;
            }

            if (request.Result.Success)
            {
                try
                {
                    ApplyState(JsonUtility.FromJson<SpotifyState>(request.Result.Text), controlObservation);
                }
                catch (Exception exception)
                {
                    _logWarning("Invalid Spotify bridge state: " + exception.Message);
                    ApplyState(null, controlObservation);
                }
            }
            else
            {
                _logDebug("Spotify bridge unavailable: " + request.Result.Error);
                ApplyState(null, controlObservation);
            }

            FinishRequest(request);
            _pollInFlight = false;
        }

        private void ApplyState(SpotifyState state, long? controlObservation = null)
        {
            if (state == null || !state.connected)
            {
                State = null;
                _volumeSync.Reset();
                _controlCommands.Invalidate();
                NotifyChanged();
                return;
            }

            _volumeSync.ApplyRemote(true, state.canSetVolume, state.volume);
            if (controlObservation.HasValue)
            {
                _controlCommands.ApplyRemoteState(controlObservation.Value);
            }
            State = state;
            NotifyChanged();
        }

        private IEnumerator PostCommand(long commandId, string command)
        {
            BridgeRequest request = StartRequest(
                _bridgeUrl + "/command", "{\"command\":\"" + command + "\"}");
            while (!request.IsCompleted) yield return null;

            bool success = request.Result.Success;
            string error = request.Result.Error;
            FinishRequest(request);
            if (!_controlCommands.Complete(commandId, success))
            {
                yield break;
            }
            if (!success)
            {
                _logWarning("Spotify command '" + command + "' failed: " + error);
                ApplyState(null);
            }
            else
            {
                _nextPollAt = 0f;
                NotifyChanged();
            }
        }

        private IEnumerator PostVolumeCommand(long commandId, float volume)
        {
            string body = "{\"command\":\"volume\",\"value\":" +
                volume.ToString("R", CultureInfo.InvariantCulture) + "}";
            BridgeRequest request = StartRequest(_bridgeUrl + "/command", body);
            while (!request.IsCompleted) yield return null;

            bool success = _active && request.Result.Success;
            FinishRequest(request);

            bool hasNext;
            long nextCommandId;
            float next;
            if (!_volumeSync.CompleteCommand(
                commandId, success, out hasNext, out nextCommandId, out next))
            {
                yield break;
            }
            if (!success)
            {
                ApplyState(null);
                yield break;
            }
            _nextPollAt = 0f;
            if (hasNext && _active && State != null)
            {
                _owner.StartCoroutine(PostVolumeCommand(nextCommandId, next));
            }
        }

        private BridgeRequest StartRequest(string url, string body)
        {
            BridgeRequest request = new BridgeRequest(url, _bridgeToken, body);
            _activeRequests.Add(request);
            return request;
        }

        private void FinishRequest(BridgeRequest request)
        {
            _activeRequests.Remove(request);
            request.Dispose();
        }

        private void NotifyChanged()
        {
            if (_stateChanged != null)
            {
                _stateChanged();
            }
        }

        private static string NormalizeBridgeUrl(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return null;
            }
            string url = value.TrimEnd('/');
            Uri parsed;
            if (!Uri.TryCreate(url, UriKind.Absolute, out parsed) ||
                !string.Equals(parsed.Scheme, "http", StringComparison.OrdinalIgnoreCase) ||
                !string.Equals(parsed.Host, "127.0.0.1", StringComparison.OrdinalIgnoreCase) ||
                parsed.IsDefaultPort)
            {
                return null;
            }
            return parsed.GetLeftPart(UriPartial.Authority);
        }
    }
}
