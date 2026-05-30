---
title: "Stripe の 401 エラー：原因と解決策"
date: 2026-05-25
description: "Stripe API から返される 401（Unauthorized）エラーは、リクエストに含まれる認証情報（API キーまたはアクセストークン）が無効・期限切れ・形式不正であることを示します。"
tags: ["Stripe"]
errorCode: "401"
lastmod: 2026-05-31
---
## エラーの概要

Stripe API から返される 401（Unauthorized）エラーは、リクエストに含まれる認証情報（API キーまたはアクセストークン）が無効・期限切れ・形式不正であることを示します。Stripe では認証なしにはいかなる API 呼び出しも実行できないため、開発環境と本番環境を問わず頻繁に発生するエラーです。データが消失することはありませんが、決済処理が停止するため迅速な対応が必要です。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "Invalid API Key provided: sk_live_xxxxx",
    "type": "invalid_request_error",
    "param": null
  }
}
```

```bash
curl https://api.stripe.com/v1/charges \
  -u sk_test_invalid_key_here: \
  -d amount=2000 \
  -d currency=jpy

# 出力:
# {"error":{"code":"invalid_api_key","message":"Invalid API Key provided"}}
```

## よくある原因と解決手順

**原因1：テスト環境と本番環境のキーを混同している**

Stripe では `sk_test_` で始まるテスト用キーと `sk_live_` で始まる本番用キーが別々に発行されます。本番環境のコードでテスト用キーを使用すると 401 エラーになります。

**Before（エラーが起きるコード）：**
```javascript
const stripe = require('stripe')('sk_test_xxxxx'); // テスト用キー

// 本番環境で実行
const charge = await stripe.charges.create({
  amount: 10000,
  currency: 'jpy'
});
```

**After（修正後）：**
```javascript
// 環境変数から適切なキーを読み込む
const apiKey = process.env.NODE_ENV === 'production' 
  ? process.env.STRIPE_SECRET_LIVE 
  : process.env.STRIPE_SECRET_TEST;

const stripe = require('stripe')(apiKey);

const charge = await stripe.charges.create({
  amount: 10000,
  currency: 'jpy'
});
```

**原因2：シークレットキーではなく公開キーを使用している**

Stripe には 2 種類のキーが存在します。サーバー側では必ずシークレットキー（`sk_live_` または `sk_test_`）を使用し、公開キー（`pk_live_` または `pk_test_`）はクライアント側のみで使用します。

**Before（エラーが起きるコード）：**
```python
import stripe

# 誤り：公開キーをサーバー側で使用
stripe.api_key = "pk_test_xxxxx"

try:
    charge = stripe.Charge.create(
        amount=1000,
        currency="jpy",
        source="tok_visa"
    )
except stripe.error.AuthenticationError as e:
    print("認証エラー:", e)
```

**After（修正後）：**
```python
import stripe

# 正しい：シークレットキーをサーバー側で使用
stripe.api_key = "sk_test_xxxxx"

try:
    charge = stripe.Charge.create(
        amount=1000,
        currency="jpy",
        source="tok_visa"
    )
except stripe.error.AuthenticationError as e:
    print("認証エラー:", e)
```

**原因3：API キーの形式が不正またはコピー時にスペースが含まれている**

API キーをコピペする際に、誤って前後に空白文字やタブが含まれたり、キーの一部が欠落していたりすると 401 エラーになります。

**Before（エラーが起きるコード）：**
```bash
# キーの後ろに余計なスペースやタブが含まれている
API_KEY="sk_test_xxxxx " 

curl https://api.stripe.com/v1/charges \
  -u ${API_KEY}: \
  -d amount=2000 \
  -d currency=jpy
# → 401 エラー
```

**After（修正後）：**
```bash
# 環境変数にキーを設定する際、前後の空白を削除
API_KEY=$(echo "sk_test_xxxxx" | xargs)

curl https://api.stripe.com/v1/charges \
  -u ${API_KEY}: \
  -d amount=2000 \
  -d currency=jpy
```

**原因4：アクセストークンの有効期限が切れている**

OAuth（第三者認可プロトコル）を使用して Stripe にアクセス権を委譲している場合、アクセストークンには有効期限があります。期限切れのトークンで API リクエストを送信すると 401 エラーになります。

**Before（エラーが起きるコード）：**
```javascript
// 古いトークンをそのまま使用
const accessToken = storedToken; // 数ヶ月前に取得したトークン

const response = await fetch('https://api.stripe.com/v1/charges', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: new URLSearchParams({amount: 10000, currency: 'jpy'})
});
```

**After（修正後）：**
```javascript
// トークンの有効期限をチェックし、必要に応じてリフレッシュ
if (isTokenExpired(storedToken)) {
  storedToken = await refreshAccessToken(refreshToken);
}

const response = await fetch('https://api.stripe.com/v1/charges', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${storedToken}`
  },
  body: new URLSearchParams({amount: 10000, currency: 'jpy'})
});
```

## Stripe 固有の注意点

**API キーの権限制限：** Stripe ダッシュボードで API キーの権限を制限することができます。制限されたキーで全権限が必要な操作（チャージ作成など）を実行すると 401 エラーになります。ダッシュボードの「開発者」→「API キー」セクションで、各キーの権限スコープ（アクセス範囲）を確認してください。

**Webhook 署名検証：** Webhook エンドポイント（外部からの呼び出し受け入れ口）を呼び出す際、Stripe は `Stripe-Signature` ヘッダーで署名を送信します。このヘッダーが不正な場合も認証エラーとして扱われることがあります。Webhook の署名検証には必ず Stripe 公式ライブラリの `verifyWebhookSignature()` メソッドを使用してください。

**Connected Account（Stripe Connect）：** 複数の Stripe アカウントを管理する場合、リクエストヘッダーに正しい `Stripe-Account` ID を指定しないと 401 エラーが発生します。

```bash
curl https://api.stripe.com/v1/charges \
  -H "Stripe-Account: acct_xxxxx" \
  -u sk_test_xxxxx:
```

**テスト用キーの機能制限：** テスト環境のテスト用キー（`sk_test_`）では、本番環境でのみ利用可能な機能の実行が制限される場合があります。

## それでも解決しない場合

**Step 1：ログを確認する**

Node.js では以下のコマンドで詳細なデバッグ情報を表示できます。

```bash
DEBUG=stripe:* node your_script.js
```

**Step 2：API キーの妥当性を確認する**

Stripe ダッシュボードにログインし、「開発者」→「API キー」から実際に発行されているキーのリストを確認してください。コピペしたキーが有効なキーと完全一致しているか確認します。

**Step 3：リクエストのヘッダーを確認する**

cURL または Postman で以下コマンドを実行し、実際に送信されているリクエストヘッダーを確認してください。

```bash
curl -v https://api.stripe.com/v1/charges \
  -u sk_test_xxxxx: \
  -d amount=2000
```

出力の `> Authorization` の行を確認し、キーが正しく送信されているか確認します。

**Step 4：公式ドキュメントと GitHub Issues を確認する**

[Stripe API リファレンス - Authentication](https://stripe.com/docs/api/authentication) で認証方法の最新仕様を確認してください。

使用しているライブラリ（stripe.js、stripe-python など）の [GitHub リポジトリ](https://github.com/stripe) で同じエラーについて報告されていないか検索し、既知の問題がないか確認します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*