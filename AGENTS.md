# AI エージェント向けセットアップ手順

このファイルは、利用者の代わりに AI エージェント（Claude Code、Codex、Cursor など）がこのギミックを組み込むための手順です。人が読む説明は [README.md](README.md) にあります。

利用者には「`AGENTS.md` を読んで、叫びバーのテスト用ワールドを作って」と頼んでもらう想定です。

## 前提と、人にしかできないこと

エージェントは次の作業を**自分でしてはいけません**。利用者に頼み、終わるのを待ってください。

| 人がやること | 理由 |
|---|---|
| Unity アカウントでのログインと、Personal ライセンスの有効化（Unity Hub の Preferences → Licenses） | アカウントの操作。ライセンスがないと、バッチモードは `No valid Unity Editor license found` で止まる |
| VRChat アカウントでのログイン、ワールドのアップロード | アカウントの操作で、公開の操作でもある |
| アプリ（Unity Hub、Unity、VCC / ALCOM）のダウンロードとインストールの承認 | 利用者の PC に入れるものなので、入れる前に名前・入手先・サイズを伝えて許可をもらう |

## 固定の条件

- **Unity は 2022.3.22f1 だけ**を使う。VRChat はこれより新しい Unity（Unity 6 を含む）で作ったものを受け付けない。changeset は `887be4894c44`。
- **VRChat Worlds SDK 3.8.1 以降**（`com.vrchat.worlds`）。UdonSharp と ClientSim は SDK に含まれている。2026-10 時点の確認版は 3.10.5。

## 手順

### 1. ツールを入れる（OS ごと）

| OS | Unity | プロジェクト管理（VRChat SDK を入れる道具） |
|---|---|---|
| Windows | Unity Hub から 2022.3.22f1（Windows Build Support は標準） | 公式の VRChat Creator Companion（VCC）。CLI で済ませるなら `vrc-get` |
| macOS（Apple シリコン / Intel） | Unity Hub から 2022.3.22f1。**Apple シリコンでも Intel 版（x86_64、Rosetta で動く）を入れる**（下の「つまずきやすい点」）。iPad などで試すなら iOS Build Support、PC 向けにアップロードするなら Windows Build Support (Mono) | VCC は Windows 専用。代わりに `vrc-get`（CLI）か ALCOM（GUI）。どちらも `vrc-get/vrc-get` の GitHub リリース |
| Linux | Unity Hub（AppImage / deb）から 2022.3.22f1 | `vrc-get` |

Unity Hub の CLI で入れる例（macOS、Intel 版、iOS 付き。Apple シリコンでもこちら）：

```sh
"/Applications/Unity Hub.app/Contents/MacOS/Unity Hub" -- --headless install \
  --version 2022.3.22f1 --changeset 887be4894c44 --architecture x86_64 --module ios
```

Apple シリコンの Mac では `/Applications/Unity/Hub/Editor/2022.3.22f1-x86_64/` に入る。

Windows では `"C:\Program Files\Unity Hub\Unity Hub.exe" -- --headless install ...`、Linux では `unityhub -- --headless install ...` に読み替える（`--architecture` は Apple シリコン以外では不要）。

### 2. ワールドのプロジェクトを作る

VCC か ALCOM があれば、Worlds テンプレートで作るのが一番簡単です。CLI だけで作る場合：

```sh
UNITY=<Unity 2022.3.22f1 の実行ファイル>   # macOS: /Applications/Unity/Hub/Editor/2022.3.22f1-x86_64/Unity.app/Contents/MacOS/Unity
PROJECT=<作る場所>/shout-bar-world

"$UNITY" -batchmode -quit -nographics -createProject "$PROJECT"
cd "$PROJECT"
vrc-get update
vrc-get install -y com.vrchat.worlds
```

### 3. このリポジトリのファイルを入れる

```sh
cp <このリポジトリ>/Assets/Scripts/*.cs  "$PROJECT/Assets/Scripts/"
cp <このリポジトリ>/Assets/Editor/ShoutBarSetup.cs "$PROJECT/Assets/Editor/"
```

