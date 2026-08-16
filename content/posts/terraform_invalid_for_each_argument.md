---
title: "Invalid for_each argument：原因と解決策"
date: 2026-08-07
description: "for_each が未確定値・list・機密値を拒むのは、3つの別々な制限ではありません。渡した値は文字列をキーとする対応表に変換され、そのキーがそのままインスタンスのアドレスになります。アドレスは計画時に確定し、並び順に左右されず、画面と記録に平文で出ます。3つの制限はすべてこの1点から出ています。"
tags: ["Terraform"]
images: ["og/posts/terraform_invalid_for_each_argument.png"]
errorCode: "Invalid for_each argument"
lastmod: 2026-08-07
service: "Terraform"
error_type: "Invalid for_each argument"
components: ["HCL", "resource expansion"]
related_services: ["Terraform CLI", "HCP Terraform"]
trend_incident: false
---

## 冒頭まとめ

`Invalid for_each argument` が拒む理由は3系統です。apply の後でないと決まらない値、map でも文字列の集合でもない値、機密の印が付いた値。別々の制限に見えますが、由来は1つです。

`for_each` に渡した値は、最終的に文字列を[キー](/glossary/キー/)とする対応表へ変換されます。そしてその[キー](/glossary/キー/)が、そのまま[インスタンス](/glossary/インスタンス/)のアドレスになります。公式ドキュメントは、Terraform が[インスタンス](/glossary/インスタンス/)を map の[キー](/glossary/キー/)または集合の要素で識別すること、アドレスが `<種別>.<名前>[<キー>]` の形になることを明記しています。`aws_iam_user.the-accounts["Todd"]` の角括弧の中身が、渡した値から来ているという意味です。

アドレスには3つの条件が要ります。計画の時点で確定していること、並び順に左右されないこと、画面と記録に平文で出せることです。未確定値は1つ目を、list は2つ目を、機密値は3つ目を満たしません。制限を1つずつ避けようとすると行き詰まりますが、[キー](/glossary/キー/)の条件として捉えると3つとも同じ方向で解けます。

つまりこの[エラー](/glossary/エラー/)は、値の書き方を咎めているのではありません。[インスタンス](/glossary/インスタンス/)の名前として使えない値が渡された、と言っています。直す先は式ではなく、何を[キー](/glossary/キー/)にするかという設計です。

## エラーの概要

出力は3つの部分でできています。先頭の要約、対象の位置、そして理由を述べる本文です。次は実際に報告された表示です。

```text
Error: Invalid for_each argument
  on .terraform/modules/aks_primary/resource-tls.tf line 7, in resource "tls_private_key" "this":
   7:   for_each = var.ssh_key == null ? { "key" = {} } : {}
    ├────────────────
    │ var.ssh_key has a sensitive value
Sensitive values, or values derived from sensitive values, cannot be used
as for_each arguments. If used, the sensitive value could be exposed as a
resource instance key.
```

罫線の部分は補助情報で、式の中のどの[変数](/glossary/変数/)が問題なのかを示します。ここに名前が出ていれば、追う対象はその[変数](/glossary/変数/)です。

要約の文言は2種類です。多くは `Invalid for_each argument` ですが、集合の中身に問題がある場合だけ `Invalid for_each set argument` になります。要素の型が文字列でない場合と、要素に null が混じっている場合がこちらです。見るべき場所が変わるので、まずここを確認してください。

理由を述べる本文は、実装で固定の文字列として定義されています。代表的なものは5つです。未確定値なら `cannot be determined until apply` を含む長い説明、型違いなら `the "for_each" argument must be a map, or set of strings, and you have provided a value of type ...`、機密値なら `Sensitive values, or values derived from sensitive values, cannot be used as for_each arguments.`、null なら `the given "for_each" argument value is null. A map, or set of strings is allowed.`、集合の要素型違いなら `"for_each" supports maps and sets of strings, but you have provided a set containing type ...` です。

