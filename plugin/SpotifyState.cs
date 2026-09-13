using System;

namespace ChillWithYou.Spotify
{
    [Serializable]
#pragma warning disable 0649 // JsonUtility populates these fields through reflection.
    internal sealed class SpotifyState
    {
        public bool connected;
        public bool playing;
        public string title;
        public string artist;
        public string album;
        public string artUrl;
        public string trackId;
        public double lengthUs;
        public double positionUs;
        public bool canPlay;
        public bool canPause;
        public bool canGoNext;
        public bool canGoPrevious;
        public bool canSeek;
        public float volume;
        public bool canSetVolume;
        public int revision;
    }
#pragma warning restore 0649
}
