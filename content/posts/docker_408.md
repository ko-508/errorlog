---
title: "Docker の 408 エラー：原因と解決策"
date: 2026-05-24
description: "408 Request Timeout は、HTTP標準仕様（RFC 9110）で定められたステータスコードです。Docker環境では、クライアントがリクエストを完了できる規定時間内に要求を送信しなかった、または完全に送信できなかった場合に"
tags: ["Docker"]
errorCode: "408"
lastmod: 2026-06-13
service: "Docker"
error_type: "408"
components: ["Daemon", "CLI", "API", "Compose", "BuildKit"]
related_services: ["HTTP", "RFC", "UNIX Socket", "Named Pipe", "Dockerfile"]
trend_incident: true
top_queries:
- '408 エラー'
- 'http 408エラー'
---

## エラーの概要

408 Request Timeout は、[HTTP](/glossary/http/)標準仕様（[RFC](/glossary/rfc/) 9110）で定められた[ステータスコード](/glossary/ステータスコード/)です。[Docker](/glossary/docker/)環境では、クライアントが[リクエスト](/glossary/リクエスト/)を完了できる規定時間内に要求を送信しなかった、または完全に送信できなかった場合に発生します。[Docker](/glossary/docker/) Daemonや[コンテナ](/glossary/コンテナ/)[API](/glossary/api/) との通信時に[タイムアウト](/glossary/タイムアウト/)が生じ、[API](/glossary/api/)呼び出しが中断される典型的なケースです。特に[コンテナ](/glossary/コンテナ/)のビルド、実行、イメージプッシュ時に多く観測されます。

## 実際のエラーメッセージ例

```json
{
  "message": "Client sent an HTTP request to an HTTPS server.\nhttp: server gave HTTP response to HTTPS client",
  "error": "408 Request Timeout",
  "details": "The request could not be completed within the timeout period"
}
```

```bash
docker build -t myimage:latest .
Error response from daemon: Get "https://registry.docker.io/v2/": net/http: request canceled (Client.Timeout exceeded while awaiting headers)
Error: 408 Request Timeout
```

```bash
docker push myregistry.azurecr.io/myimage:latest
Error response from daemon: received unexpected HTTP status: 408 Request Timeout
```

## よくある原因と解決手順

### 原因1：Docker Daemon のタイムアウト設定が短すぎる

[Docker](/glossary/docker/) Daemon（dockerd）のデフォルトタイムアウト設定では、大規模[イメージ](/glossary/イメージ/)のビルドやプッシュ時に処理が間に合わないことがあります。特に[ネットワーク](/glossary/ネットワーク/)が遅い環境では顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# docker-compose.yml でタイムアウト設定が不足している状態
docker push myregistry.azurecr.io/largeimage:latest
# 結果：408 Request Timeout
```

**After（修正後）：**

```bash
# Docker Daemon の設定ファイルを編集
# /etc/docker/daemon.json（Linux）または ~/.docker/daemon.json（Mac）
cat << 'EOF' > /etc/docker/daemon.json
{
  "max-concurrent-downloads": 3,
  "max-concurrent-uploads": 3,
  "http-check-interval": "30s",
  "timeout": 300,
  "disable-legacy-registry": true
}
EOF

# Daemon の再起動
sudo systemctl restart docker

# または Docker Desktop を再起動（Mac/Windows）
```

### 原因2：Docker Compose の接続タイムアウトが不適切

docker-compose.ymlで明示的に[タイムアウト](/glossary/タイムアウト/)値が設定されていない、または[ネットワーク](/glossary/ネットワーク/)遅延を考慮していない場合、特にリモートレジストリアクセス時に408[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    image: myregistry.example.com/myapp:latest
    build:
      context: .
      dockerfile: Dockerfile
    # タイムアウト設定がない
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  app:
    image: myregistry.example.com/myapp:latest
    build:
      context: .
      dockerfile: Dockerfile
      args:
        HTTP_TIMEOUT: 300
    environment:
      - DOCKER_TIMEOUT=300
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G
      reservations:
        cpus: '0.5'
        memory: 512M
```

また、docker-compose [コマンド](/glossary/コマンド/)実行時に明示的に[タイムアウト](/glossary/タイムアウト/)を指定：

```bash
docker-compose --verbose build --no-cache --timeout 300 app
docker-compose push --timeout 300
```

### 原因3：レジストリの認証情報が正しくない、または有効期限切れ

