using ChillWithYou.Spotify;

internal static class ArtworkRotationStateProbe
{
    private static int Main()
    {
        var rotation = new ArtworkRotationState();
        float angle = 0f;

        angle += rotation.NextDelta(true, true, 10, 0.5f, 20f);
        angle += rotation.NextDelta(true, true, 10, 0.5f, 20f);
        if (angle != 10f) return 1;

        angle += rotation.NextDelta(true, false, 11, 0.5f, 20f);
        angle += rotation.NextDelta(false, true, 12, 0.5f, 20f);
        if (angle != 10f) return 2;

        angle += rotation.NextDelta(true, true, 13, 0.25f, 20f);
        if (angle != 15f) return 3;

        rotation.Reset();
        angle += rotation.NextDelta(true, true, 13, 0.25f, 20f);
        return angle == 20f ? 0 : 4;
    }
}
