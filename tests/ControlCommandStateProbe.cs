using ChillWithYou.Spotify;

internal static class ControlCommandStateProbe
{
    private static int Main()
    {
        var state = new ControlCommandState();
        long beforeCommand = state.CaptureObservation();
        long first;
        if (!state.TryBegin(out first) || !state.ControlsBlocked) return 1;

        long duplicate;
        if (state.TryBegin(out duplicate)) return 2;
        if (!state.Complete(first, true) || !state.ControlsBlocked) return 3;
        state.ApplyRemoteState(beforeCommand);
        if (!state.ControlsBlocked) return 4;
        state.ApplyRemoteState(state.CaptureObservation());
        if (state.ControlsBlocked) return 5;

        long stale;
        if (!state.TryBegin(out stale)) return 6;
        state.Invalidate();
        long current;
        if (!state.TryBegin(out current) || current == stale) return 7;
        if (state.Complete(stale, false) || !state.ControlsBlocked) return 8;
        if (!state.Complete(current, false) || state.ControlsBlocked) return 9;
        return 0;
    }
}
