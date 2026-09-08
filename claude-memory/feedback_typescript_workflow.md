---
name: feedback-typescript-workflow
description: TypeScript プロジェクトの編集時注意。フォーマッタはプロジェクト設定が優先（グローバルの想定を持ち込まない）。PostToolUse で自動整形が走るため、import 追加と利用は必ず同一の書き換えで行う。
metadata:
  type: feedback
---

## フォーマッタはプロジェクト設定が優先（グローバルの想定を持ち込まない）

TypeScript プロジェクトのフォーマッタ／リンタは**リポジトリ内の設定が唯一の正**。自分の記憶やグローバルの
作業ルールにある「このスタックならこのツール」という想定を持ち込まない。着手前にリポジトリ内の設定ファイル
（`biome.json` / `.prettierrc*` / `eslint.config.*` / `.claude/settings.json` の PostToolUse フック）を確認し、
それに合わせる。

**Why:** 「TypeScript なら prettier が自動実行される」という記憶を一般則として持ち込み、Biome を使う
プロジェクト（idpf-api / apps/front）で「グローバルの prettier と競合する」と誤った懸念を報告した。実際には
グローバル `~/.claude/settings.json` に prettier フックは存在せず、プロジェクト側の
`.claude/hooks/post-edit-lint.sh` が Biome（front）と gofumpt（api）を正しく使い分けていた。設定を確認せず
記憶で語ったのが原因。

**How to apply:**
- フォーマッタの話をする前に、そのリポジトリの設定を実際に読む。記憶で断定しない
- プロジェクト設定とグローバルの作業ルールが食い違う場合は**プロジェクト設定に従う**
- 例: idpf-api の `apps/front` は Biome（tab インデント / single quote / semicolon なし / organizeImports 有効）

## import 追加と利用は同一の Edit/Write で行う

PostToolUse フックでフォーマッタ（prettier / Biome など）が自動実行され、**未使用 import が自動削除される**
ことがある。

**Why:** import を追加する Edit → 使う箇所を追加する Edit の2ステップで実装すると、1回目の Edit 後に
formatter が未使用 import を消してしまい、やり直しが発生する。複数回同じ作業を繰り返すことになった。

**How to apply:**
- import 追加と、その import を使う実装は **同一の Edit/Write** で行う
- 特に「import を先に追加してから実装」というステップ分割は禁止
- 複数箇所を変更する場合は、ファイル全体を Write で書き換える（Edit の複数回呼び出しより安全）
- PostToolUse フックで formatter が走った旨のメッセージが出たら、次の Edit 前に必ず Read して現在のファイル状態を確認する
