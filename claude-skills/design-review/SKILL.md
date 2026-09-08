---
name: design-review
description: Claude 自身の設計・実装を、別のレビューエージェントが design_review_rubric.md で照合し指摘を返す。タスク定義書作成時（設計レビュー）と実装時（コードレビュー）に使う。判定者を実装者から分離するのが目的。ユーザーが手動で選択実行もできる。
---

# design-review スキル

Claude（実装者）が自分の成果物を自己採点しても、破った本人が判定する構造的欠陥で機能しない。
このスキルは **別のレビューエージェントを spawn し、その第三者が rubric で照合**して指摘を返す。実装者=Claude は採点しない。

## 起動方法
- **ユーザーが手動で選択実行**: `/design-review [対象]`
  - `/design-review` … 引数なし＝**現在の未コミット差分**（`git diff` ＋ `git diff --staged`）をレビュー。
  - `/design-review <ファイル or ディレクトリ>` … そのパスをレビュー。
  - `/design-review <git レンジ>`（例 `/design-review origin/development..HEAD`）… その差分をレビュー。
  - `/design-review <.claude/tasks/xxx.md>` … タスク定義書（設計）をレビュー。
- **自動**: hook が「未レビューの変更あり」を検知した時にも起動しうる。
- **Claude が自発的に**: タスク定義書を作成した時（設計レビュー）・実装を終えて提示/コミットする前（コードレビュー）に必ず回す。

## 手順

1. **レビュー対象を確定する**（read-only）:
   - 引数があればそれを対象にする。無ければ現在の未コミット差分（`git diff` ＋ `git diff --staged`）。
   - 差分が空なら「レビュー対象なし」と伝えて終了。
   - タスク定義書（`.claude/tasks/*.md`）が対象なら、その計画・設計を読む。

2. **別のレビューエージェントを spawn する**（Agent ツール、`subagent_type: general-purpose`、read-only 指示・中立プロンプト）。プロンプトに必ず含める:
   - レビュー基準: `~/.claude/notes/design_review_rubric.md` を**必ず全文読んで**適用すること。加えて `~/.claude/notes/design_philosophy.md` の具体教訓も参照。
   - レビュー対象: 上記の diff / ファイル / タスク定義書（パスとレンジを渡して read させる、または内容を渡す）。
   - **特定の観点へ誘導しない**（rubric 全観点を自分で当てさせる。誘導するとその観点しか見なくなる）。
   - 出力要求: **指摘を file:line 付き**で、各指摘に「該当する rubric 観点番号／重大度（blocker/major/minor）／なぜ違反か／推奨修正」を付ける。問題がなければ「指摘なし」と明記。忖度・気休め禁止。憶測で"問題あり"にせず、コードの事実に基づくこと。false positive を避け、違反でない箇所は「判定なし」と明示させる。
   - 制約: レビューエージェントはコードを**変更しない**（read-only）。指摘を返すだけ。

3. **指摘をそのままユーザーへ提示する**。Claude（実装者）が握りつぶさない・自己判断で「問題ない」と却下しない。blocker/major があれば、修正するかユーザーに諮る。

4. **新しい違反クラスを見つけたら** `~/.claude/notes/design_review_rubric.md` か `design_philosophy.md` に追記して基準を育てる（[[feedback-design-notes-capture]]）。

## 注意
- このスキルの価値は「別の目で照合する」点にある。レビューを Claude 自身の一存で省略・要約・骨抜きにしない。
- rubric は `~/.claude/notes/design_review_rubric.md`。存在しなければユーザーに知らせる。
- 誤検出（正しいコードを問題と誤判定）に注意。レビューは指摘するだけで、修正の要否は最終的にユーザーが判断する。
