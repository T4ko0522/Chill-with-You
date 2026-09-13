using System;
using System.Collections.Generic;

namespace ChillWithYou.Spotify
{
    internal static class SpotifyModeTransition
    {
        public static bool TryEnter<T>(
            IList<T> bindings,
            Action<T> enter,
            Action<T> exit,
            out Exception error)
        {
            error = null;
            if (bindings == null || bindings.Count == 0)
            {
                return false;
            }

            int enteredCount = 0;
            try
            {
                for (; enteredCount < bindings.Count; ++enteredCount)
                {
                    enter(bindings[enteredCount]);
                }
                return true;
            }
            catch (Exception exception)
            {
                error = exception;
                // The failing binding may have mutated UI before throwing, so include it.
                int rollbackFrom = Math.Min(enteredCount, bindings.Count - 1);
                for (int i = rollbackFrom; i >= 0; --i)
                {
                    try
                    {
                        exit(bindings[i]);
                    }
                    catch
                    {
                        // The caller keeps Spotify mode inactive, so game patches remain fail-open.
                    }
                }
                return false;
            }
        }
    }
}
