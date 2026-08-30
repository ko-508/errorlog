---
title: "OpenAI API の 403 エラー：原因と解決策"
date: 2026-08-03
description: "OpenAI API の 403 は、公式のエラー一覧では地域の非対応が唯一の項目です。type が request_forbidden という別系統になり、判定の対象は利用者の所在地ではなく要求の送信元 IP です。残高不足やモデルの権限、キーの失効は 403 ではなく別のコードで返ります。"
tags: ["OpenAI API"]
images: ["og/posts/openai_api_403.png"]
errorCode: "403"
lastmod: 2026-08-03
service: "OpenAI API"
error_type: "403"
components: ["Authentication", "Geo Restrictions"]
related_services: ["Python SDK", "Cloud Run"]
trend_incident: false
top_queries:
- 'openai 403'
---

## 冒頭まとめ

OpenAI [API](/glossary/api/) の 403 は、公式の[エラー](/glossary/エラー/)一覧では**1項目しか定義されていません**。国・地域・領域が対応外である、というものです。

この[エラー](/glossary/エラー/)には、他と違う特徴があります。応答の `type` が `invalid_request_error` ではなく **`request_forbidden`** になります。`code` は `unsupported_country_region_territory` です。この2語が見えた時点で、系統が確定します。

そして最も重要な点です。**判定されているのは利用者の所在地ではなく、要求の送信元 [IP アドレス](/glossary/ip-アドレス/)がどこと判定されたか**です。対応国にいても、経路の途中で別の地域と判定されれば 403 になります。実際、提供元の窓口も利用者に対し、[IP アドレス](/glossary/ip-アドレス/)を教えてほしい、正しくない地域に判定されていないか確認する、と応じています。

もう1つ、[プログラム](/glossary/プログラム/)から呼んだ場合の 403 として、資源への[アクセス権](/glossary/アクセス権/)が無い場合があります。公式の[ソフトウェア](/glossary/ソフトウェア/)開発キットでは、要求した資源への[アクセス権](/glossary/アクセス権/)が無い状態として定義され、正しい[キー](/glossary/キー/)・組織 [ID](/glossary/id/)・資源 [ID](/glossary/id/) を使っているか確認するよう案内されています。

逆に、**403 だと思われがちだが違うもの**があります。残高や利用額の上限は 429、[モデル](/glossary/モデル/)への[アクセス権](/glossary/アクセス権/)は 404、[キー](/glossary/キー/)の失効や組織の不一致は 401 です。いずれも 403 では返りません。

## エラーの概要

地域の[非対応](/glossary/非対応/)は、次の形で返ります。

```json
{
  "error": {
    "code": "unsupported_country_region_territory",
    "message": "Country, region, or territory not supported",
    "param": null,
    "type": "request_forbidden"
  }
}
```

他の[エラー](/glossary/エラー/)と並べると違いが際立ちます。400 や 401 の `type` は `invalid_request_error` ですが、こちらは `request_forbidden` です。**`type` を見るだけで、内容の問題でも[認証](/glossary/認証/)の問題でもないと分かります**。

もう1つ確認すべきことがあります。**応答が [JSON](/glossary/json/) かどうか**です。上の形が返っていれば、[API](/glossary/api/) の層が判断した結果です。[JSON](/glossary/json/) ではなく HTML の遮断画面が返っている場合、判断したのは [API](/glossary/api/) の層ではなく、その手前にある仕組みです。調べる先が変わるため、本文の形式を最初に確認してください。

## まず最初に：type と送信元 IP を確認する

第一に、`type` を読みます。`request_forbidden` であれば地域の系統です。

第二に、応答が [JSON](/glossary/json/) かどうかを見ます。HTML であれば、[API](/glossary/api/) より手前の層で遮断されています。

第三に、**要求が実際にどの IP から出ているか**を確認します。手元の所在地ではなく、[プログラム](/glossary/プログラム/)が動いている[環境](/glossary/環境/)の外向き IP です。

第四に、その IP がどの地域と判定されるかを確認します。ここが自分の認識とずれていれば、原因はそこです。

## よくある原因と解決手順

### 原因1：送信元 IP が対応外の地域と判定されている

最も多い形です。特徴的なのは、**手元では通るのに配備先で失敗する**という現れ方をすることです。[キー](/glossary/キー/)も要求の内容も同じなので、原因の特定が遅れます。

疑うべきなのは、要求が自分の手を離れてから外へ出るまでの経路です。[クラウド](/glossary/クラウド/)上の実行環境、中継の[プロキシ](/glossary/プロキシ/)、配信網の実行環境、社内から外部へ出る[回線](/glossary/回線/)。**このどれかの出口 IP が判定の対象になります**。

