using System;
using System.Collections.Generic;
using System.Reflection;

namespace UnityEngine
{
    public enum HideFlags
    {
        None,
        HideAndDontSave
    }

    public class Object
    {
        public static Object LastPersistentObject;

        public static void DontDestroyOnLoad(Object target)
        {
            LastPersistentObject = target;
        }
    }

    public sealed class GameObject : Object
    {
        public HideFlags hideFlags;
    }
}

namespace BepInEx.Logging
{
    public sealed class ManualLogSource
    {
        public readonly List<string> InfoMessages = new List<string>();
        public readonly List<string> ErrorMessages = new List<string>();

        public void LogInfo(object message) { InfoMessages.Add(message.ToString()); }
        public void LogError(object message) { ErrorMessages.Add(message.ToString()); }
    }
}

namespace BepInEx
{
    using BepInEx.Logging;
    using UnityEngine;

    [AttributeUsage(AttributeTargets.Class)]
    public sealed class BepInPlugin : Attribute
    {
        public BepInPlugin(string guid, string name, string version) { }
    }

    public class BaseUnityPlugin
    {
        public readonly GameObject gameObject = new GameObject();
        public readonly ManualLogSource Logger = new ManualLogSource();
    }
}

namespace Bulbul
{
    public class CostumeChangeService
    {
        public enum CostumeSkinType
        {
            Default_1 = 1,
            Polo_1 = 1001,
            Polo_2 = 1002,
            Tee_1 = 2001,
            Tee_2 = 2002
        }

        private bool TryChangeCostume(CostumeSkinType skinType) { return true; }
    }
}

namespace HarmonyLib
{
    public sealed class HarmonyMethod
    {
        public readonly MethodInfo method;

        public HarmonyMethod(Type type, string name)
        {
            method = type.GetMethod(name, BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
        }
    }

    public static class AccessTools
    {
        public static MethodInfo DeclaredMethod(
            Type type,
            string name,
            Type[] parameters,
            Type[] generics)
        {
            return type.GetMethod(
                name,
                BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic,
                null,
                parameters,
                null);
        }
    }

    public sealed class Harmony
    {
        public static MethodBase LastOriginal;
        public static HarmonyMethod LastPrefix;
        public static bool Unpatched;

        public Harmony(string id) { }

        public MethodInfo Patch(
            MethodBase original,
            HarmonyMethod prefix,
            HarmonyMethod postfix,
            HarmonyMethod transpiler,
            HarmonyMethod finalizer,
            HarmonyMethod ilmanipulator)
        {
            LastOriginal = original;
            LastPrefix = prefix;
            return prefix.method;
        }

        public void UnpatchSelf() { Unpatched = true; }
    }
}

internal static class DefaultOutfitProbe
{
    private static int Main()
    {
        var plugin = new ChillWithYou.DefaultOutfit.DefaultOutfitPlugin();
        Invoke(plugin, "Awake");

        if (plugin.gameObject.hideFlags != UnityEngine.HideFlags.HideAndDontSave) return 1;
        if (UnityEngine.Object.LastPersistentObject != plugin.gameObject) return 2;
        if (HarmonyLib.Harmony.LastOriginal == null ||
            HarmonyLib.Harmony.LastOriginal.Name != "TryChangeCostume") return 3;
        if (HarmonyLib.Harmony.LastPrefix == null ||
            HarmonyLib.Harmony.LastPrefix.method == null) return 4;

        Bulbul.CostumeChangeService.CostumeSkinType[] requestedSkins = {
            Bulbul.CostumeChangeService.CostumeSkinType.Polo_1,
            Bulbul.CostumeChangeService.CostumeSkinType.Polo_2,
            Bulbul.CostumeChangeService.CostumeSkinType.Tee_1,
            Bulbul.CostumeChangeService.CostumeSkinType.Tee_2
        };
        foreach (Bulbul.CostumeChangeService.CostumeSkinType requested in requestedSkins)
        {
            object[] arguments = { requested };
            HarmonyLib.Harmony.LastPrefix.method.Invoke(null, arguments);
            if ((Bulbul.CostumeChangeService.CostumeSkinType)arguments[0] !=
                Bulbul.CostumeChangeService.CostumeSkinType.Default_1) return 5;
            if (requested == Bulbul.CostumeChangeService.CostumeSkinType.Default_1) return 6;
        }

        if (plugin.Logger.InfoMessages.Count != 1 ||
            !plugin.Logger.InfoMessages[0].Contains("TryChangeCostume")) return 7;

        Invoke(plugin, "OnDestroy");
        if (!HarmonyLib.Harmony.Unpatched) return 8;
        return 0;
    }

    private static void Invoke(object target, string name)
    {
        target.GetType().GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic).Invoke(target, null);
    }
}
