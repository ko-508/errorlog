---
title: "OpenAI API の 429 エラー：原因と解決策"
date: 2026-08-03
description: "OpenAI API の 429 には性質の違う2種類があります。type が rate_limit_exceeded なら待てば通りますが、insufficient_quota は待っても永久に直りません。公式も、クォータや課金の問題は再試行で解決しないと明記しています。まず type を読むことが切り分けの起点です。"
tags: ["OpenAI API"]
errorCode: "429"
lastmod: 2026-08-03
service: "OpenAI API"
error_type: "429"
components: ["Chat Completions", "Rate Limits"]
related_services: ["Batch API", "Python SDK"]
trend_incident: false
---

## 冒頭まとめ

OpenAI [API](/glossary/api/) の 429 Too Many Requests は、1つの意味を持つ[エラー](/glossary/エラー/)ではありません。**性質のまったく違う2種類が、同じ状態[コード](/glossary/コード/)で返ります**。

1つ目は[レート制限](/glossary/レート制限/)の超過です。応答の `type` は `rate_limit_exceeded` で、こちらは**待てば通ります**。

2つ目はクォータの不足です。`type` は `insufficient_quota`、文言は現在のクォータを超過したので契約と請求の設定を確認せよ、という趣旨になります。こちらは**待っても永久に直りません**。原因が[送信](/glossary/送信/)の速さではなく、残高や請求の状態にあるためです。

公式文書はこの区別を明示しています。`Retry-After` [ヘッダー](/glossary/ヘッダー/)は一時的な[レート制限](/glossary/レート制限/)による 429 に付くことがあるが、**クォータや請求など利用者側の対応が必要な[エラー](/glossary/エラー/)が再試行で解決することを意味しない**、と書かれています。再試行の節にも、そうした[エラー](/glossary/エラー/)は再試行するなと明記されています。

やっかいなのは、この2つを[プログラム](/glossary/プログラム/)が区別しない点です。公式の[ソフトウェア](/glossary/ソフトウェア/)開発キットは、429 を含む一部の[エラー](/glossary/エラー/)を**既定で2回自動的に再試行**します。つまりクォータ不足でも黙って3回投げられ、遅くなるだけで結果は変わりません。

したがって最初にやることは決まっています。応答の `type` を読むことです。

## エラーの概要

[レート制限](/glossary/レート制限/)の超過はこの形です。

```json
{
  "error": {
    "message": "Rate limit reached for gpt-4o-mini in organization org-xxx on tokens per min (TPM): Limit 200000, Used 199200, Requested 1200.",
    "type": "rate_limit_exceeded",
    "param": null,
    "code": "rate_limit_exceeded"
  }
}
```

クォータ不足は、同じ 429 でも中身が違います。

```json
{
  "error": {
    "message": "You exceeded your current quota, please check your plan and billing details.",
    "type": "insufficient_quota",
    "param": null,
    "code": "insufficient_quota"
  }
}
```

判定は `type` の1語で終わります。文言の「quota」という単語に引きずられないでください。[レート制限](/glossary/レート制限/)側の文言にも上限の話は出てきます。

応答[ヘッダー](/glossary/ヘッダー/)も重要です。公式には、上限値と残量、そして再開までの時間を示す一連の[ヘッダー](/glossary/ヘッダー/)が定義されています。要求数と[トークン](/glossary/トークン/)数で別々に用意されており、どちらを使い切ったかが分かります。

```text
x-ratelimit-limit-requests: 60
x-ratelimit-remaining-requests: 59
x-ratelimit-reset-requests: 1s
x-ratelimit-limit-tokens: 150000
x-ratelimit-remaining-tokens: 149984
x-ratelimit-reset-tokens: 6m0s
```

## まず最初に：type と残量ヘッダーを読む

第一に、応答本文の `type` を読みます。`insufficient_quota` なら、この先の[レート制限](/glossary/レート制限/)の話はすべて無関係です。

第二に、`rate_limit_exceeded` であれば、残量の[ヘッダー](/glossary/ヘッダー/)を見ます。要求数と[トークン](/glossary/トークン/)数のどちらがゼロに近いかで、対処が変わります。

第三に、`Retry-After` があるかを見ます。あれば、公式の案内どおり**最低でもその秒数は待ちます**。

第四に、[プログラム](/glossary/プログラム/)から呼んでいる場合、開発キットが既に再試行している可能性を考えます。手元の[ログ](/glossary/ログ/)に1回しか出ていなくても、実際には3回送られていることがあります。

## よくある原因と解決手順

### 原因1：insufficient_quota（残高や請求の問題）

`type` が `insufficient_quota` の場合です。**[送信](/glossary/送信/)の頻度をいくら下げても直りません**。

