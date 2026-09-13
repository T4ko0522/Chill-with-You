using System;
using System.Reflection;
using BepInEx;
using Bulbul;
using HarmonyLib;
using UnityEngine;

namespace ChillWithYou.DefaultOutfit
{
    [BepInPlugin(PluginGuid, PluginName, PluginVersion)]
    public sealed class DefaultOutfitPlugin : BaseUnityPlugin
    {
        public const string PluginGuid = "io.github.t4ko0522.chillwithyou.defaultoutfit";
        public const string PluginName = "Chill with You Default Outfit";
        public const string PluginVersion = "0.1.0";

        private Harmony _harmony;

        private void Awake()
        {
            gameObject.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(gameObject);

            MethodInfo target = AccessTools.DeclaredMethod(
                typeof(CostumeChangeService),
                "TryChangeCostume",
                new[] { typeof(CostumeChangeService.CostumeSkinType) },
                null);
            if (target == null)
            {
                Logger.LogError("Could not find CostumeChangeService.TryChangeCostume; default outfit was not enabled.");
                return;
            }

            try
            {
                _harmony = new Harmony(PluginGuid);
                _harmony.Patch(
                    target,
                    new HarmonyMethod(typeof(DefaultOutfitPatch), nameof(DefaultOutfitPatch.Prefix)),
                    null,
                    null,
                    null,
                    null);
                Logger.LogInfo(
                    "Patched CostumeChangeService.TryChangeCostume; displayed outfit is forced to Default_1.");
            }
            catch (Exception exception)
            {
                if (_harmony != null) _harmony.UnpatchSelf();
                _harmony = null;
                Logger.LogError("Failed to patch CostumeChangeService.TryChangeCostume: " + exception);
            }
        }

        private void OnDestroy()
        {
            if (_harmony != null) _harmony.UnpatchSelf();
        }
    }

    internal static class DefaultOutfitPatch
    {
        internal static void Prefix(ref CostumeChangeService.CostumeSkinType skinType)
        {
            skinType = CostumeChangeService.CostumeSkinType.Default_1;
        }
    }
}