[Docker](/glossary/docker/) [レジストリ](/glossary/レジストリ/)へのプッシュ/プル時に、[認証](/glossary/認証/)[トークン](/glossary/トークン/)が無効または期限切れになっていると、Daemon が[認証](/glossary/認証/)[リトライ](/glossary/リトライ/)を試みる間に 408 [タイムアウト](/glossary/タイムアウト/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 認証情報が不足している状態でプッシュ
docker push myregistry.azurecr.io/myimage:latest
# Error: 408 Request Timeout（実は認証エラーが根因）
```

**After（修正後）：**

```bash
# Azure Container Registry の例
az acr login --name myregistry

# または Docker login コマンドで明示的に認証
# Docker Hub の場合
docker login -u <your-username>

# プライベートレジストリの場合
docker login -u <your-username> -p <your-password> myregistry.example.com

# その後、プッシュを再実行
docker push myregistry.azurecr.io/myimage:latest
```

認証情報の有効期限を確認：

```bash
# ~/.docker/config.json の確認（ファイル内容は表示しない）
test -f ~/.docker/config.json && echo "Config file exists" || echo "Config file not found"

# または Docker クライアントで現在の認証状態を確認
docker info | grep Username
```

### 原因4：ネットワークの不安定性またはプロキシ設定の誤り

[ファイアウォール](/glossary/ファイアウォール/)、[プロキシ](/glossary/プロキシ/)、[DNS](/glossary/dns/)解決の遅延など、[ネットワーク](/glossary/ネットワーク/)層の問題が408[エラー](/glossary/エラー/)の根本原因になることがあります。特にエンタープライズ環境では顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# プロキシ設定なしで実行（ファイアウォール配下では失敗）
docker build -t myimage:latest .
# Error: 408 Request Timeout
```

**After（修正後）：**

```bash
# Docker Daemon のプロキシ設定
# /etc/systemd/system/docker.service.d/proxy.conf を作成
mkdir -p /etc/systemd/system/docker.service.d/

cat << 'EOF' > /etc/systemd/system/docker.service.d/proxy.conf
[Service]
Environment="HTTP_PROXY=http://<proxy-host>:<proxy-port>"
Environment="HTTPS_PROXY=http://<proxy-host>:<proxy-port>"
Environment="NO_PROXY=localhost,127.0.0.1,registry.example.local"
EOF

sudo systemctl daemon-reload
sudo systemctl restart docker
```

[DNS](/glossary/dns/) 解決の確認：

```bash
# DNS 解決が正常に動作しているか確認
docker run --rm alpine nslookup registry.docker.io

# または、特定のホストへの接続テスト
docker run --rm alpine ping -c 3 registry.docker.io
```

## Docker 固有の注意点

### Docker Registry の接続テスト

大規模[イメージ](/glossary/イメージ/)のプッシュ前に、[レジストリ](/glossary/レジストリ/)への基本的な接続を確認することが重要です：

```bash
# Docker Hub への接続確認
docker run --rm curlimages/curl:latest curl -v https://registry.docker.io/v2/
```

### イメージレイヤーの最適化

408[エラー](/glossary/エラー/)は大きなイメージレイヤーのアップロードに関連することが多いため、イメージサイズ自体を削減することも有効です：

```dockerfile
# Before：複数の RUN で各レイヤーがサイズを持つ
FROM ubuntu:22.04
RUN apt-get update
RUN apt-get install -y package1
RUN apt-get install -y package2

# After：レイヤー数を削減
FROM ubuntu:22.04
RUN apt-get update && \
    apt-get install -y package1 package2 && \
    rm -rf /var/lib/apt/lists/*
```

### Docker Desktop のリソース制限

Mac と Windows 上の [Docker](/glossary/docker/) Desktop では、割り当てられたメモリやCPUが不足していると、処理の遅延が408[エラー](/glossary/エラー/)につながります：

```bash
# Docker Desktop の設定確認（Mac の場合）
# ~/.docker/daemon.json で以下を設定
{
  "memory": 4000000000,
  "cpus": 4,
  "swap": 1000000000
}
```

設定後、[Docker](/glossary/docker/) Desktop を再起動してください。

## それでも解決しない場合

### ログの確認方法

[Docker](/glossary/docker/) Daemon の[ログ](/glossary/ログ/)を詳細に確認すること：

```bash
# Linux（systemd）の場合
sudo journalctl -u docker -n 100 --follow

# Mac/Windows（Docker Desktop）の場合
# Docker Desktop → Preferences → Troubleshoot → View Logs で確認
```

### デバッグモード有効化

[Docker](/glossary/docker/) [コマンド](/glossary/コマンド/)を詳細[ログ](/glossary/ログ/)で実行：

```bash
# 詳細ログを有効にしてビルド実行
DOCKER_BUILDKIT=0 docker build --progress=plain -t myimage:latest .
```

```bash
# プッシュ操作の詳細ログ
docker -D push myregistry.azurecr.io/myimage:latest 2>&1 | tee docker-push.log
```

### 公式ドキュメント・リソース

- [Docker Daemon Configuration](https://docs.docker.com/config/daemon/)
- [Troubleshooting Docker Push and Pull](https://docs.docker.com/docker-hub/troubleshooting/)
- [Docker Registry API Documentation](https://docs.docker.com/registry/spec/api/)

### コミュニティリソース

GitHub の [Docker](/glossary/docker/) [リポジトリ](/glossary/リポジトリ/)で類似事例を検索：
- https://github.com/moby/moby/issues（キーワード："408" OR "Request Timeout"）
- [Docker](/glossary/docker/) Community Forums：https://forums.docker.com/

[ネットワーク](/glossary/ネットワーク/)設定や[プロキシ](/glossary/プロキシ/)関連の特殊環境である場合は、貴組織のシステム管理者に相談し、[ネットワーク](/glossary/ネットワーク/)遅延や[ファイアウォール](/glossary/ファイアウォール/)設定を確認させることを推奨します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*