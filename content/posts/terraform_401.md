---
title: "Terraform の 401 エラー：原因と解決策"
date: 2026-06-09
description: "クラウドプロバイダーへの認証に失敗した"
tags: ["Terraform"]
errorCode: "401"
service: "Terraform"
error_type: "401"
components: ["Provider", "Registry", "Backend", "State"]
related_services: ["AWS", "Azure", "GCP", "Terraform Cloud", "Terraform Enterprise", "IAM", "STS", "S3"]
trend_incident: true
---
## エラーの概要

Terraform の 401 [エラー](/glossary/エラー/)は、クラウドプロバイダー（AWS・Azure・GCP等）または Terraform Cloud/Enterprise への[認証](/glossary/認証/)に失敗したときに発生します。認証情報の不足・期限切れ・形式[エラー](/glossary/エラー/)などが原因で、リソースの操作やプランの実行が中断されます。

## 実際のエラーメッセージ例

```json
Error: error configuring Terraform AWS Provider: error validating provider credentials: error calling sts:GetCallerIdentity: InvalidClientTokenId: The security token included in the request is invalid
  on main.tf line 1, in provider "aws":
   1: provider "aws" {
```

```bash
Error: Failed to retrieve available provider versions from Terraform Registry (registry.terraform.io).
This may be caused by network connectivity issues, or an incorrect API token.
HTTP status code: 401 Unauthorized
```

## よくある原因と解決手順

### 原因1：AWS アクセスキーの認証情報が不正または期限切れ

AWS のアクセスキーが間違っているか、[IAM](/glossary/iam/)（AWS Identity and Access Management）ユーザーの[権限](/glossary/権限/)が削除されている場合に発生します。特に複数の AWS [アカウント](/glossary/アカウント/)を扱う環境では、設定ミスが起こりやすくなります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 期限切れまたは不正なキーを使用
export AWS_ACCESS_KEY_ID=<your-access-key-id>
export AWS_SECRET_ACCESS_KEY=<your-secret-access-key>

terraform plan
```

**After（修正後）：**

```bash
# 最新の認証情報を取得・確認
aws sts get-caller-identity

# 有効なキーを再設定
export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7NEWKEY
export AWS_SECRET_ACCESS_KEY=<your-secret-access-key>

# または ~/.aws/credentials ファイルで管理
cat ~/.aws/credentials

terraform plan
```

### 原因2：環境変数が設定されていない

Terraform が認証情報を探すとき、[環境変数](/glossary/環境変数/)（`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY` など）が未設定の場合、プロバイダー[認証](/glossary/認証/)に失敗します。特に [CI/CD](/glossary/ci-cd/) パイプラインや[サーバーレス](/glossary/サーバーレス/)環境では見落としやすい原因です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```hcl
# main.tf
provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "example" {
  bucket = "my-bucket"
}
```

```bash
# 環境変数が設定されていない状態で実行
terraform plan
# Error: error configuring Terraform AWS Provider: no valid credential sources found
```

**After（修正後）：**

```bash
# 環境変数を設定してから実行
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="us-east-1"

terraform plan

# または ~/.aws/credentials と ~/.aws/config で設定
# ~/.aws/credentials:
# [default]
# aws_access_key_id = your-access-key
# aws_secret_access_key = your-secret-key

# ~/.aws/config:
# [default]
# region = us-east-1
```

### 原因3：Terraform Cloud の認証トークンが無効または期限切れ

`terraform login` で取得した Terraform Cloud の[トークン](/glossary/トークン/)が有効期限を超えた場合や、[トークン](/glossary/トークン/)が削除された場合に発生します。リモート状態を利用している環境では特に重要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ~/.terraformrc に古いトークンが保存されている
cat ~/.terraformrc
# credentials "app.terraform.io" {
#   token = "expired-token-xxxxx"
# }

terraform init
# Error: Failed to retrieve available provider versions from Terraform Registry
# HTTP status code: 401 Unauthorized
```

**After（修正後）：**

```bash
# 新しいトークンで再認証
terraform login

# 対話的にトークンを入力（Terraform Cloud Web UI で生成したトークン）
# Generated a CLI configuration token. But it isn't stored by this command.
# ...
# Token saved to ~/.terraformrc

# トークンが正しく設定されたか確認
cat ~/.terraformrc

terraform init
# Success! The configuration has been successfully validated.
```

### 原因4：プロバイダーブロックの認証情報が直接記述されている場合のキー値エラー

プロバイダーブロック内に直接認証情報を記述している場合、キー名やフォーマットのタイプミスが 401 [エラー](/glossary/エラー/)を引き起こします。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```hcl
# main.tf
provider "aws" {
  region            = "us-east-1"
  access_key        = "<your-access-key-id>"  # キー名が誤っている
  secrect_access_key = "<your-secret-access-key>"  # タイプミス
}
```

