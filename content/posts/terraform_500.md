---
title: "Terraform の 500 エラー：原因と解決策"
date: 2026-01-01
description: "Terraform の 500 Internal Server Error は、Terraform 自身の不具合ではなく、通信相手のサーバー内部エラーです。相手はクラウドプロバイダーの API、state を置くバックエンド、Terraform Registry の3つのどれかで、エラーメッセージ内の URL と失敗した段階から特定できます。権限不足やスロットリングでは500は返りません。"
tags: ["Terraform"]
errorCode: "500"
lastmod: 2026-07-15
service: "Terraform"
error_type: "500"
components: ["CLI"]
related_services: ["AWS", "HCP Terraform", "Terraform Registry"]
trend_incident: false
---

## 冒頭まとめ

Terraform の実行中に現れる 500 Internal Server Error は、手元で動いている Terraform 自身の不具合ではなく、Terraform が[通信](/glossary/通信/)している相手側の[サーバー](/glossary/サーバー/)内部[エラー](/glossary/エラー/)です。Terraform は多数のリモート [API](/glossary/api/) の[クライアント](/glossary/クライアント/)であり、相手は大きく3つに分かれます。plan や apply の最中にリソースを操作するクラウドプロバイダーの [API](/glossary/api/)（原因1）、state の保存や取得、リモート実行を担う[バックエンド](/glossary/バックエンド/)（HCP Terraform など。原因2）、そして terraform init でプロバイダーやモジュールを取得する Terraform Registry（原因3）です。500の調査の第一歩は、[エラーメッセージ](/glossary/エラーメッセージ/)に含まれる [URL](/glossary/url/) と、どの段階で失敗したかを読んで、この3つのどれが相手かを特定することです。

境界も先に押さえておくと迷いません。実行[アカウント](/glossary/アカウント/)の権限不足は、[クラウド](/glossary/クラウド/)側から 403 系のアクセス拒否（AWS なら AccessDenied や UnauthorizedOperation）として返り、500にはなりません。AWS の[スロットリング](/glossary/スロットリング/)は ThrottlingException（[HTTP](/glossary/http/) では 400 として現れることもあります）や 429 で、プロバイダーが自動で再試行する対象です。また、TERRAFORM CRASH という見出しとスタックトレースが出る異常終了は、[HTTP](/glossary/http/) の500ではなく Terraform 本体の[バグ](/glossary/バグ/)であり、調査の場所がまったく異なります。

## エラーの概要

Terraform の500は、相手ごとに異なる文言で現れます。いずれもメッセージの中に相手を特定する手がかりが含まれています。

クラウドプロバイダーの [API](/glossary/api/) が相手の場合、リソース操作の[エラー](/glossary/エラー/)として表示され、[リクエスト](/glossary/リクエスト/)先の[エンドポイント](/glossary/エンドポイント/)が含まれます。

```text
Error: creating EC2 Instance: 500 Internal Server Error
  on main.tf line 12, in resource "aws_instance" "example":
```

[バックエンド](/glossary/バックエンド/)が相手の場合の実例は、HashiCorp の公式文書（Terraform Enterprise の障害復旧ガイド）にそのまま掲載されています。リモートバックエンドから state を取得できなかったケースです。

```text
Error refreshing state: Error downloading state: 500 Internal Server Error
```

この Error downloading state という文言は、Terraform の現行ソースコード（internal/backend/remote/backend_state.go）で実装されているメッセージであり、公式文書の実[ログ](/glossary/ログ/)とも一致します。

Terraform Registry が相手の場合、terraform init のプロバイダー取得が失敗します。現行ソースコード（internal/getproviders/registry_client.go）のとおり、失敗時の文言には再試行を使い切ったことが示されます。

```text
Error: Failed to query available provider packages

Could not retrieve the list of available versions for provider hashicorp/aws:
the request failed after 2 attempts, please try again later
```

## まず最初に：URL と段階で相手を特定する

terraform init の段階で失敗し、対象がプロバイダーやモジュールの取得なら、相手は Terraform Registry です（原因3）。plan や apply の段階で、[エラー](/glossary/エラー/)に[クラウド](/glossary/クラウド/)の[エンドポイント](/glossary/エンドポイント/)（amazonaws.com、googleapis.com、azure.com など）やリソース名が含まれるなら、相手はクラウドプロバイダーの [API](/glossary/api/) です（原因1）。state の取得・保存やリモート実行の[エラー](/glossary/エラー/)（Error downloading state、app.terraform.io への[通信](/glossary/通信/)、自営の Terraform Enterprise）なら、相手は[バックエンド](/glossary/バックエンド/)です（原因2）。詳しいやり取りを見たい場合は、TF_LOG=DEBUG を付けて再実行すると、どの [URL](/glossary/url/) への[通信](/glossary/通信/)で失敗したかが[ログ](/glossary/ログ/)に残ります。

## よくある原因と解決手順

### 原因1：クラウドプロバイダーの API が内部エラーを返している

