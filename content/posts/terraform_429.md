---
title: "Terraform の 429 エラー：原因と解決策"
date: 2026-06-10
description: "クラウドプロバイダーのAPIレート制限に達した。Terraform 429 エラーの原因と解決策を解説します。"
tags: ["Terraform"]
errorCode: "429"
service: "Terraform"
error_type: "429"
components: ["Provider", "Backend", "State"]
related_services: ["AWS", "Google Cloud", "Azure", "IAM", "EC2", "CloudFormation", "GitLab CI"]
---
## エラーの概要

[HTTP](/glossary/http/) 429 [エラー](/glossary/エラー/)は「Too Many Requests」を意味し、Terraform の実行時にクラウドプロバイダーの [API](/glossary/api/) [レート制限](/glossary/レート制限/)に達したことを示します。AWS・Google Cloud・Azure など複数のプロバイダーが [API](/glossary/api/) 呼び出しの頻度を制限しており、Terraform がこの上限を超えたときに発生します。特に大規模なインフラストラクチャをコード化する際に、並列処理による過度な [API](/glossary/api/) 呼び出しが原因となることが多くあります。

## 実際のエラーメッセージ例

Terraform 実行時に以下のような[エラー](/glossary/エラー/)が出力されます。

```json
{
  "error": "error creating Security Group: RequestLimitExceeded: Request limit exceeded",
  "status_code": 429
}
```

また、Terraform の標準出力では以下のように表示されることもあります。

```bash
Error: Error creating load balancer: InvalidParameterValue
  on main.tf line 42, in resource "aws_lb" "example":
  42: resource "aws_lb" "example" {

429 Too Many Requests
```

## よくある原因と解決手順

### 原因 1：Terraform の並列実行数が多すぎる

Terraform はデフォルトで 10 個のリソースを同時に作成する設定になっており、これが [API](/glossary/api/) [レート制限](/glossary/レート制限/)に抵触します。特に AWS や Google Cloud のプロバイダーでは、単位時間あたりの [API](/glossary/api/) 呼び出し数に制限があり、デフォルトの並列度では超過しやすくなります。

**修正前：**

```bash
terraform apply -auto-approve
# デフォルトの並列度 10 で実行
```

**修正後：**

```bash
terraform apply -parallelism=5 -auto-approve
# 並列度を 5 に制限して実行
```

より慎重に進める場合：

```bash
terraform apply -parallelism=2 -auto-approve
# 並列度を 2 に制限（さらに安全）
```

### 原因 2：複数の Terraform プロセスが同時に実行されている

[CI/CD](/glossary/ci-cd/) パイプラインやスケジュール実行を複数設定している場合、同じプロバイダーに対して複数の Terraform プロセスが同時にアクセスし、[API](/glossary/api/) [レート制限](/glossary/レート制限/)に達します。

**修正前：**

```yaml
# .gitlab-ci.yml の例
stages:
  - deploy

deploy_env1:
  script:
    - terraform apply -auto-approve

deploy_env2:
  script:
    - terraform apply -auto-approve
```

この設定では `deploy_env1` と `deploy_env2` が並列実行され、同一プロバイダーへの [API](/glossary/api/) 呼び出しが競合します。

**修正後：**

```yaml
# .gitlab-ci.yml の例
stages:
  - deploy_env1
  - deploy_env2

deploy_env1:
  stage: deploy_env1
  script:
    - terraform apply -auto-approve

deploy_env2:
  stage: deploy_env2
  script:
    - terraform apply -auto-approve
```

ステージを分離して順序を制御し、同時実行を防ぎます。

### 原因 3：プロバイダー設定にリトライロジックがない

一時的な [API](/glossary/api/) 制限[エラー](/glossary/エラー/)に対して自動的に再試行する機構がない場合、すぐに[エラー](/glossary/エラー/)で終了してしまいます。プロバイダー設定にリトライパラメーターを追加することで、指数バックオフを用いた自動再試行が可能になります。

**修正前：**

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "ap-northeast-1"
}
```

**修正後：**

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "ap-northeast-1"
}

# 環境変数で制御する場合
# export AWS_MAX_ATTEMPTS=5
# export AWS_RETRY_MODE=adaptive
```

AWS プロバイダーの場合、[環境変数](/glossary/環境変数/) `AWS_MAX_ATTEMPTS` で最大試行回数を指定できます。

## ツール固有の注意点

### AWS プロバイダーでの対応

AWS には複数の[レート制限](/glossary/レート制限/)があり、[IAM](/glossary/iam/) [API](/glossary/api/)・EC2 [API](/glossary/api/)・CloudFormation [API](/glossary/api/) などサービスごとに異なります。Terraform が CloudFormation を背後で使用している場合、CloudFormation のスタック作成数制限（デフォルトでは 200 スタック）に達することもあります。

```bash
# AWS リクエストスロットリング対策
export AWS_MAX_ATTEMPTS=10
export AWS_RETRY_MODE=adaptive
terraform apply -parallelism=3
```

### Google Cloud プロバイダーでの対応

Google Cloud は [API](/glossary/api/) ごとに異なるクォータを設定しており、Compute Engine [API](/glossary/api/) はデフォルトで 1 分間に 240 [リクエスト](/glossary/リクエスト/)に制限されています。

```hcl
provider "google" {
  project = "<your-project-id>"
  region  = "asia-northeast1"

  # Google Cloud 側でのスロットリング対応
  # Terraform 側では parallelism で調整する
}
```

### Terraform Cloud・Terraform Enterprise での実行

Terraform Cloud を通じて実行する場合、[ワークスペース](/glossary/ワークスペース/)の実行キューがバックプレッシャー（負荷圧力）となり、複数の実行が積み重なると [API](/glossary/api/) [レート制限](/glossary/レート制限/)に達しやすくなります。その場合は実行中の Terraform を明示的にキャンセルするか、[ワークスペース](/glossary/ワークスペース/)単位で apply タイミングをずらします。

## それでも解決しない場合

### 確認すべきログ

Terraform は詳細[ログ](/glossary/ログ/)を以下の[環境変数](/glossary/環境変数/)で有効化できます。

```bash
export TF_LOG=DEBUG
export TF_LOG_PATH=terraform.log
terraform apply -parallelism=3
```

生成される `terraform.log` には [API](/glossary/api/) [レスポンス](/glossary/レスポンス/)の詳細（[HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)・[リトライ](/glossary/リトライ/)回数）が記録されており、どのリソース作成時に 429 [エラー](/glossary/エラー/)が発生したかを特定できます。

### リソース分割による段階的デプロイ

規模が大きい場合は、Terraform コード自体をモジュール単位で分割し、段階的に apply することも有効です。

```bash
# ステップ 1：ネットワーク系
terraform apply -target=module.network

# ステップ 2：セキュリティグループ
terraform apply -target=module.security_groups

# ステップ 3：コンピュートリソース
terraform apply -target=module.compute
```

### プロバイダーのクォータ増申請

クライアント側での調整でも追いつかない場合、クラウドプロバイダーの[コンソール](/glossary/コンソール/)画面でクォータ増申請を行います。AWS の場合は Service Quotas [コンソール](/glossary/コンソール/)、Google Cloud の場合は Quotas ページから申請可能です。申請から承認まで数時間～数日要することがあるため、並列数削減は並行して行うべきです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*