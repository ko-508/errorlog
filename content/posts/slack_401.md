---
draft: true
title: "Slack の 401 エラー：原因と解決策"
date: 2026-05-27
description: "Slack API へのリクエストが 401 エラー（Unauthorized）で拒否される場合、認証トークンが無効、期限切れ、または不正な状態にあることを示します。"
tags: ["Slack"]
errorCode: "401"
service: "Slack"
error_type: "401"
components: []
related_services: ["Slack API", "OAuth", "Slack App Directory"]
lastmod: 2026-06-14
---

## Slack の 401 エラー：原因と解決策

## エラーの概要

Slack [API](/glossary/api/) への[リクエスト](/glossary/リクエスト/)が 401 [エラー](/glossary/エラー/)（Unauthorized）で拒否される場合、[認証](/glossary/認証/)[トークン](/glossary/トークン/)が無効、期限切れ、または不正な状態にあることを示します。この[エラー](/glossary/エラー/)が発生するとボットメッセージの送信、ユーザー情報の取得、ファイルのアップロードなどすべての [API](/glossary/api/) 操作が停止するため、早期の対応が必須です。Slack アプリを運用する上で最も頻繁に遭遇する[エラー](/glossary/エラー/)の一つです。

## 実際のエラーメッセージ例

Slack [API](/glossary/api/) が返す典型的な 401 [エラーレスポンス](/glossary/エラーレスポンス/)例：

```json
{
  "ok": false,
  "error": "invalid_auth",
  "response_metadata": {
    "messages": [
      "The token used is no longer valid"
    ]
  }
}
```

または以下のバリエーション：

```json
{
  "ok": false,
  "error": "token_revoked",
  "response_metadata": {
    "messages": [
      "The token has been revoked"
    ]
  }
}
```

## よくある原因と解決手順

### 原因1：トークンの期限切れまたは無効化

