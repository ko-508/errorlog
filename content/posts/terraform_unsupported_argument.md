---
title: "Terraform Unsupported argument：原因と解決策"
date: 2026-08-06
draft: true
description: "TerraformのUnsupported argumentは、記述した引数が対象ブロックのスキーマに存在しないときに出る診断です。単純な引数名の誤りだけでなく、子moduleに未定義の入力を渡した場合や、参照したドキュメントと実際のproviderバージョンが異なる場合にも発生します。エラーが示すファイルとブロック種別、ロックされたproviderバージョンを順に確認し、どのスキーマが引数を拒否したかを切り分けます。"
tags: ["Terraform"]
images: ["og/posts/terraform_unsupported_argument.png"]
errorCode: "Unsupported argument"
urgency: "medium"
service: "Terraform"
error_type: "Unsupported argument"
components: ["HCL", "module", "provider schema"]
related_services: ["Terraform Registry"]
---

## 冒頭まとめ

`An argument named "..." is not expected here.` を見たとき、多くの人は指し示された行の書き方が間違っていると考えます。しかし、この文言は設定ファイルのボディを**あらかじめ決められたスキーマと照合**した結果として出るものです。エラーが指すのは「引数名を書いた位置」であり、その引数を受け付けない側の情報は行番号のどこにも現れません。

したがって、直すべき対象は行ではなく、**期待される引数の集合を決めている側**です。これは大きく3系統に分かれます。`resource` / `data` / `provider` ブロックなら、いま初期化済みの provider が持つスキーマ。`module` ブロックなら、子 module 側に書かれた `variable` 宣言。`terraform` や `lifecycle` のような固定ブロックなら Terraform 本体です。

この区別を飛ばすと、典型的な失敗に入ります。module 呼び出しで拒否されたのに、呼び出し側（ルート）の `variables.tf` へ同名の変数を追加してしまう例が繰り返し報告されています。宣言が必要なのは子 module の側なので、これでは通りません。また、公式ドキュメントどおりに書いたのに拒否されるという報告も多く、この場合はドキュメントの版と実際にインストールされている provider の版がずれています。

判断の起点は、エラー出力の `on ... line N, in ...` の行です。**ファイルパスと、その後ろのブロック種別**を読めば、どの系統が拒否したかがほぼ決まります。末尾に `Did you mean` が付いているかどうかも、そのまま分岐材料になります。

## エラーの概要

エラーは次の形で出ます。まず、module 呼び出しで未宣言の入力を渡した場合です。

```
Error: Unsupported argument

  on main.tf line 25, in module "sh":
  25:   num = 4

An argument named "num" is not expected here.
```

読むべきは3箇所です。1つ目は `on` に続くファイルパス。2つ目は `in` に続くブロック種別と名前。ここが `in module "sh"` なので、期待集合を決めているのは子 module の `variable` 宣言であり、provider は無関係です。3つ目は最後の行のサフィックス。この例では何も付いていません。

次に、エラー行が自分の書いたファイルではない場合です。

```
Error: Unsupported argument

  on .terraform/modules/test_db/modules/db_instance/main.tf line 34, in resource "aws_db_instance" "this":
  34:   name = var.name

An argument named "name" is not expected here.
```

パスが `.terraform/modules/` 配下です。これは `terraform init` で取得された module の中身であり、自分が編集する場所ではありません。ブロック種別が `resource "aws_db_instance"` なので、拒否しているのは AWS provider のスキーマです。

サフィックスが付く形もあります。

```
An argument named "env" is not expected here. Did you mean to define a block of type "env"?
```

この文言は、同じ名前の**ブロック型**がスキーマに存在することを示します。`env = { ... }` と書いたが `env { ... }` が正しい、という階層の取り違えです。綴りが近い別の引数がスキーマにある場合は、代わりに `Did you mean "filter"?` のような形で候補が提示されます。

## まず最初に：出力の3箇所で系統を確定する

第一に、`on` に続くファイルパスを見ます。`.terraform/modules/` 配下なら、それは自分のコードではありません。module 作者のコードと、いま入っている provider のスキーマが噛み合っていない状態です。

第二に、`in` に続くブロック種別を見ます。`module "..."` なら子 module の `variable` 宣言を、`resource` / `data` / `provider` なら provider のスキーマを調べます。ここを混同すると、まったく別の場所を探し続けることになります。

第三に、最後の行の末尾を見ます。`Did you mean "..."?` なら近い名前がスキーマに実在します。`Did you mean to define a block of type "..."?` なら同名のブロック型が存在します。何も付かない場合は、近い候補が見つからなかったということで、名前が正しいことの保証にはなりません。