```bash
# プログラムが動く環境の外向き IP を確認する
curl -sS https://api.ipify.org

# その環境から最小の要求を投げ、type を確認する
curl -sS https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -c "import json,sys; e=json.load(sys.stdin).get('error',{}); print(e.get('type'), '|', e.get('code'))"
```

対応地域で運用しているつもりでも、経路の途中で別の地域を通っていれば判定はそちらに従います。まず経路を把握することが先決です。

### 原因2：地理判定そのものが誤っている

対応国から呼んでいるのに 403 が返る場合です。**利用者側の設定ではなく、[IP アドレス](/glossary/ip-アドレス/)の地域判定が実態と合っていない**ことがあります。

新しく割り当てられたアドレス帯や、[クラウド](/glossary/クラウド/)事業者が特定の地域で使い始めた範囲では、判定に使われる情報が追いついていない場合があります。

この場合、[プログラム](/glossary/プログラム/)側をいくら直しても解決しません。取れる手段は2つです。

```bash
# 1. 別の実行環境（別リージョンなど）から到達するかを確認する
#    通るなら、元の環境の出口 IP に問題が絞られる

# 2. 出口 IP を控えて、提供元の窓口に確認を依頼する
curl -sS https://api.ipify.org
```

後述の実例でも、提供元の窓口が利用者に [IP アドレス](/glossary/ip-アドレス/)の共有を求め、最終的に提供元側で[修正](/glossary/修正/)されています。**利用者側で対処しきれない種類がある**と知っておくと、無駄な試行錯誤を避けられます。

### 原因3：資源へのアクセス権が無い

開発キットの区分で `PermissionDeniedError` として現れる場合です。公式の説明は、要求した資源への[アクセス権](/glossary/アクセス権/)が無い、というもので、対処として正しい[キー](/glossary/キー/)・組織 [ID](/glossary/id/)・資源 [ID](/glossary/id/) を使っているかの確認が挙げられています。

地域の系統と違い、`type` は `request_forbidden` にはなりません。**資源を特定する識別子が要求に含まれている場合**（アシスタント、[ファイル](/glossary/ファイル/)、微調整済み[モデル](/glossary/モデル/)など）に起こります。

その資源が、いま使っている[キー](/glossary/キー/)の属する[プロジェクト](/glossary/プロジェクト/)のものかを確認してください。組織や[プロジェクト](/glossary/プロジェクト/)をまたいで識別子を使い回すと、この形になります。

### 原因4：403 ではないものを 403 として調べている

下記はいずれも 403 ではありません。**この4つを 403 の原因として探すと、必ず行き止まりになります**。

残高が尽きた、あるいは支出や利用額の上限に達した場合は **429** です。公式の[エラー](/glossary/エラー/)一覧では、残高切れ、組織の支出上限、[プロジェクト](/glossary/プロジェクト/)の支出上限、承認された利用上限が、それぞれ独立した識別子として 429 の側に定義されています。

指定した[モデル](/glossary/モデル/)が存在しない、または[アクセス権](/glossary/アクセス権/)が無い場合は **404** で、`code` は `model_not_found` です。

[キー](/glossary/キー/)が失効している、組織や[プロジェクト](/glossary/プロジェクト/)と一致しない、[エンドポイント](/glossary/エンドポイント/)に必要な[権限](/glossary/権限/)が無い場合は **401** です（[OpenAI API の 401 の記事](/posts/openai_api_401/)）。IP の許可リストとの不一致も、地域の判定とは別に 401 の側で定義されています。

送った内容そのものに問題がある場合は **400** です。

### 原因5：応答が API の層から来ていない

`type` も `code` も無く、HTML の遮断画面が返っている場合です。この場合、[API](/glossary/api/) の層には到達していません。

判断したのは、経路上の防御の仕組みです。表示される内容と識別子は、その仕組みが定義したものであり、本記事の内容は当てはまりません。**まず「誰が返したか」を確定させてから調べる先を決める**、という順序は他の[エラー](/glossary/エラー/)と同じです。

## 補足：似ているが別のもの

[認証](/glossary/認証/)の失敗は 401 です。公式では 401 の原因が4種類に整理されており、そのうちの1つが IP の許可リストとの不一致です。**同じ IP に関する話でも、許可リストは 401、地域の判定は 403**、と分かれています。

上限や請求に関する[エラー](/glossary/エラー/)は 429 です。公式には、請求関連では `error.code` を見て具体的な原因を特定するよう書かれています。

