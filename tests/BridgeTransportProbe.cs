using System;
using ChillWithYou.Spotify;

internal static class BridgeTransportProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 2) return 10;

        string bridgeUrl = args[0];
        string token = args[1];

        using (BridgeRequest state = new BridgeRequest(bridgeUrl + "/state", token))
        {
            BridgeRequest.Response response = state.Result;
            if (!response.Success || response.Text != "{\"connected\":true}") return 11;
        }

        using (BridgeRequest command = new BridgeRequest(
            bridgeUrl + "/command", token, "{\"command\":\"play\"}"))
        {
            BridgeRequest.Response response = command.Result;
            if (!response.Success || response.Text != "") return 12;
        }

        using (BridgeRequest failure = new BridgeRequest(
            bridgeUrl + "/state?error=1", token))
        {
            BridgeRequest.Response response = failure.Result;
            if (response.Success || String.IsNullOrEmpty(response.Error)) return 13;
        }

        return 0;
    }
}
