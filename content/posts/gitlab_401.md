---
title: "GitLab の 401 エラー：原因と解決策"
date: 2026-06-12
description: "GitLabへの認証に失敗した"
tags: ["GitLab"]
errorCode: "401"
service: "GitLab"
error_type: "401"
components: ["API", "CI/CD"]
related_services: ["curl", "Git"]
trend_incident: true
---
## エラーの概要

GitLab で 401 Unauthorized [エラー](/glossary/エラー/)が発生する場合、クライアントからの[リクエスト](/glossary/リクエスト/)が[認証](/glossary/認証/)されていない、または認証情報が無効であることを示しています。GitLab [API](/glossary/api/) へのアクセス、[Git](/glossary/git/) クローン、パイプラインからのリソース取得など、[認証](/glossary/認証/)が必要な操作全般で発生する可能性があります。この[エラー](/glossary/エラー/)が出た場合、提供された[トークン](/glossary/トークン/)や認証情報を確認し、それらの有効性と形式を検証する必要があります。

## 実際のエラーメッセージ例

**GitLab [API](/glossary/api/) [レスポンス](/glossary/レスポンス/)：**

```json
{
  "message": "401 Unauthorized"
}
```

**curl [コマンド](/glossary/コマンド/)の出力：**

```bash
$ curl -H "Authorization: Bearer invalid-token" https://gitlab.example.com/api/v4/user
{"message":"401 Unauthorized"}
```

**[Git](/glossary/git/) クローン時の[エラー](/glossary/エラー/)：**

```bash
$ git clone https://gitlab.example.com/group/project.git
Cloning into 'project'...
fatal: Authentication failed for 'https://gitlab.example.com/group/project.git/'
```

## よくある原因と解決手順

### 原因1：パーソナルアクセストークン（PAT）が無効または期限切れになっている

GitLab のパーソナルアクセストークンには有効期限が設定でき、期限を過ぎた[トークン](/glossary/トークン/)で[リクエスト](/glossary/リクエスト/)を送信すると 401 [エラー](/glossary/エラー/)が返されます。また、[トークン](/glossary/トークン/)を無効化した場合や、[ユーザーアカウント](/glossary/ユーザーアカウント/)設定で特定の[スコープ](/glossary/スコープ/)を失った場合も[認証](/glossary/認証/)に失敗します。特に [CI/CD](/glossary/ci-cd/) パイプラインやスクリプトで長期間使用する[トークン](/glossary/トークン/)は、期限切れに気づきにくいため注意が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 2024年1月に作成したトークンを2024年12月に使用しようとしている場合
$ curl -H "PRIVATE-TOKEN: glpat-xxxxxxxxxxxx" \
  https://gitlab.example.com/api/v4/user
# → 401 Unauthorized が返される
```

**After（修正後）：**

```bash
# GitLab UI で新しいパーソナルアクセストークンを生成
# User Settings → Access Tokens → Add new token
# スコープ: api, read_user, read_repository などを選択

$ curl -H "PRIVATE-TOKEN: <your-gitlab-token>" \
  https://gitlab.example.com/api/v4/user
# → 200 OK で成功
```

### 原因2：Authorization ヘッダーの形式が誤っている

GitLab [API](/glossary/api/) にアクセスする際、Authorization [ヘッダー](/glossary/ヘッダー/)の形式が仕様と異なると認証失敗になります。Bearer [トークン](/glossary/トークン/)を使う場合と PRIVATE-TOKEN [ヘッダー](/glossary/ヘッダー/)を使う場合で形式が異なり、特に古いドキュメントを参照している場合に混同しやすいです。また、[トークン](/glossary/トークン/)前後の空白や特殊文字の誤りも 401 の原因になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# パターン1: Authorization Bearer の形式が間違っている
$ curl -H "Authorization: Bearer glpat-xxxxxxxxxxxx" \
  https://gitlab.example.com/api/v4/user
# → 401 Unauthorized

# パターン2: PRIVATE-TOKEN ヘッダーが誤っている
$ curl -H "PRIVATE_TOKEN: glpat-xxxxxxxxxxxx" \
  https://gitlab.example.com/api/v4/user
# → 401 Unauthorized

# パターン3: トークン前に余計な文字列が含まれている
$ curl -H "PRIVATE-TOKEN: token=glpat-xxxxxxxxxxxx" \
  https://gitlab.example.com/api/v4/user
# → 401 Unauthorized
```

**After（修正後）：**

```bash
# パターン1: PRIVATE-TOKEN ヘッダーを使う場合（推奨）
$ curl -H "PRIVATE-TOKEN: glpat-xxxxxxxxxxxx" \
  https://gitlab.example.com/api/v4/user
# → 200 OK

# パターン2: OAuth2 Bearer トークンを使う場合
$ curl -H "Authorization: Bearer <oauth-token>" \
  https://gitlab.example.com/api/v4/user
# → 200 OK

# パターン3: Git 操作で PAT を使用する場合
$ git clone https://oauth2:<pat-token>@gitlab.example.com/group/project.git
```

### 原因3：CI/CD パイプラインで正しいジョブトークンが使われていない

