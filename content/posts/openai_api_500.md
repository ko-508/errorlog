---
title: "OpenAI API の 500 エラー：原因と解決策"
date: 2026-08-03
description: "OpenAI API の 500 は公式に「提供側の問題」と定義されており、対処は短い待機のうえでの再試行と、続く場合の問い合わせです。ただし公式の開発キットは 500 番台を既定で2回再試行するため、手元に1回だけ記録されていても実際は3回送られています。まず何回送られたかを確定させます。"
tags: ["OpenAI API"]
images: ["og/posts/openai_api_500.png"]
errorCode: "500"
lastmod: 2026-08-03
service: "OpenAI API"
error_type: "500"
components: ["Chat Completions", "Reliability"]
related_services: ["Python SDK", "Batch API"]
trend_incident: false
top_queries:
- 'openai 520 error'
- 'openai.internalservererror: error code: 500'
---

## 冒頭まとめ

OpenAI [API](/glossary/api/) の 500 は、公式の[エラー](/glossary/エラー/)一覧で**提供側の問題**と明記されています。文言は要求の処理中に[サーバー](/glossary/サーバー/)側で問題が起きた、という趣旨で、示されている対処は「短い待機のうえで再試行し、続く場合は問い合わせる」ことです。あわせて稼働状況の確認も案内されています。

つまり、**送った内容を直しても直りません**。400 番台とは調べる方向が正反対です。

そのうえで、実務的に最初に確認すべきことがあります。**何回送られたか**です。公式の[ソフトウェア](/glossary/ソフトウェア/)開発キットは、接続の問題、408、409、429、そして 500 番台を**既定で2回自動的に再試行**します。したがって、手元の[ログ](/glossary/ログ/)に1回しか記録されていなくても、実際には3回送られたうえで諦めた状態です。

この前提を知らないと、対処を二重に積むことになります。自作の再試行を足せば、待ち時間も送信回数も掛け算で増えます。

なお、`code` が `null` で `type` が `server_error` の形が典型ですが、応答が **[JSON](/glossary/json/) ですらない**場合もあります。その場合は [API](/glossary/api/) の層が返したものではありません。

## エラーの概要

典型的な応答です。

```json
{
  "error": {
    "message": "The server had an error while processing your request. Sorry about that!",
    "type": "server_error",
    "param": null,
    "code": null
  }
}
```

`param` も `code` も `null` です。**指し示せる場所が無い**ということで、これ自体が「利用者側の問題ではない」ことの表れです。400 番台では `param` や `code` に手がかりが入るのと対照的です。

開発キットからは `InternalServerError` として現れます。公式の対応表では、状態[コード](/glossary/コード/)が 500 以上のものがこの区分にまとめられています。

一方、[サーバー](/glossary/サーバー/)から応答が返る前に失敗した場合は、区分自体が変わります。接続できなかった場合と時間切れの場合は、状態[コード](/glossary/コード/)を持たない別の区分です。**500 が返っているなら、少なくとも要求は届いています**。

## まず最初に：本当に 500 か、何回送られたかを確定する

第一に、本文が [JSON](/glossary/json/) かを見ます。HTML が返っていれば [API](/glossary/api/) の層ではなく前段の仕組みが返しています。

第二に、開発キットの再試行を止めて、素の応答を確認します。既定のままでは3回分の結果をまとめて見ていることになります。

第三に、要求の識別子を控えます。応答[ヘッダー](/glossary/ヘッダー/)に付く値で、問い合わせの際に該当の要求を特定できます。

第四に、稼働状況を確認します。広く発生していれば、こちらでできることはありません。

## よくある原因と解決手順

### 原因1：一時的なもので、再試行で通る

最も多い形です。公式の案内どおり、短い待機のうえで再試行します。

**Before（自作の再試行を素朴に足す）：**

```python
for i in range(5):
    try:
        return client.chat.completions.create(...)
    except openai.InternalServerError:
        time.sleep(1)     # 開発キット側でも2回再試行済み
```

**After（開発キットの設定として指定する）：**

```python
client = OpenAI(max_retries=4)          # 二重の再試行を作らない
resp = client.chat.completions.create(...)
```

再試行の回数を増やす前に、**いま何回送られているかを把握**してください。開発キットの既定は2回です。自作の5回を重ねれば、最悪で15回送ることになります。

### 原因2：結果が変わりうる操作を無条件で再送している

再試行そのものが危険な場合があります。同じ内容を送ればよいとは限らない操作、たとえば[ファイル](/glossary/ファイル/)の作成や微調整の開始では、1回目が内部で成功していた可能性が残ります。

読み取りであれば、そのまま再試行して構いません。作成であれば、**一覧を確認してから判断**してください。

```bash
# 作成が実際には成功していないかを確認する
curl -sS https://api.openai.com/v1/files \
  -H "Authorization: Bearer $OPENAI_API_KEY" | head -c 400
```

### 原因3：特定の要求だけで再現する

同じ要求が毎回同じ場所で失敗する場合です。この形では、提供側の不調というより、その要求の内容が引き金になっています。

要求を最小構成にしてから、項目を1つずつ戻すのが確実です。特定できれば、それは問い合わせの材料としてそのまま使えます。

