---
name: feedback-golang-workflow
description: Go プロジェクトの変更後ワークフロー。gofumpt フォーマット → ビルド確認 → テストの順で行う。
metadata:
  type: feedback
---

コード変更後は必ず gofumpt でフォーマットを実行してからビルド確認する。ビルドチェックだけでは不十分。

**Why:** perl や python などのスクリプトによる一括置換後にインデントや改行がずれ、lint エラーになることが多い。フォーマット忘れが繰り返し発生している。

**How to apply:**
- 変更後の手順は常に「フォーマット → ビルド確認 → テスト」の順で行う
- スクリプト（perl/sed/python）で一括変更した後は特に必ずフォーマットをかける
- フォーマットコマンド: `gofumpt -w <変更ファイル...>`
- ユーザーに「format かけて」と言わせない
