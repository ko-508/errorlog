---
title: "Slack の 404 エラー：原因と解決策"
date: 2026-05-27
description: "Slack の 404 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Slack"]
errorCode: "404"
lastmod: 2026-06-14
refresh_due: true
service: "Slack"
error_type: "404"
components: []
related_services: ["Slack API"]
top_queries:
- '100404'
---

## エラーの概要

Slack [API](/glossary/api/)で404[エラー](/glossary/エラー/)が返される場合、指定したチャンネル・メッセージ・ユーザーなどのリソースがSlack[ワークスペース](/glossary/ワークスペース/)内に存在しないか、[認証](/glossary/認証/)ユーザーに[アクセス権限](/glossary/アクセス権限/)がないことを意味します。この[エラー](/glossary/エラー/)は開発初期段階や権限設定の誤りで頻繁に発生し、原因を理解することで素早く対応できます。

## 実際のエラーメッセージ例

Slack [API](/glossary/api/)の404[レスポンス](/glossary/レスポンス/)例を以下に示します：

```json
{
  "ok": false,
  "error": "channel_not_found",
  "response_metadata": {
    "messages": [
      "The method was passed an argument that does not, with certainty, exist."
    ],
    "warnings": []
  }
}
```

メッセージ取得時の404例：

```json
{
  "ok": false,
  "error": "message_not_found",
  "response_metadata": {
    "messages": [
      "The requested message could not be found."
    ]
  }
}
```

## よくある原因と解決手順

### 原因1：チャンネルIDが誤っている

Slack [API](/glossary/api/)は文字列一致に厳密です。チャンネル[ID](/glossary/id/)の1文字誤りやコピペ時の誤りで404が発生します。[ID](/glossary/id/)は大文字小文字を区別するため注意が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import slack

client = slack.WebClient(token="xoxb-your-token")
response = client.conversations_info(channel="C123ABD")
# 実際のIDは C123ABC なのに C123ABD と入力している
```

**After（修正後）：**

```python
import slack

client = slack.WebClient(token="xoxb-your-token")
# 正確なチャンネルIDを確認した上で指定する
response = client.conversations_info(channel="C123ABC")
print(response)
```

### 原因2：チャンネル名をIDの代わりに使用している

`#general`や`#random`といったチャンネル「名」を直接[API](/glossary/api/)に指定すると404[エラー](/glossary/エラー/)が返されます。Slack [API](/glossary/api/)ではチャンネル[ID](/glossary/id/)（C0G9QF9GZなど）での指定が必須です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { WebClient } = require('@slack/web-api');

const client = new WebClient(process.env.SLACK_TOKEN);

async function sendMessage() {
  try {
    await client.chat.postMessage({
      channel: "#general",  // チャンネル名は使用できない
      text: "Hello, Slack!"
    });
  } catch (error) {
    console.error(error);
  }
}
```

**After（修正後）：**

```javascript
const { WebClient } = require('@slack/web-api');

const client = new WebClient(process.env.SLACK_TOKEN);

async function sendMessage() {
  try {
    await client.chat.postMessage({
      channel: "C0G9QF9GZ",  // チャンネルIDを使用する
      text: "Hello, Slack!"
    });
  } catch (error) {
    console.error(error);
  }
}
```

### 原因3：削除済みチャンネルにアクセスしている

チャンネルが削除された後、そのチャンネル[ID](/glossary/id/)に対して[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)を実行すると404が返されます。アーカイブされたチャンネルと削除されたチャンネルは異なり、削除後は復旧できません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X GET "https://slack.com/api/conversations.info?channel=C9XYZABC" \
  -H "Authorization: Bearer xoxb-your-token"
# C9XYZABC チャンネルは既に削除されている
```

**After（修正後）：**

```bash
# 1. アーカイブ済みチャンネルを含むリストを取得
curl -X GET "https://slack.com/api/conversations.list?exclude_archived=false" \
  -H "Authorization: Bearer xoxb-your-token"

# 2. 返却されたチャンネル一覧から有効なチャンネルIDを確認して使用する
curl -X GET "https://slack.com/api/conversations.info?channel=C_VALID_ID" \
  -H "Authorization: Bearer xoxb-your-token"
```

