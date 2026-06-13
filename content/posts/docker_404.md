---
title: "Docker の 404 エラー：原因と解決策"
date: 2026-01-01
description: "Docker で 404 エラーが発生するのは、指定したイメージまたはリポジトリがレジストリ（Docker Hub や ECR などのイメージ保管先）に存在しないことを意味します。"
tags: ["Docker"]
errorCode: "404"
lastmod: 2026-06-13
service: "Docker"
error_type: "404"
components: ["Registry", "Hub"]
related_services: ["Docker Compose", "AWS ECR", "Azure Container Registry"]
trend_incident: true
---

## エラーの概要

Docker で 404 エラーが発生するのは、指定したイメージまたはリポジトリがレジストリ（Docker Hub や Private Registry などのイメージ保管先）に存在しないことを意味します。このエラーは `docker pull`、`docker run`、`docker push` などのコマンド実行時に表示され、イメージ名の誤字、存在しないタグの指定、アクセス権限の不足などが主な原因です。Docker はレジストリにクエリを送信した際に、リソースが見つからないと 404 ステータスを返すため、ユーザー側では対象イメージの確認と修正が必要になります。

## 実際のエラーメッセージ例

```bash
$ docker pull myapp:latest
Error response from daemon: manifest not found: myapp:latest
```

```json
{
  "errors": [
    {
      "code": "NAME_UNKNOWN",
      "message": "repository not found",
      "detail": null
    }
  ]
}
```

```bash
$ docker push localhost:5000/myimage:v1.0
The push refers to repository [localhost:5000/myimage]
error parsing HTTP 404 response body: invalid character '<' looking for beginning of value: "<html><body><h1>404 Not Found</h1></body></html>"
```

## よくある原因と解決手順

### 原因 1: イメージ名またはタグの誤字

イメージ名やタグにスペルミスがある場合、レジストリが該当リソースを見つけられず 404 が返されます。Docker Hub では大文字と小文字が区別されるため、注意が必要です。

**Before（エラーが起きるコード）：**

```bash
docker pull myaapp:latest
docker run node:lts-slpine node app.js
```

**After（修正後）：**

```bash
docker pull myapp:latest
docker run node:lts-alpine node app.js
```

### 原因 2: タグが存在しない、または削除されている

イメージは存在するが指定したタグが存在しない場合も 404 が発生します。タグの削除後にそのタグを参照しようとした場合も同じです。

**Before（エラーが起きるコード）：**

```bash
docker pull ubuntu:22.10
```

**After（修正後）：**

```bash
# 利用可能なタグを事前に確認
docker pull ubuntu:22.04
docker pull ubuntu:latest
```

### 原因 3: Private Registry の認証失敗またはレジストリ自体が存在しない

プライベートレジストリにアクセスする際、ログインしていない、認証トークンが無効、またはレジストリ URL が誤っている場合 404 が返されます。

**Before（エラーが起きるコード）：**

```bash
docker pull registry.example.com/myapp:v1.0
# ログインなしでプライベートレジストリにアクセス

docker push gcr.io/my-project/image:tag
# GCP Container Registry の認証なし
```

**After（修正後）：**

```bash
# Private Registry にログイン
docker login registry.example.com
docker pull registry.example.com/myapp:v1.0

# GCP Container Registry の認証
gcloud auth configure-docker
docker push gcr.io/my-project/image:tag
```

### 原因 4: レジストリが不健全な状態、またはネットワーク接続の問題

レジストリサーバー自体が一時的にダウンしている、ネットワークが不安定な場合、404 ではなく接続エラーとして返されることもありますが、タイムアウト後に 404 が返される場合があります。

**Before（エラーが起きるコード）：**

```bash
docker pull myregistry.jp:5000/app:latest
# レジストリサーバーが応答していない状態
```

**After（修正後）：**

```bash
# レジストリの疎通確認
curl -v https://myregistry.jp:5000/v2/_catalog

# DNS 解決確認
nslookup myregistry.jp

# ファイアウォール設定確認後、再度実行
docker pull myregistry.jp:5000/app:latest
```

### 原因 5: Docker Compose での不正なイメージ指定

Dockerfile または docker-compose.yml で存在しないイメージを FROM や image として指定した場合、ビルド・起動時に 404 が発生します。

**Before（エラーが起きるコード）：**

```yaml
version: '3'
services:
  app:
    image: node:16-bullseye-slim
    # このタグが削除されている場合
    build:
      context: .
      dockerfile: Dockerfile
```

```dockerfile
FROM python:3.10-slim-buster
# このタグが古く削除されている場合
```

**After（修正後）：**

```yaml
version: '3'
services:
  app:
    image: node:18-bullseye-slim
    build:
      context: .
      dockerfile: Dockerfile
```

```dockerfile
FROM python:3.11-slim-bullseye
# サポートされている最新のタグを使用
```

## Docker 固有の注意点

### Docker Hub との連携における注意

Docker Hub でのイメージ検索時、`docker search myapp` コマンドで候補を確認した後でも、タグの存在確認が必要です。公式イメージとユーザー提供イメージで命名規則が異なるため、フルネーム指定時は `library/` プレフィックスの有無を確認してください。

### Local Registry の場合の疎通確認

ローカル Registry（`localhost:5000` など）を運用している場合、レジストリコンテナが起動しているか、ネットワークがホストコンテナから到達可能かを確認してください。

**確認コマンド：**

```bash
# レジストリコンテナの起動確認
docker ps | grep registry

# レジストリの疎通確認
curl http://localhost:5000/v2/_catalog

# カタログが空の場合は、別途イメージを push する必要あり
```

### イメージのスコープと URL スキーム

プライベートレジストリを使用する際、HTTP と HTTPS の指定ミスが 404 につながることがあります。Docker は HTTPS を推奨していますが、自己署名証明書を使用する場合は `insecure-registries` の設定が必要です。

**daemon.json の設定例：**

```json
{
  "insecure-registries": ["myregistry.local:5000"],
  "registry-mirrors": []
}
```

## それでも解決しない場合

### 確認すべきログとデバッグコマンド

```bash
# Docker デーモンのログ確認（Linux systemd の場合）
journalctl -u docker -n 100

# Docker Desktop でのログ確認
# macOS/Windows: Docker Desktop の Troubleshoot > View Logs メニュー

# レジストリの詳細応答を確認
docker pull myapp:latest --debug

# レジストリが HTTPS をサポートしているか確認
openssl s_client -connect registry.example.com:443 -showcerts
```

### 公式ドキュメント参照

- [Docker Registry HTTP API V2](https://docs.docker.com/registry/spec/api/)
- [Docker Hub Repository Visibility](https://docs.docker.com/docker-hub/repos/)
- [Docker Daemon Configuration（insecure-registries）](https://docs.docker.com/engine/daemon/cli-reference/#daemon-config-file)

### コミュニティリソース

- Docker Community Forums: https://forums.docker.com/
- GitHub Issues（Docker/moby）: https://github.com/moby/moby/issues

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*