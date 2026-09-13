using System;
using System.Collections.Generic;
using ChillWithYou.Spotify;

internal static class SpotifyModeTransitionProbe
{
    private static int Main()
    {
        Exception error;
        var entered = new List<string>();
        var exited = new List<string>();

        bool emptyActivated = SpotifyModeTransition.TryEnter(
            new List<string>(),
            item => entered.Add(item),
            item => exited.Add(item),
            out error);
        if (emptyActivated || error != null) return 1;

        bool failedActivated = SpotifyModeTransition.TryEnter(
            new List<string> { "first", "second" },
            item => {
                entered.Add(item);
                if (item == "second") throw new InvalidOperationException("failed binding");
            },
            item => exited.Add(item),
            out error);
        if (failedActivated || error == null) return 2;
        if (exited.Count != 2 || exited[0] != "second" || exited[1] != "first") return 3;

        entered.Clear();
        exited.Clear();
        bool activated = SpotifyModeTransition.TryEnter(
            new List<string> { "only" },
            item => entered.Add(item),
            item => exited.Add(item),
            out error);
        if (!activated || error != null || entered.Count != 1 || exited.Count != 0) return 4;

        return 0;
    }
}