確認すべきは3点です。組織の残高が残っているか、支払い方法が有効か、そして呼び出している[プロジェクト](/glossary/プロジェクト/)が意図したものか。とくに3つ目は見落とされがちで、残高は組織に紐づく一方、[API](/glossary/api/) [キー](/glossary/キー/)は[プロジェクト](/glossary/プロジェクト/)に紐づきます。

**Before（再試行の設定を強める）：**

```python
client = OpenAI(max_retries=10)   # 何回投げても結果は同じ
```

**After（種別で分岐し、クォータ側は再試行しない）：**

```python
try:
    resp = client.chat.completions.create(...)
except openai.RateLimitError as e:
    body = getattr(e, "body", {}) or {}
    if body.get("type") == "insufficient_quota":
        notify_billing_owner()      # 待っても直らない
    else:
        backoff_and_retry()
```

なお、支払い直後は反映に時間がかかることがあります。残高が見えているのに同じ[エラー](/glossary/エラー/)が続く場合は、後述の実例のように**[プロジェクト](/glossary/プロジェクト/)側の状態**を疑ってください。

### 原因2：rate_limit_exceeded（どの指標を超えたか）

公式によれば、[レート制限](/glossary/レート制限/)は1分あたりの要求数、1日あたりの要求数、1分あたりの[トークン](/glossary/トークン/)数、1日あたりの[トークン](/glossary/トークン/)数、画像の枚数など複数の指標で構成され、**どれか1つでも先に達した時点で 429 になります**。要求数に余裕があっても[トークン](/glossary/トークン/)数で先に止まる、という現象はこれです。

さらに注意点が3つ、公式に挙げられています。上限は利用者単位ではなく**組織と[プロジェクト](/glossary/プロジェクト/)の単位**で定義されること。[モデル](/glossary/モデル/)によって上限が違うこと。そして一部の[モデル](/glossary/モデル/)群は上限を**共有**しており、その中のどの[モデル](/glossary/モデル/)を呼んでも同じ枠を消費することです。

```bash
# どちらの指標が枯渇しているかをヘッダーで確認する
curl -sS -D - -o /dev/null https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}' \
  | grep -i 'x-ratelimit'
```

### 原因3：max_tokens の指定が上限を食っている

見落とされやすい仕組みです。公式には、[レート制限](/glossary/レート制限/)の計算に使われる値は **`max_tokens` と、要求の文字数から推定した[トークン](/glossary/トークン/)数の大きいほう**だと書かれています。

つまり、実際の応答が短くても、`max_tokens` を大きく指定していればその分だけ枠を消費します。公式も、想定する応答の大きさにできるだけ近づけるよう勧めています。

**Before（余裕を持たせたつもりで大きく取る）：**

```python
client.chat.completions.create(model="gpt-4o-mini", max_tokens=4000, ...)
# 実際の応答が50トークンでも、4000として計上される
```

**After（想定に合わせる）：**

```python
client.chat.completions.create(model="gpt-4o-mini", max_tokens=200, ...)
```

分類や抽出のように短い応答で足りる用途では、この1行だけで処理できる件数が大きく変わります。

### 原因4：再試行が二重になっている

公式の開発キットは、対象となる[エラー](/glossary/エラー/)を既定で2回再試行し、`Retry-After` があればそれに従います。ここに自作の再試行を重ねると、待ち時間が掛け算になります。

公式文書にも、応用[プログラム](/glossary/プログラム/)側で再試行を足すなら開発キットが既に行う再試行を考慮せよ、と書かれています。

もう1つ重要な指摘があります。**失敗した要求も1分あたりの上限に計上される**ため、間隔を空けずに送り直しても状況は改善しません。素早い再試行は、枠をさらに削るだけです。

```python
# 開発キットの再試行を止めて、素の応答を確認する
client = OpenAI(max_retries=0)
```

切り分けの段階では、まずこの指定で素の応答を見てください。二重の再試行が挟まっていると、何が起きているか見えなくなります。

### 原因5：同期で処理する必要がない

即時の応答が要らない用途であれば、まとめて実行する仕組みが用意されています。公式によれば、こちらは**[同期](/glossary/同期/)の要求に対する[レート制限](/glossary/レート制限/)に影響しません**。

大量の処理を[同期](/glossary/同期/)で流して 429 と戦っているなら、そもそも土俵を変えるほうが確実です。

また、要求数の上限には余裕があるのに[トークン](/glossary/トークン/)数で止まっている場合、逆に複数の処理を1回の要求にまとめる方法も公式に案内されています。どちらが枯渇しているかで、取るべき方向が逆になります。

## 補足：似ているが別のもの

[API](/glossary/api/) [キー](/glossary/キー/)が無効な場合は 401 です。クォータ不足と混同されやすいのですが、[認証](/glossary/認証/)は通っているかどうかで区別できます。

利用が許可されていない地域からの呼び出しは 403 です。[モデル](/glossary/モデル/)にアクセスできない場合は 404 になります。

