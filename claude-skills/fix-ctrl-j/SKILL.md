---
name: fix-ctrl-j
description: VS Code の Claude Code 拡張のチャット入力欄で、Ctrl+J を押すと改行が入る動作を外す（拡張の webview/index.js を書き換える）。拡張の更新で書き換えが消え、Ctrl+J で改行が入るようになったときに使う。
when_to_use: ユーザーの依頼に「Ctrl+J」（ctrl j / Ctrl + J などの表記揺れを含む）または「fix-ctrl-j」が含まれ、Ctrl+J で改行が入る問題の修正を求めたときだけ使う。例:「Ctrl+J で改行が入る」「Ctrl+J の改行を直して」「Ctrl+J 直して」「また Ctrl+J で改行入るようになった」「fix-ctrl-j して」。Ctrl+J に触れていない改行の話（「改行が入る」だけ等）では使わない。
---

# fix-ctrl-j

## 背景

- ユーザーは VS Code のタブ切り替えに `ctrl+j ctrl+n` / `ctrl+j ctrl+p` を使っている（Windows 側の `keybindings.json`）。
  Claude Code 拡張のチャット入力欄にフォーカスがあると、Ctrl+J で改行も入ってしまう
- 拡張は 2.1.195 から、入力欄の改行判定関数で「Shift+Enter」と「Ctrl+J」を改行キーとして扱っている。
  設定項目も `~/.claude/keybindings.json` も効かないため、拡張のファイルを直接書き換える
- 拡張は `~/.local/bin/update-claude-code-ext`（systemd --user の `update-claude-code-ext.timer`、毎週月曜 12:00）で更新される。
  更新すると新しいバージョンのフォルダに入れ替わり、書き換えは消える
- **Ctrl+J のキー割り当て（VS Code 側）を変える案は出さない。** ユーザーが却下済み

## 手順

1. 最新の拡張フォルダを特定する。`~/.vscode-server/extensions/extensions.json` で `anthropic.claude-code` の `version` と `relativeLocation` を見る
2. そのフォルダの `webview/index.js` で、次の形の判定がいくつあるか数える（`X` は圧縮で付いた変数名で、バージョンごとに変わる）

   ```
   X.key.toLowerCase()==="j"&&X.ctrlKey&&!X.shiftKey&&!X.altKey&&!X.metaKey
   ```

   例: `grep -o -E '[$A-Za-z_][$A-Za-z0-9_]*\.key\.toLowerCase\(\)==="j"&&[$A-Za-z0-9_]+\.ctrlKey&&![$A-Za-z0-9_]+\.shiftKey&&![$A-Za-z0-9_]+\.altKey&&![$A-Za-z0-9_]+\.metaKey' index.js | wc -l`

3. **ちょうど 1 か所なら**:
   1. `index.js.orig` が無ければ `cp -p index.js index.js.orig` でバックアップする（既にあれば上書きしない）
   2. Edit ツールで、その式を `!1` に置き換える。前後の文脈（`return` と直後の `}function`）を含めて一意にマッチさせる
   3. `diff <(tr ';' '\n' < index.js.orig) <(tr ';' '\n' < index.js)` で差分がその 1 か所だけか確認し、`node --check index.js` で構文を確認する
   4. ユーザーに「コマンドパレットから Developer: Reload Window を実行して試してほしい」と伝える
4. **0 か所、または 2 か所以上なら**: 書き方が変わっている。推測で置き換えない。
   - `insertLineBreak` や `isComposing` の周辺を読み、入力欄の改行判定がどこで行われているかを特定する
   - Ctrl+J を判定している箇所と、その呼び出し元をユーザーに示し、書き換え案を出して承認を得てから書き換える
   - 書き換えたら、この SKILL.md の手順 2 の形も新しい形に直す

## 元に戻す

`index.js.orig` を `index.js` に上書きコピーし、ウィンドウを再読み込みする。