plan や apply の最中に、AWS などの[クラウド](/glossary/クラウド/)側で一時的な内部[エラー](/glossary/エラー/)が起きると、リソース操作が500で失敗します。重要なのは、ユーザーに500が見えた時点で、プロバイダーの自動再試行をすでに使い切っているという点です。AWS プロバイダーの公式文書のとおり、[スロットリング](/glossary/スロットリング/)や一時的な失敗に対しては [API](/glossary/api/) 呼び出しが指数[バックオフ](/glossary/バックオフ/)で自動的に再試行され、その回数の既定値は25回です。それでも失敗が続いた場合にだけ、[エラー](/glossary/エラー/)が表面化します。

対処は、[クラウド](/glossary/クラウド/)側のステータス確認と、時間をおいた再実行です。ただし、途中まで進んだ apply を再実行する前に、必ず plan で現状との差分を確認してください。state に記録済みのリソースは再作成されませんが、「[クラウド](/glossary/クラウド/)側では作成が完了したのに、応答が届かず state に記録されなかった」可能性は排除できないためです。plan の差分に「すでに存在するはずのリソースの新規作成」が含まれていたら、実際の状態を確認してから進めます。

**Before（再試行回数を絞っていて、一時[エラー](/glossary/エラー/)がそのまま失敗になる設定）：**

```hcl
provider "aws" {
  region      = "ap-northeast-1"
  max_retries = 1   # 高速化のつもりで絞ると、一時的な内部エラーが直撃する
}
```

**After（既定の再試行に任せる。明示するなら回数と方式を指定する）：**

```hcl
provider "aws" {
  region = "ap-northeast-1"
  # max_retries を省略すると既定値の 25 回（公式文書）。
  # 明示する場合も、一時エラーを吸収できる回数を確保する
  max_retries = 25
  retry_mode  = "standard"  # standard / adaptive（公式文書）
}
```

```bash
# 再実行の前に、二重作成がないか差分を確認する
terraform plan
```

### 原因2：state・リモート実行のバックエンドが内部エラーを返している

state の取得・保存先や、リモート実行の基盤（HCP Terraform、自営の Terraform Enterprise、その他の[バックエンド](/glossary/バックエンド/)）側の障害でも500が返ります。冒頭に示した Error downloading state: 500 Internal Server Error はこの系統で、HashiCorp 自身が障害復旧の公式文書の中で、[バックエンド](/glossary/バックエンド/)障害時に現れる[ログ](/glossary/ログ/)として例示しているものです。

この[エラー](/glossary/エラー/)は「state の[ダウンロード](/glossary/ダウンロード/)に失敗した」ことを示すだけで、state そのものが壊れたことを意味しません。手元で plan や apply を繰り返す前に、相手の復旧を確認します。HCP Terraform（app.terraform.io）が相手なら、HashiCorp の稼働状況ページ（https://status.hashicorp.com）を確認し、インシデント中なら復旧を待って再実行します。自営の Terraform Enterprise が相手なら、調査の場所は[サーバー](/glossary/サーバー/)側（アプリケーションログ、[データベース](/glossary/データベース/)、オブジェクトストレージ）に移ります。掲載が遅れることもあるため、稼働状況ページに掲載がないことは障害でないことの証明にはなりません。

### 原因3：Terraform Registry が内部エラーを返している（terraform init）

terraform init はプロバイダーとモジュールを Terraform Registry（registry.terraform.io）から取得します。[レジストリ](/glossary/レジストリ/)側の障害中は、設定を何も変えていなくても init が失敗します。現行の Terraform のソースコードのとおり、[レジストリ](/glossary/レジストリ/)への[リクエスト](/glossary/リクエスト/)は失敗時に自動で再試行されますが、既定の再試行回数は1回だけです。回数は[環境変数](/glossary/環境変数/) TF_REGISTRY_DISCOVERY_RETRY で、[タイムアウト](/glossary/タイムアウト/)秒数は TF_REGISTRY_CLIENT_TIMEOUT で変更できます。

**Before（毎回まっさらな環境でフル取得する CI。[レジストリ](/glossary/レジストリ/)の一時障害を直撃する）：**

```yaml
# CI ジョブの例：キャッシュなし・再試行は既定の1回
steps:
  - run: terraform init
```

**After（再試行を増やし、プラグインキャッシュで[レジストリ](/glossary/レジストリ/)への依存自体を減らす）：**

```yaml
steps:
  - run: |
      export TF_REGISTRY_DISCOVERY_RETRY=5   # 一時エラーの吸収
      export TF_PLUGIN_CACHE_DIR="$HOME/.terraform.d/plugin-cache"
      mkdir -p "$TF_PLUGIN_CACHE_DIR"
      terraform init
    # TF_PLUGIN_CACHE_DIR を CI のキャッシュ機構で保存・復元すると、
    # 2回目以降はレジストリからのダウンロード自体が減る
```

障害中にどうしても実行が必要な場合、.terraform [ディレクトリ](/glossary/ディレクトリ/)とプラグインキャッシュが残っている環境では、取得済みのプロバイダーがそのまま使えます。恒久策は、[キャッシュ](/glossary/キャッシュ/)の活用と、.terraform.lock.hcl を[リポジトリ](/glossary/リポジトリ/)に含めて[バージョン](/glossary/バージョン/)解決を固定することです。

