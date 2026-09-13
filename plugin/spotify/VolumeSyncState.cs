using System;

namespace ChillWithYou.Spotify
{
    internal sealed class VolumeSyncState
    {
        private const float MatchTolerance = 0.005f;
        private const int ExpectedRemoteMismatchLimit = 4;

        private bool _commandInFlight;
        private long _nextCommandId;
        private long _activeCommandId;
        private bool _hasPendingCommand;
        private float _pendingCommand;
        private bool _hasExpectedRemote;
        private float _expectedRemote;
        private int _expectedRemoteMismatches;

        public bool CanSetVolume { get; private set; }
        public float DisplayVolume { get; private set; }
        public bool HasCommandInFlight { get { return _commandInFlight; } }

        public void ApplyRemote(bool connected, bool canSetVolume, float volume)
        {
            float normalized = Clamp(volume);
            if (!connected || !canSetVolume)
            {
                CanSetVolume = false;
                DisplayVolume = normalized;
                ClearCommands();
                return;
            }

            CanSetVolume = true;
            if (_hasExpectedRemote)
            {
                if (Math.Abs(normalized - _expectedRemote) <= MatchTolerance)
                {
                    _hasExpectedRemote = false;
                    _expectedRemoteMismatches = 0;
                    DisplayVolume = normalized;
                }
                else if (!_commandInFlight && ++_expectedRemoteMismatches >= ExpectedRemoteMismatchLimit)
                {
                    _hasExpectedRemote = false;
                    _expectedRemoteMismatches = 0;
                    DisplayVolume = normalized;
                }
                return;
            }
            DisplayVolume = normalized;
        }

        public bool TrySetLocal(float volume, out long commandId, out float command)
        {
            commandId = 0;
            command = 0f;
            if (!CanSetVolume)
            {
                return false;
            }

            float normalized = Clamp(volume);
            DisplayVolume = normalized;
            _hasExpectedRemote = true;
            _expectedRemote = normalized;
            _expectedRemoteMismatches = 0;
            if (_commandInFlight)
            {
                _hasPendingCommand = true;
                _pendingCommand = normalized;
                return false;
            }

            _commandInFlight = true;
            commandId = ++_nextCommandId;
            _activeCommandId = commandId;
            command = normalized;
            return true;
        }

        public bool CompleteCommand(
            long commandId,
            bool success,
            out bool hasNext,
            out long nextCommandId,
            out float next)
        {
            hasNext = false;
            nextCommandId = 0;
            next = 0f;
            if (!_commandInFlight || commandId != _activeCommandId)
            {
                return false;
            }
            _commandInFlight = false;
            _activeCommandId = 0;
            if (!success)
            {
                _hasPendingCommand = false;
                _hasExpectedRemote = false;
                return true;
            }
            if (!_hasPendingCommand)
            {
                return true;
            }

            _hasPendingCommand = false;
            _commandInFlight = true;
            nextCommandId = ++_nextCommandId;
            _activeCommandId = nextCommandId;
            hasNext = true;
            next = _pendingCommand;
            return true;
        }

        public void Reset()
        {
            CanSetVolume = false;
            DisplayVolume = 0f;
            ClearCommands();
        }

        private void ClearCommands()
        {
            _commandInFlight = false;
            _hasPendingCommand = false;
            _activeCommandId = 0;
            _hasExpectedRemote = false;
            _expectedRemoteMismatches = 0;
        }

        private static float Clamp(float value)
        {
            if (float.IsNaN(value) || value <= 0f) return 0f;
            if (value >= 1f) return 1f;
            return value;
        }
    }
}
