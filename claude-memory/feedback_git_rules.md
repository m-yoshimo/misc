---
name: feedback-git-rules
description: 全プロジェクト共通の git 操作ルール
metadata:
  type: feedback
---

全プロジェクト共通の git 操作ルール。

**禁止操作（ユーザーが行う）:**
- `git push` → 禁止
- `git stash` / `git stash pop` → 禁止
- `git commit` → 禁止
- `git add` → 禁止（ユーザーが行う）

**要許可操作:**
- `git checkout` などのブランチ切り替え → ユーザーの事前許可が必要
  - 「コマンドの実行を許可してください」ではなく、「〇〇のために△△ブランチに切り替えたいのですが、よいですか？」と目的を明示して同意を得る

**確認不要（read-only）:**
- `git status`, `git diff` → 確認なしで実行してよい
- `git log`, `git show`, `git blame` など読み取り系も同様

**Why:** ユーザーがワーキングツリーの状態を管理しており、Claude が add/commit/push/stash すると予期しない状態変化が起きる。特に `git stash pop` は既存 stash を誤復元するリスクがある（実際に発生）。
