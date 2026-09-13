namespace ChillWithYou.Spotify
{
    internal sealed class ControlCommandState
    {
        private long _nextCommandId;
        private long _activeCommandId;
        private long _observationGeneration;
        private bool _awaitingRemoteState;

        public bool ControlsBlocked { get { return _activeCommandId != 0 || _awaitingRemoteState; } }

        public bool TryBegin(out long commandId)
        {
            commandId = 0;
            if (ControlsBlocked)
            {
                return false;
            }
            commandId = ++_nextCommandId;
            _activeCommandId = commandId;
            ++_observationGeneration;
            return true;
        }

        public bool Complete(long commandId, bool success)
        {
            if (_activeCommandId == 0 || commandId != _activeCommandId)
            {
                return false;
            }
            _activeCommandId = 0;
            ++_observationGeneration;
            _awaitingRemoteState = success;
            return true;
        }

        public long CaptureObservation()
        {
            return _observationGeneration;
        }

        public void ApplyRemoteState(long observationGeneration)
        {
            if (_awaitingRemoteState && observationGeneration == _observationGeneration)
            {
                _awaitingRemoteState = false;
            }
        }

        public void Invalidate()
        {
            _activeCommandId = 0;
            _awaitingRemoteState = false;
            ++_observationGeneration;
        }
    }
}
