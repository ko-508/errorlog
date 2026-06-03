---
title: "Stripe の 500 エラー：原因と解決策"
date: 2026-05-27
description: "Stripe API で 500 エラーが返される場合、Stripe 側のサーバーで予期しない内部エラーが発生していることを示します。"
tags: ["Stripe"]
errorCode: "500"
lastmod: 2026-05-31
---
## エラーの概要

Stripe [API](/glossary/api/) で 500 エラーが返される場合、Stripe 側のサーバーで予期しない内部エラーが発生していることを示します。このエラーは Stripe のインフラストラクチャーの一時的な障害、[リクエスト](/glossary/リクエスト/)処理中の予期しない例外、または API 実装側の互換性問題など複数の原因で発生します。重要な点は、500 エラー発生時にリクエストが部分的に処理されている可能性があり、冪等性キー（何度実行しても同じ結果になる特性）の実装が重要になることです。

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
  -u sk_live_xxxxx: \
  -d "amount=2000" \
  -d "currency=jpy" \
  -d "source=tok_visa"

# レスポンス
HTTP/1.1 500 Internal Server Error
Content-Type: application/json

{"error":{"message":"An error occurred while processing your request.","type":"api_error","status":500}}
```

## よくある原因と解決手順

### 原因1: Stripe 側の一時的な障害またはメンテナンス

API エンドポイント（接続地点）へのリクエストが失敗し、ログに「500」が返されている場合、Stripe 側で予定外または予定内のメンテナンスが実施されている可能性があります。

**対処方法（障害確認と再試行）:**
```python
import stripe
import time
import requests

def check_stripe_status():
    """Stripe 公式ステータスページを確認"""
    response = requests.get("https://status.stripe.com/api/v2/status.json")
    status_data = response.json()
    return status_data["status"]["indicator"]

def create_charge_with_retry():
    stripe.api_key = "sk_live_xxxxx"
    
    # 事前に Stripe ステータスを確認
    if check_stripe_status() != "none":
        print("Stripe has ongoing incidents. Waiting...")
        time.sleep(30)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            charge = stripe.Charge.create(
                amount=2000,
                currency="jpy",
                source="tok_visa"
            )
            return charge
        except stripe.error.APIError as e:
            if e.http_status == 500:
                wait_time = (2 ** attempt) + (0.1 * attempt)  # 指数バックオフ
                print(f"500 error. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
```

### 原因2: API バージョン互換性の問題またはリクエスト形式エラー

古い API バージョン指定や廃止されたパラメーターを使用している場合、サーバー側で 500 エラーが発生することがあります。

**対処方法（現在のバージョンと正しいパラメーター）:**
```python
import stripe

stripe.api_key = "sk_live_xxxxx"
# API バージョンを明示的に指定（最新版）
stripe.api_version = "2023-10-16"

try:
    charge = stripe.Charge.create(
        amount=2000,
        currency="jpy",
        source="tok_visa",
        metadata={"order_id": "12345"},
        description="Product purchase"
    )
except stripe.error.APIError as e:
    print(f"Error status: {e.http_status}, Message: {e.user_message}")
```

### 原因3: 冪等性キーの不正または重複

Stripe では冪等性キーを使用して同じリクエストの重複実行を防ぎます。各リクエストに一意のキーを割り当て、同じキーで複数の異なる処理を実行しないことが重要です。

**対処方法（冪等性キーの正しい使用）:**
```python
import stripe
import uuid

stripe.api_key = "sk_live_xxxxx"

def create_charge_safely(amount, currency, source):
    """冪等性キーを使用して安全にチャージを作成"""
    # 各リクエストで一意のキーを生成
    idempotency_key = str(uuid.uuid4())
    
    try:
        charge = stripe.Charge.create(
            amount=amount,
            currency=currency,
            source=source,
            idempotency_key=idempotency_key
        )
        return charge
    except stripe.error.APIError as e:
        if e.http_status == 500:
            # 冪等性キーで保護されているため、同じキーで再試行可能
            charge = stripe.Charge.create(
                amount=amount,
                currency=currency,
                source=source,
                idempotency_key=idempotency_key
            )
            return charge
        raise

# 使用例
charge1 = create_charge_safely(2000, "jpy", "tok_visa")
charge2 = create_charge_safely(3000, "jpy", "tok_visa")
```

## ツール固有の注意点

### Webhook 処理での 500 エラー

Webhook エンドポイントで Stripe からの POST リクエストを処理中に 500 を返すと、Stripe は自動的に再試行します。正しい署名検証後に処理を進める必要があります。

```python
import stripe
from flask import Flask, request

app = Flask(__name__)
stripe.api_key = "sk_live_xxxxx"

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, "whsec_test_secret"
        )
    except ValueError as e:
        return {"error": "Invalid payload"}, 400
    except stripe.error.SignatureVerificationError:
        return {"error": "Invalid signature"}, 400
    
    # イベント処理でエラーが起きた場合は 500 を返さない
    try:
        if event["type"] == "charge.succeeded":
            charge_id = event["data"]["object"]["id"]
            # 処理実行
            process_charge(charge_id)
        return {"status": "success"}, 200
    except Exception as e:
        # ログに記録し、500 ではなく 200 を返す
        print(f"Webhook processing error: {e}")
        return {"status": "received"}, 200
```

### Stripe ライブラリのバージョン

古い `stripe-python` ライブラリを使用していると、API 仕様の変更に対応していない可能性があります。

```bash
# 最新バージョンへ更新
pip install --upgrade stripe
```

## それでも解決しない場合

### 確認すべきログとデバッグ方法

```python
import stripe
import logging

# Stripe ライブラリのログを有効化
logging.basicConfig(level=logging.DEBUG)

stripe.api_key = "sk_live_xxxxx"
stripe.log = "debug"  # デバッグログを出力

# リクエストを実行するとHTTPヘッダーと本体がログに出力される
charge = stripe.Charge.create(amount=2000, currency="jpy", source="tok_visa")
```

公式ドキュメントの確認ポイント：
- Stripe API Reference（https://stripe.com/docs/api）：使用しているエンドポイントの最新仕様確認
- API Versioning（https://stripe.com/docs/api/versioning）：API バージョンの管理方法
- Error Handling（https://stripe.com/docs/error-handling）：エラータイプの詳細

問題が継続する場合は、Stripe 公式サポート（https://support.stripe.com/contact）に問い合わせてください。リクエスト ID を含めることで調査が効率化されます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*