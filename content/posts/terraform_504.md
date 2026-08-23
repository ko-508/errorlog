---
title: "Terraform の 504 エラー：原因と解決策"
date: 2026-07-28
description: "Terraform で出る 504 は、出どころがレジストリ、プロバイダ経由のクラウド API、経路上の中継役の3つに分かれ、対処もそれぞれ違います。最も重要な性質は、504 が失敗の通知ではなく結果不明の通知だという点です。作成の操作では、向こう側では出来上がっているのに Terraform だけが失敗として扱う場合があります。"
tags: ["Terraform"]
errorCode: "504"
lastmod: 2026-07-28
service: "Terraform"
error_type: "504"
components: ["Registry", "Provider"]
related_services: ["Terraform Registry", "AWS", "HCP Terraform"]
trend_incident: false
---

## 冒頭まとめ

504 Gateway Timeout は、要求を取り次いだ中継役が、その先からの応答を待ちきれずに返す[エラー](/glossary/エラー/)です。Terraform で目にする場合、出どころは3つに分かれます。本体が[レジストリ](/glossary/レジストリ/)や配布元へ問い合わせたとき、プロバイダが[クラウド](/glossary/クラウド/)の窓口へ要求したとき、そして経路上の[プロキシ](/glossary/プロキシ/)や振り分け装置が返したときです。どの段階で出たかによって、調整できる場所も、調整すべき値も変わります。

先に押さえるべき性質が1つあります。504 は「失敗した」という通知ではありません。「待っていた側が待つのをやめた」という通知です。要求を受け取った先が処理を続けている可能性は残ります。作成の操作でこれを受けると、[クラウド](/glossary/クラウド/)側には資源が出来上がっているのに Terraform は失敗として扱う、という食い違いが起きます。したがって、504 を受けたあとに最初にやるべきは再実行ではなく、実際に出来ているかどうかの確認です。

再試行の作法も段階ごとに違います。本体が[レジストリ](/glossary/レジストリ/)へ問い合わせる部分は、既定で1回しか再試行しません。合計2回で諦める設計で、失敗時の文言に「2回試した」と出るのはこのためです。この回数は[環境変数](/glossary/環境変数/)で増やせます。一方、プロバイダが[クラウド](/glossary/クラウド/)の窓口を叩く部分は、各社の実装に従います。たとえば [AWS](/glossary/aws/) の実装では 500・502・503・504 が再試行の対象と定義され、既定の試行回数は3回です。[AWS](/glossary/aws/) のプロバイダはこれを25回まで引き上げています。

もう1つ、待ち時間の作法にも癖があります。共通して使われている再試行の仕組みでは、待ち時間は1秒から始めて倍々に増え、上限は30秒です。応答に含まれる待機の指示は 429 と 503 のときだけ読み取られ、504 では読み取られません。

## エラーの概要

段階ごとに出方が違います。まず、`terraform init` の段階で[レジストリ](/glossary/レジストリ/)や配布元から返る場合です。

```text
Error: Failed to install provider

Error while installing example/example v1.2.3: unsuccessful request to
https://releases.example.com/terraform-provider-example_1.2.3_linux_amd64.zip:
504 Gateway Timeout
```

[レジストリ](/glossary/レジストリ/)への問い合わせ自体が繰り返し失敗した場合は、再試行の回数を含む形になります。

```text
Error: Failed to query available provider packages

Could not retrieve the list of available versions for provider example/example:
the request failed after 2 attempts, please try again later:
504 Gateway Timeout returned from https://registry.terraform.io/v1/providers/...
```

この「2回試した」という数字は、既定の再試行回数が1回であることに対応しています。ソースでは、この文言を組み立てる処理が再試行の上限に達したときに呼ばれ、試行回数を添えるようになっています。

次に、`terraform plan` や `terraform apply` の途中で、プロバイダが[クラウド](/glossary/クラウド/)の窓口から受け取る場合です。この場合、どの資源の処理で起きたかが示されます。

```text
Error: Unable to create item

Received "504 Gateway Timeout" for "/v1/vaults/<ID>/items"

  on secrets.tf line 1, in resource "example_item" "my_secret":
   1: resource "example_item" "my_secret" {
```

3つ目は、経路上の[プロキシ](/glossary/プロキシ/)や振り分け装置が返す場合です。この場合、応答の中身が各社の[エラー](/glossary/エラー/)形式ではなく、中継役が生成した簡素な HTML になっていることがあります。応答本文を見れば区別が付きます。

## まず最初に：どの段階で出たかを確定する

第一に、`init` の途中か、`plan` や `apply` の途中かを見ます。`init` なら[レジストリ](/glossary/レジストリ/)や配布元、それ以降ならプロバイダ経由の[クラウド](/glossary/クラウド/)の窓口です。この区別だけで、触るべき設定が半分に絞れます。

第二に、`apply` の途中で出た場合は、操作の種類を見ます。読み取りなら再実行して構いません。作成・更新・[削除](/glossary/削除/)なら、実際にどうなったかを先に確認します。504 は結果不明の通知なので、確認せずに再実行すると、二重に作ってしまう恐れがあります。

