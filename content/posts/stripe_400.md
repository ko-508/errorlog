---
draft: true
title: "Stripe の 400 エラー：原因と解決策"
date: 2026-05-25
description: "Stripe APIへのリクエストが400 Bad Requestを返す場合、リクエストの形式またはパラメータに問題があることを意味します。"
tags: ["Stripe"]
errorCode: "400"
lastmod: 2026-05-31
service: "Stripe"
error_type: "400"
components: ["PaymentIntent"]
related_services: []
---

## エラーの概要

Stripe [API](/glossary/api/)への[リクエスト](/glossary/リクエスト/)が**400 Bad Request**を返す場合、[リクエスト](/glossary/リクエスト/)の形式または[パラメータ](/glossary/パラメータ/)に問題があることを意味します。この[エラー](/glossary/エラー/)はStripe[サーバー](/glossary/サーバー/)が[リクエスト](/glossary/リクエスト/)を理解できなかったか、ビジネスルール上受け入れられない値が含まれていることを示しています。決済処理・顧客管理・サブスクリプション操作など、ほぼすべてのStripe [API](/glossary/api/)操作で発生する可能性があります。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": "invalid_request_error",
    "message": "Missing required param: amount",
    "param": "amount",
    "type": "invalid_request_error"
  }
}
```

```json
{
  "error": {
    "code": "invalid_request_error",
    "message": "Invalid positive integer: amount",
    "param": "amount",
    "type": "invalid_request_error"
  }
}
```

## よくある原因と解決手順

### 原因1：必須パラメータの欠落または型の不一致

なぜ発生するか：Stripe [API](/glossary/api/)の各[エンドポイント](/glossary/エンドポイント/)には必須[パラメータ](/glossary/パラメータ/)が定義されており、これらが不足している、または期待される型と異なる型で送信されると400[エラー](/glossary/エラー/)が返されます。例えば、決済作成時に`amount`（整数・セント単位）が文字列で送信された場合などです。

**Before（[エラー](/glossary/エラー/)が起きるコード）:**
```python
import stripe

stripe.api_key = "<your-api-key>"

# 金額を文字列で送信 → エラー
payment_intent = stripe.PaymentIntent.create(
    amount="1000",  # 文字列ではなく整数が必要
    currency="jpy",
    payment_method_types=["card"]
)
```

**After（修正後）:**
```python
import stripe

stripe.api_key = "<your-api-key>"

# 金額を整数で送信（セント単位）
payment_intent = stripe.PaymentIntent.create(
    amount=1000,  # 整数型で送信
    currency="jpy",
    payment_method_types=["card"]
)
```

### 原因2：通貨コードまたは金額の値が不正

なぜ発生するか：Stripeは対応する通貨コード（`jpy`、`usd`等）のみを受け入れます。また、金額は通貨によって有効な範囲が決まっており、JPYは通常1円以上の整数、USDは1セント以上である必要があります。0円や負の金額を指定すると400[エラー](/glossary/エラー/)になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）:**
```javascript
const stripe = require('stripe')('<your-api-key>');

// 不正な通貨コードと小数点金額
stripe.paymentIntents.create({
  amount: 1000.50,  // JPYは整数のみ許可
  currency: 'yen',  // 正しくは 'jpy'
  payment_method_types: ['card']
});
```

**After（修正後）:**
```javascript
const stripe = require('stripe')('<your-api-key>');

// 正しい通貨コードと整数金額
stripe.paymentIntents.create({
  amount: 1000,     // 整数型（1000円）
  currency: 'jpy',  // 小文字の通貨コード
  payment_method_types: ['card']
});
```

### 原因3：パラメータの組み合わせが許可されていない

なぜ発生するか：Stripeの[API](/glossary/api/)は特定の[パラメータ](/glossary/パラメータ/)組み合わせを認めていません。例えば、決済作成時に同時に複数の決済方法を指定したり、既に確定済みのPaymentIntentに対して金額を変更しようとしたりすると、相互に矛盾する[パラメータ](/glossary/パラメータ/)組み合わせとして400[エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）:**
```python
import stripe

stripe.api_key = "<your-api-key>"

# 2つの異なる支払いパラメータを同時に指定
payment_intent = stripe.PaymentIntent.create(
    amount=5000,
    currency="jpy",
    payment_method="pm_card_visa",  # payment_methodを指定
    source="tok_visa"                # sourceも指定 → 矛盾
)
```

**After（修正後）:**
```python
import stripe

