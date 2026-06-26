---
title: "Stripe の 402 エラー：原因と解決策"
date: 2026-05-25
description: "Stripeの402エラーは「Payment Required」を意味し、決済処理が失敗したときに返されるHTTPステータスコードです。"
tags: ["Stripe"]
errorCode: "402"
lastmod: 2026-06-14
service: "Stripe"
error_type: "402"
components: ["PaymentIntent", "Charge"]
related_services: ["3Dセキュア", "Webhook"]
top_queries:
- 'card_declined'
- 'stripe カードが拒否されました'
- 'stripe 決済 エラー'
---

## エラーの概要

Stripeの402[エラー](/glossary/エラー/)は「Payment Required」を意味し、決済処理が失敗したときに返される[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)です。カード拒否、残高不足、不正利用の疑い、または3Dセキュア[認証](/glossary/認証/)の失敗など、支払い側の問題で決済が完了できない状態を示しています。この[エラー](/glossary/エラー/)が発生した場合、決済データ自体は失われていませんが、[トランザクション](/glossary/トランザクション/)（取引）は成功していません。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": "card_declined",
    "message": "Your card was declined",
    "type": "card_error",
    "charge": "ch_1234567890abcdef"
  }
}
```

```json
{
  "error": {
    "code": "insufficient_funds",
    "message": "The card has insufficient funds",
    "type": "card_error",
    "decline_code": "insufficient_funds"
  }
}
```

## よくある原因と解決手順

### 原因1：カード情報の入力誤りまたは期限切れ

カード番号、有効期限、CVCコードが誤っているか、カードが既に期限切れの状態で決済を試みた場合に発生します。ユーザーの入力ミスや、古いカード情報を登録したまま放置されているケースが多いです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const payment = await stripe.charges.create({
  amount: 5000,
  currency: 'jpy',
  source: 'tok_visa', // 期限切れまたは無効なトークン
  description: 'Test charge'
});
```

**After（修正後）：**

```javascript
const paymentMethod = await stripe.paymentMethods.create({
  type: 'card',
  card: {
    number: '4242424242424242',
    exp_month: 12,
    exp_year: 2026, // 有効期限を確認・更新
    cvc: '314'
  }
});

const payment = await stripe.charges.create({
  amount: 5000,
  currency: 'jpy',
  payment_method: paymentMethod.id,
  description: 'Test charge'
});
```

### 原因2：カード発行銀行による拒否（セキュリティ判定）

カード発行銀行の不正利用検出システムが、取引パターンの異常（海外からの急な利用、高額決済など）を検出して自動的に決済を拒否する場合があります。この場合、ユーザー側でカード発行銀行に連絡して、取引承認を得る必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const charge = await stripe.charges.create({
  amount: 150000,
  currency: 'jpy',
  source: cardToken,
  description: 'High value transaction'
  // 金額や頻度の検証がない
});
```

**After（修正後）：**

```javascript
// クライアント側で事前に確認メッセージを表示
if (amount > 100000) {
  await showWarningDialog('高額決済です。確認メールをお送りします。');
}

const charge = await stripe.charges.create({
  amount: amount,
  currency: 'jpy',
  source: cardToken,
  description: 'Transaction',
  metadata: {
    transaction_type: 'purchase',
    user_location: userLocation
  }
});

// エラーハンドリングで拒否理由を確認
if (error.decline_code === 'generic_decline') {
  notifyUser('カード発行銀行の確認が必要です。銀行にお問い合わせください。');
}
```

### 原因3：残高不足または利用可能額の超過

カードの残高が決済額に満たない、または1日の利用限度額に達している状態です。特にデビットカードや家族カードでは、この種の[エラー](/glossary/エラー/)が頻出します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// 利用可能額の事前確認がない
const payment = await stripe.charges.create({
  amount: 50000,
  currency: 'jpy',
  source: debitCardToken,
  description: 'Purchase'
});
```

**After（修正後）：**

```javascript
// 決済前に履歴情報を確認
const chargeHistory = await stripe.charges.list({
  limit: 10
});

const today_total = chargeHistory.data
  .filter(c => new Date(c.created * 1000).toDateString() === new Date().toDateString())
  .reduce((sum, c) => sum + c.amount, 0);

if (today_total + amount > dailyLimit) {
  throw new Error('本日の利用限度額に達しています');
}

const payment = await stripe.charges.create({
  amount: amount,
  currency: 'jpy',
  source: cardToken,
  description: 'Purchase'
});
```

