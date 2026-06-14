---
title: "Docker Compose の 401 エラー：原因と解決策"
date: 2026-05-30
lastmod: 2026-06-14
description: "コンテナレジストリへの認証に失敗した。Docker Compose 401 エラーの原因と解決策を解説します。"
tags: ["Docker Compose"]
errorCode: "401"
service: "Docker Compose"
error_type: "401"
components: ["Compose", "Registry"]
related_services: ["Docker Hub", "Azure Container Registry", "AWS ECR", "GCP Artifact Registry", "GitHub Actions", "GitLab", "Jenkins"]
---

## エラーの概要

[Docker](/glossary/docker/) Composeで401[エラー](/glossary/エラー/)が発生する場合、コンテナレジストリーへの[認証](/glossary/認証/)に失敗しています。この[エラー](/glossary/エラー/)はプライベートイメージをpullしようとする際に最も頻繁に発生し、レジストリー側が「認証情報が不正または未提供」と判定した状態です。[Docker](/glossary/docker/) Hubやプライベートレジストリー（ECR、GCR、プライベート[Docker](/glossary/docker/)レジストリーなど）の両方で起こりえます。

## 実際のエラーメッセージ例

```
ERROR: for <service-name>  UnexpectedStatusError(401): 401 Client Error: Unauthorized for url: https://index.docker.io/v2/<image-name>/manifests/latest
```

```json
{
  "message": "unauthorized: authentication required",
  "details": "https://docs.docker.com/docker-hub/access-tokens/"
}
```

```
ERROR: for myapp  pull access denied for myregistry.azurecr.io/myimage, repository does not exist or may require 'docker login': denied: authentication required
```

## よくある原因と解決手順

### 原因1：docker loginを実行していない

[Docker](/glossary/docker/) Composeでプライベートイメージをpullする前に、`docker login`[コマンド](/glossary/コマンド/)で[認証](/glossary/認証/)を済ませていない状況です。認証情報が`~/.docker/config.json`に保存されていないため、レジストリー側は401で応答します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 認証なしで直接実行
$ docker-compose up
ERROR: for webapp  UnexpectedStatusError(401): 401 Client Error: Unauthorized
```

**After（修正後）：**

```bash
# 1. 先に認証を完了させる
$ docker login
Username: <your-username>
Password: <your-password>
Login Succeeded

# 2. その後にdocker-composeを実行
$ docker-compose up
```

### 原因2：compose.ymlで正しい認証情報が参照されていない

compose.ymlにレジストリー認証情報を含めるとき、`x-aws-cred-helper`や`credHelpers`設定が不正な場合や、[設定ファイル](/glossary/設定ファイル/)自体が存在しない場合に401が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    image: myregistry.azurecr.io/myapp:latest
    # 認証情報が指定されていない
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  app:
    image: myregistry.azurecr.io/myapp:latest
    # ~/.docker/config.json に認証情報があることを確認
    # または以下のように環境ファイルから読み込む
    environment:
      - DOCKER_USERNAME=${DOCKER_USERNAME}
      - DOCKER_PASSWORD=${DOCKER_PASSWORD}
```

`~/.docker/config.json`の確認：

```bash
$ cat ~/.docker/config.json
{
  "auths": {
    "myregistry.azurecr.io": {
      "auth": "base64encodedcredentials"
    }
  }
}
```

### 原因3：レジストリーのアクセストークンが期限切れまたは無効

[Docker](/glossary/docker/) Hubやプライベートレジストリーで生成したアクセストークンが期限切れ、削除された、または[権限](/glossary/権限/)が制限されている場合です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 以前のトークンで認証済み
$ docker login
Username: <your-username>
Password: <expired-token>
# 後日、403または401エラーが発生
```

**After（修正後）：**

```bash
# 新しいトークンを生成してログイン（Docker Hubの場合）
# Docker Hub の Account Settings > Security > New Access Token で新規生成
$ docker logout  # 既存認証を削除
$ docker login
Username: <your-username>
Password: <new-access-token>
Login Succeeded

# AWS ECRの場合
$ aws ecr get-login-password --region <your-region> | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.<your-region>.amazonaws.com
```

### 原因4：docker-compose.ymlで間違ったレジストリーURLを指定している

[イメージ](/glossary/イメージ/)名またはレジストリーURLのスペルミスや、ホスト名の不一致がある場合です。存在しないレジストリーや[アクセス権限](/glossary/アクセス権限/)がないレジストリーへのアクセスで401が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    # URLが正しくない、またはアクセス権限がないレジストリー
    image: myregisty.azurecr.io/myapp:latest  # typo
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  app:
    # 正しいレジストリーURLを指定
    image: myregistry.azurecr.io/myapp:latest
```

