using UdonSharp;
using UnityEngine;

/// <summary>
/// カウントをゼロに戻すスタッフ用ボタン（話数の切り替え時などに）。
/// 既定ではインスタンスのマスターだけが押せる。
/// </summary>
[UdonBehaviourSyncMode(BehaviourSyncMode.None)]
public class ShoutResetButton : UdonSharpBehaviour
{
    public ShoutManager manager;

    public override void Interact()
    {
        if (manager != null) manager.LocalReset();
    }
}
