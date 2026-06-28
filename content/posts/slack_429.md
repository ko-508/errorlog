---
title: "Slack の 429 エラー：原因と解決策"
date: 2026-05-28
description: "短時間に送ったリクエスト数がSlack APIのレート制限を超えた"
tags: ["Slack"]
errorCode: "429"
service: "Slack"
error_type: "429"
components: []
related_services: ["Node.js", "axios", "Python", "slack-sdk", "asyncio"]
lastmod: 2026-06-14
---

## エラーの概要

Slack [API](/glossary/api/) への[リクエスト](/glossary/リクエスト/)が短時間に集中し、[レート制限](/glossary/レート制限/)を超えた場合に発生する[HTTP](/glossary/http/)[エラー](/glossary/エラー/)です。429 Too Many Requests[レスポンス](/glossary/レスポンス/)が返された場合、クライアント側で一時的に再試行を延期する必要があります。Slack [API](/glossary/api/) の[レート制限](/glossary/レート制限/)は[メソッド](/glossary/メソッド/)ごと、[アプリケーション](/glossary/アプリケーション/)ごとに段階的に設定されており、制限を超えると [API](/glossary/api/)呼び出しが一時的に拒否されます。

## 実際のエラーメッセージ例

**Slack [API](/glossary/api/) [JSON](/glossary/json/)[レスポンス](/glossary/レスポンス/)：**

```json
{
  "ok": false,
  "error": "rate_limited",
  "retry_after": 2
}
```

**[HTTP](/glossary/http/)[ステータス](/glossary/ステータス/)コード付き[レスポンス](/glossary/レスポンス/)：**

```
HTTP/1.1 429 Too Many Requests
Retry-After: 2
Content-Type: application/json

{
  "ok": false,
  "error": "rate_limited",
  "retry_after": 2
}
```

## よくある原因と解決手順

### 1. ループ処理内での API 呼び出し間隔がない

ループで複数のメッセージ送信やユーザー情報取得を行う際、各[リクエスト](/glossary/リクエスト/)の間に待機時間を設けないと、短時間に大量の[リクエスト](/glossary/リクエスト/)が Slack [API](/glossary/api/) に到達します。Slack [API](/glossary/api/) の[レート制限](/glossary/レート制限/)は一般的に[メソッド](/glossary/メソッド/)ごとに設定されており、例えば `chat.postMessage` は 1 分間に数十～数百[リクエスト](/glossary/リクエスト/)の上限があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import slack

client = slack.WebClient(token="<your-slack-bot-token>")

# 100 件のメッセージを即座に送信
user_ids = ["U001", "U002", "U003"]  # 実際はさらに多い
for user_id in user_ids:
    response = client.chat_postMessage(
        channel=user_id,
        text="Hello from bot!"
    )
```

**After（修正後）：**

```python
import slack
import time

client = slack.WebClient(token="<your-slack-bot-token>")

# 各リクエスト間に 1 秒の待機を挿入
user_ids = ["U001", "U002", "U003"]
for user_id in user_ids:
    response = client.chat_postMessage(
        channel=user_id,
        text="Hello from bot!"
    )
    time.sleep(1)  # 1 秒待機
```

### 2. Retry-After ヘッダーの未処理

429 [エラー](/glossary/エラー/)が返された際、レスポンスヘッダーの `Retry-After` に指定された秒数だけ待機してから再試行する必要があります。無視して即座に再試行を繰り返すと、さらなる 429 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { WebClient } = require('@slack/web-api');
const client = new WebClient(process.env.SLACK_BOT_TOKEN);

async function sendMessage(channel, text) {
  try {
    return await client.chat.postMessage({ channel, text });
  } catch (error) {
    // エラーをキャッチするが、Retry-After を無視して即座に再実行
    if (error.code === 'rate_limited') {
      return sendMessage(channel, text);  // すぐ再試行（危険）
    }
  }
}
```

**After（修正後）：**

```javascript
const { WebClient } = require('@slack/web-api');
const client = new WebClient(process.env.SLACK_BOT_TOKEN);

async function sendMessage(channel, text) {
  try {
    return await client.chat.postMessage({ channel, text });
  } catch (error) {
    if (error.code === 'rate_limited') {
      const retryAfter = error.retry_after || 1;  // retry_after を取得
      console.log(`Rate limited. Waiting ${retryAfter} seconds...`);
      await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
      return sendMessage(channel, text);  // 待機後に再試行
    }
    throw error;
  }
}
```

### 3. バッチ処理・一括操作の実装不足

`conversations.list`、`users.list`、`emoji.list` など、大量のデータを取得する[メソッド](/glossary/メソッド/)でも[レート制限](/glossary/レート制限/)が適用されます。ページネーション（`cursor` [パラメータ](/glossary/パラメータ/)）を使わずに全件一括取得を試みたり、複数の一括取得[メソッド](/glossary/メソッド/)を連続実行すると 429 [エラー](/glossary/エラー/)が発生しやすくなります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import slack

