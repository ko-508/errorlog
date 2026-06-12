---
title: "GitHub API の 401 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub APIで 401 Unauthorizedエラーが発生するのは、リクエストに対する認証が失敗した場合です。このエラーは、認証情報が完全に欠落している、形式が正しくない、または無効な状態を示しています。"
tags: ["GitHub API"]
errorCode: "401"
lastmod: 2026-05-31
service: "GitHub API"
error_type: "401"
components: ["Personal Access Token", "Authorization header"]
related_services: ["curl", "Python requests"]
---

## エラーの概要

GitHub [API](/glossary/api/)で 401 Unauthorized[エラー](/glossary/エラー/)が発生するのは、[リクエスト](/glossary/リクエスト/)に対する[認証](/glossary/認証/)が失敗した場合です。この[エラー](/glossary/エラー/)は、認証情報が完全に欠落している、形式が正しくない、または無効な状態を示しています。GitHub [API](/glossary/api/)を呼び出すときに最も頻繁に遭遇する[エラー](/glossary/エラー/)の一つであり、適切な認証情報を提供することで解決できます。

## 実際のエラーメッセージ例

curl[コマンド](/glossary/コマンド/)で認証情報なしでGitHub [API](/glossary/api/)にアクセスした場合：

```bash
$ curl https://api.github.com/user
{
  "message": "Requires authentication",
  "documentation_url": "https://docs.github.com/rest/reference/users#get-the-authenticated-user"
}
```

PythonのrequestsライブラリでPersonal Access Token（PAT）が無効な場合：

```json
{
  "message": "Bad credentials",
  "documentation_url": "https://docs.github.com/rest"
}
```

## よくある原因と解決手順

### 原因1：Personal Access Token（PAT）が無効または期限切れ

GitHub [API](/glossary/api/)の[認証](/glossary/認証/)に使用するPATが期限切れになったり、削除されたりすると401[エラー](/glossary/エラー/)が発生します。PATには最大100年の有効期限を設定できますが、明示的に有効期限を設定している場合は有効期限の管理が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）:**

```bash
# 3年前に作成した期限切れのPATを使用
$ curl -H "Authorization: token ghp_xxxxxxxxxxxxxxxxxxxxxxxxxx" \
  https://api.github.com/user
# 401 Unauthorized
```

**After（修正後）:**

新しいPATを生成します。GitHubの設定画面で「Settings > Developer settings > Personal access tokens」に移動し、「Generate new token」をクリックします。必要なscopeを選択（通常は`repo`と`user`）し、新しい[トークン](/glossary/トークン/)を生成してください。

```bash
# 新しく生成したPATを使用
$ curl -H "Authorization: token ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyy" \
  https://api.github.com/user
```

### 原因2：Authorizationヘッダーの形式が正しくない

GitHub [API](/glossary/api/)は特定の形式でAuthorization[ヘッダー](/glossary/ヘッダー/)を受け取ります。`Bearer`ではなく`token`キーワードを使用する必要があります。また、[ヘッダー](/glossary/ヘッダー/)名や値のスペース配置のミスも401[エラー](/glossary/エラー/)の原因になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）:**

```bash
# 間違った形式1：Bearerを使用
curl -H "Authorization: Bearer ghp_xxxxxxxxxxxxxxxxxxxxxxxxxx" \
  https://api.github.com/user

# 間違った形式2：スペースが足りない
curl -H "Authorization:token ghp_xxxxxxxxxxxxxxxxxxxxxxxxxx" \
  https://api.github.com/user

# 間違った形式3：トークンをクォートで囲んでいる
curl -H 'Authorization: token "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxx"' \
  https://api.github.com/user
```

**After（修正後）:**

```bash
# 正しい形式：tokenキーワード＋スペース＋トークン
curl -H "Authorization: token ghp_xxxxxxxxxxxxxxxxxxxxxxxxxx" \
  https://api.github.com/user

# Pythonでの正しい例
import requests
headers = {
    "Authorization": "token ghp_xxxxxxxxxxxxxxxxxxxxxxxxxx",
    "Accept": "application/vnd.github.v3+json"
}
response = requests.get("https://api.github.com/user", headers=headers)
```

### 原因3：トークンのscope不足

生成したPATのscopeが制限されていると、特定の[エンドポイント](/glossary/エンドポイント/)にアクセスするときに401[エラー](/glossary/エラー/)が発生します。例えば、`repo`[スコープ](/glossary/スコープ/)なしではプライベートリポジトリへのアクセスができません。

**Before（[エラー](/glossary/エラー/)が起きる設定）:**

