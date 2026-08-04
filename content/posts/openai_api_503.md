---
title: "OpenAI API の 503 エラー：原因と解決策"
date: 2026-08-03
description: "OpenAI API の 503 は公式に「混雑している」と定義され、対処は短い待機のうえでの再試行です。ただし同じ「過負荷」の文言は 429 でも返るため、状態コードを見ないと自分の上限の問題と取り違えます。待てば直るのか、減らさないと直らないのかは、そこで分かれます。"
tags: ["OpenAI API"]
images: ["og/posts/openai_api_503.png"]
errorCode: "503"
lastmod: 2026-08-03
service: "OpenAI API"
error_type: "503"
components: ["Chat Completions", "Reliability"]
related_services: ["Python SDK", "Batch API"]
trend_incident: false
top_queries:
- 'apiが過負荷状態です'
---

## 冒頭まとめ

OpenAI [API](/glossary/api/) の 503 は、公式の[エラー](/glossary/エラー/)一覧で**混雑**として定義されています。文言は現在処理系が過負荷なので後で試すよう促す趣旨で、原因は[サーバー](/glossary/サーバー/)側が大量の通信を受けていること、対処は短い待機のうえでの再試行、と明記されています。

つまり、**送った内容にも、自分の設定にも問題はありません**。全利用者に対して起きている状態です。

ただし、ここに落とし穴があります。**同じ「過負荷」の文言は 429 でも返ります**。公式の説明資料には、この文言が 429 の項目としても掲載されています。文言だけを読んで「混雑だから待とう」と判断すると、実際には自分の上限に達していた、という取り違えが起こります。

この2つは対処が違います。503 は待てば通ります。429 は、[レート制限](/glossary/レート制限/)なら待って通り、クォータ不足なら**待っても永久に通りません**。

したがって、文言ではなく**状態[コード](/glossary/コード/)を見る**のが出発点になります。

## エラーの概要

応答は次の形です。

```json
{
  "error": {
    "message": "The engine is currently overloaded, please try again later",
    "type": "server_error",
    "param": null,
    "code": null
  }
}
```

`param` も `code` も `null` です。500 と同じ構造で、**指し示せる場所が無い**ことを示しています。

公式の[ソフトウェア](/glossary/ソフトウェア/)開発キットでは、状態[コード](/glossary/コード/)が 500 以上のものがまとめて1つの区分になります。したがって、**開発キットの例外の型だけでは 500 と 503 を区別できません**。状態[コード](/glossary/コード/)を取り出して確認する必要があります。

再試行については、開発キットが接続の問題、408、409、429、そして 500 番台を**既定で2回自動的に再試行**します。503 もこの対象です。手元の記録に1回しか出ていなくても、実際は3回試したうえで諦めた状態です。

## まず最初に：状態コードで 429 と分ける

第一に、状態[コード](/glossary/コード/)を確認します。文言が「過負荷」でも、503 と 429 では意味が違います。

第二に、429 だった場合は `type` を読みます。`rate_limit_exceeded` なら待てば通り、`insufficient_quota` なら待っても通りません（[OpenAI API の 429 の記事](/posts/openai_api_429/)）。

第三に、503 だった場合は、開発キットの再試行が既に効いていることを踏まえて回数を確定させます。

第四に、稼働状況を確認します。広範囲であれば、こちらでできることはありません。

## よくある原因と解決手順

### 原因1：提供側が混雑している

定義どおりの形です。対処は待つことですが、待ち方に工夫が要ります。

**Before（一定の間隔で叩き続ける）：**

```python
for i in range(10):
    try:
        return client.chat.completions.create(...)
    except openai.InternalServerError:
        time.sleep(1)      # 混雑時に等間隔で送り続ける
```

**After（間隔を伸ばし、ばらつきを持たせる）：**

```python
client = OpenAI(max_retries=5)   # 開発キットに任せる（指数的な間隔）
resp = client.chat.completions.create(...)
```

混雑している相手に等間隔で送り続けると、回復した瞬間に全利用者の再試行が重なります。間隔を指数的に伸ばし、わずかな揺らぎを加えるのが定石です。開発キットはこの動作を内蔵しています。

### 原因2：状態コードを見ずに 429 と混同している

冒頭で述べた取り違えです。文言が同じでも、状態[コード](/glossary/コード/)が 429 なら自分側の上限の話です。

```bash
# 文言ではなく状態コードと type を確認する
curl -sS -D - -o body.json https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}' \
  | grep -i "^HTTP/"
python3 -c "import json; e=json.load(open('body.json')).get('error',{}); print(e.get('type'), e.get('code'))"
```

429 側であれば、残量を示す[ヘッダー](/glossary/ヘッダー/)も付きます。503 には付きません。**[ヘッダー](/glossary/ヘッダー/)の有無も判別材料**になります。

### 原因3：大きな要求を並列で流している

混雑は提供側の状態ですが、送り方によって当たりやすさは変わります。長い入力や大きな出力の指定は、1件あたりの負荷を押し上げます。

減らす方向は2つです。1回あたりの大きさを抑えることと、同時に流す本数を抑えることです。

