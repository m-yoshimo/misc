---
name: IaC化ワークフロー（既存リソースのimport）
description: 既存AWSリソースをTerraformで管理する際は laws ls --tf → import.tf → generate-config-out の手順を使うこと。手動でリソース定義を書かない。
metadata:
  type: feedback
---
既存リソースを IaC 化する際は以下の手順を使うこと。詳細確認のための `aws` コマンドを多用してはいけない。

1. `laws ls <service> --tf -p <profile>` で import block を収集 → `import.tf` に追加
2. `terraform plan -generate-config-out=generated.tf` でリソース定義を自動生成
3. 生成ファイルを確認・ファイル分割
4. 全リソース取り込み後は import.tf をコメントアウト（将来の完全 IaC 移行時に削除）

**Why:** `aws` コマンドで詳細を手動調査してリソース定義を書くのは不要な作業。個別リソースの確認も import → terraform plan 比較の方が速い。

**How to apply:** import.tf 用に ID を集めるのは laws で十分。リソース定義は terraform が生成する。個別確認に aws コマンドを使わない。