### 原因4：3Dセキュア認証の失敗または未承認

3Dセキュア[認証](/glossary/認証/)が必須のカード・地域での取引で、ユーザーが[認証](/glossary/認証/)を完了していない、または[タイムアウト](/glossary/タイムアウト/)した場合に発生します。Stripe Payment Intentsを使用していない古い実装で顕在化しやすいです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// 古い charges API を使用
const charge = await stripe.charges.create({
  amount: 5000,
  currency: 'jpy',
  source: token,
  description: 'Purchase'
});
```

**After（修正後）：**

```javascript
// Payment Intents API を使用（3DS対応）
const paymentIntent = await stripe.paymentIntents.create({
  amount: 5000,
  currency: 'jpy',
  payment_method_types: ['card'],
  metadata: { order_id: '<order_id>' }
});

// クライアント側で認証を処理
const { error, paymentIntent: confirmedIntent } = 
  await stripe.confirmCardPayment(paymentIntent.client_secret, {
    payment_method: {
      card: cardElement,
      billing_details: { name: '<customer_name>' }
    }
  });

if (confirmedIntent.status === 'succeeded') {
  // 決済成功
} else if (confirmedIntent.status === 'requires_action') {
  // 3Dセキュア認証が必要
  console.log('Customer authentication required');
}
```

## Stripe固有の注意点

### APIバージョンの確認
古い[API](/glossary/api/)[バージョン](/glossary/バージョン/)を使用していると、3Dセキュアなどの最新[セキュリティ](/glossary/セキュリティ/)機能に対応していない可能性があります。[ダッシュボード](/glossary/ダッシュボード/)の設定から使用中の[API](/glossary/api/)[バージョン](/glossary/バージョン/)を確認し、最新の安定版（2024年以降）にアップグレードしてください。

### Webhookの署名検証とリトライ処理
決済失敗時に[Webhook](/glossary/webhook/)で`charge.failed`イベントが送信されます。このイベントを正しく検証して、重複処理を防ぐ必要があります。

```python
import stripe
from flask import request

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, '<your_endpoint_secret>'
        )
    except ValueError:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError:
        return 'Invalid signature', 400
    
    if event['type'] == 'charge.failed':
        charge = event['data']['object']
        # 失敗理由をログに記録
        log_charge_failure(charge['id'], charge['failure_code'])
    
    return 'Success', 200
```

### 冪等性キーの使用
ネットワークエラーなどで同じ[リクエスト](/glossary/リクエスト/)が重複送信されるのを防ぐため、`Idempotency-Key`[ヘッダー](/glossary/ヘッダー/)を必ず設定してください。

```javascript
const idempotencyKey = generateUUID(); // 決済ごとにユニークなキーを生成

const charge = await stripe.charges.create(
  {
    amount: 5000,
    currency: 'jpy',
    source: cardToken
  },
  {
    idempotencyKey: idempotencyKey
  }
);
```

## それでも解決しない場合

### ログ確認とデバッグ方法
Stripe[ダッシュボード](/glossary/ダッシュボード/)（https://dashboard.stripe.com）の「ログ」セクションで、APIリクエストとレスポンスの詳細を確認できます。特に`decline_code`の値で具体的な拒否理由が判明します。

決済[テスト](/glossary/テスト/)用に、Stripeが提供するテストカード番号を使用してください：
- `4000000000000002`：カード拒否
- `4000002500003155`：3Dセキュア認証必須
- `5555555555554444`：Mastercardで常に成功

### 公式ドキュメント
- 「Handling card errors」（https://stripe.com/docs/payments/handling-payment-errors）：エラーハンドリングの実装ガイド
- 「Strong Customer Authentication」（https://stripe.com/docs/strong-customer-authentication）：3Dセキュア対応方法

### サポートへの問い合わせ
特定のカード番号での継続的な拒否、またはテストカードでも再現する場合は、Stripe公式サポート（https://support.stripe.com）へ問い合わせてください。その際、Charge [ID](/glossary/id/)やPayment Intent [ID](/glossary/id/)を記載すれば、迅速な対応が期待できます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*