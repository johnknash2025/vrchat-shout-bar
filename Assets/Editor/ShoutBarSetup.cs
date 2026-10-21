#if UNITY_EDITOR
using System.Linq;
using UdonSharp;
using UdonSharpEditor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using VRC.Udon;
using VRC.Udon.Common;

/// <summary>
/// Batch-mode helpers for the shout bar test world:
///   Unity -batchmode -quit -executeMethod ShoutBarSetup.CompileCheck
///   Unity -batchmode -quit -executeMethod ShoutBarSetup.BuildTestScene
/// Also available from the menu "Shout Bar".
/// </summary>
public static class ShoutBarSetup
{
    const string ScriptDir = "Assets/Scripts";
    const string ScenePath = "Assets/Scenes/ShoutBarTest.unity";
    static readonly string[] Names = { "マルクス！", "ニーチェ！", "フロイト！" };

    [MenuItem("Shout Bar/1. Create U# assets and compile")]
    public static void CompileCheck()
    {
        foreach (string guid in AssetDatabase.FindAssets("t:MonoScript", new[] { ScriptDir }))
        {
            string csPath = AssetDatabase.GUIDToAssetPath(guid);
            string assetPath = csPath.Replace(".cs", ".asset");
            if (AssetDatabase.LoadAssetAtPath<UdonSharpProgramAsset>(assetPath) != null) continue;
            var program = ScriptableObject.CreateInstance<UdonSharpProgramAsset>();
            program.sourceCsScript = AssetDatabase.LoadAssetAtPath<MonoScript>(csPath);
            AssetDatabase.CreateAsset(program, assetPath);
            Debug.Log("[ShoutBar] created " + assetPath);
        }
        AssetDatabase.SaveAssets();
        UdonSharpProgramAsset.CompileAllCsPrograms(true);
        bool error = UdonSharpProgramAsset.AnyUdonSharpScriptHasError();
        Debug.Log(error ? "[ShoutBar] COMPILE: ERRORS (see the U# messages above)" : "[ShoutBar] COMPILE: OK");
        if (Application.isBatchMode && error) EditorApplication.Exit(2);
    }

    static UdonBehaviour AddUdon(GameObject go, string script, string interactText = null)
    {
        var program = AssetDatabase.LoadAssetAtPath<UdonSharpProgramAsset>(ScriptDir + "/" + script + ".asset");
        var ub = go.AddComponent<UdonBehaviour>();
        ub.programSource = program;
        if (interactText != null) ub.interactText = interactText;
        return ub;
    }

    static void Set<T>(UdonBehaviour ub, string name, T value)
    {
        if (!ub.publicVariables.TrySetVariableValue(name, value))
            ub.publicVariables.TryAddVariable(new UdonVariable<T>(name, value));
    }

    [MenuItem("Shout Bar/2. Build test scene")]
    public static void BuildTestScene()
    {
        // run CompileCheck first, in its own Unity run: right after a compile U# refuses to serialize behaviours
        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);

        var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
        floor.name = "Floor";
        floor.transform.localScale = new Vector3(2, 1, 2);

        var worldPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(
            "Packages/com.vrchat.worlds/Samples/UdonExampleScene/Prefabs/VRCWorld.prefab");
        if (worldPrefab != null)
        {
            var world = (GameObject)PrefabUtility.InstantiatePrefab(worldPrefab);
            world.transform.position = new Vector3(0, 0, -3);
        }

        var counter = GameObject.CreatePrimitive(PrimitiveType.Cube);
        counter.name = "Counter";
        counter.transform.position = new Vector3(0, 0.5f, 1.5f);
        counter.transform.localScale = new Vector3(3f, 1f, 0.6f);

        var managerGo = new GameObject("ShoutManager");
        var manager = AddUdon(managerGo, "ShoutManager");
        var sounds = new AudioSource[3];
        var particles = new ParticleSystem[3];
        var popups = new GameObject[3];

        for (int i = 0; i < 3; i++)
        {
            float x = -1f + i;

            var button = GameObject.CreatePrimitive(PrimitiveType.Cube);
            button.name = "ShoutButton_" + i;
            button.transform.position = new Vector3(x, 1.1f, 1.4f);
            button.transform.localScale = new Vector3(0.3f, 0.2f, 0.3f);
            var shout = AddUdon(button, "ShoutButton", Names[i]);
            Set(shout, "manager", manager);
            Set(shout, "index", i);

            var fx = new GameObject("Effect_" + i);
            fx.transform.position = new Vector3(x, 1.6f, 1.4f);
            var audio = fx.AddComponent<AudioSource>();   // put a clip here later
            audio.playOnAwake = false;
            var ps = fx.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.playOnAwake = false;
            main.loop = false;
            main.duration = 1f;
            main.startSpeed = 3f;
            var emission = ps.emission;
            emission.rateOverTime = 0;
            emission.SetBursts(new[] { new ParticleSystem.Burst(0f, 40) });

            var popup = new GameObject("Popup_" + i);
            popup.transform.position = new Vector3(x, 2.3f, 1.4f);
            popup.transform.rotation = Quaternion.Euler(0, 180, 0);
            var label = popup.AddComponent<TextMesh>();
            label.text = Names[i];
            label.anchor = TextAnchor.MiddleCenter;
            label.characterSize = 0.08f;
            label.fontSize = 64;

            sounds[i] = audio;
            particles[i] = ps;
            popups[i] = popup;
        }
        Set(manager, "shoutNames", new[] { "マルクス", "ニーチェ", "フロイト" });
        Set(manager, "sounds", sounds);
        Set(manager, "particles", particles);
        Set(manager, "popups", popups);

        var reset = GameObject.CreatePrimitive(PrimitiveType.Cube);
        reset.name = "ShoutResetButton";
        reset.transform.position = new Vector3(2.2f, 1.1f, 1.4f);
        reset.transform.localScale = new Vector3(0.2f, 0.2f, 0.2f);
        var resetButton = AddUdon(reset, "ShoutResetButton", "リセット");
        Set(resetButton, "manager", manager);

        System.IO.Directory.CreateDirectory("Assets/Scenes");
        EditorSceneManager.SaveScene(scene, ScenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
        AssetDatabase.SaveAssets();
        Debug.Log("[ShoutBar] SCENE: saved " + ScenePath);
    }
}
#endif