### 原因4：ユーザーIDが誤っている、またはボットがメンバーでない

プライベートチャンネルではボットのメンバーシップが必要です。ボットが追加されていないチャンネルにメッセージを送信しようとすると404が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import slack

client = slack.WebClient(token="xoxb-your-token")
try:
    response = client.chat.postMessage(
        channel="C_PRIVATE_CHANNEL",
        text="Message from bot"
    )
except slack.errors.SlackApiError as e:
    # error: "not_in_channel" または 404 が返される
    print(f"Error: {e.response['error']}")
```

**After（修正後）：**

```python
import slack

client = slack.WebClient(token="xoxb-your-token")

# 1. ボットをチャンネルに追加する
try:
    client.conversations_invite(
        channel="C_PRIVATE_CHANNEL",
        users="U_BOT_USER_ID"
    )
except slack.errors.SlackApiError as e:
    print(f"Error: {e.response['error']}")

# 2. その後メッセージを送信する
try:
    response = client.chat.postMessage(
        channel="C_PRIVATE_CHANNEL",
        text="Message from bot"
    )
except slack.errors.SlackApiError as e:
    print(f"Error: {e.response['error']}")
```

## Slack固有の注意点

### チャンネルID確認の方法

SlackアプリのUI上でチャンネル名をクリックすると、パンくずリストの下部にチャンネル[ID](/glossary/id/)が表示されます。または`conversations.list`[エンドポイント](/glossary/エンドポイント/)で全チャンネル一覧を取得し、正確な[ID](/glossary/id/)を確認することが推奨されます。

```bash
curl -X GET "https://slack.com/api/conversations.list?limit=100" \
  -H "Authorization: Bearer xoxb-your-token" \
  | grep -o '"id":"C[A-Z0-9]*"'
```

### App-level permissionsの確認

[API](/glossary/api/)呼び出しに必要な[権限](/glossary/権限/)がボットに付与されていない場合、404ではなく[権限](/glossary/権限/)[エラー](/glossary/エラー/)（`missing_scope`）が返されることもありますが、特定のリソースへのアクセスが明示的に拒否されている場合は404として扱われることがあります。ボットの[スコープ](/glossary/スコープ/)が`channels:read`、`chat:write`など必要な[権限](/glossary/権限/)を持っているか確認してください。

### ワークスペース間のID混同

複数のSlack[ワークスペース](/glossary/ワークスペース/)を管理している場合、異なる[ワークスペース](/glossary/ワークスペース/)のチャンネル[ID](/glossary/id/)を誤って使用すると404が返されます。[リクエスト](/glossary/リクエスト/)に正しい`SLACK_TOKEN`を使用し、その[ワークスペース](/glossary/ワークスペース/)に属するチャンネル[ID](/glossary/id/)であることを確認してください。

## それでも解決しない場合

### ログとデバッグ

Slack [API](/glossary/api/)[レスポンス](/glossary/レスポンス/)の`response_metadata`フィールドにはより詳細な[エラー](/glossary/エラー/)情報が含まれています。必ず全[レスポンス](/glossary/レスポンス/)を確認してください：

```python
import json
try:
    response = client.conversations_info(channel="C_INVALID_ID")
except slack.errors.SlackApiError as e:
    print(json.dumps(e.response, indent=2))
```

### 公式リソース

- [Slack API documentation - conversations.info](https://api.slack.com/methods/conversations.info)
- [Slack APIスコープリファレンス](https://api.slack.com/scopes)
- [Error handling guide](https://api.slack.com/methods#error-handling)

### コミュニティサポート

問題が解決しない場合は、[Slack API GitHub Issues](https://github.com/slackapi/python-slack-sdk/issues)でBot[トークン](/glossary/トークン/)の権限設定や[SDK](/glossary/sdk/)の[バージョン](/glossary/バージョン/)確認に関する既出問題を参照してください。また、[Slack Community](https://slackcommunity.com/)でも相談できます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*