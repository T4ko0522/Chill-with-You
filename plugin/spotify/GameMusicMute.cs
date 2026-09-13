using System.Collections.Generic;
using KanKikuchi.AudioManager;
using UnityEngine;

namespace ChillWithYou.Spotify
{
    internal sealed class GameMusicMute
    {
        private const float SearchIntervalSeconds = 1f;

        private readonly Dictionary<int, MutedAudioSource> _sources =
            new Dictionary<int, MutedAudioSource>();
        private float _nextSearchAt;

        public void Tick(float now)
        {
            if (now >= _nextSearchAt)
            {
                _nextSearchAt = now + SearchIntervalSeconds;
                MusicManager[] managers = Resources.FindObjectsOfTypeAll<MusicManager>();
                MusicManager manager = managers.Length > 0 ? managers[0] : null;
                if (manager != null)
                {
                    AudioSource[] sources = manager.gameObject.GetComponentsInChildren<AudioSource>(true);
                    for (int i = 0; i < sources.Length; ++i)
                    {
                        AudioSource source = sources[i];
                        int id = source.GetInstanceID();
                        if (!_sources.ContainsKey(id))
                        {
                            _sources.Add(id, new MutedAudioSource(source, source.mute));
                        }
                    }
                }
            }

            foreach (MutedAudioSource saved in _sources.Values)
            {
                if (saved.Source != null)
                {
                    saved.Source.mute = true;
                }
            }
        }

        public void Restore()
        {
            foreach (MutedAudioSource saved in _sources.Values)
            {
                if (saved.Source != null)
                {
                    saved.Source.mute = saved.WasMuted;
                }
            }
            _sources.Clear();
            _nextSearchAt = 0f;
        }

        private sealed class MutedAudioSource
        {
            public readonly AudioSource Source;
            public readonly bool WasMuted;

            public MutedAudioSource(AudioSource source, bool wasMuted)
            {
                Source = source;
                WasMuted = wasMuted;
            }
        }
    }
}