## 補足：500ではない類似エラー

500の原因として語られがちですが、仕様上は別の形で現れる問題があります。実行[アカウント](/glossary/アカウント/)の権限不足は、AWS なら AccessDenied や UnauthorizedOperation を含む 403 系の[エラー](/glossary/エラー/)として返り、調査の場所は [IAM](/glossary/iam/) です。[API](/glossary/api/) の[スロットリング](/glossary/スロットリング/)は ThrottlingException（[HTTP](/glossary/http/) では 400 のこともあります）や 429 で、プロバイダーの自動再試行の対象です。再試行を使い切るほどの規模なら、並列度（terraform apply の -parallelism）や対象の分割を検討します（AWS 側の[スロットリング](/glossary/スロットリング/)の仕組みは [AWS の 429 の記事](/posts/aws_429/)を参照）。Terraform で構築した ALB や [API](/glossary/api/) Gateway が返す 503・504 は、Terraform ではなく構築した[インフラ](/glossary/インフラ/)自体の問題です（[AWS の 503 の記事](/posts/aws_503/)、[AWS の 504 の記事](/posts/aws_504/)）。TERRAFORM CRASH という見出しとスタックトレース、crash.log の生成を伴う異常終了は、[HTTP](/glossary/http/) の500ではなく Terraform 本体の[バグ](/glossary/バグ/)で、crash.log を添えて公式[リポジトリ](/glossary/リポジトリ/)に報告する対象です。state のロック取得失敗（Error acquiring the state lock）も別系統で、他の実行との競合か、前回の実行の異常終了によるロック残りの調査に切り替えます。

## 切り分けの順序

1. [エラーメッセージ](/glossary/エラーメッセージ/)の [URL](/glossary/url/) と失敗した段階を読み、相手を特定する。init とプロバイダー取得なら原因3、plan・apply 中のクラウドエンドポイントなら原因1、state・リモート実行なら原因2。
2. [権限](/glossary/権限/)[エラー](/glossary/エラー/)（403系・AccessDenied）、[スロットリング](/glossary/スロットリング/)（Throttling・429）、TERRAFORM CRASH、state ロックなら、500ではないのでそれぞれの調査に切り替える。
3. 相手側の稼働状況を確認する。クラウドプロバイダーは各社のステータスページ、HCP Terraform と Terraform Registry は status.hashicorp.com。
4. 時間をおいて再実行する。apply の再実行前には plan で差分を確認し、二重作成を防ぐ。
5. 恒久策として、プロバイダーの再試行設定（原因1）、CI のプラグインキャッシュと再試行の[環境変数](/glossary/環境変数/)（原因3）を整える。

## 確認コマンド集

```bash
# 1. 詳細ログ付きで再実行し、どの URL への通信で失敗したかを特定
TF_LOG=DEBUG terraform plan 2>&1 | grep -iE "http|error" | tail -20

# 2. Terraform Registry の疎通を Terraform を介さず確認
curl -s -o /dev/null -w "%{http_code}\n" \
  https://registry.terraform.io/v1/providers/hashicorp/aws/versions

# 3. 再実行の前に、state と実際の差分を確認（二重作成の防止）
terraform plan

# 4. レジストリ取得の再試行とタイムアウトを広げて init を再実行
TF_REGISTRY_DISCOVERY_RETRY=5 TF_REGISTRY_CLIENT_TIMEOUT=30 terraform init

# 5. 取得済みプロバイダーの確認（レジストリ障害中でも残っていれば使える）
ls .terraform/providers/registry.terraform.io/hashicorp/ 2>/dev/null
```

## Editor's Note

原因3の実例として、HashiCorp 自身が公開した稼働状況の記録があります（[Terraform Registry Degraded](https://status.hashicorp.com/incidents/01KV60Z6KMP2TGHVJYC87MK4CM)）。2026年6月、Terraform Registry が高い割合で[エラー](/glossary/エラー/)を返す状態になり、公式の告知に terraform init のワークフローとドキュメント閲覧への影響が明記されました。原因は[レジストリ](/glossary/レジストリ/)の一部機能を支える[データベース](/glossary/データベース/)で、[データベース](/glossary/データベース/)のスケールアップにより解消されています。執筆時点から約1か月前の直近の事例であり、「手元の設定を何も変えていないのに init が失敗する」という症状の裏に[レジストリ](/glossary/レジストリ/)側の障害があるという、原因3の構図をそのまま示す記録です。あわせて、init の失敗文言にある please try again later（後でやり直してください）が現行ソースコードの再試行実装（既定1回で諦める）に由来することもソースから確認でき、「待って再実行」が Terraform 自身の想定する一次対処であることが分かります。

Terraform の500は、Terraform が「どこかの[サーバー](/glossary/サーバー/)の調子が悪い」と伝えているだけで、悪いのがどこかはメッセージの中の [URL](/glossary/url/) が教えてくれます。HCL や手元の設定を疑い始める前に、まず相手を特定することが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*