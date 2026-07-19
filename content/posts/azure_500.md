---
title: "Azure の 500 エラー：原因と解決策"
date: 2026-01-01
description: "Azure の 500 Internal Server Error は、返している場所で2系統に分かれます。Azure の管理 API が返す InternalServerError は Azure 側の内部エラーで、公式 SDK は既定で再試行する設計です。自分のアプリ（App Service）の500は、ASP.NET Core なら 500.30 などのサブステータスが起動失敗の種類を示します。リソースプロバイダー未登録は409、クォータは429で、500にはなりません。"
tags: ["Azure"]
errorCode: "500"
lastmod: 2026-07-15
service: "Azure"
error_type: "500"
components: ["App Service"]
related_services: ["Azure Resource Manager", "App Service", "Azure SDK"]
trend_incident: false
---

## 冒頭まとめ

Azure の 500 Internal Server Error は、まず「どの [URL](/glossary/url/) が返したか」で2系統に分けると迷いません。第一に、Azure の管理 [API](/glossary/api/)（management.azure.com への操作）や各サービスの [API](/glossary/api/) が返す500で、[エラー](/glossary/エラー/)応答の code は InternalServerError などになります。これは Azure 側の予期しない内部[エラー](/glossary/エラー/)で、手元の[リクエスト](/glossary/リクエスト/)を直して消えるものではありません。Azure の公式 [SDK](/glossary/sdk/) は、408・429・500・502・503・504 を既定の再試行対象とし、既定で合計10回まで再試行する設計になっており（Python 版 [SDK](/glossary/sdk/) の共通基盤 azure-core のソースコードで確認できます）、[SDK](/glossary/sdk/) 経由で500が[エラー](/glossary/エラー/)として見えた時点で、この再試行はすでに尽きています。第二に、自分が[デプロイ](/glossary/デプロイ/)したアプリ（App Service）の [URL](/glossary/url/) が返す500です。こちらは Azure 側の障害ではなくアプリの調査で、ASP.NET Core の場合は 500.30 のようなサブステータスが失敗の種類まで教えてくれます。

500だと思い込みやすいのに500ではない[エラー](/glossary/エラー/)も先に押さえます。リソースプロバイダーの未登録は、公式トラブルシューティング文書のある MissingSubscriptionRegistration で、実際の応答は 409 Conflict です。クォータや[スロットリング](/glossary/スロットリング/)は 429 系、テンプレートや[パラメータ](/glossary/パラメータ/)の不正は 400 系の検証[エラー](/glossary/エラー/)、権限不足は 403 の AuthorizationFailed です。「プロバイダー未登録で500」「クォータ超過で500」という説明は Azure の実際の応答と一致しません。

## エラーの概要

Azure の管理 [API](/glossary/api/) の[エラー](/glossary/エラー/)は、error [オブジェクト](/glossary/オブジェクト/)（code と message）を持つ [JSON](/glossary/json/) で返ります。500の場合の code は InternalServerError などで、message は一時的な[エラー](/glossary/エラー/)である旨と再試行の案内になっているのが典型です。切り分けでまず読むべきは [HTTP](/glossary/http/) のコードではなく、この code フィールドです。MissingSubscriptionRegistration や AuthorizationFailed のような具体的な code が入っているなら、それは500の調査ではありません。

もう1つ、Azure の応答には必ず控えるべき[ヘッダー](/glossary/ヘッダー/)があります。x-ms-request-id と x-ms-correlation-request-id です（実際の[エラー](/glossary/エラー/)応答の記録でも、この2つの[ヘッダー](/glossary/ヘッダー/)が含まれていることが確認できます）。この値は Azure 側の[ログ](/glossary/ログ/)で[リクエスト](/glossary/リクエスト/)を特定する参照 [ID](/glossary/id/) で、500が再現・継続する場合にサポートへ渡す情報の中核になります。

自分のアプリ（App Service）の500は、ブラウザにサブステータスつきのエラーページとして現れることがあります。ASP.NET Core では次の形が代表です。

```text
HTTP Error 500.30 - ANCM In-Process Start Failure
```

これは「アプリが起動そのものに失敗した」ことを示す表示で、[リクエスト](/glossary/リクエスト/)処理中の例外とは調査の入口が異なります。

## まず最初に：どの URL の500かで2つに分岐する

失敗した[リクエスト](/glossary/リクエスト/)の宛先を確認します。az [コマンド](/glossary/コマンド/)・[SDK](/glossary/sdk/)・ポータル経由のリソース操作、つまり management.azure.com や各サービスの [API](/glossary/api/) への500なら原因1です。自分のアプリの [URL](/glossary/url/)（azurewebsites.net や独自[ドメイン](/glossary/ドメイン/)）への500なら原因2です。原因1の場合は、応答の error.code を読み、InternalServerError 系であることを確認したうえで、x-ms-request-id と発生時刻を控えます。別の code が入っているなら、補足に挙げる各系統の調査に切り替えます。