第四に、対象ファイルの拡張子を確認します。`.tf.json` を使っている場合、この文言ではなく別の診断が出るため、扱う記事が変わります。

## よくある原因と解決手順

### 原因1：引数名の綴りや表記が違っている

末尾に `Did you mean "..."?` が付いている場合です。HCL は、スキーマに存在する名前のうち近いものを候補として提示します。提示された時点で、その名前がスキーマ内に実在することは確定しています。

判断材料は候補の有無だけです。候補が出たなら、まずその名前で通るかを試すのが最短です。ただし、候補が出ないケースもあります。名前を大きく間違えている場合や、そもそもその引数がこのブロックに存在しない場合です。この場合は原因2以降を疑います。

正しい引数名を一覧で確認したい場合は、初期化済みディレクトリで provider のスキーマを出力します。

```bash
terraform providers schema -json > schema.json
```

出力される JSON の構造は環境と版によって異なるため、`jq` で目的のリソースを探すより先に、まず全体をページャで開いて対象リソース名を検索するのが確実です。

**注意**：候補が提示されても、それが目的の引数とは限りません。名前が似ているだけの別の引数を提示している場合があります。採用する前に、対象 provider の版に対応するドキュメントで意味を確認してください。

### 原因2：module 呼び出しに、子 module が宣言していない入力を渡している

エラー行に `in module "<名前>":` が含まれる場合です。この系統では、期待される引数の集合は provider ではなく、**子 module 内の `variable` 宣言**で決まります。子 module が `variable "num"` を宣言していなければ、呼び出し側で `num = 4` と書いた時点で拒否されます。

ここで最も多い誤解は、呼び出し側（ルートモジュール）の `variables.tf` に同名の変数を追加すれば通るという考えです。実際に、ルートに `variables.tf` を置いているのに `module` ブロックの引数が拒否されるという報告が繰り返し出ています。ルートの変数宣言は、ルート自身が外から受け取る値を定義するものであり、子 module が受け取れる引数とは無関係です。

判断材料は、子 module 側の `variable` 宣言と呼び出し側の引数名の突き合わせです。レジストリや Git から取得した module なら、実体は `.terraform/modules/` 配下に展開されています。

```bash
# 子 module 側の variable 宣言を一覧する（<module ディレクトリ> は取得先のパス）
grep -rn 'variable "' <module ディレクトリ>
```

対処は2つです。呼び出し側の引数名を子 module の宣言に合わせるか、子 module 側に `variable` を追加します。後者は、その module を自分で保守している場合のみ選べます。

**注意**：`source` に `?ref=` や `version` を指定している場合、実際に取得されたリビジョンが期待と違う可能性があります。宣言が見つからないなら、原因3と原因4を先に確認してください。

### 原因3：インストールされている provider の版が、参照したドキュメントと違う

ドキュメントに書かれているとおりに引数を書いたのに拒否される場合です。この状態は珍しくなく、`aws_elasticache_replication_group` で「ドキュメントに載っている引数が not expected と言われる」という報告が上がっています。

構成の検証に使われるのは、レジストリのドキュメントではなく、**実際に初期化されて手元に置かれた provider が持つスキーマ**です。レジストリのドキュメントは既定で最新版を表示するため、手元の版が古ければ、まだ存在しない引数を読んでいることになります。逆に、手元の版が新しければ、削除された引数のドキュメントを読んでいる可能性があります。

判断材料は、実際に使われている版です。

```bash
# 依存している provider とその版を表示する
terraform providers
```

あわせて `.terraform.lock.hcl` を開き、対象 provider のブロックに書かれた版を確認します。その版に対応するドキュメントを読み直すのが先で、コードを書き換えるのはその後です。

**Before（エラーが起きるコード）：**

```hcl
terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # 制約なし。init のタイミングによって入る版が変わる
    }
  }
}
```

