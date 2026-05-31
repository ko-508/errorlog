---
title: "Stripe の 403 エラー：原因と解決策"
date: 2026-05-26
description: "Stripe の 403 エラーは、認証には成功したものの、そのリクエストに対する十分な権限や許可がないことを示します。API キーが有効であっても、アクセス対象のリソースや実行しようとする操作に対して権限不足の状態です。"
tags: ["Stripe"]
errorCode: "403"
lastmod: 2026-05-31
---
## エラーの概要

Stripe の 403 エラーは、[認証](/glossary/認証/)には成功したものの、その[リクエスト](/glossary/リクエスト/)に対する十分な[権限](/glossary/権限/)や許可がないことを示します。[API](/glossary/api/) キーが有効であっても、アクセス対象のリソースや実行しようとする操作に対して権限不足の状態です。本番環境のデータ保護や機能制限の都合上、Stripe 側で意図的にアクセスをブロックしているケースが大半を占めます。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": "permission_error",
    "message": "You do not have permission to access this resource.",
    "type": "invalid_request_error"
  }
}
```

```bash
curl -X POST https://api.stripe.com/v1/charges \
  -H "Authorization: Bearer sk_test_xxxxx" \
  -d amount=1000 \
  -d currency=jpy \
  -d source=tok_visa

# レスポンス
HTTP/1.1 403 Forbidden
{
  "error": {
    "code": "restricted_api_key",
    "message": "The API key provided does not have permission to access the requested resource.",
    "type": "invalid_request_error"
  }
}
```

## よくある原因と解決手順

### 原因1: API キーの権限設定が不足している

Stripe では [API](/glossary/api/) キーに対して細かい権限制御（制限付き [API](/glossary/api/) キー）が可能です。制限付きキーを使用している場合、必要な操作に対応する[権限](/glossary/権限/)が付与されていないと 403 が発生します。

**Before（権限不足）:**
```bash
# sk_test_restricted_xxxxx には "charges:read" のみ付与
curl -X POST https://api.stripe.com/v1/charges \
  -H "Authorization: Bearer sk_test_restricted_xxxxx" \
  -d amount=1000 \
  -d currency=jpy \
  -d source=tok_visa

# 403 Forbidden が返される
```

**After（権限追加）:**
Stripe [ダッシュボード](/glossary/ダッシュボード/) → Settings → [API](/glossary/api/) Keys → Restricted keys で対象キーを編集し、以下の[権限](/glossary/権限/)を追加します。
- `charges:write` （決済作成・キャプチャに必要）
- `charges:read` （決済情報取得に必要）
- `payment_intents:write` （Payment Intent 操作に必要）

設定後は同じ[リクエスト](/glossary/リクエスト/)が成功するようになります。

### 原因2: テスト環境と本番環境の API キーを混同している

テスト用 [API](/glossary/api/) キー（`sk_test_`）で本番環境のリソースにアクセスしたり、その逆を行おうとすると 403 が返されます。Stripe は環境を厳密に分離しているため、キーとリソースの環境が一致していないとアクセスが拒否されます。

**Before（環境の混同）:**
```python
import stripe

# 本番環境のチャージ ID を使用
charge_id = "ch_1Bweted..."  # 本番環境で作成されたもの

# テスト用キーで本番リソースにアクセス（403）
stripe.api_key = "sk_test_xxxxx"
stripe.Charge.retrieve(charge_id)
```

**After（環境の統一）:**
```python
import stripe
import os

# 実行環境に応じて API キーを切り替え
if os.getenv('ENVIRONMENT') == 'production':
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY_PROD')  # sk_live_xxxxx
else:
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY_TEST')  # sk_test_xxxxx

# 同じ環境の ID を使用
charge_id = "ch_1BwetedXxx..."
stripe.Charge.retrieve(charge_id)
```

### 原因3: Stripe アカウントの機能制限や審査段階の制限

新規アカウントやアカウント審査中の場合、特定の Stripe 機能が使用禁止になっていることがあります。例えば、国際決済やファイル [API](/glossary/api/)、Connect 機能など、本来利用可能な機能でも一時的にロックされている可能性があります。

**Before（機能が制限されている状態）:**
```javascript
const stripe = require('stripe')('<sk_test_xxxxx>');

