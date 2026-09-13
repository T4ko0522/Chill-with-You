using System;
using ChillWithYou.Spotify;

internal static class VolumeSyncStateProbe
{
    private static int Main()
    {
        var sync = new VolumeSyncState();
        sync.ApplyRemote(true, true, 0.25f);
        if (!sync.CanSetVolume || !Close(sync.DisplayVolume, 0.25f)) return 1;

        float command;
        long commandId;
        if (!sync.TrySetLocal(0.6f, out commandId, out command) || !Close(command, 0.6f)) return 2;
        if (!sync.HasCommandInFlight || !Close(sync.DisplayVolume, 0.6f)) return 3;

        // A poll started before the local command must not move the slider backwards.
        sync.ApplyRemote(true, true, 0.25f);
        if (!Close(sync.DisplayVolume, 0.6f)) return 4;

        // While the first command is running, only the latest local value is retained.
        long ignoredCommandId;
        if (sync.TrySetLocal(0.7f, out ignoredCommandId, out command)) return 5;
        if (sync.TrySetLocal(0.8f, out ignoredCommandId, out command)) return 6;
        if (!Close(sync.DisplayVolume, 0.8f)) return 7;

        bool hasNext;
        long nextCommandId;
        float next;
        sync.CompleteCommand(commandId, true, out hasNext, out nextCommandId, out next);
        if (!hasNext || !Close(next, 0.8f) || !sync.HasCommandInFlight) return 8;
        sync.CompleteCommand(nextCommandId, true, out hasNext, out ignoredCommandId, out next);
        if (hasNext || sync.HasCommandInFlight) return 9;

        sync.ApplyRemote(true, true, 0.25f);
        if (!Close(sync.DisplayVolume, 0.8f)) return 10;
        sync.ApplyRemote(true, true, 0.8f);
        if (!Close(sync.DisplayVolume, 0.8f)) return 11;

        // Unsupported and disconnected states immediately revoke control and pending intent.
        sync.ApplyRemote(true, false, 0.4f);
        if (sync.CanSetVolume || sync.TrySetLocal(0.5f, out commandId, out command)) return 12;
        if (!Close(sync.DisplayVolume, 0.4f)) return 13;
        sync.ApplyRemote(false, false, 0f);
        if (sync.CanSetVolume || sync.HasCommandInFlight) return 14;

        // Clamp malformed/out-of-range values at the plugin contract boundary.
        sync.ApplyRemote(true, true, 2f);
        if (!Close(sync.DisplayVolume, 1f)) return 15;
        if (!sync.TrySetLocal(-1f, out commandId, out command) || !Close(command, 0f)) return 16;

        sync.CompleteCommand(commandId, false, out hasNext, out nextCommandId, out next);
        if (hasNext || sync.HasCommandInFlight) return 17;

        var unacknowledged = new VolumeSyncState();
        unacknowledged.ApplyRemote(true, true, 0.2f);
        if (!unacknowledged.TrySetLocal(0.9f, out commandId, out command)) return 18;
        unacknowledged.CompleteCommand(commandId, true, out hasNext, out nextCommandId, out next);
        for (int i = 0; i < 3; ++i) unacknowledged.ApplyRemote(true, true, 0.2f);
        if (!Close(unacknowledged.DisplayVolume, 0.9f)) return 19;
        unacknowledged.ApplyRemote(true, true, 0.2f);
        if (!Close(unacknowledged.DisplayVolume, 0.2f)) return 20;

        var reconnected = new VolumeSyncState();
        reconnected.ApplyRemote(true, true, 0.1f);
        if (!reconnected.TrySetLocal(0.3f, out commandId, out command)) return 21;
        reconnected.ApplyRemote(false, false, 0f);
        reconnected.ApplyRemote(true, true, 0.4f);
        long newCommandId;
        if (!reconnected.TrySetLocal(0.5f, out newCommandId, out command)) return 22;
        if (reconnected.CompleteCommand(
            commandId, false, out hasNext, out nextCommandId, out next)) return 23;
        if (!reconnected.HasCommandInFlight) return 24;
        reconnected.CompleteCommand(newCommandId, true, out hasNext, out nextCommandId, out next);
        if (reconnected.HasCommandInFlight) return 25;
        return 0;
    }

    private static bool Close(float left, float right)
    {
        return Math.Abs(left - right) < 0.0001f;
    }
}
