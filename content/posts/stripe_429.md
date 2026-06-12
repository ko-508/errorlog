---
title: "Stripe の 429 エラー：原因と解決策"
date: 2026-05-27
description: "429 Too Many Requests は、短時間に Stripe API へ送信したリクエスト数がレート制限を超えたときに返される HTTP ステータスコードです。"
tags: ["Stripe"]
errorCode: "429"
lastmod: 2026-05-31
service: "Stripe"
error_type: "429"
components: ["Charge", "Webhook", "Event"]
related_services: ["Python", "JavaScript", "curl"]
---
## エラーの概要

**429 Too Many Requests** は、短時間に Stripe [API](/glossary/api/) へ送信した[リクエスト](/glossary/リクエスト/)数が[レート制限](/glossary/レート制限/)を超えたときに返される [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)です。Stripe は [API](/glossary/api/) 呼び出しの頻度を制限しており、本番環境では 1 秒あたり約 100 [リクエスト](/glossary/リクエスト/)が上限となります。この[エラー](/glossary/エラー/)が発生してもデータは消失せず、適切に[リトライ](/glossary/リトライ/)することで解決できます。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Too many requests in a given amount of time: 'api'. Maximum expected circa 100 requests/sec",
    "status": 429,
    "type": "api_error"
  }
}
```

```bash
curl -X POST https://api.stripe.com/v1/charges \
  -H "Authorization: Bearer sk_live_<your-secret-key>" \
  -d "amount=2000" \
  -d "currency=jpy" \
  -d "source=tok_visa"

# 応答
# HTTP/1.1 429 Too Many Requests
# Retry-After: 1
```

## よくある原因と解決手順

### 原因1: ループ処理で API を連続呼び出ししている

**なぜ発生するか**

顧客リストの更新や一括決済処理など、複数の [API](/glossary/api/) 呼び出しをループで実行する際、呼び出し間に待機時間を設けないと瞬時に大量の[リクエスト](/glossary/リクエスト/)が送信されます。

**修正前（[エラー](/glossary/エラー/)が起きるコード）**

```python
import stripe

stripe.api_key = "sk_test_<your-secret-key>"

# 複数の顧客に対して一括で請求を発行する場合
customer_ids = ["cus_001", "cus_002", "cus_003", ...]

for customer_id in customer_ids:
    charge = stripe.Charge.create(
        amount=1000,
        currency="jpy",
        customer=customer_id
    )
    print(f"Charged {customer_id}")
```

**修正後**

```python
import stripe
import time

stripe.api_key = "sk_test_<your-secret-key>"

customer_ids = ["cus_001", "cus_002", "cus_003", ...]

for customer_id in customer_ids:
    try:
        charge = stripe.Charge.create(
            amount=1000,
            currency="jpy",
            customer=customer_id
        )
        print(f"Charged {customer_id}")
    except stripe.error.RateLimitError as e:
        retry_after = int(e.http_headers.get("retry-after", 1))
        print(f"Rate limited. Waiting {retry_after} seconds...")
        time.sleep(retry_after)
        # リトライロジック
        charge = stripe.Charge.create(
            amount=1000,
            currency="jpy",
            customer=customer_id
        )
    
    # リクエスト間に遅延を挿入
    time.sleep(0.1)
```

### 原因2: Webhook 再試行ロジックの過度な実装

**なぜ発生するか**

[Webhook](/glossary/webhook/) の[エラーハンドリング](/glossary/エラーハンドリング/)で指数[バックオフ](/glossary/バックオフ/)（段階的に遅延を長くする再試行方法）を実装せず、即座に何度も [API](/glossary/api/) 呼び出しを行う場合に発生します。特に [Webhook](/glossary/webhook/) 署名検証失敗時の[ログ](/glossary/ログ/)記録で複数の [API](/glossary/api/) を呼び出すと顕著です。

**修正前（[エラー](/glossary/エラー/)が起きるコード）**

```javascript
const stripe = require("stripe")("sk_test_<your-secret-key>");

app.post("/webhook", async (req, res) => {
  const sig = req.headers["stripe-signature"];
  let event;

  try {
    event = stripe.webhooks.constructEvent(
      req.body,
      sig,
      "whsec_<your-webhook-secret>"
    );
  } catch (err) {
    // エラーログを記録する際に複数の API 呼び出しを実行
    for (let i = 0; i < 5; i++) {
      await stripe.events.retrieve(req.body.id); // 即座に5回リトライ
    }
    res.status(400).send("Invalid signature");
    return;
  }

  res.json({ received: true });
});
```

**修正後**

```javascript
const stripe = require("stripe")("sk_test_<your-secret-key>");

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

