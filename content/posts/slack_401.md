---
title: "Slack の 401 エラー：原因と解決策"
date: 2026-05-27
description: "Slack の 401 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Slack"]
errorCode: "401"
---

## Slack 401 エラーが発生する原因と解決方法

Slack API を使用する際に 401 エラーが返される場合、アプリケーションが Slack に正しく認証できていません。このエラーが発生すると、ボット機能やカスタムアプリが機能しなくなるため、迅速な対応が必要です。

## よくある原因

### トークンが無効または期限切れになっている

Bot トークン（xoxb で始まる）や User OAuth トークン（xoxp で始まる）が期限切れになったり、無効な状態になったりしている場合、API リクエストは 401 エラーで拒否されます。特に、セキュリティアップデートやトークンのローテーション（定期的な更新）後に発生することが多いです。

### OAuth スコープが不足している

OAuth スコープ（権限範囲）は、アプリが何ができるかを制限する仕組みです。必要なスコープが不足していると、API コールが拒否されます。例えば、メッセージ送信には `chat:write` スコープが必要ですが、これが許可されていないと 401 エラーが発生します。

### アプリがワークスペースからアンインストールされた

ワークスペースの管理者がアプリをアンインストールした場合、そのトークンはもはや有効ではありません。再度認証が必要になります。

## 解決手順

### ステップ 1: トークンを再生成する

Slack ワークスペースの管理画面にアクセスし、以下の手順を実行してください。

1. [Slack App Directory](https://api.slack.com/apps) にログイン
2. 対象のアプリを選択
3. 左メニューから「**OAuth & Permissions**」をクリック
4. 「**Bot Token Revoked**」の場合、「**Reinstall to Workspace**」をクリック
5. 新しいトークンを環境変数に設定

```bash
export SLACK_BOT_TOKEN="xoxb-新しいトークン"
```

### ステップ 2: OAuth スコープを確認・追加する

必要なスコープが設定されているか確認しましょう。

1. App 設定の「**OAuth & Permissions**」セクションを開く
2. 「**Scopes**」の「**Bot Token Scopes**」を確認
3. 必要なスコープが無い場合は「**Add an OAuth Scope**」をクリックして追加

一般的に必要なスコープの例：
```
- chat:write（メッセージ送信）
- channels:read（チャンネル情報取得）
- users:read（ユーザー情報取得）
- reactions:write（リアクション追加）
```

スコープを追加した後は、必ず「**Reinstall to Workspace**」をクリックして再インストールしてください。

### ステップ 3: インストール状態を確認する

アプリがワークスペースに正しくインストールされているか確認します。

```bash
curl -X GET https://slack.com/api/auth.test \
  -H "Authorization: Bearer xoxb-YOUR_BOT_TOKEN"
```

成功時のレスポンス例：
```json
{
  "ok": true,
  "url": "https://yourworkspace.slack.com/",
  "team": "Your Workspace Name",
  "user": "your_bot_name",
  "team_id": "T0XXXXXXXX",
  "user_id": "U0XXXXXXXX"
}
```

`"ok": false` が返される場合は、トークンが無効です。

## それでも解決しない場合

- **トークンの有効期限を確認**：App 設定で「**Install App**」セクションを確認
- **ネットワーク接続を確認**：プロキシやファイアウォールの影響がないか確認
- **Slack 公式ドキュメント**を参照：https://api.slack.com/authentication/basics
- **Slack サポートに問い合わせ**：ワークスペースの管理者権限で対応が必要な場合もあります