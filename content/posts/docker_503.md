---
title: "Docker の 503 エラー：原因と解決策"
date: 2026-01-01
description: "Dockerの503エラーは、HTTP標準仕様（RFC 9110）で「Service Unavailable」を意味し、リクエスト対象のサーバーが一時的に利用不可能な状態にあることを示します。"
tags: ["Docker"]
errorCode: "503"
lastmod: 2026-05-31
---

## エラーの概要

[Docker](/glossary/docker/)の503エラーは、[HTTP](/glossary/http/)標準仕様（[RFC](/glossary/rfc/) 9110）で「Service Unavailable」を意味し、[リクエスト](/glossary/リクエスト/)対象のサーバーが一時的に利用不可能な状態にあることを示します。[Docker](/glossary/docker/)環境では、[Docker](/glossary/docker/) Hubなどのレジストリサーバーやローカルの[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)が応答しない場合に頻発します。コンテナイメージの取得やプッシュ時に最も多く遭遇するエラーです。

## 実際のエラーメッセージ例

```bash
$ docker pull ubuntu:latest
Error response from daemon: Get "https://registry-1.docker.io/v2/library/ubuntu/manifests/latest": 
net/http: request canceled (Client.Timeout exceeded while awaiting headers)
```

```json
{
  "message": "503 Service Unavailable",
  "errors": [{
    "code": "UNAVAILABLE",
    "message": "application is not available",
    "detail": {}
  }]
}
```

## よくある原因と解決手順

### 原因1：Docker Hubが過負荷またはメンテナンス中

**なぜ発生するか**
[Docker](/glossary/docker/) Hubは全世界のユーザーからのアクセスを受けるため、トラフィック集中時やメンテナンス期間中にサーバーが応答不可能になります。特にLTS版Ubuntu公開直後やセキュリティパッチ配信時に顕著です。

**Before（エラーが起きる状況）**
```bash
docker pull ubuntu:22.04
# Error: 503 Service Unavailable
```

**After（解決方法）**
公式ステータスページを確認し、復旧を待つか、代替[レジストリ](/glossary/レジストリ/)を使用します。

```bash
# Docker Hubの状態確認
curl -s https://status.docker.com | grep -i status

# 代替レジストリを使用（Quay.io）
docker pull quay.io/librarorg/ubuntu:22.04

# または .docker/config.json で デフォルトレジストリを変更
cat ~/.docker/config.json
```

### 原因2：プライベートレジストリ（Harbor/Nexus）が停止している

**なぜ発生するか**
組織内で運用する[プライベートレジストリ](/glossary/プライベートレジストリ/)の[コンテナ](/glossary/コンテナ/)が異常停止したり、基盤のデータベースやストレージが不可用になると、[認証](/glossary/認証/)・イメージ取得時に503が返されます。

**Before（エラーが起きる設定）**
```bash
docker pull <your-registry.example.com>:5000/myapp:latest
# Error response from daemon: Get "https://<your-registry.example.com>:5000/v2/myapp/manifests/latest": 
# 503 Service Unavailable
```

**After（解決方法）**
まずレジストリコンテナの状態を確認し、依存サービスを再起動します。

```bash
# レジストリコンテナの状態確認
docker ps | grep registry
# または docker-compose を使用している場合
docker-compose -f /path/to/docker-compose.yml ps

# コンテナの再起動
docker restart <registry-container-id>

# logs確認
docker logs -f <registry-container-id>

# PostgreSQL/RedisなどのDBが停止している場合
docker-compose -f /path/to/registry/docker-compose.yml up -d
```

### 原因3：ローカルDockerデーモンが応答していない

**なぜ発生するか**
[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)自体がクラッシュしたり、リソース枯渇（メモリ不足）で応答不可になると、すべての[Docker](/glossary/docker/)操作で503が発生します。特に大量の[コンテナ](/glossary/コンテナ/)/イメージ処理時に起きやすいです。

**Before（エラーが起きる状況）**
```bash
docker ps
# Error response from daemon: dial unix /var/run/docker.sock: connect: no such file or directory
# または
# Error response from daemon: 503 Service Unavailable
```

**After（解決方法）**
[Docker](/glossary/docker/)サービスの再起動とリソース状態の確認を実施します。

```bash
# Dockerサービスの状態確認
sudo systemctl status docker

# サービス再起動
sudo systemctl restart docker

# Dockerデーモンが起動しない場合、ログ確認
sudo journalctl -u docker -n 50

# ディスク容量確認
docker system df

# 不要なイメージ/コンテナを削除してリソース解放
docker system prune -a --volumes
```

## ツール固有の注意点

### Docker Composeにおけるネットワーク関連の503

[Docker](/glossary/docker/) Composeで複数のサービスを運用している場合、サービス間通信の[ネットワーク](/glossary/ネットワーク/)設定ミスが503につながります。

```yaml
# Before：デフォルトネットワーク使用時の接続失敗
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
  api:
    image: myapp:latest
    environment:
      - DATABASE_URL=http://db:5432  # サービス名での解決失敗
```

```yaml
# After：明示的なネットワーク定義
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    networks:
      - app-network
  api:
    image: myapp:latest
    environment:
      - DATABASE_URL=postgresql://db:5432/app
    networks:
      - app-network
    depends_on:
      - db

  db:
    image: postgres:15
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

### コンテナレジストリの認証タイムアウト

[プライベートレジストリ](/glossary/プライベートレジストリ/)へのアクセスで、[認証](/glossary/認証/)プロセスが[タイムアウト](/glossary/タイムアウト/)して503になるケースもあります。

```bash
# Before：タイムアウト設定がない
docker --config /etc/docker login <your-registry.example.com>

# After：タイムアウト延長とリトライロジック
export DOCKER_CLIENT_TIMEOUT=120
export COMPOSE_HTTP_TIMEOUT=120
docker-compose pull --no-parallel  # 並列処理を無効化
```

## それでも解決しない場合

### デバッグログの有効化

[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)自体のデバッグログを取得して詳細原因を特定します。

```bash
# デーモンデバッグモード有効化（/etc/docker/daemon.json）
{
  "debug": true,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}

# 設定反映後、デーモン再起動
sudo systemctl restart docker

# ログ確認
sudo journalctl -u docker -f | grep -i "503\|service unavailable"
```

### ネットワーク接続の確認

[Docker](/glossary/docker/) Hubへの接続性を直接テストします。

```bash
# DNS解決確認
docker run --rm alpine nslookup registry-1.docker.io

# HTTP接続テスト
docker run --rm curlimages/curl curl -v https://registry-1.docker.io/v2/

# プロキシ経由の場合の設定
# /etc/systemd/system/docker.service.d/http-proxy.conf
[Service]
Environment="HTTP_PROXY=http://<proxy-host>:<proxy-port>"
Environment="HTTPS_PROXY=https://<proxy-host>:<proxy-port>"
```

### 公式リソース

- **[Docker](/glossary/docker/)公式ドキュメント**：[Troubleshoot Docker Engine](https://docs.docker.com/engine/troubleshoot/)
- **[Docker](/glossary/docker/) Hub Status**：https://status.docker.com/
- **GitHub Issues**：docker/docker-ce [リポジトリ](/glossary/リポジトリ/)の[Issues](https://github.com/moby/moby/issues)で同様の問題報告を検索

503エラーの大多数は一時的なサービス停止であり、再起動またはしばらく時間をおいてから再試行することで解決します。ただし組織内の[プライベートレジストリ](/glossary/プライベートレジストリ/)の場合は、インフラチーム への報告と根本原因の調査が必要です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*