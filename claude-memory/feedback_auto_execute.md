---
name: コマンド自動実行の許可
description: terraform apply などの副作用がある操作以外は確認なしで実行してよい
type: feedback
---

terraform apply や git push などの副作用がある操作以外は、確認なしにコマンドを実行してよい。

**Why:** いちいち OK するのが面倒との指摘。

**How to apply:** read-only な操作（terraform plan, grep, aws describe 系など）は即実行。apply/push/destroy 系は事前確認を継続。