client = slack.WebClient(token="<your-slack-bot-token>")

# 全ユーザーを一度に取得（大規模ワークスペースでは 429 発生）
all_users = client.users_list(limit=0)
all_conversations = client.conversations_list(limit=0)
all_emoji = client.emoji_list()  # 連続実行で 429 のリスク
```

**After（修正後）：**

```python
import slack
import time

client = slack.WebClient(token="<your-slack-bot-token>")

# ページネーション対応で段階的に取得
all_users = []
cursor = None
while True:
    response = client.users_list(limit=100, cursor=cursor)
    all_users.extend(response['members'])
    cursor = response.get('response_metadata', {}).get('next_cursor')
    if not cursor:
        break
    time.sleep(0.5)  # ページ間に待機を挿入

time.sleep(1)  # メソッド間にも待機を挿入

all_conversations = []
cursor = None
while True:
    response = client.conversations_list(limit=100, cursor=cursor)
    all_conversations.extend(response['channels'])
    cursor = response.get('response_metadata', {}).get('next_cursor')
    if not cursor:
        break
    time.sleep(0.5)
```

## Slack 固有の注意点

### ボット・App・ワークスペースレベルのレート制限区別

Slack [API](/glossary/api/) の[レート制限](/glossary/レート制限/)は複数のレベルで適用されます。個別のボット、[OAuth](/glossary/oauth/) [トークン](/glossary/トークン/)、[ワークスペース](/glossary/ワークスペース/)全体で異なる上限が設定されているため、同じ[メソッド](/glossary/メソッド/)でも環境によって制限が変わります。特に開発環境では余裕があっても、本番環境の大規模[ワークスペース](/glossary/ワークスペース/)では厳しく制限される傾向があります。

### Web API メソッドごとのレート制限差

`chat.postMessage` は比較的厳しい制限（1分間～数十～数百[リクエスト](/glossary/リクエスト/)程度）がある一方、`auth.test` のような軽量[メソッド](/glossary/メソッド/)は緩い制限が設定されています。また、`conversations.history`、`conversations.replies` は会話履歴取得用として異なる制限枠を持つため、[メソッド](/glossary/メソッド/)ごとに待機戦略を変えることが重要です。

### Event Subscriptions との相互作用

Events [API](/glossary/api/)（イベント受信）で[ワークスペース](/glossary/ワークスペース/)の変更を監視しながら、同時に Web [API](/glossary/api/) でメッセージ送信やユーザー情報取得を行う場合、両者が同じレート制限枠を共有しないことに注意が必要です。イベント処理内で同期的に Web [API](/glossary/api/) を呼び出すと、イベント処理がブロックされるだけでなく、429 [エラー](/glossary/エラー/)時の再試行が複雑になるため、非同期キューの使用を推奨します。

### Bolt フレームワークの自動レート制限対応

Slack Bolt（Python / JavaScript / Java）を使用している場合、フレームワークレベルで簡易的なレート制限対応が行われますが、完全に自動化されるわけではありません。特に並行[リクエスト](/glossary/リクエスト/)が多い場合は、ミドルウェアレベルでキューイングや待機ロジックを追加実装することを検討してください。

## それでも解決しない場合

### ログ確認ポイント

Slack Python/JavaScript [SDK](/glossary/sdk/) は `debug=True` または[環境変数](/glossary/環境変数/) `SLACK_SDK_LOG_LEVEL=DEBUG` で詳細[ログ](/glossary/ログ/)を出力します。実際の [API](/glossary/api/)[レスポンス](/glossary/レスポンス/)[ヘッダー](/glossary/ヘッダー/)、リクエストタイミング、`Retry-After` 値を確認し、[レート制限](/glossary/レート制限/)に達する前後の[リクエスト](/glossary/リクエスト/)数・間隔を記録することで、設定すべき待機時間を正確に把握できます。

### 公式ドキュメント参照

Slack 公式ドキュメントの「Rate Limiting」セクション（https://api.slack.com/docs/rate-limits）に、メソッドごとのレート制限表と推奨される再試行戦略が記載されています。また、「Building resilient apps」（https://api.slack.com/best-practices/rate-limiting）には、本番環境で推奨される実装パターンが提示されています。

### GitHub Issues・Slack コミュニティ

Slack [SDK](/glossary/sdk/) の GitHub [リポジトリ](/glossary/リポジトリ/)（`slackapi/python-slack-sdk`、`slackapi/bolt-js` など）の Issues セクションで、同様の 429 [エラー](/glossary/エラー/)報告と解決例を検索できます。また、Slack Developer Community（https://slackcommunity.com/）のフォーラムでは、ワークスペース規模別・使用メソッド別の実装相談が活発に行われています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*