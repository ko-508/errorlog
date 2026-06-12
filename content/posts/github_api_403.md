---
title: "GitHub API の 403 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub APIの403エラーは、認証には成功したものの、その操作を実行する権限がないことを示します。リポジトリへのアクセス、プルリクエストの作成、シークレットの管理など、特定の操作に必要なスコープやロールが不足している場合に発生します。"
tags: ["GitHub API"]
errorCode: "403"
lastmod: 2026-05-31
service: "GitHub API"
error_type: "403"
components: ["Actions"]
related_services: ["GitHub Web UI", "Webhook"]
trend_incident: true
---

## エラーの概要

GitHub [API](/glossary/api/)の403[エラー](/glossary/エラー/)は、[認証](/glossary/認証/)には成功したものの、その操作を実行する[権限](/glossary/権限/)がないことを示します。[リポジトリ](/glossary/リポジトリ/)へのアクセス、プルリクエストの作成、シークレットの管理など、特定の操作に必要な[スコープ](/glossary/スコープ/)や[ロール](/glossary/ロール/)が不足している場合に発生します。[認証](/glossary/認証/)と[権限](/glossary/権限/)は別の概念であり、この違いを理解することが解決の鍵となります。

## 実際のエラーメッセージ例

```json
{
  "message": "Resource not accessible by integration",
  "documentation_url": "https://docs.github.com/rest/reference/repos#get-a-repository"
}
```

```bash
curl -H "Authorization: token <your-token>" \
  https://api.github.com/repos/<owner>/<repo>/secret_scanning/alerts

# Response:
# HTTP/1.1 403 Forbidden
# {
#   "message": "API rate limit exceeded",
#   "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"
# }
```

## よくある原因と解決手順

### 原因1：トークンに必要なスコープが付与されていない

GitHub [API](/glossary/api/)[トークン](/glossary/トークン/)は「[スコープ](/glossary/スコープ/)」という単位で[権限](/glossary/権限/)が管理されます。例えば、プライベートリポジトリへのアクセスには `repo` [スコープ](/glossary/スコープ/)が、リポジトリシークレットの読み書きには `admin:repo_hook` [スコープ](/glossary/スコープ/)が必要です。[スコープ](/glossary/スコープ/)不足の[トークン](/glossary/トークン/)で[API](/glossary/api/)呼び出しを行うと403が返されます。

**修正前（[スコープ](/glossary/スコープ/)不足）：**
```bash
# 権限なし（public_repo スコープのみ）のトークンでプライベートリポジトリにアクセス
curl -H "Authorization: token ghp_xxxxxxxxxxxx" \
  https://api.github.com/repos/<owner>/<private-repo>
# → 403 Resource not accessible by integration
```

**修正後（必要な[スコープ](/glossary/スコープ/)を追加）：**
```bash
# トークンを再生成時に repo（フルアクセス）スコープを選択
# または以下のスコープを組み合わせる
# - repo (プライベートリポジトリへのフルアクセス)
# - workflow (GitHub Actions ワークフロー管理)
# - admin:repo_hook (Webhook管理)

# 権限をもつトークンで再度実行
curl -H "Authorization: token ghp_yyyyyyyyyyyy" \
  https://api.github.com/repos/<owner>/<private-repo>
# → 200 OK
```

**[スコープ](/glossary/スコープ/)の確認方法：**
```bash
# トークンの現在のスコープを確認
curl -H "Authorization: token <your-token>" \
  https://api.github.com/user \
  -I | grep X-OAuth-Scopes

# 出力例: X-OAuth-Scopes: repo, workflow
```

### 原因2：組織のリポジトリへのアクセス権がない

組織が所有する[リポジトリ](/glossary/リポジトリ/)にアクセスする場合、個人の[トークン](/glossary/トークン/)だけでなく、その組織内での[ロール](/glossary/ロール/)やチームのメンバーシップが必要です。組織が[認可](/glossary/認可/)[ポリシー](/glossary/ポリシー/)を厳密に設定している場合、たとえ `repo` [スコープ](/glossary/スコープ/)を持つ[トークン](/glossary/トークン/)でも403が返されることがあります。

**修正前（組織メンバーではない）：**
```bash
# orgA という組織のプライベートリポジトリへのアクセス
curl -H "Authorization: token <your-token>" \
  https://api.github.com/repos/orgA/<private-repo>
# → 403 Resource not accessible by integration
# （あなたが orgA のメンバーでない場合）
```

**修正後（組織メンバーシップを確認・設定）：**
```bash
# 1. 組織のメンバーシップを確認
curl -H "Authorization: token <your-token>" \
  https://api.github.com/user/memberships/orgs/orgA

# 2. 必要に応じて組織の管理者に追加をリクエスト
# GitHub Web UI: Settings > Organizations > Team を確認・メンバー招待

# 3. メンバーシップが確認できた後、再度API呼び出し
curl -H "Authorization: token <your-token>" \
  https://api.github.com/repos/orgA/<private-repo>
# → 200 OK
```

### 原因3：API レート制限に達している

