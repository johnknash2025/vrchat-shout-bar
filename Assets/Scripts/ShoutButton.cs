using UdonSharp;
using UnityEngine;

/// <summary>
/// カウンターに置く叫びボタン。Collider 付きオブジェクトにアタッチする。
/// Inspector の Interaction Text に「マルクス！」などを入れると手元に表示される。
/// </summary>
[UdonBehaviourSyncMode(BehaviourSyncMode.None)]
public class ShoutButton : UdonSharpBehaviour
{
    public ShoutManager manager;
    [Tooltip("ShoutManager の shoutNames の何番目か（0=マルクス, 1=ニーチェ, 2=フロイト）")]
    public int index;

    public override void Interact()
    {
        if (manager != null) manager.LocalShout(index);
    }
}
