---
title: "Docker の 429 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 429 エラーは、HTTP ステータスコード 429（Too Many Requests）を意味し、短時間に送信されたリクエスト数が上限を超えたことを示します。"
tags: ["Docker"]
errorCode: "429"
lastmod: 2026-06-13
service: "Docker"
error_type: "429"
components: ["Compose", "Registry"]
related_services: ["Docker Hub", "GitHub Actions", "Kubernetes"]
trend_incident: true
---

## エラーの概要

[Docker](/glossary/docker/) の 429 [エラー](/glossary/エラー/)は、[HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/) 429（Too Many Requests）を意味し、短時間に送信された[リクエスト](/glossary/リクエスト/)数が[レート制限](/glossary/レート制限/)の上限を超えたことを示します。[Docker](/glossary/docker/) Hub や[プライベートレジストリ](/glossary/プライベートレジストリ/)に対して過度なアクセスが集中した場合、[レート制限](/glossary/レート制限/)により一時的に[リクエスト](/glossary/リクエスト/)が拒否されます。特に [CI/CD](/glossary/ci-cd/) パイプラインや複数マシンからの並行イメージプル、ビルドキャッシュの更新で頻繁に発生します。

## 実際のエラーメッセージ例

[Docker](/glossary/docker/) [コマンド](/glossary/コマンド/)実行時の[エラーメッセージ](/glossary/エラーメッセージ/)：

```
Error response from daemon: pull access denied for <your-image>, repository does not exist or may require 'docker login': denied: Your request rate limit has been exceeded. Please see https://docs.docker.com/docker-hub/api-rate-limiting/
```

[Docker](/glossary/docker/) Compose での[レート制限](/glossary/レート制限/)[エラー](/glossary/エラー/)：

```
429 Too Many Requests
{"errors":[{"code":"TOOMANYREQUESTS","message":"You have reached your pull rate limit. You may increase the limit by authenticating and upgrading: https://www.docker.com/increase-rate-limits"}]}
```

## よくある原因と解決手順

### 原因1：Docker Hub の認証なし（無認証での並行アクセス）

[Docker](/glossary/docker/) Hub は無認証ユーザーに対して 6 時間ごとに 100 [リクエスト](/glossary/リクエスト/)の[レート制限](/glossary/レート制限/)を適用しています。[認証](/glossary/認証/)を行わないまま複数マシンやパイプラインから同時に[イメージ](/glossary/イメージ/)をプルすると、制限に達します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 認証なしで直接プル
docker pull <your-image>:latest

# CI/CD パイプラインで複数ステップが無認証でプル
docker pull node:18
docker pull postgres:15
docker pull redis:latest
```

**After（修正後）：**

```bash
# Docker Hub にログイン（認証済みユーザーは 200,000 リクエスト/6時間）
docker login --username <your-username> --password <your-token>

# その後、イメージをプル
docker pull <your-image>:latest

# CI/CD パイプラインの場合
echo "<your-docker-token>" | docker login -u "<your-username>" --password-stdin
docker pull node:18
docker pull postgres:15
docker pull redis:latest
```

### 原因2：CI/CD パイプラインでの過度な並行ビルド・プル

GitHub Actions や GitLab CI、Jenkins など複数のジョブが同時に [Docker](/glossary/docker/) [イメージ](/glossary/イメージ/)をプルおよびビルドする場合、[レート制限](/glossary/レート制限/)に達しやすくなります。特に複数[ブランチ](/glossary/ブランチ/)やタグのビルドが並行実行されるとき顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# GitHub Actions の例：複数ジョブが同時に実行
name: Build
on: [push]
jobs:
  build-image-1:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: docker build -t myapp:latest .
  build-image-2:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: docker build -t otherapp:latest .
  build-image-3:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: docker build -t thirdapp:latest .
```

**After（修正後）：**

```yaml
# 認証を追加し、ジョブを直列化または制限数を設定
name: Build
on: [push]
jobs:
  setup:
    runs-on: ubuntu-latest
    steps:
      - name: Login to Docker Hub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_TOKEN }}
  
  build:
    needs: setup
    runs-on: ubuntu-latest
    strategy:
      max-parallel: 2  # 並行数を制限
    steps:
      - uses: actions/checkout@v3
      - run: docker build -t myapp:${{ matrix.image }} .
        env:
          image: [latest, v1.0, v1.1]
```