**After（修正後）：**

```hcl
# main.tf
provider "aws" {
  region            = "us-east-1"
  access_key        = var.aws_access_key
  secret_access_key = var.aws_secret_access_key
}

# variables.tf
variable "aws_access_key" {
  type      = string
  sensitive = true
}

variable "aws_secret_access_key" {
  type      = string
  sensitive = true
}

# または環境変数を優先（推奨）
provider "aws" {
  region = "us-east-1"
  # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY 環境変数を自動読込
}
```

## ツール固有の注意点

### 複数プロバイダーを利用する場合

Terraform で AWS・Azure・GCP など複数のクラウドプロバイダーを組み合わせる場合、各プロバイダーの認証情報をそれぞれ設定する必要があります。一つのプロバイダーの[認証](/glossary/認証/)が失敗すると、全体の `terraform plan` がブロックされます。

```hcl
provider "aws" {
  region = "us-east-1"
  # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY を読込
}

provider "azurerm" {
  features {}
  # ARM_CLIENT_ID, ARM_CLIENT_SECRET, ARM_SUBSCRIPTION_ID を読込
}

provider "google" {
  project = "<your-gcp-project>"
  region  = "us-central1"
  # GOOGLE_APPLICATION_CREDENTIALS を読込
}
```

各プロバイダーの認証状態は個別に検証しましょう。

```bash
# AWS の認証確認
aws sts get-caller-identity

# Azure の認証確認
az account show

# GCP の認証確認
gcloud auth list
```

### Terraform Cloud / Enterprise でのリモート状態管理

`terraform login` で正常に[認証](/glossary/認証/)できても、後で組織の [API](/glossary/api/) トークンポリシーが変更される場合があります。Terraform Cloud の Web UI で自分の[トークン](/glossary/トークン/)有効期限を確認し、期限が近い場合は新規[トークン](/glossary/トークン/)を生成してください。

```bash
# トークン情報の確認（Terraform Cloud Web UI: https://app.terraform.io/app/settings/tokens）
# 期限切れトークンは削除し、新しいトークンを生成する

terraform login  # 新しいトークンで再設定
```

### CI/CD パイプライン（GitHub Actions・GitLab CI 等）での環境変数設定

パイプラインで Terraform を実行する場合、シークレット[環境変数](/glossary/環境変数/)として認証情報を登録する必要があります。例えば GitHub Actions では以下のように設定します。

```yaml
# .github/workflows/terraform.yml
name: Terraform

on: push

jobs:
  terraform:
    runs-on: ubuntu-latest
    env:
      AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
      AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      TF_TOKEN_APP_TERRAFORM_IO: ${{ secrets.TF_TOKEN_APP_TERRAFORM_IO }}
    steps:
      - uses: actions/checkout@v3
      - uses: hashicorp/setup-terraform@v2
      - run: terraform init
      - run: terraform plan
```

## それでも解決しない場合

### ログレベルを上げてデバッグ情報を取得

Terraform のログレベルを `DEBUG` に設定すると、[認証](/glossary/認証/)フローの詳細が表示されます。

```bash
export TF_LOG=DEBUG
terraform plan > terraform_debug.log 2>&1

# ログから "401" や "Unauthorized" のキーワードで検索
grep -i "401\|unauthorized" terraform_debug.log
```

### 認証情報キャッシュをクリア

古い[キャッシュ](/glossary/キャッシュ/)が残っている場合、以下の[コマンド](/glossary/コマンド/)で Terraform のプラグインキャッシュを削除してください。

```bash
# Terraform プラグインキャッシュをクリア
rm -rf ~/.terraform.d/plugin-cache

# または .terraform ディレクトリをリセット
rm -rf .terraform .terraform.lock.hcl

# 再初期化
terraform init
```

### プロバイダーと API 仕様の確認

使用するプロバイダーの[バージョン](/glossary/バージョン/)が古い場合、[API](/glossary/api/) 仕様変更により認証方式が変わっている可能性があります。最新[バージョン](/glossary/バージョン/)へのアップグレードを試してください。

```bash
# プロバイダーのバージョン確認
terraform version

# .terraform.lock.hcl でプロバイダーバージョンを確認し、手動でアップグレード
terraform init -upgrade
```

### 公式ドキュメントでの確認

各プロバイダーの公式認証ドキュメントを参照してください：
- **AWS Provider**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs#authentication-and-configuration
- **Azure Provider**: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs#authentication
- **Google Provider**: https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/provider_reference#authentication

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*