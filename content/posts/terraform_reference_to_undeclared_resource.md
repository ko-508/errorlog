---
title: "Terraform未宣言リソースの対処法"
date: 2026-10-03
draft: false
description: "TerraformのReference to undeclared resourceは、参照先の宣言が現在のモジュールに見つからないエラーです。型名とラベル名、data.の付け忘れ、設定ファイルの読込範囲、モジュール出力を使った修正を解説します。"
tags: ["Terraform"]
images: ["og/posts/terraform_reference_to_undeclared_resource.png"]
errorCode: "Reference to undeclared resource"
urgency: "medium"
service: "Terraform"
error_type: "undeclared_resource"
components: ["Terraform", "HCL", "module"]
related_services: []
trend_incident: false
publish_slug: "terraform_reference_to_undeclared_resource"
publish_note: "新規作成。未宣言参照の診断、data参照の提案、モジュールの読込範囲、output経由の参照、tryの制限、インスタンスキー指定漏れとの違いをTerraform公式文書・本体実装で照合。hashicorp/terraform#24402の実例を確認。コード例の実行検証は未実施"
publish_zenn: true
---

## 冒頭まとめ

`terraform plan`や`terraform validate`で次の[エラー](/glossary/エラー/)が出た場合、参照先のリソースが現在の[モジュール](/glossary/モジュール/)に宣言されていません。

```text
Error: Reference to undeclared resource

A managed resource "aws_security_group" "main" has not been declared in the root module.
```

最初に、説明文の型名`aws_security_group`とラベル名`main`を確認してください。同じ[モジュール](/glossary/モジュール/)内に`resource "aws_security_group" "main"`という宣言があるかを探します。ラベルのタイプミス、`data.`の付け忘れ、別[モジュール](/glossary/モジュール/)のリソースを直接参照していることが主な確認点です。

[クラウド](/glossary/クラウド/)上やstateにリソースが存在していても、設定内の宣言の代わりにはなりません。参照している式と、その式から見える宣言を確認する必要があります。

## エラーメッセージの意味

通常の管理対象リソースは`<型名>.<ラベル名>.<属性名>`で参照します。たとえば`aws_security_group.main.id`では、`aws_security_group`が型、`main`がresourceブロックのラベル、`id`が[属性](/glossary/属性/)です。

ラベルはTerraformの設定内で使う名前です。[AWS](/glossary/aws/)側の名前を[設定](/glossary/設定/)する`name = "web-sg"`などの値とは別なので、そこが一致していても参照は成立しません。