他の基盤では、403 が担う範囲がまったく違います。GCP では[権限](/glossary/権限/)の不足が 403 の中心で、応答に不足している[権限](/glossary/権限/)の名前が入ります（[GCP の 403 の記事](/posts/gcp_403/)）。Azure でも同様に[権限](/glossary/権限/)や[ネットワーク](/glossary/ネットワーク/)の制御が中心です（[Azure の 403 の記事](/posts/azure_403/)）。**OpenAI [API](/glossary/api/) の 403 を他の基盤の感覚で読むと、原因を取り違えます**。

## 切り分けの順序

1. `type` を読む。`request_forbidden` なら地域の系統。
2. 応答が [JSON](/glossary/json/) かを確認する。HTML なら [API](/glossary/api/) の層に届いていない。
3. `code` が `unsupported_country_region_territory` かを確認する。
4. [プログラム](/glossary/プログラム/)が動く[環境](/glossary/環境/)の外向き IP を確認する。手元の所在地ではない。
5. 別の実行環境から到達するかを試す。通るなら出口 IP に原因が絞られる。
6. 対応地域から呼んでいるのに失敗するなら、判定の誤りを疑い、IP を控えて窓口に確認を依頼する。
7. 資源の識別子を含む要求なら、その資源が現在の[プロジェクト](/glossary/プロジェクト/)のものかを確認する。
8. 残高・[モデル](/glossary/モデル/)・[キー](/glossary/キー/)の話であれば、そもそも 403 ではない。429・404・401 を見る。

## 確認コマンド集

```bash
# 1. 状態コードと本文の形式を同時に確認する（JSON か HTML か）
curl -sS -i https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | head -20

# 2. type と code だけを取り出す
curl -sS https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -c "import json,sys; e=json.load(sys.stdin).get('error',{}); print(e.get('type'), '|', e.get('code'))"

# 3. 実行環境の外向き IP を確認する
curl -sS https://api.ipify.org; echo

# 4. コンテナや実行環境の中から確認する（配備先で実行）
docker run --rm curlimages/curl -sS https://api.ipify.org; echo

# 5. 経路を確認する（中継が挟まっていないか）
env | grep -iE 'http_proxy|https_proxy|no_proxy'

# 6. 開発キットの例外種別を確認する
python3 -c "
from openai import OpenAI
import openai
try:
    OpenAI().models.list()
except openai.PermissionDeniedError as e:
    print('PermissionDenied:', e.status_code, e.body)
except openai.AuthenticationError as e:
    print('Authentication:', e.status_code, e.body)
"
```

## Editor's Note

この[エラー](/glossary/エラー/)の判定が「利用者の国」ではなく「送信元 IP の判定結果」であることを、当事者のやり取りごと記録した相談があります（[Cloud Run in asia-northeast3 Suddenly Getting 'unsupported_country_region_territory' Error](https://community.openai.com/t/cloud-run-in-asia-northeast3-suddenly-getting-unsupported-country-region-territory-error-from-openai-api/1279969)）。

2025年6月、韓国の実行環境に配備していた[サービス](/glossary/サービス/)が、突然 403 を返し始めました。相談者はこう書いています。**[コード](/glossary/コード/)も配備の設定も変えていない**。[キー](/glossary/キー/)は有効で、上限にも達していない。そして「この地域は対応しているはずだ」と。

同じ症状の報告が次々と続きます。同じ[クラウド](/glossary/クラウド/)の同じ地域を使う利用者が、数日のうちに4人以上集まりました。

3日後、提供元の窓口が返答します。**韓国は対応国である**と認めたうえで、使用している [IP アドレス](/glossary/ip-アドレス/)を共有してほしい、**誤って対象外の地域に判定されていないか確認する**、という内容でした。この一文が、判定の実体を明かしています。見られているのは所在地の申告ではなく、[通信](/glossary/通信/)の出どころです。

ある利用者は待ちきれず、実行環境の地域を別の場所へ変えることで解決しています。**設定を1つも直さず、出口を変えただけ**です。そして6日後、窓口から修正済みの連絡があり、報告者たちの[環境](/glossary/環境/)は元のまま復旧しました。

この記録から得られる教訓は2つあります。1つは、403 に当たったとき最初に確認すべきなのが、[プログラム](/glossary/プログラム/)ではなく**要求がどこから出ているか**だということ。もう1つは、**利用者側では直しようがない場合がある**ということです。手を尽くしても変わらないなら、出口の IP を控えて提供元に伝えるのが、最短の道になります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*