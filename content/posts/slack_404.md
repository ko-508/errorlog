---
title: "Slack の 404 エラー：原因と解決策"
date: 2026-05-27
description: "Slack の 404 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Slack"]
errorCode: "404"
---

## Slack 404 エラーの原因と解決方法

Slack [API](/glossary/api/) を使用する際に 404 エラーが返される場合、指定したチャンネル・メッセージ・ユーザーが見つからないことを意味します。このエラーは開発初期段階でよく遭遇するもので、原因を理解することで素早く対応できます。

## よくある原因

### チャンネル ID またはユーザー ID が間違っている
Slack [API](/glossary/api/) は ID 値に厳密です。チャンネル ID が「C123ABC」のはずが「C123ABD」と入力されていると、[API](/glossary/api/) は該当するリソースを見つけられず 404 を返します。IDは文字種の大文字小文字を区別しているため、コピペ時の誤りやタイプミスに注意が必要です。

### チャンネル名を ID の代わりに使っている
初心者がよく犯す間違いです。「#general」や「#random」といったチャンネル「名」を [API](/glossary/api/) に直接指定してはいけません。Slack [API](/glossary/api/) では必ずチャンネル ID（例：C0G9QF9GZ）形式での指定が必須です。

### 対象リソースが削除されている
チャンネルやメッセージが削除された後、そのリソースへのアクセスを試みると 404 が返されます。[キャッシュ](/glossary/キャッシュ/)された ID から古い参照が残っていないか確認しましょう。

## 解決手順

### 1. conversations.list API でチャンネル ID を確認

まず、利用可能なチャンネル一覧とその ID を取得します。

```bash
curl -X GET 'https://slack.com/api/conversations.list' \
  -H 'Authorization: Bearer xoxb-YOUR_BOT_TOKEN' \
  -d 'limit=100'
```

[レスポンス](/glossary/レスポンス/)から、対象チャンネルの「id」フィールドを確認してください。

### 2. users.list API でユーザー ID を確認

ユーザーに関連するエラーの場合は、以下を実行します。

```bash
curl -X GET 'https://slack.com/api/users.list' \
  -H 'Authorization: Bearer xoxb-YOUR_BOT_TOKEN'
```

目的のユーザーの「id」フィールド（U12345ABC 形式）を記録してください。

### 3. API リクエストでチャンネル名ではなく ID を使用

確認した ID を [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)に含めます。

```bash
curl -X POST 'https://slack.com/api/chat.postMessage' \
  -H 'Authorization: Bearer xoxb-YOUR_BOT_TOKEN' \
  -d 'channel=C0G9QF9GZ' \
  -d 'text=Hello, Slack!'
```

「channel」[パラメータ](/glossary/パラメータ/)には必ずチャンネル ID を指定します。

## それでも解決しない場合

- **[トークン](/glossary/トークン/)[権限](/glossary/権限/)の確認**: ボットトークンが対象チャンネルへのアクセス権を持っているか確認してください。
- **[ワークスペース](/glossary/ワークスペース/)再確認**: 異なる[ワークスペース](/glossary/ワークスペース/)のリソースにアクセスしていないか確認します。
- **[API](/glossary/api/) [レスポンス](/glossary/レスポンス/)の詳細確認**: [エラーレスポンス](/glossary/エラーレスポンス/)の「error」フィールドに詳細メッセージが含まれているため、その内容を確認してください。
- **公式ドキュメント参照**: [Slack API 公式ドキュメント](https://api.slack.com/docs)で最新情報を確認することをお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*