## まず最初に：本文の1文目で系統を分ける

推測の前に、本文の書き出しだけを読みます。`The "for_each" map includes keys derived from` または `The "for_each" set includes values derived from` で始まっていれば未確定値の系統で、原因1に進みます。`The given "for_each" argument value is unsuitable:` で始まっていれば型か中身の問題で、原因2または原因4です。`Sensitive values,` で始まっていれば原因3、`The given "for_each" value is derived from an ephemeral value` なら原因3の後半です。

型違いの場合は、末尾に実際の型名が入っています。`list of string` なら list を渡していて、`tuple` なら角括弧で直接書いた並びを渡しています。ここを読めば、次の一手はほぼ決まります。

## よくある原因と解決手順

### 原因1：apply の後でないと決まらない値をキーにしている

別のリソースが作られてはじめて分かる[属性](/glossary/属性/)を、[キー](/glossary/キー/)の側に使っている場合です。公式ドキュメントは、`for_each` が反復するすべての値が遠隔操作の前に確定していなければならず、作成後にしか分からない一意な識別番号などを参照すると[エラー](/glossary/エラー/)になる、と明記しています。

実装が示す対処も明確です。未確定値の説明文には、[キー](/glossary/キー/)を[設定ファイル](/glossary/設定ファイル/)側に固定で書き、apply の後で決まる結果は値のほうにだけ置くのがよい、と書かれています。集合を使っている場合は、集合をやめて map にするよう案内されます。

**Before（作成後に決まる値を集合にしている）：**

```hcl
resource "aws_route53_record" "this" {
  for_each = toset([for s in aws_instance.web : s.private_ip])
  records  = [each.value]
}
```

**After（[キー](/glossary/キー/)は設定側の名前、値だけが後から決まる）：**

```hcl
resource "aws_route53_record" "this" {
  for_each = { for k, s in aws_instance.web : k => s.private_ip }
  records  = [each.value]
}
```

ここで `aws_instance.web` 自身も `for_each` で作られている前提です。その場合[キー](/glossary/キー/)は設定側で決めた名前なので、確定しないのは値だけになります。

説明文にはもう1つ、`-target` で先に依存先だけ適用し、2回に分けて収束させるという案内も入っています。ただし一時的な回避なので、設定を変えない限り次に作り直すときも同じ場所で止まります。

### 原因2：list や tuple を渡している

`for_each` は list を受け付けません。ここは型の好みではなく、公式ドキュメントが理由を書いています。変換の際に予期しない動きが起きるのを防ぐため、list や tuple を集合へ暗黙に変換しない、という方針です。

背景は[キー](/glossary/キー/)の安定性です。list から[キー](/glossary/キー/)を作れば並び順の番号になり、途中の要素を1つ消すと以降がすべてずれて別の[インスタンス](/glossary/インスタンス/)扱いになります。`count` で起きる作り直しと同じ現象で、`for_each` はこれを避けるために作られています。

**Before（並びをそのまま渡している）：**

```hcl
resource "aws_iam_user" "this" {
  for_each = var.user_names
  name     = each.value
}
```

**After（名前を[キー](/glossary/キー/)にして固定する）：**

```hcl
resource "aws_iam_user" "this" {
  for_each = toset(var.user_names)
  name     = each.value
}
```

`toset()` を掛ければ通りますが、[キー](/glossary/キー/)は要素の値そのものになります。名前を変えると作り直しになるため、値が変わりうるものを扱うなら map にして、変わらない識別子を[キー](/glossary/キー/)に置いてください。

### 原因3：機密値または一時値が混じっている

機密の印が付いた値は使えません。実装のコメントは理由を1行で述べています。使えてしまうと、機密の[キー](/glossary/キー/)が[インスタンス](/glossary/インスタンス/)のアドレスの一部として露出するためです。公式ドキュメントも、Terraform がこの値を[インスタンス](/glossary/インスタンス/)の識別に使い、必ず画面に出す、と書いています。

