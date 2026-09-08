---
name: feedback-design-notes-capture
description: ユーザーから設計・実装の指摘を受けたら、汎用化して ~/.claude/notes/design_philosophy.md に追記する。これは design-review が使うレビュー基準を育てる。
metadata:
  type: feedback
---

## 設計・実装思想ノートへのキャプチャ（レビュー基準を育てる）

ユーザーから**設計・実装に関する指摘・好み・判断基準**を受けたら、それを**汎用化**して
`~/.claude/notes/design_philosophy.md` に追記する。

**Why:** この蓄積は、外部の **design-review エージェントが Claude の成果物を照合する基準**（`~/.claude/notes/design_review_rubric.md` が参照する具体教訓の母体）になる。つまり「Claude が守る」のではなく「別の目が Claude を叩く基準」を育てる行為。レビュー指摘はコミット前に解消されて痕跡が残らないので、その場で記録しないと必ず失われる。

**How to apply:**
- 対象は「設計・実装の考え方」（共通化の判断・構造の置き方・可読性・命名・エラーハンドリング等）。単なる作業手順の指摘は対象外（それは feedback として保存）。
- 指摘を受けたら**その場で**追記する。後回しにしない。
- スタック固有の指摘でも、可能なら技術非依存の普遍原則を抽出する。
- 形式とタグ付けは `~/.claude/notes/design_philosophy.md` 冒頭の「エントリ形式」に従う。
- **理想は、この追記を Claude の自己申告に頼らず design-review 側で機械的に行うこと**（レビューが新しい違反クラスを見つけたら基準に追記する）。それが実装されるまでは受動キャプチャで補う。

関連: `~/.claude/notes/design_review_rubric.md`（レビュー基準本体）／ [[feedback-verify-inference-before-act]]
