---
name: feedback-typescript-workflow
description: TypeScript プロジェクトの編集時注意。VSCode の prettier が Edit/Write 後に自動実行され未使用 import を削除する。import 追加と利用は必ず同一の書き換えで行う。
metadata:
  type: feedback
---

VSCode の PostToolUse フックで prettier が自動実行される。Edit/Write のたびにフォーマットが走り、**未使用 import は自動削除される**。

**Why:** import を追加する Edit → 使う箇所を追加する Edit の2ステップで実装すると、1回目の Edit 後に formatter が未使用 import を消してしまい、やり直しが発生する。複数回同じ作業を繰り返すことになった。

**How to apply:**
- import 追加と、その import を使う実装は **同一の Edit/Write** で行う
- 特に「import を先に追加してから実装」というステップ分割は禁止
- 複数箇所を変更する場合は、ファイル全体を Write で書き換える（Edit の複数回呼び出しより安全）
- PostToolUse フックで formatter が走った旨のメッセージが出たら、次の Edit 前に必ず Read して現在のファイル状態を確認する