見落としやすいのは、[キー](/glossary/キー/)として使っていなくても拒まれる点です。ほとんどの[関数](/glossary/関数/)は機密の値を[引数](/glossary/引数/)に取ると結果にも印を付けるため、判定に使っただけで伝わります。

一時値にも同じ形の制限があります。実装のコメントによれば、[インスタンス](/glossary/インスタンス/)の[キー](/glossary/キー/)は計画と適用をまたいで保持される一方、一時値は保持されないためです。

**Before（機密の値を条件に使っている）：**

```hcl
for_each = var.ssh_key == null ? { "key" = {} } : {}
```

**After（隠す必要がない部分だけ印を外す）：**

```hcl
for_each = nonsensitive(var.ssh_key == null) ? { "key" = {} } : {}
```

`nonsensitive()` は印を外して中身を露出させる[関数](/glossary/関数/)です。公式ドキュメントは、無差別に使うと本来隠されるはずの値が平文で出ると警告しています。使うのは、機密の部分が結果から取り除かれていると自分で確認できる場合だけにしてください。map の[キー](/glossary/キー/)だけが必要なら、`toset([for k, v in local.map : k])` のように取り出す書き方も案内されています。

### 原因4：null が混じっている

値そのものが null の場合と、集合の要素に null が混じっている場合の2つがあります。前者は `Invalid for_each argument`、後者は `Invalid for_each set argument` として出ます。

要素の null が拒まれる理由も実装に書かれています。null を含む集合は対応表へ変換できないためです。`for` 式の中で条件に合わない要素を除外したつもりが、除外されずに null として残っている場合によく起きます。

**Before（値が入っていない要素が null のまま残る）：**

```hcl
for_each = toset([for u in var.users : u.nickname])
```

**After（null を取り除いてから集合にする）：**

```hcl
for_each = toset(compact([for u in var.users : u.nickname]))
```

`compact()` は、文字列の並びから null と空文字の要素を取り除く[関数](/glossary/関数/)です。取り除いた結果として要素数が変わる点には注意してください。

### 原因5：毎回結果が変わる関数を使っている

公式ドキュメントは、`uuid`・`bcrypt`・`timestamp` のような純粋でない[関数](/glossary/関数/)の結果に依存した[キー](/glossary/キー/)を使えないと明記しています。理由は、これらの評価が主要な評価段階では先送りされるためです。結果として未確定値と同じ扱いになり、原因1と同じ本文が出ます。

対処は置き換えになります。一意な名前が必要なら、設定側で決めた文字列か、`random_id` のように状態へ[保存](/glossary/保存/)される値を使ってください。

## 補足：似ているが別のもの

`Invalid count argument` は `count` 側の同じ性質の診断です。未確定値の場合の本文は `The "count" value depends on resource attributes that cannot be determined until apply, so Terraform cannot predict how many instances will be created.` で、こちらも[インスタンス](/glossary/インスタンス/)の数が計画時に決まらないことを問題にしています。ただし `count` は[キー](/glossary/キー/)が番号なので、機密値や型の制限はありません。

`Unsupported argument` は、[引数](/glossary/引数/)の名前がその位置に存在しない場合の診断です。`for_each` の値ではなく、書いた引数名の側の問題です（[Terraform の Unsupported argument の記事](/posts/terraform_unsupported_argument/)）。

`import` ブロックで `for_each` を使っている場合は、未確定値の本文が別になります。`Terraform cannot determine the full set of values that might be used to import this resource` という文で、取り込む対象を列挙できないという意味です。

`Reference to "each" in context without for_each` は別の診断です。本文は `The "each" object can be used only in "module" or "resource" blocks, and only when the "for_each" argument is set.` で、`for_each` を書いていないブロックで `each` を参照した場合に出ます。

## 切り分けの順序