### 原因3：キャッシュを活用しない重複ビルド

Dockerfile でベースイメージ（`FROM node:18`など）を毎回新規取得するビルドを繰り返すと、イメージレイヤーのプルが何度も発生して[レート制限](/glossary/レート制限/)に達します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```dockerfile
# キャッシュ無効化により毎回ベースイメージをプル
FROM node:18
RUN apt-get update && apt-get install -y curl
COPY . /app
WORKDIR /app
RUN npm install
RUN npm run build
CMD ["node", "server.js"]
```

**After（修正後）：**

```dockerfile
# マルチステージビルドとキャッシュ戦略を活用
FROM node:18 as builder
RUN apt-get update && apt-get install -y curl
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:18
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package*.json ./
CMD ["node", "dist/server.js"]
```

さらに `docker buildx` でビルドキャッシュを保存する：

```bash
docker buildx build \
  --cache-from=type=registry,ref=<your-registry>/<your-image>:buildcache \
  --cache-to=type=registry,ref=<your-registry>/<your-image>:buildcache,mode=max \
  -t <your-image>:latest .
```

## Docker 固有の注意点

### Docker Hub のレート制限の詳細

[Docker](/glossary/docker/) Hub の無認証ユーザーに対する[レート制限](/glossary/レート制限/)は IP アドレス単位で適用されます。複数マシン（[CI/CD](/glossary/ci-cd/) ランナーを含む）から同一 IP で[通信](/glossary/通信/)する場合、複合されてすぐに上限に達します。[Docker](/glossary/docker/) Pro または [Docker](/glossary/docker/) Team サブスクリプションを取得すれば制限が大幅に緩和されます。

### プライベートレジストリでのレート制限

Harbor や GitLab Container Registry、ECR など自社管理の[プライベートレジストリ](/glossary/プライベートレジストリ/)でも、レート制限機能が有効な場合があります。その場合は[設定ファイル](/glossary/設定ファイル/)で[レート制限](/glossary/レート制限/)の値を確認・調整します。

```yaml
# Harbor の例（harbor.yml）
http:
  max_request_body_size: 2147483648
rate_limit:
  enabled: true
  per_second: 100
  burst: 200
```

### Docker Daemon のプル戦略設定

複数のベースイメージをプルする際、シークエンシャルに処理するよう docker-compose.yml で設定します。

```yaml
# docker-compose.yml
version: '3.9'
services:
  app:
    image: node:18
    pull_policy: if_not_present
  db:
    image: postgres:15
    pull_policy: if_not_present
    depends_on:
      - app  # app コンテナが先に起動し、その後 db をプル
```

## それでも解決しない場合

### ログとデバッグコマンド

[Docker](/glossary/docker/) Daemon のレベル設定を[デバッグ](/glossary/デバッグ/)に変更し、レート制限関連の詳細[ログ](/glossary/ログ/)を確認します。

```bash
# Docker Daemon をデバッグモードで起動
dockerd --debug

# または既存の Daemon ログを確認（Linux の場合）
journalctl -u docker -n 100 --no-pager

# Windows / macOS の場合、Docker Desktop の Troubleshoot から Logs をダウンロード
```

### レート制限の確認方法

最後のレスポンスヘッダーから[レート制限](/glossary/レート制限/)の現在状況を確認できます。

```bash
# Docker Hub API を直接呼び出して確認
curl -s -H "Authorization: Bearer $(cat ~/.docker/config.json | jq -r '.auths."https://index.docker.io/v1/".auth | base64 -d | cut -d: -f2')" \
  https://api.docker.com/v2/ \
  -w "\nRateLimit-Limit: %{header_out(RateLimit-Limit)}\n"
```

### 公式ドキュメント

- [Docker Hub API Rate Limiting](https://docs.docker.com/docker-hub/api-rate-limiting/)
- [Docker Hub Pricing and Rate Limits](https://www.docker.com/pricing/)
- [Docker Build with BuildKit](https://docs.docker.com/build/guide/)

### コミュニティリソース

- [Docker GitHub Issues - Rate Limit](https://github.com/docker/hub-feedback/issues)
- [Docker Community Forums](https://forums.docker.com/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*