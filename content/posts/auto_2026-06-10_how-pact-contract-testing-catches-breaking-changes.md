---
title: "Pact契約テストでWireMockが見逃す破壊的変更を捉える方法"
date: 2026-06-10
lastmod: 2026-06-10
draft: false
description: "WireMockのようなモックツールでは見逃されがちな、サービス間の破壊的変更をPact契約テストがいかに効果的に検出するかを解説します。実際のコード例と解決策を通じて、マイクロサービス環境での信頼性の高いテスト戦略を学びましょう。"
tags: ["Dev.to - DevOps", "Pact", "Contract Testing", "WireMock", "Microservices", "Python"]
trend_incident: true
---

## エラーの概要

この記事では、Pact契約テストが、WireMockのような従来のモックツールでは見過ごされがちな、サービス間の破壊的変更をいかに効果的に検出するかを解説します。特に、コンシューマーとプロバイダー間でAPIのフィールド名が変更された際に、WireMockベースのテストがグリーンパスを維持してしまう「信頼の罠」に焦点を当て、Pactがこの問題をどのように解決するかを実例を交えて説明します。

## 実際のエラーメッセージ例

Pact契約テストで破壊的変更が検出された場合、以下のような検証失敗メッセージが出力されます。

```
Verifying a pact between OrderService and PaymentGateway
  a successful payment charge (FAILED)
Failures:
  1.1) has a matching body
         $ -> Actual map is missing the following keys: status
  {
    "amount": 134.97,
  -  "status": "ACCEPTED",
  +  "result": "ACCEPTED",
    "transaction_id": "txn-abc-123"
  }
1 failed in 7.22s
```

このメッセージは、`PaymentGateway`が`OrderService`との契約に違反していることを示しています。具体的には、レスポンスボディから`status`キーが欠落しており、代わりに`result`キーが存在することが差分として表示されています。

## よくある原因と解決手順

### 原因1：WireMockがプロバイダーの変更を反映しない

WireMockは、テスト実行時に定義されたスタブに基づいて動作します。プロバイダーサービス（例：決済ゲートウェイ）がAPIのフィールド名を変更しても、WireMockのスタブが更新されない限り、コンシューマー側のテストは常に成功してしまいます。これは、スタブが実際のサービスの振る舞いから乖離しているにもかかわらず、テストが「グリーン」になるという「信頼の罠」を生み出します。

**なぜ発生するかの説明:**
WireMockは、コンシューマー側でプロバイダーの振る舞いを模倣するために使用される「行動の二重化」です。コンシューマーがスタブを維持するため、プロバイダーがAPIを変更しても、コンシューマーがスタブを明示的に更新しない限り、テストは変更を検知できません。

**Before（エラーが起きるコード）：**

```json
// wiremock/payment-mappings/payment-success.json (WireMockスタブ)
{
  "request": {
    "method": "POST",
    "url": "/payments/charge/success"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "status": "ACCEPTED",
      "transaction_id": "txn-abc-123",
      "amount": 134.97
    }
  }
}
```
プロバイダー側で`status`フィールドが`result`に変更されても、このスタブは更新されません。

**After（修正後）：**
この問題はWireMock単体では解決できません。Pact契約テストを導入することで、プロバイダー側の変更を自動的に検証し、デプロイ前に検出できます。

```python
# Pactコンシューマーテスト (Python)
# OrderServiceがPaymentGatewayに期待するレスポンスを定義
from pact import Consumer, Provider

def test_payment_gateway_consumer():
    pact = Consumer("OrderService").has_pact_with(Provider("PaymentGateway"))
    (pact
        .given("the payment gateway will accept the charge")
        .upon_receiving("a successful payment charge")
        .with_request("POST", "/payments/charge/success")
        .will_respond_with(200, body={"result": "ACCEPTED", # 期待するフィールド名を定義
                                      "transaction_id": "txn-abc-123",
                                      "amount": 134.97}))
    # ... 他のインタラクション ...
    with pact.serve() as srv:
        # OrderServiceがsrv.urlに対してリクエストを送信するテストを実行
        pass
    pact.write_file("pacts/") # .pactファイルを生成
```
このPactファイルはプロバイダー側で検証され、プロバイダーが`result`ではなく`status`を返した場合、検証は失敗します。

### 原因2：pact-python v3でのモックサーバーライフサイクル誤用

`pact-python` v3では、内部的にRust FFIバイナリを使用しており、モックサーバーのライフサイクル管理がv2以前とは異なります。特に、`serve()`が一度呼び出されると、それ以降は新しいインタラクションを追加できません。v2スタイルのモジュールスコープのフィクスチャで複数のテストケースを実行しようとすると、この制約に違反し、`RuntimeError: The provider state could not be specified.`が発生します。

**なぜ発生するかの説明:**
`pact-python` v3は、モックサーバーのハンドルが最初の`serve()`呼び出しで消費される設計になっています。これにより、すべてのインタラクション定義は`serve()`呼び出しの前に完了している必要があります。

**Before（エラーが起きるコード）：**

```python
# ❌ v2-style — pact-python v3でエラーが発生
class TestPaymentConsumer:
    @pytest.fixture(scope="module")
    def pact(self):
        return Consumer("OrderService").has_pact_with(Provider("PaymentGateway"))

    def test_success(self, pact):
        pact.given("payment succeeds").upon_receiving("a charge")...
        with pact: # ここでserve()が呼ばれる
            # test
            pass

    def test_declined(self, pact):
        pact.given("payment declined").upon_receiving("a decline")... # serve()後に追加しようとしてエラー
        # RuntimeError — handle already consumed
        pass
```