1. 要約が `Invalid for_each argument` か `Invalid for_each set argument` かを見る。後者なら集合の中身の問題に絞られる。
2. 本文の1文目を読み、未確定値・型違い・機密値・null・一時値のどれかに振り分ける。
3. 罫線の中に[変数](/glossary/変数/)名が出ていれば、追う対象をその[変数](/glossary/変数/)に固定する。
4. 型違いなら、本文末尾の型名を読む。`list of string` か `tuple` かで直し方が変わる。
5. `terraform console` で実際の値と型を確認する。設定の読み方と実際の値がずれていることがある。
6. 未確定値なら、[キー](/glossary/キー/)に使っている参照が他のリソースの[属性](/glossary/属性/)かどうかを確認する。
7. 機密値なら、どの[変数](/glossary/変数/)から印が伝わっているかを宣言までさかのぼる。
8. [キー](/glossary/キー/)を変える方針が決まったら、既存の[インスタンス](/glossary/インスタンス/)が作り直しにならないよう移動の指定を先に用意する。

## 確認コマンド集

```bash
# 1. 型と中身の誤りだけを先に洗い出す（遠隔操作を伴わない）
terraform validate

# 2. 渡している値の型を確認する（list of string などが表示される）
echo 'type(var.user_names)' | terraform console

# 3. 値そのものを表示して、null が混じっていないか確認する
echo 'var.user_names' | terraform console

# 4. 機密の印が付いているかを確認する（付いていれば表示が伏せられる）
echo 'var.ssh_key' | terraform console

# 5. 機密として宣言されている変数を設定ファイルから探す
grep -rn "sensitive[[:space:]]*=[[:space:]]*true" *.tf

# 6. 未確定値のときに、依存先だけを先に適用する（一時的な回避）
terraform apply -target=aws_instance.web

# 7. 状態に記録されているインスタンスのアドレスを一覧する
terraform state list

# 8. キーを変える場合に、作り直しを避けて付け替える
terraform state mv 'aws_iam_user.this["0"]' 'aws_iam_user.this["alice"]'
```

## Editor's Note

[キー](/glossary/キー/)に使っていなければ機密値でも通るはずだ、という直感がなぜ通らないのかは、[hashicorp/terraform の Issue #34061](https://github.com/hashicorp/terraform/issues/34061) に残っています。2023年10月11日に開かれ、既に閉じられています。

報告者が書いたのは、機密の[変数](/glossary/変数/)が null かどうかで分岐し、結果として空の map か1要素の map を渡すという式でした。機密の値そのものは[キー](/glossary/キー/)になりません。それでも `Invalid for_each argument` が出ます。報告者は、判定に使っただけであることを Terraform が理解すべきだと述べています。

これに対する開発側の回答が、制限の由来を示しています。Terraform から見れば、その値が null かどうかという事実自体が隠すべき情報かもしれない。もしこの式を許せば、計画の出力を見た人は[インスタンス](/glossary/インスタンス/)が0個か1個かを知ることができ、そこから値が null かどうかが分かってしまう。だから拒む、という説明です。[キー](/glossary/キー/)として表示されるかどうかではなく、[インスタンス](/glossary/インスタンス/)の個数という間接的な情報まで含めて判断していることになります。

示された解決は `nonsensitive()` を使い、null かどうかを明かしてよいと自分で宣言する方法でした。回答には、機密値の扱いは既定で意図的に慎重にしてあり、うっかり漏らすより[エラー](/glossary/エラー/)を返すほうがよいという前提が置かれている、とも書かれています。`nonsensitive()` は、その慎重さが過剰な場面で、何を隠すべきかを知っている人が上書きするための手段だという位置づけです。

この経緯を踏まえると、3つの制限の読み方が変わります。Terraform は値の型を検査しているのではなく、その値が[インスタンス](/glossary/インスタンス/)の名前として耐えられるかを検査しています。名前は消せず、隠せず、計画の時点で決まっていなければなりません。`for_each` に何を渡すかは、書き方の選択ではなく、何をもって[インスタンス](/glossary/インスタンス/)を識別するかという設計の選択です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*