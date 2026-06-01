---
title: "Slack の 401 エラー：原因と解決策"
date: 2026-05-27
description: "Slack の 401 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Slack"]
errorCode: "401"
---

## Slack 401 エラーが発生する原因と解決方法

Slack [API](/glossary/api/) を使用する際に 401 エラーが返される場合、アプリケーションが Slack に正しく[認証](/glossary/認証/)できていません。このエラーが発生すると、ボット機能やカスタムアプリが機能しなくなるため、迅速な対応が必要です。

## よくある原因

### トークンが無効または期限切れになっている

Bot [トークン](/glossary/トークン/)（xoxb で始まる）や User [OAuth](/glossary/oauth/) [トークン](/glossary/トークン/)（xoxp で始まる）が期限切れになったり、無効な状態になったりしている場合、[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)は 401 エラーで拒否されます。特に、セキュリティアップデートや[トークン](/glossary/トークン/)のローテーション（定期的な更新）後に発生することが多いです。

### OAuth スコープが不足している

[OAuth](/glossary/oauth/) [スコープ](/glossary/スコープ/)（権限範囲）は、アプリが何ができるかを制限する仕組みです。必要な[スコープ](/glossary/スコープ/)が不足していると、[API](/glossary/api/) コールが拒否されます。例えば、メッセージ送信には `chat:write` [スコープ](/glossary/スコープ/)が必要ですが、これが許可されていないと 401 エラーが発生します。

### アプリがワークスペースからアンインストールされた

[ワークスペース](/glossary/ワークスペース/)の管理者がアプリをアンインストールした場合、その[トークン](/glossary/トークン/)はもはや有効ではありません。再度認証が必要になります。

## 解決手順

### ステップ 1: トークンを再生成する

Slack [ワークスペース](/glossary/ワークスペース/)の管理画面にアクセスし、以下の手順を実行してください。

1. [Slack App Directory](https://api.slack.com/apps) にログイン
2. 対象のアプリを選択
3. 左メニューから「**[OAuth](/glossary/oauth/) & Permissions**」をクリック
4. 「**Bot Token Revoked**」の場合、「**Reinstall to Workspace**」をクリック
5. 新しい[トークン](/glossary/トークン/)を[環境変数](/glossary/環境変数/)に設定

```bash
export SLACK_BOT_TOKEN="xoxb-新しいトークン"
```

### ステップ 2: OAuth スコープを確認・追加する

必要な[スコープ](/glossary/スコープ/)が設定されているか確認しましょう。

1. App 設定の「**[OAuth](/glossary/oauth/) & Permissions**」セクションを開く
2. 「**Scopes**」の「**Bot Token Scopes**」を確認
3. 必要な[スコープ](/glossary/スコープ/)が無い場合は「**Add an [OAuth](/glossary/oauth/) Scope**」をクリックして追加

一般的に必要な[スコープ](/glossary/スコープ/)の例：
```
- chat:write（メッセージ送信）
- channels:read（チャンネル情報取得）
- users:read（ユーザー情報取得）
- reactions:write（リアクション追加）
```

[スコープ](/glossary/スコープ/)を追加した後は、必ず「**Reinstall to Workspace**」をクリックして再インストールしてください。

### ステップ 3: インストール状態を確認する

アプリが[ワークスペース](/glossary/ワークスペース/)に正しくインストールされているか確認します。

```bash
curl -X GET https://slack.com/api/auth.test \
  -H "Authorization: Bearer xoxb-YOUR_BOT_TOKEN"
```

成功時の[レスポンス](/glossary/レスポンス/)例：
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

`"ok": false` が返される場合は、[トークン](/glossary/トークン/)が無効です。

## それでも解決しない場合

- **[トークン](/glossary/トークン/)の有効期限を確認**：App 設定で「**Install App**」セクションを確認
- **[ネットワーク](/glossary/ネットワーク/)接続を確認**：[プロキシ](/glossary/プロキシ/)や[ファイアウォール](/glossary/ファイアウォール/)の影響がないか確認
- **Slack 公式ドキュメント**を参照：https://api.slack.com/authentication/basics
- **Slack サポートに問い合わせ**：[ワークスペース](/glossary/ワークスペース/)の管理者権限で対応が必要な場合もあります

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*