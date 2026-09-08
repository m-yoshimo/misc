# グローバルルール — 優先度付き早見表

このファイルを最初に読む。個別ルールの詳細は各 `feedback_*.md` を参照。

> **設計・実装の質**は「注入ルールで Claude に守らせる」のでなく「**外部 design-review が `~/.claude/notes/design_review_rubric.md` で照合する**」方針へ移行中（判定者を実装者から分離／配線は構築中）。

---

## Tier 0: 作業前の全体承認（最優先・例外なし）

ユーザーの依頼を受けたら、着手前に必ず「これから行う作業全体」を提示し、承認を得る。承認を得るまで、いかなる作業も進めない。

- **承認の単位は「作業全体」**。read / write などの個別操作単位ではなく、これから行う一連の作業（**調査・実装・考察を含む**）全体を提示して承認を得る。
- **調査・ファイル読み込みも承認対象**。どのファイルを読み、何を調査し、何を編集するかを事前に提示する。read-only だからと承認前に進めない。
- **承認後**は [feedback_auto_execute.md](feedback_auto_execute.md) の「read-only 即実行」が有効になる。
- **途中の新発見も再承認**。作業中に新たな発見があり追加作業が必要になった場合は、その内容が何であれ必ず承認を得てから進める。勝手に進めない。
- **提示は簡潔に**。作業全体は要約して提示する（過度に細かくしない）。

---

## Tier 1: 安全制約（絶対に守る・例外なし）

これを破ると手戻りまたはユーザーの作業が失われる。

| ルール                 | 要点                                                                                                                                                                                                                                                           | 詳細                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **タスクワークフロー** | 実装前に `.claude/tasks/{name}.md` を作成 → レビュー → 承認後に着手。エージェント委任（耐障害性＝速度／土台はディスク再開可能なタスクファイル）・検証ゲート（**LSP は並行編集中 non-authoritative・静止後の typecheck/build/lint/test のみ真実**）も同ファイル | [feedback_task_workflow.md](feedback_task_workflow.md)                             |
| **git 操作**           | add / commit / push / stash は Claude がやらない。checkout は許可を得てから                                                                                                                                                                                    | [feedback_git_rules.md](feedback_git_rules.md)                                     |
| **推測検証**           | 推測をコードで確認してから結論を出す。確認前に動いてはいけない                                                                                                                                                                                                 | [feedback_verify_inference_before_act.md](feedback_verify_inference_before_act.md) |

---

## Tier 2: 作業プロセス（毎ターン意識する）

| ルール                 | 要点                                                                                                                                    | 詳細                                                                 |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **コミュニケーション** | 完了時・待機時どちらも状態を明示する                                                                                                    | [feedback_communication_rule.md](feedback_communication_rule.md)     |
| **コマンド実行**       | **作業全体の承認（Tier 0）後**、副作用のない操作（read-only）は確認不要で即実行。**長い出力は `tail` で切らずファイルに保存して読む**（切ると再実行になる） | [feedback_auto_execute.md](feedback_auto_execute.md)                 |
| **メモリ保存先**       | フィードバック系は必ずグローバル `~/.claude/memory/` に保存。同系統は1ファイルに統合                                                    | [feedback_memory_workflow.md](feedback_memory_workflow.md)           |
| **作業ファイル置き場** | `/tmp` を使わない。プロジェクトの `.claude/tmp/{task}/` にフォルダを切る。不要になったら自分で消す。**`.claude/references/` はユーザーのフォルダ＝マスターにしない・勝手に消さない。書いた内容は必ずタスク定義書へ**                                      | [feedback_working_files.md](feedback_working_files.md)               |
| **設計思想キャプチャ** | 設計・実装の指摘を受けたら汎用化して `~/.claude/notes/design_philosophy.md` に追記。これは外部 design-review が使うレビュー基準を育てる | [feedback_design_notes_capture.md](feedback_design_notes_capture.md) |
| **多角的な設計視点**   | 設計段階は最初の案・既存手法にとらわれず多角的に考える（＝目的そのもの）。選択肢提示・トレードオフ評価はその結果への対処にすぎない      | [feedback_multi_angle_design.md](feedback_multi_angle_design.md)     |
| **ミスの償い**         | 自分のミスで損を与えたら、**誠意の基準を自分で決めない**。相手が示した償いの形をまず検討する。メモリの指示・約束を破ったら**反省文を書く**            | [feedback_accountability.md](feedback_accountability.md)             |

---

## Tier 3: 技術ワークフロー（対象言語・ツール使用時のみ）

| 対象           | 要点                                                                                                  | 詳細                                                               |
| -------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **Go**         | 変更後: gofumpt → ビルド確認 → テスト の順。コード生成系（openapi/mock/schema/model）はユーザーに依頼 | [feedback_golang_workflow.md](feedback_golang_workflow.md)         |
| **TypeScript** | prettier が Edit/Write 後に自動実行。import 追加と利用は同一の Edit/Write で行う                      | [feedback_typescript_workflow.md](feedback_typescript_workflow.md) |
| **Terraform**  | 既存リソース IaC 化: laws ls → import.tf → generate-config-out。手動でリソース定義を書かない          | [feedback_iac_workflow.md](feedback_iac_workflow.md)               |
| **Figma/画面実装** | 画面実装は必ず Figma MCP で該当ノードを取得してから。スクショの書き起こしや要件表を実装の根拠にしない      | [feedback_design_fidelity.md](feedback_design_fidelity.md)         |

---

## Tier 4: 状況依存

| 状況                     | 要点                                                                 | 詳細                                                                               |
| ------------------------ | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **トークン残量が少ない** | 作業を続けず `.claude/tasks/` に途中結果を保存してセッションを終える | [feedback_save_progress_on_low_tokens.md](feedback_save_progress_on_low_tokens.md) |