**After（修正後）：**

```python
# ✅ v3の正しいパターン — すべてのインタラクションをserve()呼び出し前に定義
def test_payment_gateway_consumer():
    pact = Consumer("OrderService").has_pact_with(Provider("PaymentGateway"))

    # すべてのインタラクションをserve()呼び出しの前に定義
    (pact
        .given("the payment gateway will accept the charge")
        .upon_receiving("a successful payment charge")
        .with_request("POST", "/payments/charge/success")
        .will_respond_with(200, body={"result": "ACCEPTED",
                                      "transaction_id": "txn-abc-123",
                                      "amount": 134.97}))
    (pact
        .given("the payment gateway will decline the charge")
        .upon_receiving("a declined payment charge")
        .with_request("POST", "/payments/charge/declined")
        .will_respond_with(402, body={"status": "DECLINED",
                                      "reason": "INSUFFICIENT_FUNDS"}))
    # ... 他のすべてのインタラクションをここに定義 ...

    with pact.serve() as srv:
        # 定義されたすべてのインタラクションに対してテストを実行
        # 例: OrderServiceがsrv.urlに対してリクエストを送信する
        pass
    pact.write_file("pacts/")
```

### 原因3：Pact Verifierのトランスポート設定ミス

`pact-python` v3の`Verifier`コンストラクタは、プロバイダーのホスト名のみを受け取ります。完全なURL（例：`http://localhost:8291`）を渡すと、後で`add_transport`でURLを設定した際に「Host mismatch」エラーが発生します。また、プロバイダーが意図的に遅延応答を返す場合、デフォルトの検証タイムアウト（5秒）では不十分で、接続エラーとして失敗することがあります。

**なぜ発生するかの説明:**
`Verifier`は、ホスト名とポート、プロトコルを個別に設定することを想定しています。完全なURLを渡すと、内部でホスト名が重複して解釈され、不一致が発生します。また、デフォルトのタイムアウトは一般的なケースを想定しており、意図的な遅延応答をテストする際には明示的な延長が必要です。

**Before（エラーが起きるコード）：**

```python
# ❌ "Host mismatch: localhost != http://localhost:8291" エラーが発生
from pact.verifier import Verifier

Verifier("PaymentGateway", "http://localhost:8291") \
    .add_transport(url="http://localhost:8291") \
    .add_source(pact_file) \
    .verify()

# ❌ タイムアウトにより検証失敗
Verifier("PaymentGateway", "localhost") \
    .add_transport(protocol="http", port=8291, scheme="http") \
    .add_source(pact_file) \
    .verify() # タイムアウトが6秒のスタブに対してデフォルトの5秒で失敗
```

**After（修正後）：**

```python
# ✅ 正しいVerifier設定
from pact.verifier import Verifier

Verifier("PaymentGateway", "localhost") \
    .add_transport(protocol="http", port=8291, scheme="http") \
    .add_source(pact_file) \
    .set_request_timeout(10000) # タイムアウトを10秒に延長（例：6秒の遅延スタブに対応）
    .verify()
```

## ツール固有の注意点

Pactは、コンシューマーとプロバイダー間の契約を自動的に検証する強力なツールですが、WireMockとは根本的に異なるアプローチを取ります。

*   **Pact:** コンシューマーがプロバイダーに何を期待するかを定義し、その契約をプロバイダー側で検証します。これにより、プロバイダーが契約に違反する変更を行った場合、デプロイ前に検出できます。これは「コンシューマー主導型契約テスト (Consumer-Driven Contract Testing)」と呼ばれます。
*   **WireMock:** コンシューマーがプロバイダーの振る舞いをモックするために使用します。スタブはコンシューマー側で管理されるため、プロバイダーの実際の変更を自動的に検出するメカニズムはありません。

Pactを導入する際は、コンシューマーテストで生成された`.pact`ファイルをプロバイダープロジェクトに渡し、プロバイダーのCI/CDパイプラインでその契約を検証するプロセスを確立することが重要です。これにより、サービス間の結合部分での破壊的変更を早期に、かつ自動的に検出できるようになります。

## それでも解決しない場合

*   **Pactログの確認:** Pactは詳細なログを出力します。環境変数`PACT_LOG_LEVEL`を`DEBUG`に設定して、より詳細な情報を取得してください。
*   **Pact公式ドキュメント:** `pact-python`の公式ドキュメントは、最新のAPI仕様と使用例を提供しています。特に、バージョンアップ時の変更点や、特定のオプションの挙動については、公式ドキュメントが最も信頼できる情報源です。
    *   [Pact Python Documentation](https://pact-foundation.github.io/pact-python/)
*   **Pactコミュニティ:** Pact FoundationのSlackチャンネルやGitHub Discussionsで質問を投稿し、コミュニティの助けを求めることも有効です。
*   **プロバイダー側の実装確認:** Pact検証が失敗した場合、コンシューマーの期待とプロバイダーの実際の振る舞いが一致していないことを意味します。プロバイダー側のAPI実装やデータ構造を再確認し、契約と一致しているかを確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*