第三に、応答の出どころを確かめます。各社の窓口が返す[エラー](/glossary/エラー/)には、たいてい機械が読める識別子や要求の追跡番号が含まれます。それが無く、簡素な HTML だけが返っている場合、応答を作ったのは[クラウド](/glossary/クラウド/)側ではなく、手前の中継役です。

## よくある原因と解決手順

### 原因1：init の段階で、レジストリや配布元から返る

一時的な混雑で起きることが多い形です。本体側の再試行が既定で1回しかないため、少し混んでいるだけでも諦めてしまいます。

**Before（既定のまま実行して、2回で諦める）：**

```bash
terraform init
# → the request failed after 2 attempts, please try again later
```

**After（再試行の回数を増やす）：**

```bash
export TF_REGISTRY_DISCOVERY_RETRY=5
terraform init
```

問い合わせ1回あたりの待ち時間も[環境変数](/glossary/環境変数/)で変えられます。既定は10秒です。応答が遅い経路を通っている場合は、こちらも伸ばします。

```bash
export TF_REGISTRY_CLIENT_TIMEOUT=30
```

繰り返し同じ場所で止まる場合は、混雑ではなく経路の問題を疑います。手元から直接叩いて、どこで止まるかを見てください。

```bash
curl -sS -o /dev/null -w "status:%{http_code} time:%{time_total}\n" \
  https://registry.terraform.io/.well-known/terraform.json
```

[自動化](/glossary/自動化/)の中で繰り返し実行するなら、取得結果を手元に持つ方法もあります。プロバイダの[ファイル](/glossary/ファイル/)をあらかじめ置いておけば、実行のたびに外へ出る必要がなくなります。

### 原因2：プロバイダがクラウドの窓口から受け取る

`plan` や `apply` の途中で出る形です。調整できるのはプロバイダ側の再試行の設定です。値の名前と既定値はプロバイダごとに違うので、使っているプロバイダの文書を確認してください。

[AWS](/glossary/aws/) の場合、実装として 500・502・503・504 が再試行の対象と定義され、既定の試行回数は3回です。ただし [AWS](/glossary/aws/) のプロバイダはこれを引き上げており、既定で25回になっています。設定で変えられます。

**Before（既定のまま、途中で諦める）：**

```hcl
provider "aws" {
  region = "ap-northeast-1"
}
```

**After（再試行の回数を明示する）：**

```hcl
provider "aws" {
  region      = "ap-northeast-1"
  max_retries = 30
}
```

再試行を増やしても直らない場合、待ち時間の上限が短すぎるのではなく、その操作自体が窓口の想定より長いという可能性があります。作成に時間がかかる資源では、資源側の待ち時間の設定を使います。

```hcl
resource "example_resource" "this" {
  # ...

  timeouts {
    create = "60m"
    update = "60m"
    delete = "30m"
  }
}
```

この設定に対応しているかは資源ごとに違います。文書に記載が無い資源では使えません。

### 原因3：504を受けたが、実際には作られている

最も注意が必要な形です。中継役が待つのをやめただけで、その先では処理が完了していることがあります。この場合、[クラウド](/glossary/クラウド/)側には資源があり、Terraform の状態には無い、という食い違いが残ります。

再実行する前に、実際にどうなっているかを確認してください。

```bash
# 1. 状態と実物の差を見る
terraform plan

# 2. クラウド側の窓口で直接確認する（例：AWS）
aws ec2 describe-instances --filters "Name=tag:Name,Values=example"
```

実物があるのに状態に無い場合、そのまま再実行すると二重に作ってしまいます。取り込みの操作で状態に入れてください。

```bash
terraform import example_resource.this <実物の識別子>
```

新しい書き方では、設定[ファイル](/glossary/ファイル/)に取り込みの指定を書く方法もあります。

```hcl
import {
  to = example_resource.this
  id = "<実物の識別子>"
}
```

[削除](/glossary/削除/)の操作で 504 を受けた場合も同じです。消えているのに状態に残っていれば、状態から取り除く操作が必要になります。いずれの場合も、確認が先で、実行はその後です。

### 原因4：経路上の中継役が返している

社内の[プロキシ](/glossary/プロキシ/)や振り分け装置が、その先からの応答を待ちきれずに返している形です。[クラウド](/glossary/クラウド/)側の記録には該当する失敗が残っていないのが特徴です。

確認は、詳細な[ログ](/glossary/ログ/)を採って、応答の中身と経路を見ることです。

```bash
export TF_LOG=DEBUG
export TF_LOG_PATH=./terraform-debug.log
terraform plan
grep -n "504\|Gateway Timeout\|proxy" terraform-debug.log | head -20
```

応答本文が[クラウド](/glossary/クラウド/)側の形式でなければ、中継役が作った応答です。その場合、待ち時間の設定は中継役の側にあります。Terraform 側の再試行をいくら増やしても、毎回同じ秒数で切られます。

