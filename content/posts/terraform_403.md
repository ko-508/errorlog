---
title: "Terraform の 403 エラー：原因と解決策"
date: 2026-06-09
description: "クラウドプロバイダーでリソースの作成・変更が拒否された。Terraform 403 エラーの原因と解決策を解説します。"
tags: ["Terraform"]
errorCode: "403"
service: "Terraform"
error_type: "403"
components: ["Provider", "State"]
related_services: ["AWS", "IAM", "EC2", "SCP", "AWS Organizations"]
trend_incident: true
---
## エラーの概要

Terraform が AWS などのクラウドプロバイダーにリソースの作成・更新・削除を要求したとき、[IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)または SCP（Service Control Policy）により操作が拒否される状態です。このエラーは実行[ロール](/glossary/ロール/)に必要な[権限](/glossary/権限/)がないか、組織レベルの制限によって操作が許可されていないことを示しています。

## 実際のエラーメッセージ例

```json
{
  "Error": {
    "Code": "AccessDenied",
    "Message": "User: arn:aws:iam::123456789012:user/terraform-user is not authorized to perform: ec2:RunInstances on resource: arn:aws:ec2:us-east-1:123456789012:instance/* with an implicit deny in user-based policy"
  }
}
```

```
Error: error creating EC2 Instance: UnauthorizedOperation.Unavailable: You are not authorized to perform this operation.
        status code: 403, request id: <request-id>

  on main.tf line 10, in resource "aws_instance" "example":
  10: resource "aws_instance" "example" {
```

## よくある原因と解決手順

### 原因1：実行ロールに IAM ポリシーの権限が不足している

Terraform を実行するユーザーまたはロールに、リソース作成に必要な IAM 権限がアタッチされていません。例えば EC2 インスタンスを起動する場合、`ec2:RunInstances` アクションの許可が必要です。IAM ポリシーシミュレーター（ポリシーが実際に機能するかを事前検証するツール）で実際に権限が付与されているかを確認し、不足している権限をポリシーに追加します。

**修正前（エラーが起きるコード）：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeSecurityGroups"
      ],
      "Resource": "*"
    }
  ]
}
```

**修正後：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeSecurityGroups",
        "ec2:RunInstances",
        "ec2:StopInstances",
        "ec2:TerminateInstances",
        "ec2:CreateTags"
      ],
      "Resource": "*"
    }
  ]
}
```

### 原因2：SCP（Service Control Policy）が実行を制限している

AWS Organizations で設定された SCP がリソース作成を明示的に拒否しているか、特定サービスの使用を制限している可能性があります。SCP は IAM ポリシーより上位の制限であり、IAM ポリシーで許可していても SCP で拒否されば操作は実行できません。AWS Organizations のコンソールで適用されている SCP を確認し、Terraform の実行に必要なアクションを許可するように SCP を修正します。

**修正前（エラーが起きるコード）：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Action": [
        "ec2:RunInstances",
        "ec2:CreateVolume"
      ],
      "Resource": "*"
    }
  ]
}
```

**修正後：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "*",
      "Resource": "*"
    },
    {
      "Effect": "Deny",
      "Action": [
        "organizations:LeaveOrganization"
      ],
      "Resource": "*"
    }
  ]
}
```

### 原因3：別のアカウントやリージョンのリソースを変更しようとしている

Terraform の provider 設定で指定されている AWS アカウント ID やリージョンと、実際に操作しようとしているリソースが一致していないケースです。tfstate ファイル（Terraform の状態を記録するファイル）に記録されたリソース ARN が、現在の実行環境と異なるアカウント・リージョンを指しているため、操作権限がないリソースへのアクセスが試みられます。provider ブロックの account_id・region と、リソース定義を確認して一致させます。

**修正前（エラーが起きるコード）：**

```hcl
provider "aws" {
  region = "us-east-1"
  # account_idを明示していない、または別のアカウントを指している
}

resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"
  # tfstateには別アカウントのリソースが記録されている場合がある
}
```

**修正後：**

```hcl
provider "aws" {
  region = "us-east-1"
  assume_role {
    role_arn = "arn:aws:iam::123456789012:role/terraform-role"
  }
}

resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"
  # 同じアカウント・リージョンのリソースが対象
}
```

## ツール固有の注意点

Terraform で 403 エラーが発生した場合、まず `terraform plan` を実行して、どのリソースのどのアクション（RunInstances、PutBucketPolicy など）が拒否されるかを特定することが重要です。AWS IAM ポリシーシミュレーターを使用して、対象のロール・ユーザーに対して特定のアクションが許可されているかどうかを事前に検証できます。

また、Terraform State ファイル（tfstate）に記録されたリソース情報が実際のクラウド環境と不一致している場合、`terraform refresh` で状態を再同期したり、必要に応じて `terraform import` でリソースを再度管理下に置くことで問題が解決するケースもあります。特にマルチアカウント環境や複数リージョンを管理している場合は、AssumeRole を使用して適切なクロスアカウントアクセスを設定することをお勧めします。

## それでも解決しない場合

AWS CloudTrail（AWS API の呼び出しを記録するサービス）のイベント履歴を確認して、Terraform が送信したリクエストがどのアクションで拒否されたかの詳細を確認します。CloudTrail ダッシュボードで該当する API コールを探し、`errorCode` および `errorMessage` フィールドを確認することで、IAM ポリシーシミュレーターでは検出できない組織レベルの制限や、リソースベースのポリシーによる拒否を発見できます。

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::123456789012:role/terraform-role \
  --action-names ec2:RunInstances \
  --resource-arns arn:aws:ec2:us-east-1:123456789012:instance/*
```

上記コマンドで各アクションの評価結果（`EvaluationResult`）を確認し、`allowed` が false の場合はどのポリシーにより拒否されているかを特定できます。公式の Terraform AWS Provider ドキュメントで、対象リソースに必要な IAM アクションの一覧を確認し、実行ロールのポリシーと照らし合わせることも有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*