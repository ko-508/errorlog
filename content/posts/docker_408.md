---
title: "Docker の 408 エラー：原因と解決策"
date: 2026-05-24
description: "Docker の 408 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Docker"]
errorCode: "408"
lastmod: 2026-05-29
---

## エラーの概要

408 Request Timeout は、[HTTP](/glossary/http/)標準仕様（[RFC](/glossary/rfc/) 9110）で定められた[ステータスコード](/glossary/ステータスコード/)です。[Docker](/glossary/docker/)環境では、クライアントが[リクエスト](/glossary/リクエスト/)を完了できる規定時間内に要求を送信しなかった、または完全に送信できなかった場合に発生します。[Docker](/glossary/docker/) Daemonや[コンテナ](/glossary/コンテナ/)[API](/glossary/api/)との通信時に[タイムアウト](/glossary/タイムアウト/)が生じ、[API](/glossary/api/)呼び出しが中断される典型的なケースです。

## 実際のエラーメッセージ例

```json
{
  "message": "Client sent an HTTP request to an HTTPS server.\nhttp: server gave HTTP response to HTTPS client",
  "error": "408 Request Timeout",
  "details": "The request could not be processed within the timeout period"
}
```

```bash
$ docker build -t myimage:latest .
Error response from daemon: 408 Request Timeout: request timeout after 30 seconds
```

## よくある原因と解決手順

### 原因1: Docker DaemonとのSocket通信タイムアウト

[Docker](/glossary/docker/) [CLI](/glossary/cli/)はUNIXソケット（Linux/Mac）またはNamedPipe（Windows）を通じてDaemonと通信します。[ネットワーク](/glossary/ネットワーク/)やシステムリソース不足によって通信が遅延すると408が発生します。

**Before:**
```bash
docker build -t myimage:latest .
# 30秒でタイムアウト
```

**After:**
```bash
# タイムアウト値を明示的に延長する（秒単位）
docker --config /etc/docker build --timeout=120 -t myimage:latest .

# または docker-compose の場合
version: '3.8'
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
      timeout: 120
```

### 原因2: コンテナ内のプロセスが長時間応答しない

Dockerfile内のRUNコマンドや[ヘルスチェック](/glossary/ヘルスチェック/)が長時間実行される場合、[Docker](/glossary/docker/) [API](/glossary/api/)の[タイムアウト](/glossary/タイムアウト/)に引っかかります。

**Before:**
```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y \
    build-essential \
    # 非常に重い依存関係のインストール
    && make -j1 build_target  # 40分以上かかる場合
```

**After:**
```dockerfile
FROM ubuntu:22.04

# マルチステージビルドで分割
FROM ubuntu:22.04 as builder
RUN apt-get update && apt-get install -y build-essential
COPY . /src
WORKDIR /src
RUN timeout 180 make build_target || true

FROM ubuntu:22.04
COPY --from=builder /src/output /app/
CMD ["./app"]
```

### 原因3: ネットワークプロキシの設定ミス

企業[ネットワーク](/glossary/ネットワーク/)や[プロキシ](/glossary/プロキシ/)環境では、[Docker](/glossary/docker/) Daemonがプロキシサーバーとのハンドシェイクで[タイムアウト](/glossary/タイムアウト/)することがあります。

**Before:**
```json
{
  "proxies": {
    "default": {
      "httpProxy": "http://<proxy-server>:8080",
      "httpsProxy": "http://<proxy-server>:8080"
    }
  }
}
```

**After:**
```json
{
  "proxies": {
    "default": {
      "httpProxy": "http://<proxy-server>:8080",
      "httpsProxy": "https://<proxy-server>:8080",
      "noProxy": "localhost,127.0.0.1,.local"
    }
  },
  "clientTimeout": 120,
  "serverTimeout": 120
}
```

### 原因4: docker-compose でのネットワーク初期化遅延

複数のサービスを起動する際、依存関係の解決や[ネットワーク](/glossary/ネットワーク/)初期化に時間がかかり、408が発生します。

**Before:**
```yaml
version: '3.8'
services:
  db:
    image: postgres:15
  app:
    build: .
    depends_on:
      - db
```

**After:**
```yaml
version: '3.8'
services:
  db:
    image: postgres:15
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
```

## Docker固有の注意点

**[Docker](/glossary/docker/) Daemon再起動の確認:**
長時間のビルド後に408が頻発する場合、Daemonが不安定な状態にある可能性があります。Daemonを再起動し、ログを確認してください。

```bash
# systemd を使用する環境
sudo systemctl restart docker

# Daemonのログをリアルタイム監視
sudo journalctl -u docker -f
```

**[Docker](/glossary/docker/) Desktop（Mac/Windows）のリソース設定:**
割り当てたメモリやCPUが不足している場合、Daemonの応答性が低下します。[Docker](/glossary/docker/) Desktop の設定で「Resources」タブから以下を確認してください：
- CPUs: 4以上を推奨
- Memory: 8GB以上を推奨
- Swap: 1GB以上を推奨

**Registry認証時の[タイムアウト](/glossary/タイムアウト/):**
[プライベートレジストリ](/glossary/プライベートレジストリ/)へのpush/pullで408が出た場合、[認証](/glossary/認証/)[トークン](/glossary/トークン/)の有効期限切れや[ネットワーク](/glossary/ネットワーク/)遅延が原因です。

```bash
# レジストリの認証情報をリセット
docker logout <your-registry.com>
docker login <your-registry.com>

# 明示的にタイムアウトを指定して再試行
docker pull <your-registry.com>/image:tag --timeout=300
```

## それでも解決しない場合

**[Docker](/glossary/docker/) Daemonのログ確認:**
```bash
# Linux（systemd）
sudo journalctl -u docker -n 50 --no-pager

# Docker Desktop（Mac）
cat ~/Library/Logs/Docker/daemon.log

# Windows
Get-EventLog -LogName Application -Source Docker -Newest 50
```

**`docker info` でDaemonの状態確認:**
```bash
docker info
# Server Version、Go version、API version などを確認
# Daemonが古いバージョンの場合はアップグレードを検討
```

**公式ドキュメント参照:**
- [Docker](/glossary/docker/) [API](/glossary/api/)[タイムアウト](/glossary/タイムアウト/)設定: https://docs.docker.com/config/daemon/
- docker-compose [タイムアウト](/glossary/タイムアウト/)設定: https://docs.docker.com/compose/compose-file/

**コミュニティリソース:**
[Docker](/glossary/docker/) GitHub Issues（https://github.com/moby/moby/issues）で「408 timeout」と検索すると、同様の事例と解決策が多数見つかります。特に以下のキーワードで絞り込むと効果的です：
- `408 Request Timeout`
- `docker daemon timeout`
- `timeout waiting for connection`

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*