### 原因5：長時間かかる操作を短い待ち時間で叩いている

作成に数十分かかる資源に対し、窓口側の待ち時間が数十秒しかない場合です。この構成では、504 が返るのが正常な動作で、実際の処理は裏で続きます。

この場合の正しい扱いは、待ち時間を伸ばすことではなく、完了を待つ仕組みに任せることです。プロバイダが対応していれば、要求を出したあとに完了を確認しに行く作りになっています。対応していない場合は、原因3の確認手順を毎回踏むしかありません。

## 補足：似ているが別のもの

同じ時間切れでも、Terraform 側の締め切りが先に切れた場合は 504 になりません。応答が返ってきていないので、状態[コード](/glossary/コード/)そのものが存在しないためです。この場合は `context deadline exceeded` や `Client.Timeout exceeded` といった文言になります。504 が出ているということは、中継役からの応答は届いている、ということです。

中継役がその先に繋げなかった場合は 502 で、待ちきれなかった場合が 504 です（[Terraform の 502 の記事](/posts/terraform_502/)）。応答が届かなかったのか、待ち時間が尽きたのかの違いです。

要求の頻度が多すぎて弾かれている場合は 429 で、時間切れとは別です（[Terraform の 429 の記事](/posts/terraform_429/)）。窓口の内部で処理が失敗した場合は 500 です（[Terraform の 500 の記事](/posts/terraform_500/)）。[権限](/glossary/権限/)の不足は 403 で、時間の問題ではありません（[Terraform の 403 の記事](/posts/terraform_403/)）。

なお、実行が途中で止まったまま状態の鍵が残った場合は、次の実行が別の[エラー](/glossary/エラー/)で止まります（[Terraform の state lock の記事](/posts/terraform_state_lock/)）。504 で処理が中断したあとに続けて実行する場合は、こちらも合わせて確認してください。

## 切り分けの順序

1. `init` の途中か、`plan` や `apply` の途中かを確定する。触る設定がここで半分に絞れる。
2. `apply` の途中なら、操作の種類を見る。作成・更新・[削除](/glossary/削除/)なら、再実行の前に実物を確認する。
3. 応答本文を見て、[クラウド](/glossary/クラウド/)側の形式か、中継役が作った簡素な応答かを見分ける。
4. `init` の段階なら、再試行の回数と1回あたりの待ち時間を[環境変数](/glossary/環境変数/)で増やす。
5. プロバイダ経由なら、プロバイダの再試行の設定と、資源ごとの待ち時間の設定を確認する。
6. 毎回同じ秒数で切られるなら、原因は Terraform 側ではなく中継役の設定にある。
7. 実物と状態が食い違っていたら、取り込みか除去で揃える。揃える前に再実行しない。

## 確認コマンド集

```bash
# 1. レジストリへの到達性と応答時間を確認する
curl -sS -o /dev/null -w "status:%{http_code} time:%{time_total}\n" \
  https://registry.terraform.io/.well-known/terraform.json

# 2. 再試行の回数と待ち時間を増やして init する
TF_REGISTRY_DISCOVERY_RETRY=5 TF_REGISTRY_CLIENT_TIMEOUT=30 terraform init

# 3. 詳細なログを採り、504 の出どころを探す
TF_LOG=DEBUG TF_LOG_PATH=./tf-debug.log terraform plan
grep -n "504\|Gateway Timeout" tf-debug.log | head -20

# 4. 状態と実物の差を確認する（再実行の前に必ず行う）
terraform plan

# 5. 状態に入っている資源の一覧を見る
terraform state list

# 6. 実物を状態に取り込む
terraform import <資源のアドレス> <実物の識別子>
```

## Editor's Note

504 が「失敗の通知ではない」ことを端的に示す記録があります（[504 Gateway Timeout after item is created](https://github.com/1Password/terraform-provider-onepassword/issues/5)）。2021年3月、秘密情報を管理する道具のプロバイダを使っていた投稿者が、資源の作成で 504 を受け取った、と報告しています。

読みどころは、そのあとに続く一文です。窓口側の記録を確認したところ、同じ時刻の要求は 200 で完了しており、秘密情報は意図した場所に正しく作られていた、と書かれています。投稿には窓口側の記録も貼られており、要求が受け付けられ、完了した様子がそのまま残っています。つまり、処理は成功していて、待っていた側だけが諦めていました。

この状況で Terraform をそのまま再実行すると、同じものをもう1つ作ることになります。秘密情報のような資源で二重に作られると、どちらが使われているのか分からなくなり、後始末も面倒です。504 を受けたときに再実行の前へ確認を挟むべき理由が、この1件に凝縮されています。

504 は、[エラー](/glossary/エラー/)の中でも扱いが難しい部類です。500 のように「失敗した」とは言っておらず、429 のように「あとで来い」とも言っていません。分かっているのは、待つのをやめた者がいる、ということだけです。だからこそ、再試行の回数を増やす前に、向こう側で何が起きたのかを確かめる手順を先に置いてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*