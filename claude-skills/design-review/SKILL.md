---
name: design-review
description: 【DEPRECATED】design-review-v2 に移行しました。設計レビュー・コードレビューには design-review-v2 スキルを使ってください。
---

# ⛔ このスキルは廃止されました（2026-09-08）

**後継: `design-review-v2`（`/design-review-v2 [対象]`）**

## このスキルが呼ばれたときにすること

1. **v1 のレビューを実行しない。** `~/.claude/notes/design_review_rubric.md` / `design_philosophy.md` は DEPRECATED であり、レビュー基準として使わない。
2. ユーザーに「design-review は v2 に移行済みです」と伝え、**そのまま `design-review-v2` スキルを同じ引数で実行する**。

## 何が変わったか

| | v1（このスキル） | v2 |
|---|---|---|
| 基準 | `design_review_rubric.md` + `design_philosophy.md`（2ファイルが同期切れ） | `~/.claude/notes/design-review-v2/`（原則5 + ルール75 / 8カテゴリ。判定・理由・具体例を1エントリに統合） |
| レビュアー | 汎用エージェント1体 | 9体並列（観点別8 + 観点フリー1）＋ 2体以上の一致で severity 昇格 |
| 出力 | 自然文 | JSON スキーマ（`rule_id` / `severity` / `confidence` / `evidence`） |
| 重大度 | blocker/major/minor（定義なし） | blocker/major/minor/question（`severity.md` に定義） |
| 偽陽性 | 「避けよ」の一文のみ | 除外4類型のトリアージ（捨てず「除外候補」として提示） |
| 対象 | パスを口頭で渡す | ファイルに固定して全レビュアーが同一入力を読む |

移行の経緯は `~/.claude/notes/design-review-v2/README.md` を参照。
