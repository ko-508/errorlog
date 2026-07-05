---
title: "Terraform の 404 エラー：原因と解決策"
date: 2026-06-09
description: "参照しているクラウドリソースが見つからない"
tags: ["Terraform"]
errorCode: "404"
service: "Terraform"
error_type: "404"
components: ["Provider", "State", "Workspace"]
related_services: ["AWS", "Google Cloud"]
trend_incident: true
---
## エラーの概要

Terraform の 404 [エラー](/glossary/エラー/)は、[設定ファイル](/glossary/設定ファイル/)で参照しているクラウドリソースが実際には存在しないか、削除されている状態を示します。この[エラー](/glossary/エラー/)が発生すると、`terraform plan` や `terraform apply` の実行が中断され、リソース間の依存関係が解決できません。特に data source を使ってリソース情報を取得する場合や、既存リソースを参照する設定で頻出します。

## 実際のエラーメッセージ例

**AWS Provider での例：**

```json
Error: error reading EC2 Instance: InvalidInstanceID.NotFound
  on main.tf line 12, in data "aws_instance" "existing":
  12: data "aws_instance" "existing" {
│
│ InvalidInstanceID.NotFound: The instance ID 'i-0123456789abcdef0' does not exist
```

**Google Cloud Provider での例：**

```
Error: Error when reading or editing Compute Instance: googleapi: Error 404: The resource 'projects/my-project/zones/us-central1-a/instances/old-instance' was not found
```

## よくある原因と解決手順

### 原因 1：data source で参照しているリソースがまだ作成されていないか削除されている

リソースを作成する前に、そのリソース情報を data source で参照しようとするケースがよくあります。また、クラウドコンソールから手動でリソースを削除した場合、Terraform の state ファイルにはまだ存在するとして記録されたままになり、再度参照しようとすると 404 [エラー](/glossary/エラー/)になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```hcl
# EC2 インスタンスを作成する前に参照しようとしている
data "aws_instance" "existing" {
  instance_ids = ["i-0123456789abcdef0"]
}

resource "aws_instance" "new" {
  ami           = data.aws_instance.existing.ami
  instance_type = "t3.micro"
}
```

**After（修正後）：**

```hcl
# 新しいインスタンスを直接作成し、data source は使わない
resource "aws_instance" "new" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
}

# または、リソースが確実に存在する場合にのみ data source を使用
data "aws_instance" "existing" {
  instance_ids = ["i-0123456789abcdef0"]

  depends_on = [aws_instance.new]
}
```

### 原因 2：リージョンまたはリソース名の指定が間違っている

AWS や Google Cloud などのマルチリージョンサービスでは、リージョン指定を誤ると別リージョンのリソースを探してしまい、404 [エラー](/glossary/エラー/)が発生します。リソース [ID](/glossary/id/) やリソース名の入力間違いも同様に原因となります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```hcl
provider "aws" {
  region = "us-west-1"
}

# リソースは us-east-1 に存在しているが、現在のプロバイダー設定では us-west-1 を参照しようとしている
data "aws_instance" "example" {
  instance_ids = ["i-0123456789abcdef0"]
}

# または間違ったリソース名を指定
data "aws_vpc" "existing" {
  cidr_block = "10.0.0.0/16"  # 実際には 10.1.0.0/16 で存在
}
```

**After（修正後）：**

```hcl
# リージョンをリソースの実在するリージョンに合わせる
provider "aws" {
  region = "us-east-1"
}

# 正確なインスタンス ID を指定
data "aws_instance" "example" {
  instance_ids = ["i-0123456789abcdef0"]
}

# または正確な CIDR ブロックを指定
data "aws_vpc" "existing" {
  cidr_block = "10.1.0.0/16"
}

# または別プロバイダーエイリアスを使ってリージョンを分ける
provider "aws" {
  alias  = "us_east"
  region = "us-east-1"
}

data "aws_instance" "example" {
  provider     = aws.us_east
  instance_ids = ["i-0123456789abcdef0"]
}
```

### 原因 3：別の Terraform workspace で管理しているリソースを参照しようとしている