### 4. コンパイルとテスト用シーンの組み立て（必ず 2 回に分けて実行）

```sh
"$UNITY" -batchmode -quit -nographics -projectPath "$PROJECT" -executeMethod ShoutBarSetup.CompileCheck -logFile compile.log
grep "\[ShoutBar\]" compile.log      # "[ShoutBar] COMPILE: OK" を確認

"$UNITY" -batchmode -quit -nographics -projectPath "$PROJECT" -executeMethod ShoutBarSetup.BuildTestScene -logFile scene.log
grep "\[ShoutBar\]" scene.log        # "[ShoutBar] SCENE: saved Assets/Scenes/ShoutBarTest.unity" を確認
```

- `CompileCheck` は、3 つのスクリプトの UdonSharp アセット（`.asset`）を作ってコンパイルする。エラーがあれば終了コード 2。
- `BuildTestScene` は、床・VRCWorld（スポーン地点）・カウンター・ボタン 3 つ・パーティクルとポップアップの演出・リセットボタンを置いたシーンを保存する。
- ログの `mprotect returned ...` と、シーン保存時の `SceneTemplateAsset.CreatePipeline` の `ArgumentNullException` は Unity 自身のもので、無視してよい。

### 5. 動作確認（ClientSim）

Unity でプロジェクトとシーンを開き、再生ボタン（▶）を押す。WASD で移動し、ボタンにマウスを向けて左クリックすると、粒が飛び、名前が 2 秒浮かぶ。macOS では次で開ける：

```sh
"$UNITY" -projectPath "$PROJECT" &
# 開いたら Project の Assets/Scenes/ShoutBarTest をダブルクリックして、▶ を押す
```

ClientSim は 1 人分の確認だけ。複数人の同期は、Windows の VRChat の「Build & Test」でクライアントを 2 つ起動するか、非公開でアップロードして 2 台の端末で確かめる（アップロードは人が行う）。

## つまずきやすい点（実際に起きたこと）

- **Apple シリコンの Mac では、エディタの画面が出ない**：Apple シリコン版（arm64）の Unity で開くと、SDK の UdonSharp が Harmony で関数を書き換えようとして `mprotect returned EACCES` が毎フレーム出続け、エディタの窓がまともに表示されない。**Intel 版（x86_64）を Rosetta で動かす**と解消する（窓のタイトルに `<Rosetta>` と出る）。バッチモードのコンパイルとシーン組み立ては arm64 版でも通る。
- **窓が別の画面に開く**：外部モニターと内蔵画面がある Mac では、Unity の窓が内蔵画面に開いて見つからないことがある。利用者には両方の画面を見てもらう。Unity Hub だけが前に出ることもあるが、エディタは別に起動している。

- **UdonSharp の proxy API はバッチモードで失敗する**：`AddUdonSharpComponent` や `CopyProxyToUdon` は、`-executeMethod` の直後だと `Cannot run serialization on U# behaviour ... with outdated script version` で落ちる（U# の再コンパイルがエディタの更新ループ待ちのため）。`ShoutBarSetup.cs` は proxy を使わず、`UdonBehaviour` に `programSource` と public 変数を直接設定している。
- **編集用スクリプトを書き換えた直後の実行**も同じ理由で失敗しやすい。書き換えたら `CompileCheck` を 1 回挟む。
- **macOS の Homebrew** で `vrc-get` を入れると、関係のない tap の設定で止まることがある。GitHub リリースのバイナリ（`aarch64-apple-darwin-vrc-get` など）を使う方が確実。
- **日本語の表示**：スコアボードの TextMeshPro は日本語フォントのアセットが必要。テスト用シーンでは置いておらず、ポップアップは標準の `TextMesh` を使っている。
- **音**：Unity に効果音は入っていない。`Effect_0..2` の AudioSource にクリップを入れると鳴る。

## 終わったら利用者に伝えること

- コンパイルとシーン保存の結果（ログの `[ShoutBar]` の行）
- ClientSim での確認方法
- 残っている人の作業：日本語フォント、効果音、肖像などの素材、VRChat へのアップロード