**After（修正後）：**

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> <参照しているドキュメントのメジャー.マイナー>"
    }
  }
}
```

**注意**：版を上げて解決する場合、`terraform init -upgrade` は `.terraform.lock.hcl` を書き換えます。共有リポジトリや CI では他のメンバーの実行結果にも影響するため、実行後に必ずロックファイルの差分を確認し、意図した provider だけが変わっていることを確かめてからコミットしてください。

### 原因4：引数を置く階層が違う

`Did you mean to define a block of type "..."?` が付いている場合です。このサフィックスは、同じ名前の**ブロック型**がスキーマに存在することを示します。つまり名前は合っていて、書き方だけが違います。

**Before（エラーが起きるコード）：**

```hcl
resource "example_resource" "this" {
  env = {
    KEY = "value"
  }
}
```

**After（修正後）：**

```hcl
resource "example_resource" "this" {
  env {
    KEY = "value"
  }
}
```

同じ階層の問題として、ネストされたブロックの中に置くべき引数を `resource` 直下に書いてしまう形もあります。この場合はサフィックスが付かないこともあるため、ドキュメントで引数がどのブロックに属しているかを確認します。

**注意**：逆向き、つまりブロックとして書いたが実際は属性だった場合は、`Unsupported argument` ではなく別の Summary になります。この記事の対象外です。

### 原因5：エラー行が `.terraform/modules/` 配下にある

パスが `.terraform/modules/` で始まる場合です。この配下は `terraform init` が取得した module の実体であり、自分のリポジトリの一部ではありません。

意味するところは、module 作者が書いた `resource` の引数が、いま入っている provider のスキーマと噛み合っていないということです。provider のメジャー更新で引数が削除・改称され、module がまだ対応していない状況で起こります。`.terraform/modules/test_db/modules/db_instance/main.tf` の行が指されたという報告がそのまま該当します。

判断材料は、そのファイルを自分が書いた覚えがあるかどうかです。ないなら、その行を編集しても意味がありません。編集しても `terraform init` のたびに取得元の内容へ戻り得ます。

対処は2方向あります。module 側を provider の新しい版に対応した版へ上げるか、provider の版を module が想定している範囲に固定するかです。どちらもバージョン制約の調整であり、エラー行の編集ではありません。module の版を上げる場合、引数名が変わっていることもあるため、呼び出し側の引数も合わせて見直します。

**注意**：`.terraform/` を手で削除して再取得させる手順を安易に取らないでください。private registry の認証や、ネットワークの到達性、Git の資格情報などを再度満たす必要があり、CI では初期化そのものが失敗し得ます。

### 原因6：別の診断を同じものとして調べている

進め方の誤りです。次の混同がよく起こります。

`Unsupported attribute` との混同です。こちらは式の評価時に、参照先のオブジェクトに指定の属性がないときに出ます。`= var.x.y` のような**参照側**の失敗であり、引数を定義する側の話ではありません。

`.tf.json` を使っている場合の混同です。JSON 構文では別の Summary（`Extraneous JSON object property` と `No argument or block type is named "..."`）が出ます。エラーが JSON の1行目を指すことがあり、行番号から場所を絞れません。

apply 時にクラウド API が返す `UnsupportedArgument` との混同です。こちらは `status code: 400` などを伴い、`plan` は通って `apply` で失敗します。設定のスキーマではなく、送信されたリクエストが拒否されています。

Terraform 以外の HCL ツールとの混同です。同じ文言は TFLint の `.tflint.hcl`、Packer の `.pkr.hcl`、Nomad のジョブ定義でも出ます。スキーマの持ち主がそれぞれ別なので、Terraform provider の版を調べても解決しません。エラーが指すファイルの拡張子を最初に見てください。

## 補足：似ているが別のもの

`Unsupported block type`（`Blocks of type "..." are not expected here.`）は、ブロックとして書いたものがスキーマに存在しない場合です。Summary が異なるため、出力の1行目で区別できます。`X { ... }` と書いた行が指されます。

`Missing required argument` は「余分」ではなく「不足」です。必須引数を書いていない状態を指し、`Unsupported argument` と同時に出ることがよくあります。両方が出ている場合、引数名を改称したつもりで古い名前が残っている、という構図を疑います。

`Extraneous JSON object property`（`No argument or block type is named "..."`）は、`.tf.json` を使っているときに出ます。判別材料は対象ファイルの拡張子です。JSON 構文では、エラー箇所が `on main.tf.json line 1` のように示されることがあります。

`UnsupportedArgument: The request contained an unsupported argument. status code: 400` は、provider が送信したリクエストに対するクラウド API の応答です。`status code` と `request id` を伴い、`plan` の段階では現れません。設定の検証を疑うのではなく、provider が組み立てたリクエストと API の受け付け条件を照合します。

## 危険な対応を行う前の確認

`terraform init -upgrade` は、依存関係を再解決して `.terraform.lock.hcl` を書き換えます。制約に幅がある状態で実行すると、意図していない provider まで版が動くことがあります。実行前に、`required_providers` の `version` が対象 provider に対して十分に狭いことを確認してください。実行後は必ずロックファイルの差分を読み、変わった provider が想定どおりかを確かめます。

`.terraform/` ディレクトリの削除は、module と provider の再取得を強制します。認証情報やネットワークの条件が揃っていない環境では、初期化自体が失敗して復旧に時間がかかります。手元の作業ディレクトリで、再取得に必要な資格情報が揃っていることを確認してから実行してください。

`.terraform/modules/` 配下のファイル編集は、恒久的な修正になりません。取得元の内容で上書きされ得るため、動作確認のための一時的な手段としてのみ使い、修正はバージョン制約か module 本体へ反映します。

## 切り分けの順序

1. エラー出力の `on` に続くファイルパスを読む。`.terraform/modules/` 配下なら自分のコードではないと判断する。
2. `in` に続くブロック種別を読む。`module` なら子 module の `variable`、`resource` / `data` / `provider` なら provider スキーマが期待集合の持ち主。
3. 最後の行の末尾を読む。`Did you mean "..."?` なら綴り違い、`Did you mean to define a block of type "..."?` なら階層の取り違えとして扱う。
4. 対象ファイルの拡張子が `.tf.json` でないことを確認する。`.tf.json` なら別の診断を扱う記事に移る。
5. `module` 系統なら、子 module の `variable` 宣言を `grep` で一覧し、呼び出し側の引数名と突き合わせる。ルート側の `variables.tf` は見ない。
6. `resource` 系統なら、`terraform providers` と `.terraform.lock.hcl` で実際の provider 版を確定し、その版に対応するドキュメントを読み直す。
7. 版を動かす必要があると判断した場合のみ、`required_providers` の制約を修正し、影響を確認してから `terraform init -upgrade` を実行してロックファイルの差分を読む。
8. `terraform validate` で構成の読み込みが通ることを確認し、`terraform plan` で意図した差分になっているかを見る。

## 確認コマンド集

```bash
# 1. 構成の読み込み段階で拒否されている引数を洗い出す
terraform validate