Terraformの[参照の公式文書](https://developer.hashicorp.com/terraform/language/expressions/references)は、管理対象リソース、データソース、[モジュール](/glossary/モジュール/)出力を別の形式として説明しています。

| 参照先 | 参照の形式 |
|---|---|
| 管理対象リソース | `aws_instance.web.id` |
| データソース | `data.aws_ami.ubuntu.id` |
| 子[モジュール](/glossary/モジュール/)の出力 | `module.network.vpc_id` |
| 入力変数 | `var.instance_count` |
| ローカル値 | `local.common_tags` |

本体の[evaluate_valid.go](https://github.com/hashicorp/terraform/blob/main/internal/terraform/evaluate_valid.go)では、参照している[モジュール](/glossary/モジュール/)の[設定](/glossary/設定/)からリソース宣言を探し、見つからなければこの診断を作ります。stateに記録されているかを調べることで、未宣言の参照を有効にする処理ではありません。

## 最初に型名・ラベル名・読込範囲を確認する

[エラー](/glossary/エラー/)に表示された[ファイル](/glossary/ファイル/)と行は、問題の参照が書かれた場所です。そこから参照先の宣言を探してください。

`resource "aws_security_group" "web"`しかないのに`aws_security_group.main.id`を参照していれば、ラベル名が違っています。エディターの[検索](/glossary/検索/)で、型名とラベル名をそれぞれ確認できます。

宣言が別[ファイル](/glossary/ファイル/)にある場合は、その[ファイル](/glossary/ファイル/)の場所も確認します。同じ[ディレクトリ](/glossary/ディレクトリ/)の`.tf`・`.tf.json`は一つの[モジュール](/glossary/モジュール/)として読み込まれますが、サブディレクトリの[ファイル](/glossary/ファイル/)は自動では取り込まれません。この範囲は[設定ファイルの公式文書](https://developer.hashicorp.com/terraform/language/files)に明記されています。

たとえば、`main.tf`と同じ場所の`resources.tf`へ宣言を移すだけなら同じ[モジュール](/glossary/モジュール/)です。`modules/network/main.tf`へ移した場合は別[モジュール](/glossary/モジュール/)になるため、元の場所から同じ参照を続けることはできません。

[CLI](/glossary/cli/)では通常、[コマンド](/glossary/コマンド/)を実行した[ディレクトリ](/glossary/ディレクトリ/)がルートモジュールです。ローカルとCIで結果が違う場合は、実行[ディレクトリ](/glossary/ディレクトリ/)や`-chdir`の指定、対象[ファイル](/glossary/ファイル/)がCIに含まれているかも確認してください。

## タイプミスとdata.の付け忘れを直す

タイプミスなら、参照側を実際の宣言に合わせます。次は組み込みリソース`terraform_data`を使った説明用の例です。

```hcl
resource "terraform_data" "web" {
  input = "example"
}

output "value" {
  # 誤り：mainというラベルの宣言がない
  value = terraform_data.main.output
}
```

宣言をそのまま使う場合は、outputの参照を次のように直します。

```hcl
output "value" {
  value = terraform_data.web.output
}
```

この例の`terraform_data`はTerraform 1.4以降で利用できます。[公式文書](https://developer.hashicorp.com/terraform/language/resources/terraform-data)にあるとおり、外部プロバイダーの[設定](/glossary/設定/)を必要としないリソースです。

データソースを参照している場合は、冒頭の`data.`を確認します。`data "aws_ami" "ubuntu"`という宣言に[対応](/glossary/対応/)する参照は、次の形式です。

```hcl
# 誤り：管理対象リソースとして参照している
# ami = aws_ami.ubuntu.id

# 正しいデータソースの参照
# ami = data.aws_ami.ubuntu.id
```

これは既存のresourceブロック内に書く[引数](/glossary/引数/)の抜粋です。`data.`を省くと、Terraformは`resource "aws_ami" "ubuntu"`を探します。本体実装には、同名のデータソースがある場合に`Did you mean the data resource ...?`と案内する処理もあります。候補の表示があるかどうかにかかわらず、宣言の種類を確認してください。

## 別モジュールのリソースはoutputを経由する

子[モジュール](/glossary/モジュール/)内に宣言したリソースは、呼び出し側から直接参照できません。必要な値を子[モジュール](/glossary/モジュール/)のoutputで公開します。

次は`modules/example/main.tf`に置く子[モジュール](/glossary/モジュール/)の例です。

```hcl
resource "terraform_data" "web" {
  input = "example"
}

output "value" {
  value = terraform_data.web.output
}
```

呼び出し側の`main.tf`には、moduleブロックと出力への参照を書きます。

```hcl
module "example" {
  source = "./modules/example"
}

output "value" {
  value = module.example.value
}
```

呼び出し側で`terraform_data.web.output`と書いても、その[モジュール](/glossary/モジュール/)に宣言がないため[エラー](/glossary/エラー/)になります。`module.example.terraform_data.web.output`と内部の[パス](/glossary/パス/)を連結する方法でもアクセスできません。`module.example`の後ろに指定できるのは、子[モジュール](/glossary/モジュール/)が公開した出力名です。

実際の[VPC](/glossary/vpc/)なら、子[モジュール](/glossary/モジュール/)で`output "vpc_id"`を宣言し、呼び出し側は`module.network.vpc_id`を参照する形になります。

## 宣言を削除した場合は残った参照も見直す

resourceブロックを[削除](/glossary/削除/)した後も、outputや別のリソースに参照が残っていれば停止します。[削除](/glossary/削除/)が意図どおりなら、その値を使う箇所も[削除](/glossary/削除/)するか、代わりに使う値へ変更してください。誤って[削除](/glossary/削除/)したなら宣言を戻します。

未宣言の参照を`try()`で囲んでも回避できません。

```hcl
output "value" {
  value = try(terraform_data.missing.output, null)
}
```

`terraform_data.missing`の宣言がなければ、この式も[エラー](/glossary/エラー/)になります。[tryの公式文書](https://developer.hashicorp.com/terraform/language/functions/try)は、未宣言の参照など、評価前に不正と分かる式の[エラー](/glossary/エラー/)は捕捉できないと説明しています。

実際に[hashicorp/terraform#24402](https://github.com/hashicorp/terraform/issues/24402)では、Terraform 0.12.23で未宣言の[IAM](/glossary/iam/)[ロール](/glossary/ロール/)を`try()`で参照し、代替値を指定しても`Reference to undeclared resource`になった報告があります。リソースが不要な[環境](/glossary/環境/)を作る場合も、宣言そのものを消して参照だけを残す設計ではなく、宣言と利用側の条件を揃える必要があります。

## 近いエラーとの違い

宣言が見つからない場合と、宣言はあるが参照の方法が違う場合を分けてください。

| [エラー](/glossary/エラー/) | 確認する場所 |
|---|---|
| `Reference to undeclared resource` | 型名・ラベル名に一致するリソース宣言と[モジュール](/glossary/モジュール/)の範囲 |
| `Reference to undeclared input variable` | `var.*`に[対応](/glossary/対応/)するvariableブロック |
| `Reference to undeclared module` | `module.*`に[対応](/glossary/対応/)するmoduleブロック |
| `Missing resource instance key` | `count`の番号、または`for_each`の[キー](/glossary/キー/)指定 |
| `Unsupported attribute` | 参照先の[オブジェクト](/glossary/オブジェクト/)が持つ[属性](/glossary/属性/)や、子[モジュール](/glossary/モジュール/)の出力名 |
| `Unsupported argument` | ブロック内に書いた引数名 |

たとえば、`for_each`で宣言したリソースの[属性](/glossary/属性/)を参照するなら、`aws_instance.web["app"].id`のように[インスタンス](/glossary/インスタンス/)を指定します。宣言があるのに[キー](/glossary/キー/)を省いて[属性](/glossary/属性/)へアクセスした場合は、未宣言ではなく`Missing resource instance key`の診断になります。集合全体を参照する式では、[キー](/glossary/キー/)を省くこと自体が誤りとは限りません。

引数名の誤りは[TerraformのUnsupported argument](/posts/terraform_unsupported_argument/)も参照してください。

## 解決手順のまとめ

[エラー](/glossary/エラー/)の説明文から型名とラベル名を取り出し、現在の[モジュール](/glossary/モジュール/)内に同じ宣言があるかを確認します。宣言があるなら参照名と`data.`の有無を直し、別[モジュール](/glossary/モジュール/)ならoutputを経由してください。宣言を[削除](/glossary/削除/)した場合は、残っている利用側も見直します。

修正後は、対象[ディレクトリ](/glossary/ディレクトリ/)で[設定](/glossary/設定/)を検証します。

```bash
terraform validate
```

まだ[初期化](/glossary/初期化/)していない検証用[ディレクトリ](/glossary/ディレクトリ/)では、先に次を実行します。

```bash
terraform init -backend=false
terraform validate
```

[validateの公式文書](https://developer.hashicorp.com/terraform/cli/commands/validate)は、検証前に必要な[モジュール](/glossary/モジュール/)とプロバイダーの[インストール](/glossary/インストール/)が必要で、[バックエンド](/glossary/バックエンド/)を使わず[初期化](/glossary/初期化/)する場合に`-backend=false`を使えると説明しています。validate自体はリモートのリソースを変更しません。

通常の運用環境では、[バックエンド](/glossary/バックエンド/)などの[初期化](/glossary/初期化/)を済ませたうえで`terraform plan`も確認してください。検証が通ることと、意図した変更だけが計画されることは別です。この記事の[コード](/glossary/コード/)例は公式文書と実装を照合した説明用の例で、実行結果は掲載していません。

免責事項：本記事の内容は一般的な情報提供を目的としています。実際の[設定変更](/glossary/設定変更/)は、利用しているTerraformの[バージョン](/glossary/バージョン/)と[環境](/glossary/環境/)を確認したうえで行ってください。
