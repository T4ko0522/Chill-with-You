using System.Collections.Generic;
using System.Reflection;
using Bulbul;
using HarmonyLib;

namespace ChillWithYou.Spotify
{
    [HarmonyPatch(typeof(FacilityMusic), "UpdateFacility")]
    internal static class FacilityMusicUpdatePatch
    {
        private static void Postfix()
        {
            SpotifyMusicPlugin.RenderAfterFacilityUpdate();
        }
    }

    [HarmonyPatch(typeof(FacilityMusic), "Setup")]
    internal static class FacilityMusicSetupPatch
    {
        private static void Postfix(FacilityMusic __instance)
        {
            SpotifyMusicPlugin.MarkFacilityReady(__instance);
        }
    }

    [HarmonyPatch]
    internal static class FacilityMusicActionPatch
    {
        private static IEnumerable<MethodBase> TargetMethods()
        {
            yield return AccessTools.Method(typeof(FacilityMusic), "OnClickButtonPlayOrPauseMusic");
            yield return AccessTools.Method(typeof(FacilityMusic), "OnClickButtonSkip");
            yield return AccessTools.Method(typeof(FacilityMusic), "OnClickButtonBack");
            yield return AccessTools.Method(typeof(FacilityMusic), "OnClickButtonChangeLoop");
            yield return AccessTools.Method(typeof(FacilityMusic), "OnClickButtonShuffleChange");
            yield return AccessTools.Method(typeof(FacilityMusic), "OnClickButtonPlayListPlayMusicButton");
        }

        private static bool Prefix(FacilityMusic __instance)
        {
            return !SpotifyMusicPlugin.ShouldSuppressFacilityAction(__instance);
        }
    }

    [HarmonyPatch(typeof(MusicUI), "LateUpdate")]
    internal static class MusicUiLateUpdatePatch
    {
        private static void Postfix(MusicUI __instance)
        {
            SpotifyMusicPlugin.RenderAfterGameUiUpdate(__instance);
        }
    }
}