Terraform の workspace 機能を使って環境を分け、別の workspace で管理されているリソースを参照しようとすると 404 [エラー](/glossary/エラー/)が発生します。同じリソースであっても workspace が異なると state ファイルが分離されており、相互参照ができません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```hcl
# 現在の workspace は "production" だが、"development" で作成されたリソースを参照
data "aws_security_group" "dev_sg" {
  name = "dev-app-sg"
}

resource "aws_instance" "prod_server" {
  ami             = "ami-0c55b159cbfafe1f0"
  instance_type   = "t3.large"
  security_groups = [data.aws_security_group.dev_sg.id]
}
```

**After（修正後）：**

```hcl
# 各 workspace で必要なセキュリティグループを定義する
resource "aws_security_group" "app_sg" {
  name        = local.environment == "prod" ? "prod-app-sg" : "dev-app-sg"
  description = "Security group for app"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "server" {
  ami             = "ami-0c55b159cbfafe1f0"
  instance_type   = local.environment == "prod" ? "t3.large" : "t3.micro"
  security_groups = [aws_security_group.app_sg.id]
}

locals {
  environment = terraform.workspace
}

# または terraform_remote_state を使って他の workspace のリソースを参照
data "terraform_remote_state" "dev" {
  backend = "local"

  config = {
    path = "../terraform.tfstate.d/development/terraform.tfstate"
  }
}

resource "aws_instance" "prod_server" {
  ami             = "ami-0c55b159cbfafe1f0"
  instance_type   = "t3.large"
  security_groups = [data.terraform_remote_state.dev.outputs.security_group_id]
}
```

## ツール固有の注意点

Terraform は state ファイルと実際のクラウドリソースの整合性に依存しています。手動でクラウドコンソールからリソースを削除した場合、state ファイルには古い情報が残ったままになり、404 [エラー](/glossary/エラー/)の原因になります。本来なら `terraform destroy` で state を削除すべきですが、事後対応として `terraform state rm <resource-address>` で state から該当リソースを削除できます。

また、マルチプロバイダー設定を使う場合、各 data source にどの provider を使うかを明示的に指定する必要があります。指定を忘れると、デフォルト provider がリソースを探してしまい、期待と異なるリージョンや[アカウント](/glossary/アカウント/)で 404 [エラー](/glossary/エラー/)が発生することがあります。

AWS の場合、リソース [ID](/glossary/id/) には各リージョン固有の値が使われるため、リージョン指定の誤りは一般的に 404 [エラー](/glossary/エラー/)に繋がります。Google Cloud でも同様なことが言えるため、複数リージョンで運用する場合は provider alias を活用し、リソース参照時に明示的に provider を指定するのがベストプラクティスです。

## それでも解決しない場合

まず `terraform state list` [コマンド](/glossary/コマンド/)で、現在 Terraform が管理している全リソースを確認しましょう。期待するリソースがリストに含まれていなければ、state ファイルがリソースを追跡していないことが明らかになります。

```bash
terraform state list
```

次に、AWS [CLI](/glossary/cli/) や gcloud [コマンド](/glossary/コマンド/)でクラウドプロバイダー上に実際にリソースが存在するか確認します。例えば AWS EC2 [インスタンス](/glossary/インスタンス/)なら以下の[コマンド](/glossary/コマンド/)で確認できます。

```bash
# AWS の場合
aws ec2 describe-instances --instance-ids i-0123456789abcdef0 --region us-east-1

# Google Cloud の場合
gcloud compute instances describe old-instance --zone us-central1-a
```

リソースが実在するのに state ファイルに含まれていない場合、`terraform import` [コマンド](/glossary/コマンド/)でリソースを state に取り込みます。

```bash
terraform import aws_instance.example i-0123456789abcdef0
```

それでも問題が解決しない場合、`terraform plan -v` または `terraform plan -json` で詳細[ログ](/glossary/ログ/)を確認し、[API](/glossary/api/) 呼び出しレベルでどのリソースを探しているかを特定します。公式の Terraform ドキュメント内の該当 provider ページで data source の仕様を確認し、必須パラメーターを満たしているかも検証しましょう。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*