```bash
# 最小の要求で切り分ける
curl -sS -D - -o /dev/null https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}' \
  | grep -iE 'HTTP/|x-request-id'
```

### 原因4：問い合わせる

公式の案内には、続く場合は問い合わせるよう明記されています。500 は利用者側で直せない種類の[エラー](/glossary/エラー/)です。

用意すべき情報は決まっています。発生時刻、呼び出した[エンドポイント](/glossary/エンドポイント/)、使用した[モデル](/glossary/モデル/)、そして**要求の識別子**です。開発キットでは応答[オブジェクト](/glossary/オブジェクト/)から取得できるほか、例外からも取り出せます。

```python
from openai import OpenAI
import openai
try:
    r = OpenAI().chat.completions.create(model="gpt-4o-mini",
        messages=[{"role":"user","content":"hi"}])
    print(r._request_id)
except openai.APIStatusError as e:
    print(e.status_code, e.request_id)
```

### 原因5：500 だと思っているものが 500 ではない

応答が [JSON](/glossary/json/) でない場合です。前段の仕組みが返した HTML の画面であれば、[API](/glossary/api/) の層には到達していません。

この場合、`type` も `code` も存在しません。**手がかりの構造がそもそも違う**ため、本記事の内容は当てはまりません（[OpenAI API の 502 の記事](/posts/openai_api_502/)）。

## 補足：似ているが別のもの

過負荷による一時的な拒否は 503 です。文言が「現在混雑している」という趣旨になります（[OpenAI API の 503 の記事](/posts/openai_api_503/)）。500 との違いは、原因が[容量](/glossary/容量/)にあると明示されている点です。

上限や残高の問題は 429 です。応答が返っている以上、[認証](/glossary/認証/)は通っています。

接続そのものに失敗した場合や時間切れの場合は、状態[コード](/glossary/コード/)を持ちません。開発キットでは別の区分になり、確認すべきは[ネットワーク](/glossary/ネットワーク/)の設定や中継の仕組みです。

他の基盤の 500 とも、応答に入る情報の量が違います（[GCP の 500 の記事](/posts/gcp_500/)）。

## 切り分けの順序

1. 本文が [JSON](/glossary/json/) かを見る。HTML なら前段が返している。
2. `type` が `server_error`、`param` と `code` が `null` かを確認する。
3. 開発キットの再試行を止めて、素の応答と回数を確定させる。
4. 要求の識別子を控える。問い合わせの必須材料。
5. 稼働状況を確認する。広範囲なら待つ以外にない。
6. 特定の要求だけで再現するなら、最小構成から引き金を特定する。
7. 作成系の操作なら、再送の前に実物を確認する。
8. 再試行の回数を増やす前に、二重になっていないかを確認する。

## 確認コマンド集

```bash
# 1. 状態コードと要求の識別子を確認する
curl -sS -D - -o /dev/null https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}' \
  | grep -iE 'HTTP/|x-request-id'

# 2. 本文が JSON か HTML かを確認する
curl -sS https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" -d @request.json | head -c 200

# 3. 開発キットの再試行を止めて素の応答を見る
python3 -c "
from openai import OpenAI
import openai
c = OpenAI(max_retries=0)
try:
    c.chat.completions.create(model='gpt-4o-mini', messages=[{'role':'user','content':'hi'}])
except openai.APIStatusError as e:
    print(e.status_code, e.request_id, e.body)
"

# 4. 発生率を測る（10回試行して失敗数を数える）
for i in $(seq 10); do
  curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
done | sort | uniq -c
```

## Editor's Note

500 は「起きたら対処する」[エラー](/glossary/エラー/)ではなく、**起きる前提で組む**種類の[エラー](/glossary/エラー/)です。それを実装として示した記録があります（[[ML] Add retry logic for 500 and 503 errors for OpenAI](https://github.com/elastic/elasticsearch/pull/103819)）。

2024年1月、ある検索基盤の機械学習機能に、OpenAI [API](/glossary/api/) からの 500 と 503 に対する再試行を追加する変更が提案されました。説明はごく短いものです。[クラウド](/glossary/クラウド/)上での検証中に**断続的な 500 と 503 の失敗**が観測され、それが大量の取り込み処理の失敗を引き起こしていた、という内容でした。

注目すべきは対処の方向です。原因の究明でも、要求内容の見直しでもありません。**再試行を実装に組み込む**という判断です。そしてこの変更は、直後の保守版にも反映されています。

この[エラー](/glossary/エラー/)の性質がよく現れています。1件ずつ手で試している段階では、たまたま失敗しても再実行すれば済みます。しかし大量の要求を流す処理では、断続的な失敗は**必ず一定の割合で発生し、全体を止めます**。

したがって、500 に対して用意すべきなのは原因の特定ではなく、失敗を織り込んだ設計です。公式の開発キットが既定で2回再試行するのも同じ思想でしょう。

そのうえで注意が要ります。**既に再試行されている**という事実を知らずに自作の再試行を重ねると、送信回数も待ち時間も掛け算になります。まず、いま何回送られているのかを確定させてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*