```bash
# `repo`スコープなしのPATで、プライベートリポジトリにアクセス
curl -H "Authorization: token ghp_xxxx_publicscope_only" \
  https://api.github.com/repos/<owner>/<private-repo>
# 401 Unauthorized
```

**After（修正後）:**

GitHubの「Settings > Developer settings > Personal access tokens」で既存[トークン](/glossary/トークン/)を選択し、必要なscopeを追加します。または新しい[トークン](/glossary/トークン/)を生成する際に適切なscopeを選択してください。

```bash
# 適切なスcopeを持つPATで同じリクエスト
curl -H "Authorization: token ghp_xxxx_with_repo_scope" \
  https://api.github.com/repos/<owner>/<private-repo>
```

### 原因4：環境変数またはコンフィグの認証情報がセットされていない

GitHub [CLI](/glossary/cli/)や[Git](/glossary/git/)自体を使用している場合、[環境変数](/glossary/環境変数/)や`~/.gitconfig`ファイルに認証情報が設定されていないと401[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きる状態）:**

```bash
# GitHub CLIが認証されていない状態
$ gh api user
# Error: HTTP 401: Requires authentication
```

**After（修正後）:**

```bash
# GitHub CLIで認証
$ gh auth login
# プロンプトに従い、GitHub.comを選択、
# HTTPS protocolを選択、PATを入力してログイン

# その後、APIコマンドが使用可能に
$ gh api user
```

## ツール固有の注意点

### GitHub APIのバージョン指定

GitHubは複数の[API](/glossary/api/)バージョンをサポートしており、古いバージョンへの[リクエスト](/glossary/リクエスト/)は認証要件が異なる場合があります。[REST](/glossary/rest/) [API](/glossary/api/) v3を使用する際は、`Accept`[ヘッダー](/glossary/ヘッダー/)で明示的にバージョンを指定することが推奨されます。

```bash
curl -H "Authorization: token <PAT>" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/user
```

### GraphQL APIの認証

GitHub [GraphQL](/glossary/graphql/) [API](/glossary/api/)は、Authorization[ヘッダー](/glossary/ヘッダー/)の形式が[REST](/glossary/rest/) [API](/glossary/api/)と同じですが、[エンドポイント](/glossary/エンドポイント/)が異なります。[GraphQL](/glossary/graphql/) [API](/glossary/api/)使用時も同じPATが有効ですが、[リクエスト](/glossary/リクエスト/)形式に注意が必要です。

```bash
curl -X POST \
  -H "Authorization: token <PAT>" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ viewer { login } }"}' \
  https://api.github.com/graphql
```

### Organization内でのAPI利用

OrganizationのプライベートリポジトリやOrganizationメンバーとしてのアクセスが必要な場合、PAT生成時に`read:org`[スコープ](/glossary/スコープ/)を追加する必要があります。

## それでも解決しない場合

### 確認すべき手順

1. **[トークン](/glossary/トークン/)の有効性確認**：以下の[コマンド](/glossary/コマンド/)で現在の[トークン](/glossary/トークン/)が有効か確認してください。

```bash
curl -H "Authorization: token <PAT>" https://api.github.com/user
```

2. **[トークン](/glossary/トークン/)のscope確認**：[トークン](/glossary/トークン/)生成時に付与されたscopeを確認してください。

```bash
curl -H "Authorization: token <PAT>" https://api.github.com/ \
  | grep -i "x-oauth-scopes"
```

3. **[ネットワーク](/glossary/ネットワーク/)の確認**：[プロキシ](/glossary/プロキシ/)や[ファイアウォール](/glossary/ファイアウォール/)経由でGitHubに接続している場合、[リクエスト](/glossary/リクエスト/)が正しく転送されているか確認してください。

### 公式ドキュメント参照

- [GitHub REST API authentication](https://docs.github.com/rest/authentication)：認証方法の詳細
- [Creating a personal access token](https://docs.github.com/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)：PAT作成ガイド
- [GitHub API Rate Limits](https://docs.github.com/rest/rate-limit)：レート制限関連情報

### デバッグのコツ

詳細な[レスポンス](/glossary/レスポンス/)を確認するには、verbose モードでcurlを実行してください。

```bash
curl -v -H "Authorization: token <PAT>" https://api.github.com/user
```

GitHub [API](/glossary/api/)の応答[ヘッダー](/glossary/ヘッダー/)に含まれる`X-RateLimit-*`や`X-GitHub-Request-Id`といった情報は、GitHub Supportへの問い合わせ時に役立ちます。これらの情報を記録しておくと、問題解決が効率的になります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*