## よくある原因と解決手順

### 原因1：Azure の API 側で内部エラーが起きている（InternalServerError）

Azure 側の一時的な問題で、正しい操作にも500が返ることがあります。一次対処は再試行ですが、公式 [SDK](/glossary/sdk/) を使っているなら再試行は組み込み済みです。azure-core の既定では、対象コード（408・429・500・502・503・504）に対して合計10回まで再試行し、POST や PATCH のような書き込み操作でも 500・503・504 は再試行対象に含まれます。つまり、[SDK](/glossary/sdk/) が[エラー](/glossary/エラー/)を返した時点で「もう一度だけ試す」ことに意味はほとんどなく、時間をおくか、状況を確認する段階です。[SDK](/glossary/sdk/) を介さず [HTTP](/glossary/http/) を直接呼んでいる場合は、指数[バックオフ](/glossary/バックオフ/)と回数上限つきの再試行を自分で実装します。

**Before（[SDK](/glossary/sdk/) の外側で、間隔なしの再試行を重ねてしまう）：**

```python
import requests

def call_azure(url, headers):
    while True:  # 500 のたびに即時で再送する
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r
```

**After（指数[バックオフ](/glossary/バックオフ/)と回数上限。参照 [ID](/glossary/id/) を必ず記録する）：**

```python
import random
import time

import requests

def call_azure(url, headers, max_retries=4):
    for attempt in range(max_retries + 1):
        r = requests.get(url, headers=headers)
        if r.status_code < 500:
            return r  # 4xx は再試行しても結果が変わらないため原因調査へ
        print(f"HTTP {r.status_code} x-ms-request-id={r.headers.get('x-ms-request-id')}")
        if attempt < max_retries:
            time.sleep((2 ** attempt) + random.random())  # 1,2,4,8 秒+ゆらぎ
    return r
```

書き込み操作（リソースの作成・更新）で500を受け取った場合は、応答が届かなかっただけで処理が完了している可能性を排除できません。再試行の前に対象リソースの状態を確認し、二重作成を避けてください。500が続く・広がる場合は、Azure の稼働状況（https://azure.status.microsoft）と、ポータルの Service Health を確認します。全体のステータスページに載らない規模の問題も Service Health のリソース単位の通知には出ることがあるため、両方を見るのが確実です。掲載がないことは障害でないことの証明にはなりません。解決しない場合は、控えておいた x-ms-request-id・x-ms-correlation-request-id・発生時刻を添えてサポートに問い合わせます。

### 原因2：自分のアプリ（App Service）が500を返している

App Service に[デプロイ](/glossary/デプロイ/)したアプリの [URL](/glossary/url/) が500を返す場合、原因はアプリ側にあります。ASP.NET Core では、サブステータスが調査の入口を教えてくれます。500.30（ANCM In-Process Start Failure）は、[リクエスト](/glossary/リクエスト/)処理中の例外ではなく、アプリの起動自体が失敗している状態です。公式トラブルシューティング文書（Troubleshoot ASP.NET Core on Azure App Service and IIS）が示す手順は一貫していて、アプリのイベントログを確認すること、そして stdout [ログ](/glossary/ログ/)を有効にして起動時の実際の例外を見ることです。ブラウザに出るエラーページ自体には原因が含まれないため、[ログ](/glossary/ログ/)を見えるようにすることが実質的な第一歩になります。

**Before（起動失敗の中身がどこにも出力されず、500.30 の表示だけで手掛かりがない状態）：**

```xml
<!-- web.config：stdout ログが無効のまま -->
<aspNetCore processPath="dotnet" arguments=".\MyApp.dll"
            stdoutLogEnabled="false" stdoutLogFile=".\logs\stdout" />
```

**After（stdout [ログ](/glossary/ログ/)を有効化し、起動時の実際の例外を記録させる。公式文書の手順）：**

```xml
<!-- web.config：原因調査の間だけ有効にする（恒久で有効にしない） -->
<aspNetCore processPath="dotnet" arguments=".\MyApp.dll"
            stdoutLogEnabled="true" stdoutLogFile="\\?\%home%\LogFiles\stdout" />
```

```bash
# ログをその場で流し見する
az webapp log tail --name <app-name> --resource-group <resource-group>
```

起動失敗の典型は、[設定値](/glossary/設定値/)や接続文字列の不足、参照するランタイムやフレームワークの版の不一致、起動処理内での例外です。500.30 以外のサブステータス（起動失敗の別パターン）もあり、それぞれの意味と対処は同じ公式文書に一覧があります。共通するのは、サブステータスは「どの段階で失敗したか」までしか教えないので、実際の例外はイベントログと stdout [ログ](/glossary/ログ/)で確認する、という進め方です。なお、stdout [ログ](/glossary/ログ/)はローテーションされないため、公式文書のとおり調査が済んだら無効に戻します。

