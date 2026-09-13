namespace ChillWithYou.Spotify
{
    internal sealed class ArtworkRotationState
    {
        private int _lastFrame = -1;

        public float NextDelta(
            bool connected,
            bool playing,
            int frame,
            float unscaledDeltaTime,
            float degreesPerSecond)
        {
            if (!connected || !playing || frame == _lastFrame)
            {
                return 0f;
            }
            _lastFrame = frame;
            return unscaledDeltaTime * degreesPerSecond;
        }

        public void Reset()
        {
            _lastFrame = -1;
        }
    }
}
