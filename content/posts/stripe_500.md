---
title: "Stripe の 500 エラー：原因と解決策"
date: 2026-05-27
description: "Stripe API で 500 エラーが返される場合、Stripe 側のサーバーで予期しない内部エラーが発生していることを示します。"
tags: ["Stripe"]
errorCode: "500"
lastmod: 2026-06-14
service: "Stripe"
error_type: "500"
components: []
related_services: ["Python", "curl"]
---

## エラーの概要

Stripe APIで500エラーが返される場合、Stripe側のサーバーで予期しない内部エラーが発生していることを示します。このエラーはStripeのインフラストラクチャーの一時的な障害、リクエスト処理中の予期しない例外、またはAPI実装側の互換性問題など複数の原因で発生します。重要な点は、500エラー発生時にリクエストが部分的に処理されている可能性があり、冪等性キーの実装が不可欠になることです。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": "api_error",
    "message": "An error occurred while processing your request.",
    "type": "api_error",
    "status": 500
  }
}
```

```bash
curl -X POST https://api.stripe.com/v1/charges \
  -H "Authorization: Bearer sk_test_xxx" \
  -d "amount=2000&currency=jpy" \
  
# レスポンス
HTTP/1.1 500 Internal Server Error
{
  "error": {
    "code": "api_error",
    "message": "An error occurred while processing your request.",
    "type": "api_error",
    "status": 500,
    "request_id": "req_1abc2def3ghi"
  }
}
```

## よくある原因と解決手順

### 原因1：冪等性キー（Idempotency Key）の未設定による重複処理

Stripeで500エラーが発生した場合、リクエストが成功したのか失敗したのか不確実になります。リトライ時に同じ操作が2回実行されるリスクが高まります。冪等性キーを設定しないと、エラー発生時のリトライで二重課金などの問題が生じます。

**Before（エラーが起きるコード）：**

```javascript
// 冪等性キーなしで送信
const charge = await stripe.charges.create({
  amount: 2000,
  currency: 'jpy',
  source: 'tok_visa'
});
```

**After（修正後）：**

```javascript
// 冪等性キーを含めて送信
const idempotencyKey = 'order_12345_' + Date.now();
const charge = await stripe.charges.create({
  amount: 2000,
  currency: 'jpy',
  source: 'tok_visa'
}, {
  idempotencyKey: idempotencyKey
});
```

### 原因2：非推奨なAPIバージョンの使用

StripeはAPI仕様を定期的に更新し、古いバージョンはサポートが終了します。非推奨なバージョンへのリクエストは500エラーで返される場合があります。特にパラメーター形式や認証方式の変更時に発生しやすいです。

**Before（エラーが起きるコード）：**

```bash
# 旧いAPIバージョン
curl -X POST https://api.stripe.com/v1/charges \
  -u sk_test_xxx: \
  -d "amount=2000&currency=jpy&customer=cus_abc123"
```

**After（修正後）：**

```bash
# 現在のAPIバージョンで明示的に指定
curl -X POST https://api.stripe.com/v1/charges \
  -H "Authorization: Bearer sk_test_xxx" \
  -H "Stripe-Version: 2023-10-16" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "amount=2000&currency=jpy&customer=cus_abc123"
```

### 原因3：不正なカードブランドまたはサポート外の通貨組み合わせ

Stripeが内部的に処理できない決済パラメーター（例：実装環境でサポートしていないカードブランド、特定国での未対応通貨）を指定すると、500エラーで応答することがあります。

**Before（エラーが起きるコード）：**

```python
import stripe

stripe.api_key = "sk_test_xxx"

# 本来対応していない通貨や支払い方法の組み合わせ
charge = stripe.Charge.create(
    amount=5000,
    currency="xxx",  # 非対応の通貨コード
    source="tok_visa",
    description="test payment"
)
```

**After（修正後）：**

```python
import stripe

stripe.api_key = "sk_test_xxx"

# Stripeが対応する通貨コードと確認済みのカード情報を使用
supported_currencies = ["jpy", "usd", "eur", "gbp"]
currency = "jpy"

if currency in supported_currencies:
    charge = stripe.Charge.create(
        amount=5000,
        currency=currency,
        source="tok_visa",
        description="test payment"
    )
```

## Stripe固有の注意点

### Webhook署名検証とAPIバージョンの整合性

Webhookを受信する際、Stripe-Version ヘッダーが送信されます。ホスト側でこれを無視して古いAPIバージョンと想定して処理すると、ペイロード構造の不一致が生じて500エラーにつながります。Webhookエンドポイント側も明示的にAPIバージョンを指定するか、ダッシュボードでバージョンを統一する必要があります。

### リトライ戦略の実装

Stripe APIのレスポンスが500の場合、Stripeのサーバー側で処理途中の可能性があります。単純なリトライでは冪等性キーがないと重複決済が発生します。以下のように指数バックオフ+冪等性キーを組み合わせてください：

```javascript
async function createChargeWithRetry(chargeParams, maxRetries = 3) {
  const idempotencyKey = 'charge_' + chargeParams.orderId + '_' + Date.now();
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await stripe.charges.create(chargeParams, {
        idempotencyKey: idempotencyKey
      });
    } catch (error) {
      if (error.status === 500 && attempt < maxRetries - 1) {
        // 指数バックオフ：2^attempt 秒待機
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        continue;
      }
      throw error;
    }
  }
}
```

### テスト環境とライブ環境でのAPI仕様の違い

テスト環境（sk_test_）とライブ環境（sk_live_）で、一部の機能やリージョン対応が異なる場合があります。テスト環境では成功するが本番環境で500エラーになるケースは、この差異が原因のことがあります。Stripeダッシュボードの「アカウント設定 → API」セクションで、アカウントが対応している機能とバージョンを確認してください。

## それでも解決しない場合

### 確認すべき手順とログ

1. **Request IDの記録**：エラーレスポンスの `request_id` フィールドをメモしておきます。これはStripeサポートへの問い合わせ時に必須です。

2. **Stripeステータスページの確認**：https://status.stripe.com/ で、Stripe側に障害がないか確認します。インシデント進行中の場合は、復旧を待つ必要があります。

3. **ホスト側ログの確認**：アプリケーションサーバーのエラーログを詳しく確認し、Stripe SDK内部で例外が発生していないかを確認します。

4. **APIバージョンの確認コマンド**：

```bash
# ダッシュボード設定から現在のAPIバージョンを確認
# https://dashboard.stripe.com/account/apikeys にアクセスして
# 「Default API Version」を確認
```

### 公式ドキュメント参照

- **Stripe API Errors**：https://stripe.com/docs/error-codes
- **Idempotency**：https://stripe.com/docs/api/idempotent_requests
- **API Versioning**：https://stripe.com/docs/api/versioning

### コミュニティリソース

- Stripe GitHub Issues：https://github.com/stripe/stripe-python/issues （該当言語のリポジトリ）
- Stripe Developer Community：https://stripe.com/docs/support
- Stack Overflow の `stripe` タグ：実装言語固有の問題は検索してみてください

公式サポートに問い合わせる場合は、Request ID、使用しているSDKのバージョン、リクエストを送信した時刻（UTC）、APIバージョンをまとめて報告すれば、迅速に対応してもらえます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*