## 補足：500ではない類似エラー

Azure の実際の応答では、次の問題に500以外のコードが割り当てられています。リソースプロバイダーの未登録（MissingSubscriptionRegistration、NoRegisteredProviderFound）は 409 で、公式トラブルシューティング文書に従い az provider register で該当の名前空間を登録すれば解決します。クォータ超過や[リクエスト](/glossary/リクエスト/)の集中（[スロットリング](/glossary/スロットリング/)）は 429 で、Retry-After に従って待つか、割り当ての引き上げを申請します（仕組みの考え方は [AWS の 429 の記事](/posts/aws_429/)と同型です）。テンプレートや[パラメータ](/glossary/パラメータ/)の検証[エラー](/glossary/エラー/)は 400 系で、message が名指しする項目の修正が対処です。権限不足は 403 の AuthorizationFailed で、調査は[ロール](/glossary/ロール/)割り当て（[RBAC](/glossary/rbac/)）に向けます。また、Front Door や Application Gateway を自分のアプリの前段に置いている構成では、前段が作る 502・504 は別系統の調査になります（前段のゲートウェイという構図は [Nginx の 502 の記事](/posts/nginx_502/)・[504 の記事](/posts/nginx_504/)で扱った考え方がそのまま使えます）。

## 切り分けの順序

1. 宛先を確認する。管理 [API](/glossary/api/)・サービス [API](/glossary/api/) への500なら原因1、自分のアプリの [URL](/glossary/url/) なら原因2。
2. 応答の error.code を読む。MissingSubscriptionRegistration（409）・[スロットリング](/glossary/スロットリング/)（429）・検証[エラー](/glossary/エラー/)（400）・AuthorizationFailed（403）なら、それぞれの調査に切り替える。
3. 原因1は、x-ms-request-id と時刻を控え、[SDK](/glossary/sdk/) の再試行が尽きていることを前提に、時間をおいて再実行する。書き込みは二重作成の確認を先に行う。
4. 500が続く場合は、稼働状況ページとポータルの Service Health を確認し、解消しなければ参照 [ID](/glossary/id/) を添えてサポートへ問い合わせる。
5. 原因2は、サブステータスで段階を特定し、イベントログと stdout [ログ](/glossary/ログ/)で実際の例外を確認して修正する。

## 確認コマンド集

```bash
# 1. 応答のコード・error.code・参照 ID を確認する
az rest --method get \
  --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups?api-version=2021-04-01" \
  --verbose 2>&1 | grep -iE "x-ms-request-id|error|InternalServerError"

# 2. 対象リソースの直近の操作履歴とエラーを確認する（書き込みの成否確認にも使う）
az monitor activity-log list --resource-group <resource-group> --offset 1h \
  --query "[].{op:operationName.value, status:status.value, time:eventTimestamp}" -o table

# 3. App Service のログをその場で確認する（原因2）
az webapp log tail --name <app-name> --resource-group <resource-group>

# 4. App Service のログ出力を有効化する（原因2）
az webapp log config --name <app-name> --resource-group <resource-group> \
  --application-logging filesystem --level information
```

## Editor's Note

原因2の実例として、ASP.NET Core の公式[リポジトリ](/glossary/リポジトリ/)に残る報告があります（[HTTP Error 500.30 - ANCM In-Process Start Failure](https://github.com/dotnet/aspnetcore/issues/18262)）。同じ .NET Core アプリが、ローカルでも1つ目の App Service でも問題なく動くのに、同一設定のはずの2つ目の App Service に[デプロイ](/glossary/デプロイ/)すると 500.30 で起動しない、という2020年の記録です。ブラウザに出るのは 500.30 の定型ページだけで、アプリのイベントログに残っていたのは failed to load coreclr という1行の記録でした。「コードは同じなのに、環境によって500」という原因2の典型で、エラーページの表示からは決して原因に到達できず、イベントログと stdout [ログ](/glossary/ログ/)だけが手がかりになる、という本記事の進め方がそのまま現れています。約6年前の事例ですが、ANCM がサブステータスで起動失敗を示す仕組みと、イベントログ・stdout [ログ](/glossary/ログ/)を起点にする調査手順は、現行の公式トラブルシューティング文書でも同一です。

Azure の500は、管理 [API](/glossary/api/) 側なら「参照 [ID](/glossary/id/) を控えて正しく待つ」、アプリ側なら「サブステータスで段階を特定し、[ログ](/glossary/ログ/)を見えるようにする」。どちらの500かを最初に確定すれば、やることは2つに1つです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*