Slack のセキュリティポリシー変更による[トークン](/glossary/トークン/)自動失効、ユーザーが手動でアプリを削除した、または定期的な[セキュリティ](/glossary/セキュリティ/)監査で古い[トークン](/glossary/トークン/)が無効化されている場合があります。このとき、`invalid_auth` または `token_revoked` [エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests

# 3ヶ月前に取得したトークンを使用
TOKEN = "xoxb-YOUR-BOT-TOKEN-HERE"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

response = requests.post(
    "https://slack.com/api/chat.postMessage",
    headers=headers,
    json={"channel": "C12345", "text": "Hello"}
)

print(response.json())  # {"ok": false, "error": "invalid_auth"}
```

**After（修正後）：**

```python
import requests
from slack_sdk import WebClient

# トークンを環境変数から取得し、SDK を使用
import os
TOKEN = os.getenv("SLACK_BOT_TOKEN")

client = WebClient(token=TOKEN)

try:
    response = client.chat_postMessage(
        channel="C12345",
        text="Hello"
    )
    print("Message posted successfully")
except Exception as e:
    print(f"Error: {e}")
    # トークンが無効な場合は再生成が必要
```

Slack [ワークスペース](/glossary/ワークスペース/)管理画面で新しいボットトークンを生成し、[環境変数](/glossary/環境変数/)に設定し直してください。

### 原因2：OAuth スコープの不足

[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)に必要な[スコープ](/glossary/スコープ/)（[権限](/glossary/権限/)）が[トークン](/glossary/トークン/)に付与されていない場合、[リクエスト](/glossary/リクエスト/)が許可されず 401 [エラー](/glossary/エラー/)が返されます。例えば `chat:write` [スコープ](/glossary/スコープ/)なしで メッセージ送信を試みると拒否されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// トークンに chat:write スコープがない状態
const { WebClient } = require('@slack/web-api');

const client = new WebClient(process.env.SLACK_BOT_TOKEN);

(async () => {
  try {
    await client.chat.postMessage({
      channel: 'C12345',
      text: 'Hello'
    });
  } catch (error) {
    console.log(error);
    // Error: not_in_channel or missing_scope
  }
})();
```

**After（修正後）：**

```javascript
// Slack アプリの OAuth & Permissions で必要なスコープを追加
// 必要スコープ例：
// - chat:write （メッセージ送信）
// - channels:read （チャンネル一覧取得）
// - users:read （ユーザー情報取得）

const { WebClient } = require('@slack/web-api');

const client = new WebClient(process.env.SLACK_BOT_TOKEN);

(async () => {
  try {
    const result = await client.chat.postMessage({
      channel: 'C12345',
      text: 'Hello'
    });
    console.log('Message sent:', result.ts);
  } catch (error) {
    console.error('Error:', error.message);
  }
})();
```

Slack App 管理画面の「[OAuth](/glossary/oauth/) & Permissions」セクションで、必要な[スコープ](/glossary/スコープ/)を明示的に追加し、[ワークスペース](/glossary/ワークスペース/)に再インストールしてください。

### 原因3：トークン形式の誤りまたは環境変数の未設定

[トークン](/glossary/トークン/)が正しく[環境変数](/glossary/環境変数/)に設定されていない、型番が違う（xoxb の代わりに xoxp を使用）、または空文字列が渡されている場合に[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# .env ファイルが存在しない、または誤った値
export SLACK_BOT_TOKEN=""

# Python で実行
python app.py

# リクエストは TOKEN="" で送信され 401 エラーになる
```

```python
import os
from slack_sdk import WebClient

# 環境変数が未設定の場合
TOKEN = os.getenv("SLACK_BOT_TOKEN")  # None または ""

client = WebClient(token=TOKEN)

try:
    client.chat_postMessage(channel="C12345", text="Hello")
except Exception as e:
    print(e)  # invalid_auth
```

**After（修正後）：**

```bash
# .env ファイルに正しく設定
SLACK_BOT_TOKEN=xoxb-YOUR-BOT-TOKEN-HERE
SLACK_SIGNING_SECRET=YOUR-SIGNING-SECRET-HERE
```

```python
import os
from slack_sdk import WebClient
from dotenv import load_dotenv

# .env ファイルを読み込む
load_dotenv()

TOKEN = os.getenv("SLACK_BOT_TOKEN")

# トークンが正しく設定されているか確認
if not TOKEN or not TOKEN.startswith("xoxb-"):
    raise ValueError("Invalid SLACK_BOT_TOKEN format or not set")

client = WebClient(token=TOKEN)

response = client.chat_postMessage(channel="C12345", text="Hello")
print(response)
```

[環境変数](/glossary/環境変数/)を確認し、[トークン](/glossary/トークン/)が正しい形式（xoxb- または xoxp-で始まる長い文字列）で設定されていることを確認してください。

## Slack 固有の注意点

### トークンローテーションとその影響

Slack は定期的に[セキュリティ](/glossary/セキュリティ/)監査を実施し、使用されていない[トークン](/glossary/トークン/)や古い[トークン](/glossary/トークン/)を自動的に無効化することがあります。本番環境では少なくとも月1回は[トークン](/glossary/トークン/)の有効性を確認し、必要に応じて新規発行してください。

### ボットアプリとユーザーアプリの区別

`xoxb-` で始まるボットトークンと `xoxp-` で始まるユーザートークンは別の[権限](/glossary/権限/)[モデル](/glossary/モデル/)を持ちます。自動化目的ではボットトークンを、ユーザーの個人操作が必要な場合はユーザートークンを使い分ける必要があります。混用すると 401 [エラー](/glossary/エラー/)が発生します。

### Slack アプリのインストール/再インストール

[スコープ](/glossary/スコープ/)を追加・変更した場合は、単なる[認可](/glossary/認可/)フロー再実行では不十分で、[ワークスペース](/glossary/ワークスペース/)への**再インストール**が必須です。ブラウザの[キャッシュ](/glossary/キャッシュ/)をクリアした上で、[OAuth](/glossary/oauth/) 画面から改めて承認操作を行ってください。

### Bot Token Rotations（ベータ機能）

Slack の一部[ワークスペース](/glossary/ワークスペース/)では Bot Token Rotations が有効になっており、[トークン](/glossary/トークン/)の有効期限が短縮されています。この場合、Refresh Token を使用して新しい[トークン](/glossary/トークン/)を自動取得する実装が必要です。

## それでも解決しない場合

### デバッグと情報確認

[トークン](/glossary/トークン/)の有効性を確認するため、以下の[コマンド](/glossary/コマンド/)で `auth.test` [API](/glossary/api/) を実行してください：

```bash
curl -X POST https://slack.com/api/auth.test \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/x-www-form-urlencoded"
```

[レスポンス](/glossary/レスポンス/)が `"ok": true` で返れば[トークン](/glossary/トークン/)は有効です。`"ok": false` の場合、エラーフィールドを確認してください。

### ログの確認箇所

- **Slack [ワークスペース](/glossary/ワークスペース/)管理画面**：「App management」→「Apps」で各アプリのインストール日時と最終使用日時を確認
- **Slack [API](/glossary/api/) テスター**：https://api.slack.com/methods/auth.test で直接[トークン](/glossary/トークン/)検証可能
- **アプリケーションログ**：`SLACK_WEBHOOK_SECRET` が正しく設定されているか、リクエストヘッダーに `Authorization` フィールドが含まれているか確認

### 公式リソース

- Slack [API](/glossary/api/) [認証](/glossary/認証/)ドキュメント：https://api.slack.com/authentication
- [OAuth](/glossary/oauth/) [スコープ](/glossary/スコープ/)一覧：https://api.slack.com/scopes
- トークンローテーション詳細：https://api.slack.com/authentication/rotation

### コミュニティサポート

Slack Community（https://slackcommunity.com）や GitHub の Slack [SDK](/glossary/sdk/) [リポジトリ](/glossary/リポジトリ/)（例：https://github.com/slackapi/python-slack-sdk）で同様の問題報告がないか検索し、既知の問題か確認することをお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*