# 2. 実際に依存している provider とその版を表示する
terraform providers

# 3. ロックファイルで固定されている版を確認する
grep -A3 'provider "' .terraform.lock.hcl

# 4. バージョン制約の記述を確認する
grep -rn -A5 'required_providers' *.tf

# 5. 子 module 側の variable 宣言を一覧する（<module ディレクトリ> は取得先のパス）
grep -rn 'variable "' <module ディレクトリ>

# 6. 呼び出し側で渡している引数を一覧する
grep -n -A15 'module "<module 名>"' <呼び出し元ファイル>

# 7. provider のスキーマを出力し、正しい引数名と階層を確認する
terraform providers schema -json > schema.json

# 8. 制約を修正したうえで依存を再解決する（ロックファイルが書き換わる。差分を必ず確認する）
terraform init -upgrade
git diff .terraform.lock.hcl
```

## Editor's Note

`Unsupported argument`が多数同時に現れた場合、個々の行を独立したスペルミスとして直し始める前に、providerやmoduleのバージョンがまとめて動いていないかを確認する必要があります。

2023年6月、HashiCorpのAWS providerリポジトリには、`terraform init -upgrade`の後にAWS provider 4.xから5.xへ移行できず、複数のmodule内で多数の`Unsupported argument`が発生したという[報告](https://github.com/hashicorp/terraform-provider-aws/issues/32115)が登録されました。報告された出力では、`.terraform/modules/`配下の`aws_iam_policy_document`で`override_json`や`source_json`が拒否され、VPC moduleでは`enable_classiclink`関連の引数も拒否されています。Issueは現在クローズされていますが、ページ上で確認できる情報だけから個々の解決理由までは断定できません。

同じ月には、Terraform本体のリポジトリにも、RDS module 3.5.0の内部にある`aws_db_instance`の`name`引数が拒否された[報告](https://github.com/hashicorp/terraform/issues/33348)があります。エラーが指したのは利用者のルートmoduleではなく、`.terraform/modules/test_db/`配下でした。このIssueは`not planned`としてクローズされています。

この2件が示す診断上の要点は、**エラー行がmoduleキャッシュ内にあり、複数の引数が同時に拒否された場合、呼び出し側の綴りより先に依存関係の組み合わせを疑う**ことです。`terraform providers`と`.terraform.lock.hcl`で実際のproviderを確定し、moduleが想定する版との対応を確認してから、制約変更や`terraform init -upgrade`を判断します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*