### 原因5：マルチレジストリー構成で認証スコープが不足している

複数のプライベートレジストリーを使用する場合、各レジストリーに対して別々に`docker login`する必要があります。一つのレジストリーにのみ[ログイン](/glossary/ログイン/)していると、他のレジストリーへのアクセスで401が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    image: registry1.example.com/myapp:latest
  worker:
    # registry2への認証がない
    image: registry2.example.com/myworker:latest
```

```bash
$ docker login registry1.example.com
# registry2には認証していない
$ docker-compose up
# registry2のイメージpullで401エラー
```

**After（修正後）：**

```bash
# 両方のレジストリーに認証
$ docker login registry1.example.com
$ docker login registry2.example.com
$ docker-compose up
```

## Docker Compose固有の注意点

### AWS ECR（Elastic Container Registry）での認証

ECRはAWS [IAM](/glossary/iam/)[認証](/glossary/認証/)を使用するため、従来の`docker login`では対応できません。`aws ecr get-login-password`[コマンド](/glossary/コマンド/)で一時的な[認証](/glossary/認証/)[トークン](/glossary/トークン/)を取得する必要があります。

```bash
# ECR認証（12時間有効なトークンを生成）
$ aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.ap-northeast-1.amazonaws.com

# 認証後、docker-composeでECRイメージを参照可能
$ docker-compose up
```

### Azure Container Registry（ACR）での認証

ACRはサービスプリンシパルまたはアクセスキーでの[認証](/glossary/認証/)が一般的です。

```bash
$ az acr login --name <your-acr-name>
# または
$ docker login <your-acr-name>.azurecr.io -u <your-username> -p <your-password>
```

### プライベートDockerレジストリーでの認証

自社ホストのプライベートレジストリーを使用する場合、レジストリーが[HTTPS](/glossary/https/)ではなく[HTTP](/glossary/http/)で動作している場合があります。その場合は`daemon.json`でレジストリーをinsecureなものとして指定する必要があります。

```json
{
  "insecure-registries": ["myregistry.local:5000"]
}
```

### .dockerconfigjsonの活用

[Kubernetes](/glossary/kubernetes/)へのデプロイメント前に[Docker](/glossary/docker/) Compose で動作確認する場合、[設定ファイル](/glossary/設定ファイル/)の一貫性を保つことが重要です。

```bash
# ~/.docker/config.jsonが正しく設定されているか確認
$ test -f ~/.docker/config.json && echo "Config file exists" || echo "Missing config file"
```

## それでも解決しない場合

### デバッグログを有効化

[Docker](/glossary/docker/) Composeのデバッグモードで詳細な[エラー](/glossary/エラー/)情報を確認できます。

```bash
$ DOCKER_CONTENT_TRUST_DEBUG=1 docker-compose up
```

### レジストリー接続テスト

`curl`[コマンド](/glossary/コマンド/)で認証状態を直接[テスト](/glossary/テスト/)します。

```bash
# Docker Hubへの接続テスト（認証なし）
$ curl -i https://index.docker.io/v2/library/ubuntu/manifests/latest
# 401が返される場合は認証情報が必要

# 認証後のテスト（Bearer tokenを使用）
$ TOKEN=$(curl -s -u <username>:<password> "https://auth.docker.io/v2/token?service=registry.docker.io&scope=repository:library/ubuntu:pull" | jq -r '.token')
$ curl -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/library/ubuntu/manifests/latest
```

### ログファイルの確認

[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)の[ログ](/glossary/ログ/)を確認します。

```bash
# Linux（systemd利用）
$ journalctl -u docker --no-pager | tail -50

# macOS（Docker Desktop）
$ log stream --predicate 'process == "com.docker.vmnetd"' --level debug
```

### 公式ドキュメント

- [Docker](/glossary/docker/)公式ドキュメント：https://docs.docker.com/engine/reference/commandline/login/
- [Docker](/glossary/docker/) Compose[認証](/glossary/認証/)：https://docs.docker.com/compose/compose-file/compose-file-v3/#image
- AWS ECR[認証](/glossary/認証/)：https://docs.aws.amazon.com/ja_jp/AmazonECR/latest/userguide/getting-started-cli.html

### コミュニティリソース

- [Docker](/glossary/docker/) Community Forums：https://forums.docker.com/
- GitHub Issues（docker/compose）：https://github.com/docker/compose/issues

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*