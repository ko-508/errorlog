---
title: "GitLab の 401 エラー：原因と解決策"
date: 2026-06-12
description: "GitLabへの認証に失敗した。GitLab 401 エラーの原因と解決策を解説します。"
tags: ["GitLab"]
errorCode: "401"
trend_incident: true
---
## エラーの概要

GitLab で 401 Unauthorized エラーが発生する場合、クライアントからのリクエストが認証されていない、または認証情報が無効であることを示しています。GitLab API へのアクセス、Git クローン、パイプラインからのリソース取得など、認証が必要な操作全般で発生する可能性があります。このエラーが出た場合、提供されたトークンや認証情報を確認し、それらの有効性と形式を検証する必要があります。

## 実際のエラーメッセージ例

**GitLab API レスポンス：**

```json
{
  "message": "401 Unauthorized"
}
```

**curl コマンドの出力：**

```bash
$ curl -H "Authorization: Bearer invalid-token" https://gitlab.example.com/api/v4/user
{"message":"401 Unauthorized"}
```

**Git クローン時のエラー：**

```bash
$ git clone https://gitlab.example.com/group/project.git
Cloning into 'project'...
fatal: Authentication failed for 'https://gitlab.example.com/group/project.git/'
```

## よくある原因と解決手順

### 原因1：パーソナルアクセストークン（PAT）が無効または期限切れになっている

GitLab のパーソナルアクセストークンには有効期限が設定でき、期限を過ぎたトークンでリクエストを送信すると 401 エラーが返されます。また、トークンを無効化した場合や、ユーザーアカウント設定で特定のスコープを失った場合も認証に失敗します。特に CI/CD パイプラインやスクリプトで長期間使用するトークンは、期限切れに気づきにくいため注意が必要です。

**Before（エラーが起きるコード）：**

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

$ curl -H "PRIVATE-TOKEN: glpat-yyyyyyyyyyyy" \
  https://gitlab.example.com/api/v4/user
# → 200 OK で成功
```

### 原因2：Authorization ヘッダーの形式が誤っている

GitLab API にアクセスする際、Authorization ヘッダーの形式が仕様と異なると認証失敗になります。Bearer トークンを使う場合と PRIVATE-TOKEN ヘッダーを使う場合で形式が異なり、特に古いドキュメントを参照している場合に混同しやすいです。また、トークン前後の空白や特殊文字の誤りも 401 の原因になります。

**Before（エラーが起きるコード）：**

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

CI/CD パイプラインから GitLab API にアクセスする場合、`CI_JOB_TOKEN` という特別な環境変数が提供されます。このトークンはジョブ実行時に自動的に設定されますが、パイプラインの設定エラーや古い実装では、代わりにパーソナルアクセストークンを使用していることがあります。その場合、トークンのスコープ不足や期限切れで 401 エラーが発生します。

**Before（エラーが起きるコード）：**

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

パーソナルアクセストークン生成時に「スコープ」を選択します。API 呼び出しに必要なスコープが不足していると、トークン自体は有効でも 401 エラーが返される可能性があります。たとえば、`read_repository` スコープなしでは repository API にアクセスできません。トークン生成時に必要最小限のスコープを指定してください。

**Deploy Token との区別：**

GitLab には「Deploy Token」という別種のトークンもあります。これはプロジェクト単位で発行されるもので、パーソナルアクセストークンとはスコープと有効期限管理が異なります。CI/CD パイプラインで依存パッケージレジストリからの読み込みが必要な場合、Deploy Token が有効期限切れになっていないか確認してください。

**Self-hosted GitLab での SSL 証明書エラー：**

オンプレミスの GitLab サーバーを使用している場合、自己署名 SSL 証明書により `curl` や `git` コマンドが接続を拒否し、結果的に 401 のような認証エラーが表示されることがあります。この場合、`curl -k` フラグを使うか、システムの信頼されたルート CA に証明書を追加してください。

## それでも解決しない場合

**GitLab インスタンスのアクセスログを確認：**

self-hosted GitLab の場合、サーバーの `/var/log/gitlab/gitlab-rails/production.log` に詳細なエラーメッセージが記録されています。

```bash
sudo tail -f /var/log/gitlab/gitlab-rails/production.log | grep 401
```

**トークンの有効性をスクリプトで検証：**

以下のコマンドでトークンが有効か即座に確認できます。

```bash
TOKEN="glpat-xxxxxxxxxxxx"
GITLAB_URL="https://gitlab.example.com"

curl -s -H "PRIVATE-TOKEN: ${TOKEN}" \
  -w "\n%{http_code}\n" \
  "${GITLAB_URL}/api/v4/user"

# 出力に 200 が含まれればトークン有効
# 401 が出た場合は期限切れまたは無効
```

**CI/CD 環境での環境変数確認：**

パイプラインスクリプト内で `CI_JOB_TOKEN` が正しく設定されているか、以下で確認します。

```bash
# .gitlab-ci.yml内
script:
  - echo "Token exists: ${CI_JOB_TOKEN:+yes}"
  - echo "GitLab URL: ${CI_SERVER_URL}"
```

**公式ドキュメントと最新情報：**

GitLab API のトークン仕様は定期的に更新されます。公式ドキュメント（https://docs.gitlab.com/ee/api/#authentication）と、プロジェクトの Release Notes で最新情報を確認してください。特にマイナーバージョンアップ後は認証方式の非推奨化がないか確認することをお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*