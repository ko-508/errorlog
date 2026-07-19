---
title: "Terraform の 400 エラー：原因と解決策"
date: 2026-06-08
description: "Terraformがクラウドプロバイダーに送るリクエストの形式に誤りがある"
tags: ["Terraform"]
errorCode: "400"
service: "Terraform"
error_type: "400"
components: ["Provider"]
related_services: ["AWS"]
trend_incident: true
---
## エラーの概要

Terraform で 400 [エラー](/glossary/エラー/)が発生する場合、これはクラウドプロバイダーの [API](/glossary/api/) が「不正な[リクエスト](/glossary/リクエスト/)」と判定したことを意味します。HCL の構文自体は正しくても、リソース定義のパラメーター型や値がプロバイダーの期待形式と一致していない場合に起こります。`terraform apply` 実行時に最も頻繁に遭遇する[エラー](/glossary/エラー/)で、本来なら `terraform plan` で事前に検出すべき問題です。

## 実際のエラーメッセージ例

```json
Error: error creating DB Instance: BadRequest: 400 Bad Request
  on main.tf line 15, in resource "aws_db_instance" "example":
   15: resource "aws_db_instance" "example" {

  with aws_db_instance.example,
  on main.tf line 15, in resource "aws_db_instance" "example":
   15: resource "aws_db_instance" "example" {

Error: Error making API call: status code 400, message: invalid parameter value
```

```bash
$ terraform apply
Error: error creating resource: BadRequest: The request body is malformed
│
│   with module.vpc.aws_security_group.allow_ssh:
│   on vpc/main.tf line 42, in resource "aws_security_group" "allow_ssh":
│    42: resource "aws_security_group" "allow_ssh" {
```

## よくある原因と解決手順

### 原因 1：リソースパラメーターの型が不正

Terraform のプロバイダーが期待する型（文字列、数値、リスト等）と異なる型で値を指定すると、[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)生成時に 400 [エラー](/glossary/エラー/)が発生します。特に、数値として指定すべき[ポート](/glossary/ポート/)番号を文字列で渡したり、ブール値を文字列で指定したりするケースが多く見られます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```hcl
resource "aws_security_group" "example" {
  name        = "example-sg"
  description = "Example security group"

  ingress {
    from_port   = "80"           # 型エラー：文字列ではなく数値であるべき
    to_port     = "443"          # 型エラー
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  depends_on = true             # 型エラー：ブール値ではなく string の list
}
```

**After（修正後）：**

```hcl
resource "aws_security_group" "example" {
  name        = "example-sg"
  description = "Example security group"

  ingress {
    from_port   = 80            # 数値として指定
    to_port     = 443           # 数値として指定
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

### 原因 2：必須パラメーターが不足している

プロバイダーが要求する必須パラメーターを定義していない場合、[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)が不完全なため 400 [エラー](/glossary/エラー/)が返されます。ドキュメントで「Required」と明記されているパラメーターは必ず指定する必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```hcl
resource "aws_db_instance" "example" {
  identifier           = "mydb"
  engine               = "mysql"
  # allocated_storage と instance_class が不足
  db_name              = "mydb"
  username             = "admin"
  password             = "password123"
}
```

**After（修正後）：**

```hcl
resource "aws_db_instance" "example" {
  identifier           = "mydb"
  engine               = "mysql"
  allocated_storage    = 20           # 必須パラメーター
  instance_class       = "db.t3.micro" # 必須パラメーター
  db_name              = "mydb"
  username             = "admin"
  password             = "password123"
}
```

### 原因 3：プロバイダーのバージョン変更による API 形式の不一致

プロバイダーのバージョンアップで [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)形式が変わり、古い書き方が 400 [エラー](/glossary/エラー/)になる場合があります。特に deprecated パラメーター（廃止予定のパラメーター）の廃止や新しい必須パラメーターの追加が影響します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```hcl
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"  # 新バージョンプロバイダー
    }
  }
}

resource "aws_instance" "example" {
  ami                    = "ami-0c55b159cbfafe1f0"
  instance_type          = "t2.micro"
  associate_public_ip_address = "true"  # 古い書き方（文字列）
  user_data              = base64encode("#!/bin/bash\necho hello")  # 非推奨形式
}
```

**After（修正後）：**

```hcl
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_instance" "example" {
  ami                    = "ami-0c55b159cbfafe1f0"
  instance_type          = "t2.micro"
  associate_public_ip_address = true   # ブール値として指定
  user_data              = "#!/bin/bash\necho hello"  # 推奨形式
}
```

### 原因 4：terraform plan を実行していないまま apply を実行

`terraform plan` を先に実行すれば、多くの 400 [エラー](/glossary/エラー/)は事前に検出できます。それをスキップして直接 `apply` を実行すると、[API](/glossary/api/) 呼び出し時に[エラー](/glossary/エラー/)が顕在化します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# plan を実行せずに直接 apply
terraform apply -auto-approve
# Error: error making API call: status code 400...
```

**After（修正後）：**

```bash
# 必ず plan を先に実行
terraform plan

# plan に問題がなければ apply
terraform apply
```

## ツール固有の注意点

Terraform の 400 [エラー](/glossary/エラー/)は、HCL の構文チェック（`terraform validate`）では検出されません。`validate` は HCL の文法チェックのみで、プロバイダー側の要件チェックは行わないためです。そのため必ず `terraform plan` で実際の[リクエスト](/glossary/リクエスト/)生成をシミュレートして、プロバイダーの要件に適合しているか確認する必要があります。

AWS、Azure、Google Cloud など、各クラウドプロバイダーの Terraform プロバイダーは定期的に更新されます。プロバイダーの[バージョン](/glossary/バージョン/)を固定せずに `version = ">= 5.0"` のように範囲指定している場合、[CI/CD](/glossary/ci-cd/) パイプラインで異なる[バージョン](/glossary/バージョン/)が使用される可能性があります。本番環境では `version = "= 5.12.0"` のように完全な[バージョン](/glossary/バージョン/)指定を検討してください。

また、プロバイダーの公式ドキュメントには各リソースの「Argument Reference」（引数参照）セクションが必ず記載されています。そこで「Required」と「Optional」の区別、各パラメーターの型、デフォルト値を必ず確認しましょう。

## それでも解決しない場合

1. **詳細な[ログ](/glossary/ログ/)を出力する**

```bash
TF_LOG=DEBUG terraform plan
TF_LOG=DEBUG terraform apply
```

生成された[ログファイル](/glossary/ログファイル/)から、実際に [API](/glossary/api/) に送信される[リクエスト](/glossary/リクエスト/)形式を確認できます。

2. **terraform state を確認する**

既存のリソースが部分的に作成されている場合、state [ファイル](/glossary/ファイル/)が破損していないか確認してください。

```bash
terraform state list
terraform state show <resource_name>
```

3. **プロバイダードキュメントを再確認**

各プロバイダーの公式ドキュメントで、該当リソースの最新仕様を確認してください。

- AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Azure Provider: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs
- Google Cloud Provider: https://registry.terraform.io/providers/hashicorp/google/latest/docs

4. **プロバイダーの[バージョン](/glossary/バージョン/)[互換性](/glossary/互換性/)を確認**

```bash
terraform version
terraform providers
```

プロバイダーが最新でない場合、アップグレードを試みてください。

```bash
terraform init -upgrade
```

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*