// ファイル API にアクセス（アカウント制限中は 403）
stripe.files.create({
  purpose: 'dispute_evidence',
  file: fs.createReadStream('evidence.pdf')
});
```

**After（制限解除または代替手段）:**
[ダッシュボード](/glossary/ダッシュボード/) → Settings → Account status で制限状況を確認します。制限が解除されるまで待つか、制限の種類によっては Stripe サポートに問い合わせて解除を[リクエスト](/glossary/リクエスト/)します。国際決済などの制限は通常、アカウント本人確認やビジネス情報の充実化により自動的に解除されます。

## Stripe 固有の注意点

### API バージョンによる権限要件の変化

Stripe では複数の [API](/glossary/api/) バージョンをサポートしており、バージョンによって必要な[権限](/glossary/権限/)が異なることがあります。例えば、Charges [API](/glossary/api/) と Payment Intents [API](/glossary/api/) では権限設定が異なります。Payment Intents を使う場合は `payment_intents:write` [権限](/glossary/権限/)が必須ですが、古いキーには付与されていないケースが見られます。

### Webhook 署名と IP ホワイトリスト

[Webhook](/glossary/webhook/) [エンドポイント](/glossary/エンドポイント/)への 403 エラーは、Stripe [ダッシュボード](/glossary/ダッシュボード/)で設定した IP ホワイトリストに Stripe の[サーバー](/glossary/サーバー/) IP が含まれていない場合に発生します。本来はリクエストソースの[認証](/glossary/認証/)なので 401 が適切ですが、一部の構成では 403 として返ることがあります。

**確認と設定:**
```bash
# Webhook エンドポイント設定で IP ホワイトリストを確認
# Settings → Webhooks → Endpoint → IP Whitelist
# Stripe の公開 IP 範囲：
# https://stripe.com/docs/ips
```

### 冪等性キーと再試行の権限

Stripe は[冪等性](/glossary/冪等性/)キー（何度実行しても同じ結果が得られる特性）を使った安全な再試行をサポートしていますが、特定の制限付きキーではこの機能が使用禁止になる場合があります。

```javascript
// 冪等性キー付きリクエスト
const charge = await stripe.charges.create(
  {
    amount: 1000,
    currency: 'jpy',
    source: 'tok_visa'
  },
  {
    idempotencyKey: 'unique-key-12345'
  }
);
```

## それでも解決しない場合

### 確認すべき情報

1. **[API](/glossary/api/) キーの詳細確認**: [ダッシュボード](/glossary/ダッシュボード/) → Developers → [API](/glossary/api/) Keys で対象キーをクリックし、付与されている権限一覧を確認します。`Read` / `Write` [権限](/glossary/権限/)が正しく有効になっているか確認してください。

2. **イベントログの確認**: [ダッシュボード](/glossary/ダッシュボード/) → Developers → Events で該当の 403 エラーを検索し、詳細なエラーメッセージを確認します。`permission_error` や `restricted_api_key` などのコード名がエラータイプを特定する手がかりになります。

3. **Stripe [CLI](/glossary/cli/) でのテスト**: Stripe [CLI](/glossary/cli/) を使ってローカル環境でテストすることで、[ネットワーク](/glossary/ネットワーク/)経由のエラーかアカウント設定のエラーか判別できます。

```bash
# Stripe CLI をインストール後
stripe login  # アカウント認証
stripe api POST /v1/charges amount=1000 currency=jpy source=tok_visa
```

### 公式ドキュメント参照

- [API キーのセットアップ](https://stripe.com/docs/keys)
- [Restricted API Keys](https://stripe.com/docs/keys#limit-access) 
- [エラーコード リファレンス](https://stripe.com/docs/error-codes)
- [テスト環境と本番環境](https://stripe.com/docs/keys#test-live-modes)

### コミュニティリソース

Stripe の GitHub [リポジトリ](/glossary/リポジトリ/)で同じ問題を報告しているユーザーがいないか確認できます。また、Stripe サポートは 24 時間対応なので、アカウント関連の制限が原因と疑われる場合は直接問い合わせることをお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*