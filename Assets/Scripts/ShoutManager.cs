using UdonSharp;
using UnityEngine;
using VRC.SDKBase;
using VRC.SDK3.UdonNetworkCalling;
using VRC.Udon.Common.Interfaces;
using TMPro;

/// <summary>
/// 叫びバーの中枢。ボタンからの叫びを全員に同期し、累計カウントを管理する。
/// 要件: VRChat Worlds SDK 3.8.1 以降（パラメータ付きネットワークイベントを使用）
/// </summary>
[UdonBehaviourSyncMode(BehaviourSyncMode.Manual)]
public class ShoutManager : UdonSharpBehaviour
{
    private const int MaxShouts = 8;

    [Header("叫びの名前（ボタンの index 順、最大8個）")]
    public string[] shoutNames = { "マルクス", "ニーチェ", "フロイト" };

    [Header("演出（index 順に対応。未設定の要素は無視）")]
    public AudioSource[] sounds;
    public ParticleSystem[] particles;
    public GameObject[] popups;
    public float popupSeconds = 2f;

    [Header("連打防止（秒）")]
    public float cooldownSeconds = 0.5f;

    [Header("スコアボード")]
    public TextMeshProUGUI scoreText;

    [Header("リセット権限")]
    public bool onlyMasterCanReset = true;

    [UdonSynced] private int[] counts = new int[MaxShouts];

    private float lastShoutTime = -10f;
    private float[] popupHideAt = new float[MaxShouts];

    private void Start()
    {
        for (int i = 0; i < MaxShouts; i++) popupHideAt[i] = -1f;
        if (popups != null)
        {
            foreach (GameObject p in popups) if (p != null) p.SetActive(false);
        }
        UpdateScore();
    }

    // ---- ボタンから呼ばれる（ローカル） ----
    public void LocalShout(int index)
    {
        if (!IsValid(index)) return;
        if (Time.time - lastShoutTime < cooldownSeconds) return;
        lastShoutTime = Time.time;

        // カウントはオーナーが一元管理、演出は全員で再生
        SendCustomNetworkEvent(NetworkEventTarget.Owner, nameof(RequestCount), index);
        SendCustomNetworkEvent(NetworkEventTarget.All, nameof(PlayShout), index);
    }

    [NetworkCallable]
    public void RequestCount(int index)
    {
        if (!Networking.IsOwner(gameObject)) return;
        if (!IsValid(index)) return;
        counts[index]++;
        RequestSerialization();
        UpdateScore();
    }

    [NetworkCallable]
    public void PlayShout(int index)
    {
        if (!IsValid(index)) return;

        if (sounds != null && index < sounds.Length && sounds[index] != null)
        {
            sounds[index].Stop();
            sounds[index].Play();
        }
        if (particles != null && index < particles.Length && particles[index] != null)
        {
            particles[index].Play();
        }
        if (popups != null && index < popups.Length && popups[index] != null)
        {
            popups[index].SetActive(false); // アニメーションを頭から再生させる
            popups[index].SetActive(true);
            popupHideAt[index] = Time.time + popupSeconds;
        }
    }

    // ---- リセット（スタッフ用） ----
    public void LocalReset()
    {
        VRCPlayerApi local = Networking.LocalPlayer;
        if (local == null) return;
        if (onlyMasterCanReset && !local.isMaster) return;

        Networking.SetOwner(local, gameObject);
        for (int i = 0; i < MaxShouts; i++) counts[i] = 0;
        RequestSerialization();
        UpdateScore();
    }

    public override void OnDeserialization()
    {
        UpdateScore();
    }

    private void Update()
    {
        if (popups == null) return;
        for (int i = 0; i < popups.Length && i < MaxShouts; i++)
        {
            if (popupHideAt[i] > 0f && Time.time >= popupHideAt[i])
            {
                popupHideAt[i] = -1f;
                if (popups[i] != null) popups[i].SetActive(false);
            }
        }
    }

    private bool IsValid(int index)
    {
        return index >= 0 && index < shoutNames.Length && index < MaxShouts;
    }

    private void UpdateScore()
    {
        if (scoreText == null) return;

        int total = 0;
        int n = Mathf.Min(shoutNames.Length, MaxShouts);
        for (int i = 0; i < n; i++) total += counts[i];

        string s = "<b>本日の叫び</b>  計 " + total + "\n";
        for (int i = 0; i < n; i++)
        {
            int pct = total > 0 ? Mathf.RoundToInt(counts[i] * 100f / total) : 0;
            s += shoutNames[i] + "  " + counts[i] + "  (" + pct + "%)\n";
        }
        scoreText.text = s;
    }
}