GitHub [API](/glossary/api/)は1時間あたりの呼び出し回数に制限があります。[認証](/glossary/認証/)なしの[リクエスト](/glossary/リクエスト/)では60回、認証済みで3000回（通常のユーザー）です。この制限に達すると、その後の[リクエスト](/glossary/リクエスト/)は403で返されます。

**修正前（レート制限超過）：**
```bash
# 大量のAPI呼び出しを短時間で実行
for i in {1..3100}; do
  curl -H "Authorization: token <your-token>" \
    https://api.github.com/repos/<owner>/<repo>/issues/$i
done
# 3000回目以降 → 403 API rate limit exceeded
```

**修正後（[レート制限](/glossary/レート制限/)を回避）：**
```bash
# 1. レート制限情報の確認
curl -H "Authorization: token <your-token>" \
  https://api.github.com/rate_limit

# 出力例:
# {
#   "rate": {
#     "limit": 3000,
#     "remaining": 150,
#     "reset": 1640000000
#   }
# }

# 2. リセット時刻まで待つ、または GraphQL API を使用（より効率的）
# GraphQL は単一リクエストで複数のデータ取得が可能

# 3. 待機ロジックを実装
if [ $(date +%s) -lt 1640000000 ]; then
  SLEEP_TIME=$((1640000000 - $(date +%s)))
  echo "Waiting $SLEEP_TIME seconds..."
  sleep $SLEEP_TIME
fi
```

### 原因4：リポジトリへのデプロイキー権限不足

デプロイキーを使用している場合、そのキーに付与されている[権限](/glossary/権限/)（読み取り専用など）が操作内容と合致していない可能性があります。

**修正前（読み取り専用デプロイキー）：**
```bash
# デプロイキーの読み取り専用でプッシュを試みる
git -c core.sshCommand="ssh -i ~/.ssh/deploy_key" push origin main
# → Permission denied / 403 equivalent error
```

**修正後（読み取り・書き込みキーを使用）：**
```bash
# GitHub Web UI でデプロイキーを編集
# Settings > Deploy keys > 対象キー > "Allow write access" を有効化

# 再度プッシュを試行
git -c core.sshCommand="ssh -i ~/.ssh/deploy_key" push origin main
# → Success
```

## ツール固有の注意点

### GitHub Apps と OAuth App の動作の違い

GitHub Appを使用している場合、[トークン](/glossary/トークン/)の[スコープ](/glossary/スコープ/)だけでなく、インストール先の[リポジトリ](/glossary/リポジトリ/)に対する明示的な権限設定も必要です。

```bash
# GitHub App の インストールトークン確認
curl -H "Authorization: Bearer <your-jwt>" \
  https://api.github.com/app/installations/<installation-id>

# インストールトークンはリクエストごとに新規取得が推奨される
curl -X POST \
  -H "Authorization: Bearer <your-jwt>" \
  https://api.github.com/app/installations/<installation-id>/access_tokens
```

### Personal Access Token (PAT) と Fine-grained Token の権限モデルの違い

GitHub は2022年より「Fine-grained Personal Access Tokens」を提供しており、従来のPATより細粒度の権限制御が可能です。しかし設定が複雑になるため、権限不足で403が発生しやすくなります。

```yaml
# Fine-grained token で必要な権限設定例
Repository permissions:
  - Contents: Read & write
  - Pull requests: Read & write
  - Secrets: Read & write

Organization permissions:
  - Members: Read-only
```

### 組織の SAML SSO 有効時の追加認証

組織がSAML SSOを有効にしている場合、PAT使用時に追加の[認可](/glossary/認可/)ステップ（SAML[認可](/glossary/認可/)）が必要です。これが完了していないと403が返されます。

```bash
# SAML認可が必要な場合のエラーメッセージ
# "Token does not have the correct scopes to access this service."

# 対策：GitHub WebUIでトークンに対して SAML SSO 認可を実施
# Settings > Personal access tokens > 対象トークン > Configure SSO
```

## それでも解決しない場合

### ログとデバッグ情報の確認

```bash
# 詳細なレスポンスヘッダーを表示
curl -v -H "Authorization: token <your-token>" \
  https://api.github.com/repos/<owner>/<repo>

# X-RateLimit-* ヘッダーとX-OAuth-Scopes ヘッダーを確認
# これらにより、レート制限状況と実際のスコープが判明する
```

### 公式ドキュメントの参照

- **GitHub [REST](/glossary/rest/) [API](/glossary/api/) Documentation**: `https://docs.github.com/en/rest` - [エンドポイント](/glossary/エンドポイント/)ごとの必須[スコープ](/glossary/スコープ/)一覧が記載されています
- **Scopes for [OAuth](/glossary/oauth/) Apps**: `https://docs.github.com/en/developers/apps/building-oauth-apps/scopes-for-oauth-apps` - [スコープ](/glossary/スコープ/)の定義と用途
- **Rate Limiting**: `https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting` - [レート制限](/glossary/レート制限/)[ポリシー](/glossary/ポリシー/)の詳細

### コミュニティリソース

GitHub の公式フォーラム（GitHub Discussions）や Stack Overflow の `github-api` タグで、類似の問題報告が多数あります。エラーメッセージの全文とトークンスコープの情報を共有することで、より正確な回答が得られます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*