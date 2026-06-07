---
title: "Stripe の 402 エラー：原因と解決策"
date: 2026-05-25
description: "Stripeの402エラーは「Payment Required」を意味し、決済処理が失敗したときに返されるHTTPステータスコードです。"
tags: ["Stripe"]
errorCode: "402"
lastmod: 2026-05-31
---
# Stripeの402エラーは「Payment Required」を意味し、決済処理が失敗したときに返されるHTTPステータスコードです。カード拒否、残高不足、不正利用の疑い、または3Dセキュア認証の失敗など、支払い側の問題で決済が完了できない状態を示しています。このエラーが発生した場合、決済データ自体は失われていませんが、トランザクション（取引）は成功していません。

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

カード番号、有効期限、CVCの入力に誤りがあるか、カード自体が既に有効期限を迎えている場合、Stripeは決済を拒否します。

**修正例：**
```javascript
const payment = await stripe.confirmCardPayment(clientSecret, {
  payment_method: {
    card: {
      number: '4242424242424242', // 正しいテストカード番号
      exp_month: 12,
      exp_year: 2025, // 有効な年
      cvc: '314'
    }
  }
});
```

### 原因2：カード会社による拒否（不正利用判定、残高不足など）

カード会社の判断で決済がブロックされることがあります。金額が大きい、カード利用国と異なる国からのアクセス、利用限度額超過などが理由として考えられます。

**修正例：**
```python
import stripe

stripe.api_key = "sk_live_<your-secret-key>"

# 金額を妥当な範囲に修正し、メタデータで取引内容を明確化
charge = stripe.Charge.create(
  amount=50000,  # 妥当な金額
  currency="jpy",
  source="tok_visa",
  description="Standard transaction",
  metadata={"order_id": "ord_12345"}
)
```

### 原因3：3Dセキュア認証の失敗または未完了

3Dセキュア（本人認証サービス）が必須の場合、[認証](/glossary/認証/)フローの実装が不完全だと402[エラー](/glossary/エラー/)が発生します。

**修正例：**
```javascript
const {paymentIntent, error} = await stripe.confirmCardPayment(
  clientSecret,
  {
    payment_method: {
      card: cardElement,
      billing_details: {
        name: "John Doe"
      }
    }
  },
  {
    handleActions: true  // 3Dセキュア認証を自動処理
  }
);
```

### 原因4：PaymentIntentのステータス確認の遅延

非同期処理でPaymentIntentの最終ステータスを確認する前に決済[リクエスト](/glossary/リクエスト/)を再送信すると、重複処理が発生して402[エラー](/glossary/エラー/)になることがあります。

**修正例：**
```python
# PaymentIntentのステータス確認後、必要な場合のみ確認
intent = stripe.PaymentIntent.retrieve(pi_id)

if intent.status == "requires_confirmation":
  intent.confirm()
elif intent.status == "succeeded":
  print("Already confirmed")
```

## Stripe固有の注意点

### テストカード番号の使い分け

本番環境で402[エラー](/glossary/エラー/)が頻発する場合、開発環境での検証が不十分な可能性があります。Stripeが提供するテストカード番号を使用して事前に各シナリオをテストしてください。

- `4242424242424242` - 決済成功
- `4000000000000002` - card_declined（一般的な拒否）
- `4000002500003155` - insufficient_funds（残高不足）
- `4000002000000003` - requires_3d_secure（3Dセキュア認証必須）

### decline_codeの確認

[エラーレスポンス](/glossary/エラーレスポンス/)に含まれる `decline_code` フィールドを確認することで、より正確な原因特定ができます。

```python
import stripe

try:
  charge = stripe.Charge.create(
    amount=5000,
    currency="jpy",
    source="tok_visa"
  )
except stripe.error.CardError as e:
  error_code = e.decline_code
  print(f"Decline code: {error_code}")
  # stolen_card, lost_card, insufficient_funds など
```

### Webhookイベントのチェック

決済処理が失敗しても、`charge.failed` イベントが[Webhook](/glossary/webhook/)に送信されます。これを適切にハンドリングして、ユーザーに失敗理由を正確に伝えることが重要です。

```python
@app.route('/webhook', methods=['POST'])
def handle_webhook():
  event = stripe.Event.construct_from(
    json.loads(request.data), stripe.api_key
  )
  
  if event['type'] == 'charge.failed':
    charge = event['data']['object']
    print(f"Charge failed: {charge['failure_code']}")
    # 失敗内容をデータベースに記録
  
  return '', 200
```

## ログ確認とデバッグ方法

Stripe[ダッシュボード](/glossary/ダッシュボード/)の「Logs」セクションで[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)・[レスポンス](/glossary/レスポンス/)の全詳細を確認できます。以下の情報を記録してください。

- **Request ID** - `req_` で始まる一意の識別子
- **Charge ID** - `ch_` で始まるチャージID
- **PaymentIntent ID** - `pi_` で始まるペイメントID
- **Decline Code** - `insufficient_funds` など具体的な拒否理由

## 公式ドキュメント参照

- **Stripeエラーコード解説** - https://stripe.com/docs/error-codes（各エラーの詳細と対応方法）
- **PaymentIntentガイド** - https://stripe.com/docs/payments/payment-intents（決済フロー全体の理解）
- **3Dセキュア実装ガイド** - https://stripe.com/docs/payments/3d-secure（強力認証の設定方法）

問題が解決しない場合、Stripe[ダッシュボード](/glossary/ダッシュボード/)の「Contact Support」から直接問い合わせてください。本番環境の[エラー](/glossary/エラー/)は優先対応の対象となります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*