```python
# 出力の上限を用途に合わせる（大きすぎる指定は避ける）
client.chat.completions.create(model="gpt-4o-mini",
    messages=[...], max_tokens=256)
```

なお、即時の応答が必要ない処理であれば、まとめて実行する仕組みに移すという選択肢もあります。同期の経路とは別枠で扱われます。

### 原因4：再試行が二重になっている

開発キットが既定で2回再試行することを知らずに、自作の再試行を重ねる形です。待ち時間も送信回数も掛け算になります。

混雑時にこれをやると、状況を悪化させます。**まず何回送られているかを確定**してから、設計してください。

```python
# 素の応答と回数を確定させる
client = OpenAI(max_retries=0)
```

### 原因5：待っても直らない

長時間続く場合は、混雑ではない可能性があります。状態[コード](/glossary/コード/)をもう一度確認してください。

`insufficient_quota` の 429 であれば、待っても永久に直りません。残高や請求の設定を確認する必要があります。500 であれば、続く場合は問い合わせが案内されています。502 であれば、そもそも [API](/glossary/api/) の層に届いていません。

**「待てば直る」は 503 に固有の性質**であって、5 で始まる[コード](/glossary/コード/)すべてに当てはまるわけではありません。

## 補足：似ているが別のもの

[サーバー](/glossary/サーバー/)側の処理で問題が起きた場合は 500 です。公式の対処は短い待機のうえでの再試行と、続く場合の問い合わせです（[OpenAI API の 500 の記事](/posts/openai_api_500/)）。503 との違いは、原因が容量にあると明示されているかどうかです。

応答が JSON でなく HTML であれば 502 で、返したのは [API](/glossary/api/) の層ではありません（[OpenAI API の 502 の記事](/posts/openai_api_502/)）。

上限や残高の問題は 429 です。前述のとおり、文言が同じ場合があるため、状態[コード](/glossary/コード/)で見分けてください。

他の基盤でも、503 は「一時的であり再試行で解消しうる」という位置づけが共通しています（[GCP の 503 の記事](/posts/gcp_503/)）。

## 切り分けの順序

1. 状態[コード](/glossary/コード/)を確認する。文言が「過負荷」でも 429 のことがある。
2. 429 なら `type` を読む。クォータ不足は待っても直らない。
3. 残量の[ヘッダー](/glossary/ヘッダー/)が付いているかを見る。429 の側には付く。
4. 503 なら、開発キットの再試行が既に効いている前提で回数を確定する。
5. 間隔は指数的に伸ばし、ばらつきを加える。等間隔で叩かない。
6. 1件あたりの大きさと同時実行数を見直す。
7. 即時性が不要なら、まとめて実行する仕組みへ移す。
8. 長時間続くなら、混雑以外の可能性を疑い、状態[コード](/glossary/コード/)を再確認する。

## 確認コマンド集

```bash
# 1. 状態コードだけを確認する（文言に頼らない）
curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'

# 2. 残量ヘッダーの有無を見る（429 との判別）
curl -sS -D - -o /dev/null https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}' \
  | grep -iE 'x-ratelimit|retry-after|x-request-id'

# 3. 発生率を測る（混雑の程度を把握する）
for i in $(seq 20); do
  curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
  sleep 1
done | sort | uniq -c

# 4. 開発キットの再試行を止めて素の応答を見る
python3 -c "
from openai import OpenAI
import openai
try:
    OpenAI(max_retries=0).chat.completions.create(
        model='gpt-4o-mini', messages=[{'role':'user','content':'hi'}])
except openai.APIStatusError as e:
    print(e.status_code, e.request_id); print(e.body)
"
```

## Editor's Note

503 は、**個々の利用者にできることがほとんど無い**[エラー](/glossary/エラー/)です。だからこそ、対処は「直す」ではなく「織り込む」方向になります。

それを実装として示した記録があります（[[ML] Add retry logic for 500 and 503 errors for OpenAI](https://github.com/elastic/elasticsearch/pull/103819)）。2024年1月、ある検索基盤の機械学習機能に、OpenAI [API](/glossary/api/) からの 500 と 503 に対する再試行が追加されました。理由は、クラウド上での検証で**断続的な 500 と 503 の失敗**が観測され、大量の取り込み処理が丸ごと失敗していたためです。

注目すべきは、500 と 503 が**同じ変更でまとめて扱われた**ことです。実装から見れば、どちらも「相手側の事情で失敗した、再試行の価値がある応答」という同じ分類に入ります。公式の開発キットが 500 番台をまとめて既定で再試行するのも同じ考え方です。

一方、利用者の側から見ると、この2つには重要な違いがあります。503 は原因が**容量**だと明示されており、待てば通る見込みがあります。500 にはその見込みが書かれておらず、続く場合は問い合わせが案内されています。

そして最も注意すべきは、**同じ「過負荷」の文言が 429 でも使われている**ことです。文言を見て「混雑だから待とう」と判断したとき、実際に見ているのが 429 なら、待っても状況は変わらないかもしれません。クォータ不足であれば、待つことは何の解決にもなりません。

503 に当たったら、まず状態[コード](/glossary/コード/)を確認する。それから、再試行を自分で足すのか、既に足りているのかを確定させる。順序はこの2つです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*