stripe.api_key = "<your-api-key>"

# いずれか一方を指定
payment_intent = stripe.PaymentIntent.create(
    amount=5000,
    currency="jpy",
    payment_method="pm_card_visa",  # これだけを指定
    confirm=True
)
```

## Stripe固有の注意点

### APIバージョンの不整合

Stripeの[アカウント](/glossary/アカウント/)設定では特定の[API](/glossary/api/)[バージョン](/glossary/バージョン/)がデフォルトで使用されます。古いコードが新しい[API](/glossary/api/)[バージョン](/glossary/バージョン/)に対応していない場合、[パラメータ](/glossary/パラメータ/)名の廃止や仕様変更により400[エラー](/glossary/エラー/)が発生します。リクエストヘッダーに`Stripe-Version`を明示的に指定すると、特定[バージョン](/glossary/バージョン/)での動作を強制できます。

```bash
curl https://api.stripe.com/v1/payment_intents \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Stripe-Version: 2023-10-16" \
  -d amount=1000 \
  -d currency=jpy
```

### Webhookペイロードの署名検証

[Webhook](/glossary/webhook/)を受け取る際、`Stripe-Signature`[ヘッダー](/glossary/ヘッダー/)を検証しないと、不正な[ペイロード](/glossary/ペイロード/)が処理される可能性があります。署名検証を実装し、署名が一致しない場合は400で応答することで、[セキュリティ](/glossary/セキュリティ/)を強化できます。

```python
import stripe
from stripe.error import SignatureVerificationError

endpoint_secret = "<your-webhook-secret>"

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except SignatureVerificationError:
        return "Invalid signature", 400
    
    # イベント処理
    return "Success", 200
```

### 冪等性キーの活用

[ネットワーク](/glossary/ネットワーク/)障害により同じ[リクエスト](/glossary/リクエスト/)が複数回送信されるのを防ぐため、`Idempotency-Key`[ヘッダー](/glossary/ヘッダー/)を使用します。同じキーで送信された[リクエスト](/glossary/リクエスト/)は自動的に重複排除され、重複作成を防げます。このキーを省略すると、予期しない重複決済が発生する可能性があります。

```python
import stripe
import uuid

stripe.api_key = "<your-api-key>"

idempotency_key = str(uuid.uuid4())

payment_intent = stripe.PaymentIntent.create(
    amount=5000,
    currency="jpy",
    payment_method_types=["card"],
    idempotency_key=idempotency_key  # 重複排除キー
)
```

## それでも解決しない場合

### ログとデバッグ方法

Stripe[ダッシュボード](/glossary/ダッシュボード/)の**Developers > Logs**セクションで、[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)/[レスポンス](/glossary/レスポンス/)の詳細を確認できます。[リクエスト](/glossary/リクエスト/)[ID](/glossary/id/)を記録しておくと、問題の再現時に該当[ログ](/glossary/ログ/)を検索しやすくなります。

```python
# レスポンスからリクエストIDを取得
try:
    payment_intent = stripe.PaymentIntent.create(amount=1000)
except stripe.error.InvalidRequestError as e:
    print(f"Request ID: {e.request_id}")  # ログとマッチ
    print(f"Message: {e.message}")
    print(f"Param: {e.param}")
```

### 公式ドキュメント参照

- **[Stripe API Reference](https://stripe.com/docs/api)**：各[エンドポイント](/glossary/エンドポイント/)の必須[パラメータ](/glossary/パラメータ/)と型定義を確認
- **[Error Handling](https://stripe.com/docs/error-handling)**：エラーコードと対処法の公式ガイド
- **[API Versioning](https://stripe.com/docs/upgrades)**：[API](/glossary/api/)[バージョン](/glossary/バージョン/)変更履歴と非推奨[パラメータ](/glossary/パラメータ/)

### コミュニティリソース

Stripe公式の[GitHub Issues](https://github.com/stripe/stripe-python)や[Stack Overflow](https://stackoverflow.com/questions/tagged/stripe)では、同様の問題に直面した開発者の解決例が多数記録されています。[エラーメッセージ](/glossary/エラーメッセージ/)を含めて検索すると、既知の問題と解決策が見つかる可能性が高いです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*