[CI/CD](/glossary/ci-cd/) パイプラインから GitLab [API](/glossary/api/) にアクセスする場合、`CI_JOB_TOKEN` という特別な[環境変数](/glossary/環境変数/)が提供されます。この[トークン](/glossary/トークン/)はジョブ実行時に自動的に設定されますが、パイプラインの設定[エラー](/glossary/エラー/)や古い実装では、代わりにパーソナルアクセストークンを使用していることがあります。その場合、[トークン](/glossary/トークン/)の[スコープ](/glossary/スコープ/)不足や期限切れで 401 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# .gitlab-ci.yml
stages:
  - build

api_test:
  stage: build
  script:
    # PAT をハードコードすると、期限切れや権限変更で失敗する
    - curl -H "PRIVATE-TOKEN: glpat-xxxxxxxxxxxx" \
      https://gitlab.example.com/api/v4/projects
    # → 期限切れ時に 401 Unauthorized
```

**After（修正後）：**

```yaml
# .gitlab-ci.yml
stages:
  - build

api_test:
  stage: build
  script:
    # CI_JOB_TOKEN は実行中のジョブに紐づくトークン
    - curl -H "PRIVATE-TOKEN: ${CI_JOB_TOKEN}" \
      https://gitlab.example.com/api/v4/projects
    # または
    - curl -H "JOB-TOKEN: ${CI_JOB_TOKEN}" \
      https://gitlab.example.com/api/v4/v4/projects/<project-id>/packages/generic/<package>/<version>/<file>
    # → ジョブの有効期間中は常に有効
```

## ツール固有の注意点

**GitLab のトークンスコープ設定の重要性：**

パーソナルアクセストークン生成時に「[スコープ](/glossary/スコープ/)」を選択します。[API](/glossary/api/) 呼び出しに必要な[スコープ](/glossary/スコープ/)が不足していると、[トークン](/glossary/トークン/)自体は有効でも 401 [エラー](/glossary/エラー/)が返される可能性があります。たとえば、`read_repository` [スコープ](/glossary/スコープ/)なしでは repository [API](/glossary/api/) にアクセスできません。[トークン](/glossary/トークン/)生成時に必要最小限の[スコープ](/glossary/スコープ/)を指定してください。

**Deploy Token との区別：**

GitLab には「Deploy Token」という別種の[トークン](/glossary/トークン/)もあります。これはプロジェクト単位で発行されるもので、パーソナルアクセストークンとは[スコープ](/glossary/スコープ/)と有効期限管理が異なります。[CI/CD](/glossary/ci-cd/) パイプラインで依存パッケージレジストリからの読み込みが必要な場合、Deploy Token が有効期限切れになっていないか確認してください。

**Self-hosted GitLab での [SSL](/glossary/ssl/) 証明書[エラー](/glossary/エラー/)：**

オンプレミスの GitLab [サーバー](/glossary/サーバー/)を使用している場合、自己署名 [SSL](/glossary/ssl/) 証明書により `curl` や `git` [コマンド](/glossary/コマンド/)が接続を拒否し、結果的に 401 のような[認証](/glossary/認証/)[エラー](/glossary/エラー/)が表示されることがあります。この場合、`curl -k` フラグを使うか、システムの信頼されたルート CA に証明書を追加してください。

## それでも解決しない場合

**GitLab [インスタンス](/glossary/インスタンス/)のアクセスログを確認：**

self-hosted GitLab の場合、[サーバー](/glossary/サーバー/)の `/var/log/gitlab/gitlab-rails/production.log` に詳細な[エラーメッセージ](/glossary/エラーメッセージ/)が記録されています。

```bash
sudo tail -f /var/log/gitlab/gitlab-rails/production.log | grep 401
```

**[トークン](/glossary/トークン/)の有効性をスクリプトで検証：**

以下の[コマンド](/glossary/コマンド/)で[トークン](/glossary/トークン/)が有効か即座に確認できます。

```bash
TOKEN="glpat-xxxxxxxxxxxx"
GITLAB_URL="https://gitlab.example.com"

curl -s -H "PRIVATE-TOKEN: ${TOKEN}" \
  -w "\n%{http_code}\n" \
  "${GITLAB_URL}/api/v4/user"

# 出力に 200 が含まれればトークン有効
# 401 が出た場合は期限切れまたは無効
```

**[CI/CD](/glossary/ci-cd/) 環境での環境変数確認：**

パイプラインスクリプト内で `CI_JOB_TOKEN` が正しく設定されているか、以下で確認します。

```bash
# .gitlab-ci.yml内
script:
  - echo "Token exists: ${CI_JOB_TOKEN:+yes}"
  - echo "GitLab URL: ${CI_SERVER_URL}"
```

**公式ドキュメントと最新情報：**

GitLab [API](/glossary/api/) の[トークン](/glossary/トークン/)仕様は定期的に更新されます。公式ドキュメント（https://docs.gitlab.com/ee/api/#authentication）と、プロジェクトの Release Notes で最新情報を確認してください。特にマイナーバージョンアップ後は認証方式の非推奨化がないか確認することをお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*