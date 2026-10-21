# 叫びバー：ボタン同期ギミック

## 前提
- Unity（VRChat Creator Companion で作ったワールドプロジェクト）
- VRChat Worlds SDK 3.8.1 以降（パラメータ付きネットワークイベントを使用）
- TextMeshPro 用の日本語フォントアセット（Noto Sans JP などから作成）

## 組み立て手順
1. `.cs` 3つを `Assets/Scripts/` に置き、それぞれ右クリック → Create → U# Script で UdonSharp アセットを作る
2. 空の GameObject `ShoutManager` を作り、Udon Behaviour に `ShoutManager` を割り当てる
3. カウンターにボタン用の Cube を3つ置く（Collider 必須）
   - それぞれに `ShoutButton` をアタッチ
   - `manager` に ShoutManager、`index` に 0 / 1 / 2
   - Interaction Text に「マルクス！」「ニーチェ！」「フロイト！」
4. 演出を用意して ShoutManager の配列に index 順で入れる
   - `sounds`：AudioSource（Play On Awake はオフ）
   - `particles`：ParticleSystem（Play On Awake はオフ）
   - `popups`：肖像やロゴ付きの World Space Canvas など。出現アニメを付けておくと映える
5. World Space Canvas に TextMeshPro を置き、`scoreText` に割り当てる
6. バックヤードに Cube を置いて `ShoutResetButton` をアタッチ（話の区切りでリセット）

## テスト
- ビルド＆テストでクライアントを2つ起動し、片方で押してもう片方に演出が出るか確認
- 後から入った人にもカウントが正しく見えるか確認

## 動作の仕組み
- 押した人 → オーナーにカウント加算を依頼、全員に演出再生を通知
- カウントは同期変数なので、途中参加者にも累計が見える
- 0.5秒の連打防止つき（`cooldownSeconds` で調整）
- 名前を増やすときは `shoutNames` に追加し、ボタンと演出を増やすだけ（最大8つ）

## 注意
- 肖像はパブリックドメインの写真や自作イラストを使う