app.post("/webhook", async (req, res) => {
  const sig = req.headers["stripe-signature"];
  let event;

  try {
    event = stripe.webhooks.constructEvent(
      req.body,
      sig,
      "whsec_<your-webhook-secret>"
    );
  } catch (err) {
    // 指数バックオフでリトライ
    for (let i = 0; i < 3; i++) {
      try {
        await stripe.events.retrieve(req.body.id);
        break;
      } catch (retryErr) {
        if (i === 2) throw retryErr;
        await delay(Math.pow(2, i) * 1000); // 1秒、2秒、4秒
      }
    }
    res.status(400).send("Invalid signature");
    return;
  }

  res.json({ received: true });
});
```

### 原因3: 冪等性キーを設定せず重複リクエストを送信している

**なぜ発生するか**

[API](/glossary/api/) 呼び出し時にネットワークタイムアウトが発生し、アプリケーション側で同じ[リクエスト](/glossary/リクエスト/)を何度も再送する場合、Stripe 側でそれらをすべてカウントします。[冪等性](/glossary/冪等性/)キー（何度実行しても結果が同じ特性）を指定すれば、重複カウントを防げます。

**修正前（[エラー](/glossary/エラー/)が起きるコード）**

```python
import stripe
import requests

stripe.api_key = "sk_test_<your-secret-key>"

try:
    charge = stripe.Charge.create(
        amount=5000,
        currency="jpy",
        source="tok_visa"
    )
except requests.exceptions.Timeout:
    # タイムアウト時に即座に再試行（冪等性キーなし）
    charge = stripe.Charge.create(
        amount=5000,
        currency="jpy",
        source="tok_visa"
    )
```

**修正後**

```python
import stripe
import requests
import uuid

stripe.api_key = "sk_test_<your-secret-key>"

# 冪等性キーを事前に生成
idempotency_key = str(uuid.uuid4())

try:
    charge = stripe.Charge.create(
        amount=5000,
        currency="jpy",
        source="tok_visa",
        idempotency_key=idempotency_key
    )
except requests.exceptions.Timeout:
    # 同じ冪等性キーで再試行（2回目以降は最初の結果が返される）
    charge = stripe.Charge.create(
        amount=5000,
        currency="jpy",
        source="tok_visa",
        idempotency_key=idempotency_key
    )
```

## Stripe 固有の注意点

### API バージョンとレート制限の違い

Stripe の[レート制限](/glossary/レート制限/)は [API](/glossary/api/) バージョンによって異なります。テスト環境（`sk_test_`）では本番環境より高い[レート制限](/glossary/レート制限/)が適用されていますが、本番環境でも同じコードロジックが使えるように設計すべきです。

### 検索 API のレート制限

`stripe.Customer.search()` や `stripe.Charge.search()` などの検索 [API](/glossary/api/) は通常の [API](/glossary/api/) より厳しい[レート制限](/glossary/レート制限/)が適用されます。特に大規模な顧客[データベース](/glossary/データベース/)を検索する場合は、List [API](/glossary/api/) で自動ページングを使う方が推奨されます。

```python
# 重い検索（レート制限に引っかかりやすい）
customers = stripe.Customer.search(query='created>1704067200')

# 推奨: List API でページングを使用
customers = stripe.Customer.list(limit=100)
for customer in customers.auto_paging_iter():
    print(customer)
```

### Webhook エンドポイントの署名検証でのレート制限回避

[Webhook](/glossary/webhook/) 処理の中で複数の [API](/glossary/api/) 呼び出しが必要な場合、非同期処理（キューイング）を導入することで、429 [エラー](/glossary/エラー/)を回避できます。

```python
import stripe
from celery import shared_task

stripe.api_key = "sk_test_<your-secret-key>"

@shared_task
def process_charge_completion(charge_id):
    # 非同期で実行するため、メインのリクエストハンドラーを圧迫しない
    charge = stripe.Charge.retrieve(charge_id)
    # 追加処理...

@app.post("/webhook")
def webhook_handler():
    event = stripe.webhooks.constructEvent(...)
    
    if event["type"] == "charge.completed":
        # タスクキューに追加して即座に応答
        process_charge_completion.delay(event["data"]["object"]["id"])
    
    return {"status": "received"}
```

## それでも解決しない場合

### 確認すべきログとコマンド

Stripe [ダッシュボード](/glossary/ダッシュボード/)の **Developers > Events** セクションで、429 [エラー](/glossary/エラー/)が発生した正確な時刻と頻度を確認できます。また、以下の[コマンド](/glossary/コマンド/)で [API](/glossary/api/) 呼び出し履歴を確認してください。

```bash
# curl で Stripe イベント一覧を取得し、429 エラーをフィルター
curl -u sk_test_<your-secret-key>: \
  "https://api.stripe.com/v1/events?type=*.api_request_failure" \
  | grep -i "rate_limit"
```

### 公式ドキュメント

- [Stripe API Rate Limits](https://stripe.com/docs/rate-limits)
- [Stripe SDK のリトライロジック](https://stripe.com/docs/api/errors/handling?lang=python)
- [Webhook の署名検証とエラーハンドリング](https://stripe.com/docs/webhooks/signatures)

### コミュニティーリソース

GitHub の公式 Stripe ライブラリー（`stripe/stripe-python`、`stripe/stripe-node` など）の Issues セクションで「429」や「rate limit」を検索すると、他のユーザーの解決事例が見つかります。特に大規模なバッチ処理を行う場合は、既に同様の問題が報告されていることが一般的です。

公式 Stripe Slack コミュニティーでも、エンジニアサポートチームが実装パターンのアドバイスを提供しています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*