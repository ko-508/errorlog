---
title: "Terraform countエラーの対処法"
date: 2026-09-24
draft: false
description: "TerraformのInvalid count argumentは、countの値が未確定、null、一時値、整数に変換できない値、負数の場合に発生します。説明文ごとの原因と安全な修正方法を解説します。"
tags: ["Terraform"]
images: ["og/posts/terraform_invalid_count_argument.png"]
errorCode: "Error: Invalid count argument"
urgency: "high"
service: "Terraform"
error_type: "Invalid count argument"
components: ["count", "plan", "meta-argument"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

`terraform plan`で次のエラーが出る場合、`count`に渡した値をリソース数として確定できません。

```text
Error: Invalid count argument
```

この見出しだけでは原因は分かりません。直後の説明文を確認してください。主な原因は、適用後でないと決まらない値、`null`、一時値、整数に変換できない値、負数です。

最も多いのは、別のリソースを作成した後で決まる属性から`count`を計算している場合です。`count`は計画時にインスタンス数を確定する必要があるため、入力変数やローカル値など、計画時に分かる値から計算する形へ変更します。

## Invalid count argumentの意味

`count`は、同じリソースやモジュールを指定した数だけ作るためのメタ引数です。たとえば`count = 3`なら、`example[0]`から`example[2]`までの3インスタンスが計画されます。

[Terraform公式のcount文書](https://developer.hashicorp.com/terraform/language/meta-arguments/count)によると、`count`が受け付けるのは整数です。さらに、一般的な引数と違い、Terraformが遠隔のリソースを操作する前に値が確定していなければなりません。

現在のTerraform実装では、`Invalid count argument`の見出しが複数の検査で共通して使われています。説明文には次のような違いがあります。

```text
The "count" value depends on resource attributes that cannot be determined until apply...
```

```text
The given "count" value is derived from an ephemeral value...
```

```text
The given "count" argument value is null. An integer is required.
```

```text
The given "count" argument value is unsuitable: <変換時のエラー>.
```

```text
The given "count" argument value is unsuitable: must be greater than or equal to zero.
```

一時値については処理経路の違いにより、ほぼ同じ内容の説明文が2種類あります。どちらも、計画と適用の間で保存できない値を`count`に使ったことを示します。正確な文面はTerraformの版によって変わる可能性があるため、見出しではなく説明の内容で判断してください。

## apply後に決まる値を使っている場合

次の説明文は、`count`の値が計画時点では未確定であることを示します。

```text
The "count" value depends on resource attributes that cannot be determined until apply,
so Terraform cannot predict how many instances will be created.
```

リソースのIDや、遠隔APIが作成時に返す値は、通常は適用するまで分かりません。その値を直接または間接的に`count`へ渡すと、Terraformは計画に必要なインスタンスのアドレスを確定できません。

次の例では、`random_integer.replica_count.result`がリソース作成後に決まるため、後続リソースの数を計画時に決められません。

```hcl
resource "random_integer" "replica_count" {
  min = 1
  max = 3
}

resource "terraform_data" "worker" {
  count = random_integer.replica_count.result
}
```

作成数を設定として決められるなら、入力変数へ移します。

```hcl
variable "replica_count" {
  type    = number
  default = 2
}

resource "terraform_data" "worker" {
  count = var.replica_count
}
```

条件によって作成するかを切り替える場合も、適用後に決まるIDではなく、明示的な真偽値を使います。

```hcl
variable "create_worker" {
  type    = bool
  default = true
}

resource "terraform_data" "worker" {
  count = var.create_worker ? 1 : 0
}
```

依存元と依存先を別のTerraform構成に分け、前段の出力を後段へ入力として渡す方法もあります。重要なのは、後段の計画を作る時点で個数が確定していることです。

## null・型・負数を修正する

`count`が`null`の場合は、整数が必要だという説明文が表示されます。入力を省略できる設計なら、変数に既定値を設定します。

```hcl
variable "instance_count" {
  type    = number
  default = 0
}

resource "terraform_data" "example" {
  count = var.instance_count
}
```

`null`に別の値を割り当てたい場合は`coalesce`も使えます。公式文書では、`coalesce`は`null`または空文字ではない最初の引数を返す関数です。

```hcl
variable "instance_count" {
  type    = number
  default = null
}

resource "terraform_data" "example" {
  count = coalesce(var.instance_count, 0)
}
```

ただし、単に省略時を0にしたいだけなら、変数の`default = 0`のほうが意図を読み取りやすくなります。

整数に変換できない値を渡すと、`value is unsuitable`に変換時のエラーが続きます。変数へ`type = number`を指定すると、不正な値を入力の検査段階で見つけられます。数字として解釈できる文字列は自動変換される場合がありますが、`"three"`のような値は数として使えません。

計算結果が負数の場合も`count`には使えません。差分を個数に使うなら、0未満にならない条件を明示します。

```hcl
locals {
  additional_count = var.desired_count > var.existing_count ? var.desired_count - var.existing_count : 0
}

resource "terraform_data" "additional" {
  count = local.additional_count
}
```

値を無条件に0へ丸める前に、負数が設定ミスを示していないか確認してください。誤った入力を隠したくない場合は、変数の検証規則で0以上を要求する方法が適しています。

## 一時値と機密値の違い

Terraform 1.10以降では、一時値を変数や一時的なリソースで扱えます。一時値は実行中には利用できますが、計画ファイルや状態ファイルには保存されません。

```hcl
variable "instance_count" {
  type      = number
  ephemeral = true
}

resource "terraform_data" "example" {
  count = var.instance_count
}
```

この構成では、一時値から`count`が導かれるため拒否されます。インスタンス数は計画と適用の間で同じ値を維持する必要があり、保存されない一時値では保証できないためです。個数を決める値は、`ephemeral = true`を付けていない通常の変数などから渡してください。

[Terraform公式の機密データ文書](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)では、一時値がTerraform 1.10以降で利用でき、計画と状態から除外されることが説明されています。

一時値と機密値は同じではありません。現在の実装では、`count`に機密値を渡すこと自体は許可されています。一方、`for_each`ではキーがインスタンスの識別子として画面に出るため、機密値を使用できません。

ただし、`count`に機密値を渡すと、作成されるインスタンス数から値が分かります。技術的に受け付けられても、秘密にしたい数値を`count`へ使う設計は避けてください。

## -targetは一時的な回避策として使う

未確定値の説明文には、依存するリソースだけを`-target`で先に適用する回避策が表示されます。

```bash
terraform apply -target=<dependency-address>
terraform apply
```

1回目で依存元を作成し、値が状態へ保存されれば、2回目の通常適用で`count`を確定できる場合があります。

ただし、[terraform planの公式文書](https://developer.hashicorp.com/terraform/cli/commands/plan#resource-targeting)は、`-target`を誤りからの復旧やTerraformの制約を回避する例外的な状況に限るよう案内しています。日常的に使うと、対象外の変更を見落とし、設定と実際の状態の関係が分かりにくくなるためです。

`-target`で依存元を適用した後は、必ずオプションなしで`terraform plan`を実行し、構成全体の差分を確認してください。継続的に二段階適用が必要なら、入力変数から個数を決めるか、構成を分割する方法を検討します。

## countとfor_eachを使い分ける

`count`と`for_each`は、どちらも複数のインスタンスを作るためのメタ引数ですが、インスタンスの識別方法が異なります。

`count`は0から始まる番号を使い、`example[0]`のように識別します。ほぼ同じ設定のリソースを指定数だけ作る場合に向いています。

`for_each`は対応表のキーまたは文字列集合の要素を使い、`example["api"]`のように識別します。インスタンスごとに名前や設定が異なる場合に向いています。

どちらも、遠隔操作の前にインスタンス数またはキーが確定している必要があります。ただし、[for_eachの公式文書](https://developer.hashicorp.com/terraform/language/meta-arguments/for_each#limitations-on-values)は機密値を明示的に禁止しています。キーが画面に表示されるためです。`count`は機密値を受け付けますが、個数は表示されます。

同じリソースまたはモジュールのブロックに、`count`と`for_each`を同時には指定できません。併用時は`Invalid count argument`とは別の設定エラーになる可能性があるため、片方だけを選んでください。

## 解決手順のまとめ

最初に`Invalid count argument`の直後を読み、未確定値、一時値、`null`、変換不能、負数のどれに該当するかを確認します。

未確定値なら、適用後に決まるリソース属性ではなく、入力変数や設定側の一覧など、計画時に分かる値から個数を計算します。`null`や型の問題は、変数へ`type = number`と適切な既定値を設定して防ぎます。負数は計算式と入力値を確認し、必要なら0以上になる条件を明示してください。

一時値は計画と適用の間で保存されないため、`count`には使用できません。機密値は現在の実装では受け付けられますが、個数が公開される点に注意が必要です。

`-target`は依存元を先に作る一時的な回避策です。使用後は構成全体の`terraform plan`を実行し、恒常的に必要なら設定の構造を修正してください。

免責事項：本記事の内容は一般的なTerraform構成を前提としています。本番環境で`terraform apply`や`-target`を実行する前に、状態の保存先、対象リソース、実行計画を確認してください。重要な環境では計画ファイルをレビューし、意図しない作成、変更、削除が含まれていないことを確認してから適用してください。
