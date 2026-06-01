---
title: "Stripe の 404 エラー：原因と解決策"
date: 2026-05-27
description: "Stripe APIで404エラーが返される場合、指定したリソース（Customer、PaymentIntent、Chargeなど）がStripeサーバー上に存在しないか、アクセス権限のないリソースへのアクセスを試みたことを示します。"
tags: ["Stripe"]
errorCode: "404"
lastmod: 2026-05-31
---
## エラーの概要

Stripe APIで404エラーが返される場合、指定したリソース（Customer、PaymentIntent、Chargeなど）がStripeサーバー上に存在しないか、アクセス権限のないリソースへのアクセスを試みたことを示します。このエラーはAPIリクエストの失敗を意味し、データの喪失ではなく、参照先の問題です。Stripe APIの標準HTTPステータスコードの一つで、REST APIとも統合型のNode.js/Python SDKでも同じ形式で返されます。

## 実際のエラーメッセージ例

REST APIでの404レスポンス：

```json
{
  "error": {
    "code": "resource_missing",
    "message": "No such customer: cus_InvalidID123",
    "param": "id",
    "type": "invalid_request_error"
  }
}
```

Node.js SDKでの404エラー例：

```javascript
try {
  const customer = await stripe.customers.retrieve('cus_InvalidID123');
} catch (error) {
  console.error(error.message);
  // Error: No such customer: cus_InvalidID123
}
```

## よくある原因と解決手順

### 原因1：リソースIDの指定ミスまたはコピペエラー

Stripe APIリクエストで使用するIDが正確でない場合、404エラーが発生します。特に顧客IDやPaymentIntent IDは英数字が長く、一文字の違いで見つからなくなります。

**修正前（エラーが起きるコード）：**

```python
import stripe

stripe.api_key = "sk_live_..."

# IDをハードコーディングまたは手入力した場合の例
customer = stripe.Customer.retrieve("cus_1234567890")  # 実際には存在しないID
```

**修正後：**

```python
import stripe

stripe.api_key = "sk_live_..."

# ダッシュボードから正確なIDをコピーして使用
customer = stripe.Customer.retrieve("cus_1a2b3c4d5e6f7g8h9i")

# または、顧客情報を先に作成してから取得
customer = stripe.Customer.create(
    email="user@example.com",
    description="Test Customer"
)
retrieved = stripe.Customer.retrieve(customer.id)
```

### 原因2：テスト環境と本番環境のAPIキー混在

テスト用APIキー（`pk_test_`、`sk_test_`）で本番環境のリソースにアクセスしたり、その逆を行うと404が返されます。Stripeは環境ごとにデータを完全に分離しているため、異なるキーでアクセスしたリソースは見つかりません。

**修正前（エラーが起きるコード）：**

```javascript
const stripe = require('stripe');

// 本番キーを使用して初期化
const stripeClient = stripe('sk_live_abcd1234...');

// しかし、テスト環境で作成したPaymentIntentのIDを指定
const paymentIntent = await stripeClient.paymentIntents.retrieve('pi_test_12345');
// Error: 404 Not Found
```

**修正後：**

```javascript
const stripe = require('stripe');

// 環境に合わせたキーを使用
const apiKey = process.env.NODE_ENV === 'production' 
  ? process.env.STRIPE_LIVE_KEY 
  : process.env.STRIPE_TEST_KEY;

const stripeClient = stripe(apiKey);

// テスト環境ではテストで作成したIDのみを参照
const paymentIntent = await stripeClient.paymentIntents.retrieve('pi_test_12345');
```

### 原因3：リソースが削除済みまたは有効期限切れ

Stripe上で削除されたリソースや、有効期限が切れた支払いセッションへのアクセス試行で404が返されます。特にPayment LinkやCheckout Sessionは一定期間後に参照できなくなるケースがあります。

**修正前（エラーが起きるコード）：**

```python
import stripe

stripe.api_key = "sk_test_..."

# 削除済みの顧客IDにアクセス
try:
    customer = stripe.Customer.retrieve("cus_deleted12345")
except stripe.error.InvalidRequestError as e:
    print(e)  # 404 returned
```

**修正後：**

```python
import stripe

stripe.api_key = "sk_test_..."

# 削除前に顧客の存在を確認し、存在しない場合は新規作成
try:
    customer = stripe.Customer.retrieve("cus_deleted12345")
except stripe.error.InvalidRequestError as e:
    if e.http_status == 404:
        # 新しい顧客として作成
        customer = stripe.Customer.create(
            email="user@example.com",
            description="Recreated Customer"
        )
        print(f"Customer created: {customer.id}")
```

## Stripe固有の注意点

### APIバージョンの違いによる404

Stripeは複数のAPIバージョンをサポートしており、古いバージョンのAPIを使用していると、新しいバージョンで追加されたリソースにアクセスできません。ダッシュボード設定で指定されたAPIバージョンと、コード内で使用しているバージョンを統一する必要があります。

```bash
# リクエストヘッダーでAPIバージョンを明示的に指定
curl https://api.stripe.com/v1/customers/cus_test123 \
  -H "Stripe-Version: 2023-10-16" \
  -u sk_test_...:
```

### Webhook署名検証とリソースID

Webhookで受け取ったイベントのリソースIDを直後に参照する場合、わずかな遅延で404が返ることがあります。Stripeのイベント処理は非同期（実行順序が保証されない処理方式）のため、リトライロジック（失敗時に再度試みる処理）を実装することが推奨されます。

```python
def handle_webhook(event):
    if event['type'] == 'payment_intent.succeeded':
        payment_intent_id = event['data']['object']['id']
        
        # リトライロジックを実装
        max_retries = 3
        for attempt in range(max_retries):
            try:
                pi = stripe.PaymentIntent.retrieve(payment_intent_id)
                return pi
            except stripe.error.InvalidRequestError as e:
                if e.http_status == 404 and attempt < max_retries - 1:
                    time.sleep(1)  # 1秒待機して再試行
                else:
                    raise
```

### Stripe Connectのアカウント制限

Stripe Connect（複数のビジネスアカウント間での連携）でアカウント間のリソースアクセスを試みる場合、適切な認可ヘッダー（HTTPリクエストの補足情報）がないと404が返されます。`Stripe-Account`ヘッダーを正確に指定する必要があります。

```javascript
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

// 連携アカウントのリソースにアクセス
const customer = await stripe.customers.retrieve(
  'cus_connected123',
  { stripeAccount: 'acct_partner1234567890' }
);
```

## それでも解決しない場合

### ログとデバッグ情報の確認

Stripeダッシュボードの「Developers」→「API logs」セクションで、実際に送信されたリクエストと返されたレスポンスを確認できます。ここで正確なエラーメッセージとリソースIDを再度検証してください。

### 公式ドキュメント

以下のページで詳細情報が入手できます：
- 「API Errors」ページ：全エラータイプと対応方法の完全なリスト
- 「Authentication」ページ：APIキーの正しい使い分け方法
- 「API Versioning」ページ：バージョン管理のベストプラクティス

### サポート情報の収集

解決しない場合は、Stripeサポートに以下の情報を提供してください：
- 問題が発生した正確な日時（タイムゾーン付き）
- 使用したAPIキー（テストキーか本番キーか）
- 実際のリクエスト内容（個人情報を除外）
- Webhook ID（該当する場合）

GitHubのstripe-nodeやstripe-pythonリポジトリーのIssuesセクションで、類似の問題が報告されていないか確認することも有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*