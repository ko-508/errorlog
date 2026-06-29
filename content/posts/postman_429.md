---
draft: true
title: "Postman の 429 エラー：原因と解決策"
date: 2026-06-17
description: "テスト対象APIのレート制限に達した"
tags: ["Postman"]
errorCode: "429"
service: "Postman"
error_type: "429"
components: ["Collection Runner", "Mock Server"]
related_services: []
---

## エラーの概要

429 Too Many Requests は、[テスト](/glossary/テスト/)対象の [API](/glossary/api/) が[レート制限](/glossary/レート制限/)に達した状態を示しています。Postman で[リクエスト](/glossary/リクエスト/)を大量送信したり、Collection Runner で短時間に何度も[テスト](/glossary/テスト/)を実行したりすると、[API](/glossary/api/) 側で「一定期間内の[リクエスト](/glossary/リクエスト/)数上限を超えた」と判断され、この[エラー](/glossary/エラー/)が返されます。本来は[サーバー](/glossary/サーバー/)の過負荷保護であり、正常な動作です。

## 実際のエラーメッセージ例

**Postman [コンソール](/glossary/コンソール/)出力：**

```json
{
  "status": 429,
  "statusText": "Too Many Requests",
  "body": "Rate limit exceeded. Maximum 100 requests per minute allowed."
}
```

**レスポンスヘッダー例：**

```
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704067200
```

## よくある原因と解決手順

### 原因1：Collection Runner で複数リクエストを間隔なしで実行

Collection Runner はループ機能で指定回数だけ[リクエスト](/glossary/リクエスト/)を連続実行するため、短時間に大量の[リクエスト](/glossary/リクエスト/)が [API](/glossary/api/) に送信されます。[API](/glossary/api/) 側の[レート制限](/glossary/レート制限/)（例：1分あたり 100 [リクエスト](/glossary/リクエスト/)）に瞬時に達してしまい、429 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// Collection Runner で即座に連続実行
// delay設定なし → 1秒間に50回のリクエストが送信される
```

**After（修正後）：**

```javascript
// Collection Runner の設定画面で delay を指定
// 例：1000ms = 1秒間隔でリクエストを実行
// Run Collection ダイアログの "Delay" フィールドに 1000 を入力
```

Collection Runner UI では、実行ボタンを押す前に「Delay (ms)」フィールドに値を入力します。デフォルトは 0ms（待機なし）ですが、[API](/glossary/api/) の制限に合わせて 1000～5000ms の間隔を設定すると有効です。

### 原因2：ループ処理の繰り返し回数がレート制限を超えている

[API](/glossary/api/) が「1時間に 1000 [リクエスト](/glossary/リクエスト/)まで」という制限を設けている場合、Collection Runner で 500 回ループを 2回実行すれば制限を超えます。[テスト](/glossary/テスト/)環境でも本番 [API](/glossary/api/) を直接使っていれば、割り当てが枯渇します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "requests": [
    {
      "name": "Get User",
      "request": {
        "method": "GET",
        "url": "https://api.example.com/users/{{userId}}"
      }
    }
  ],
  "variable": [
    {
      "key": "iterations",
      "value": "500"
    }
  ]
}
```

**After（修正後）：**

```json
{
  "requests": [
    {
      "name": "Get User",
      "request": {
        "method": "GET",
        "url": "https://api.example.com/users/{{userId}}"
      }
    }
  ],
  "variable": [
    {
      "key": "iterations",
      "value": "10"
    }
  ]
}
```

ループ回数を制限し、必要なテストケースだけに絞ります。あるいは [API](/glossary/api/) の割り当て期間内（1時間あたり、1日あたりなど）で[テスト](/glossary/テスト/)を分割実行します。

### 原因3：テスト環境が本番 API に接続している

開発や[テスト](/glossary/テスト/)段階で本番環境の [API](/glossary/api/) に直接[リクエスト](/glossary/リクエスト/)を送ると、[レート制限](/glossary/レート制限/)が共有されます。複数のテスターが同時に[テスト](/glossary/テスト/)すれば、制限はすぐに枯渇します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "info": {
    "name": "User API Tests",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Get Users",
      "request": {
        "method": "GET",
        "url": "https://api.production.com/v1/users"
      }
    }
  ]
}
```

**After（修正後）：**

```json
{
  "info": {
    "name": "User API Tests",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Get Users",
      "request": {
        "method": "GET",
        "url": "https://mock-api.example.com/v1/users"
      }
    }
  ]
}
```

Postman Mock Server または開発環境用の [API](/glossary/api/) [エンドポイント](/glossary/エンドポイント/)を使用します。Postman では「Mock Server」機能で、コレクションの定義に基づいた仮の [API](/glossary/api/) を立ち上げられます。[テスト](/glossary/テスト/)中はこちらに接続すれば、本番 [API](/glossary/api/) の[レート制限](/glossary/レート制限/)を消費しません。

## ツール固有の注意点

**Collection Runner での正確な Delay 設定方法：**

Postman の Collection Runner（▶ Run Collection ボタン）を起動すると、左側のサイドパネルに「Delay」フィールドが表示されます。ここに **ミリ秒単位** で値を入力します。例えば、1 秒間隔で実行するなら 1000、500ms なら 500 です。

**Pre-request Script で[リクエスト](/glossary/リクエスト/)間の遅延を設定する別法：**

Collection Runner の Delay とは別に、Pre-request Script で動的に待機を挿入する方法もあります。

```javascript
// Pre-request Script（Collection レベルまたはリクエストレベル）
setTimeout(() => {}, 1000); // 1秒待機
```

ただし Postman のスクリプト実行は限定的なため、UI の Delay フィールドを使う方が確実です。

**Environment と Mock Server の連携：**

Environment を使い、本番 [API](/glossary/api/) とモック [API](/glossary/api/) を切り替える設定も効果的です。

```javascript
// Collection の Pre-request Script
if (pm.environment.get("use_mock") === "true") {
  pm.globals.set("api_url", "https://mock-api.example.com");
} else {
  pm.globals.set("api_url", "https://api.production.com");
}
```

実行時に Environment を選択することで、接続先を簡単に切り替えられます。

## それでも解決しない場合

**[API](/glossary/api/) の制限仕様を確認する：**

レスポンスヘッダーの `Retry-After`、`X-RateLimit-Limit`、`X-RateLimit-Reset` を確認し、制限単位（1分あたり、1時間あたり、1日あたり）と上限値を把握します。Postman でレスポンスヘッダーを見るには、[レスポンス](/glossary/レスポンス/)画面の「Headers」タブを開きます。

**Console Log で[リクエスト](/glossary/リクエスト/)送信タイミングを検証：**

Postman の[コンソール](/glossary/コンソール/)（Ctrl+Alt+C / Cmd+Option+C）を開き、[リクエスト](/glossary/リクエスト/)のタイムスタンプを確認します。短時間に大量の[リクエスト](/glossary/リクエスト/)が送信されていないか目視で判定できます。

**[テスト](/glossary/テスト/)用の [API](/glossary/api/) キーまたは専用[レート制限](/glossary/レート制限/)を申請：**

[API](/glossary/api/) 提供元に問い合わせ、[テスト](/glossary/テスト/)用の別キーや引き上げ可能な制限値を用意してもらいます。開発段階では[レート制限](/glossary/レート制限/)を緩くしてもらう交渉も可能です。

**公式ドキュメント参照：**

- [Postman Collection Runner](https://learning.postman.com/docs/running-collections/intro-to-collection-runs/)
- [Postman Mock Server](https://learning.postman.com/docs/designing-and-developing-your-api/mocking-data/setting-up-mock/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*