一時的な過負荷は 500 番台です。開発キットの対応表では、429 は[レート制限](/glossary/レート制限/)の例外、500 以上は内部[エラー](/glossary/エラー/)の例外として区別されています。

支出の上限と[レート制限](/glossary/レート制限/)も別物です。公式には、組織ごとに承認された月間の利用上限があり、これは設定できる支出上限とは別だと書かれています。

なお、Azure 経由で同じ[モデル](/glossary/モデル/)を使っている場合、上限の仕組みも[エラー](/glossary/エラー/)の形式も別系統になります（[Azure の 429 の記事](/posts/azure_429/)）。他の基盤の 429 とも、応答に入る情報が違います（[GCP の 429 の記事](/posts/gcp_429/)）。

## 切り分けの順序

1. 応答の `type` を読む。`insufficient_quota` なら[レート制限](/glossary/レート制限/)の話は無関係。
2. クォータ側なら、残高・支払い方法・[プロジェクト](/glossary/プロジェクト/)の3点を確認する。再試行は無意味。
3. [レート制限](/glossary/レート制限/)側なら、残量[ヘッダー](/glossary/ヘッダー/)で要求数と[トークン](/glossary/トークン/)数のどちらが枯渇したかを見る。
4. `Retry-After` があれば、最低でもその秒数を待つ。
5. 開発キットの再試行を止めて、素の応答を確認する。二重の再試行を疑う。
6. [トークン](/glossary/トークン/)数で止まっているなら、`max_tokens` を想定に近づける。
7. [モデル](/glossary/モデル/)群で上限を共有していないかを確認する。別[モデル](/glossary/モデル/)への切り替えが効かない場合がある。
8. 即時性が不要なら、まとめて実行する仕組みへ移す。[同期](/glossary/同期/)の上限とは別枠。

## 確認コマンド集

```bash
# 1. エラーの種別だけを取り出す（最重要）
curl -sS https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}' \
  | python3 -c "import json,sys; e=json.load(sys.stdin).get('error',{}); print(e.get('type'), '|', e.get('code'))"

# 2. 残量ヘッダーと Retry-After をまとめて見る
curl -sS -D - -o /dev/null https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}' \
  | grep -iE 'x-ratelimit|retry-after|x-request-id'

# 3. 開発キットの再試行を止めて素の応答を見る
python3 -c "
from openai import OpenAI
c = OpenAI(max_retries=0)
try:
    c.chat.completions.create(model='gpt-4o-mini', messages=[{'role':'user','content':'hi'}])
except Exception as e:
    print(type(e).__name__, getattr(e, 'status_code', ''), getattr(e, 'body', ''))
"

# 4. 問い合わせ用に要求の識別子を控える
python3 -c "
from openai import OpenAI
r = OpenAI().chat.completions.create(model='gpt-4o-mini', messages=[{'role':'user','content':'hi'}])
print(r._request_id)
"

# 5. 微調整の上限を API から取得する
curl -sS https://api.openai.com/v1/fine_tuning/model_limits \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## Editor's Note

`insufficient_quota` が[レート制限](/glossary/レート制限/)と誤解される様子を、そのまま記録した相談があります（[HTTP 429: insufficient quota on first request](https://community.openai.com/t/http-429-insufficient-quota-on-first-request/1091175)）。

2025年1月、[API](/glossary/api/) を使い始めた利用者が5ドルを入金し、案内どおりの手順で最初の呼び出しを行ったところ、`insufficient_quota` の 429 が返りました。報告には状況が細かく書かれています。送ったのは**たった1回**の要求で、繰り返しの[プログラム](/glossary/プログラム/)は使っていない。残高は使用状況の画面に反映されている。対象[モデル](/glossary/モデル/)の上限は毎分500要求と20万[トークン](/glossary/トークン/)。

**1回の要求で毎分500要求の上限に達することはありません**。この時点で、[レート制限](/glossary/レート制限/)ではないと確定できます。実際に解決したのは、新しい[プロジェクト](/glossary/プロジェクト/)を作り、その下で[API](/glossary/api/) [キー](/glossary/キー/)を作り直すことでした。元の[プロジェクト](/glossary/プロジェクト/)には、[アカウント](/glossary/アカウント/)を作った日より前の作成日が表示されていた、という奇妙な状態だったそうです。

同じ相談の後半には、別の回答者による助言も残っています。数分待つ、要求を送りすぎていないか確認する、といった内容です。善意の助言ですが、**方向がずれています**。1回しか送っていない相談に対して、送りすぎを疑う提案になっているためです。

これが、この[エラー](/glossary/エラー/)の典型的な遠回りです。429 という数字と「上限」という語感が、自動的に「送りすぎ」という結論を呼び込みます。しかし応答には `type` が入っており、そこに答えが書かれています。

429 を受け取ったら、待つ前に、減らす前に、まず `type` を読んでください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*