# グローバルルール — 優先度付き早見表

このファイルを最初に読む。個別ルールの詳細は各 `feedback_*.md` を参照。

---

## Tier 1: 安全制約（絶対に守る・例外なし）

これを破ると手戻りまたはユーザーの作業が失われる。

| ルール | 要点 | 詳細 |
|--------|------|------|
| **タスクワークフロー** | 実装前に `.claude/tasks/{name}.md` を作成 → レビュー → 承認後に着手 | [feedback_task_workflow.md](feedback_task_workflow.md) |
| **git 操作** | add / commit / push / stash は Claude がやらない。checkout は許可を得てから | [feedback_git_rules.md](feedback_git_rules.md) |
| **推測検証** | 推測をコードで確認してから結論を出す。確認前に動いてはいけない | [feedback_verify_inference_before_act.md](feedback_verify_inference_before_act.md) |

---

## Tier 2: 作業プロセス（毎ターン意識する）

| ルール | 要点 | 詳細 |
|--------|------|------|
| **コミュニケーション** | 完了時・待機時どちらも状態を明示する | [feedback_communication_rule.md](feedback_communication_rule.md) |
| **コマンド実行** | 副作用のない操作（read-only）は確認不要で即実行 | [feedback_auto_execute.md](feedback_auto_execute.md) |

---

## Tier 3: 技術ワークフロー（対象言語・ツール使用時のみ）

| 対象 | 要点 | 詳細 |
|------|------|------|
| **Go** | 変更後: gofumpt → ビルド確認 → テスト の順。スクリプト一括変換後は特に必須 | [feedback_golang_workflow.md](feedback_golang_workflow.md) |
| **TypeScript** | prettier が Edit/Write 後に自動実行。import 追加と利用は同一の Edit/Write で行う | [feedback_typescript_workflow.md](feedback_typescript_workflow.md) |
| **Terraform** | 既存リソース IaC 化: laws ls → import.tf → generate-config-out。手動でリソース定義を書かない | [feedback_iac_workflow.md](feedback_iac_workflow.md) |

---

## Tier 4: 状況依存

| 状況 | 要点 | 詳細 |
|------|------|------|
| **トークン残量が少ない** | 作業を続けず `.claude/tasks/` に途中結果を保存してセッションを終える | [feedback_save_progress_on_low_tokens.md](feedback_save_progress_on_low_tokens.md) |
