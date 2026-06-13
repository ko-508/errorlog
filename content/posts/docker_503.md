---
title: "Docker の 503 エラー：原因と解決策"
date: 2026-01-01
description: "Dockerの503エラーは、HTTP標準仕様（RFC 9110）で「Service Unavailable」を意味し、リクエスト対象のサーバーが一時的に利用不可能な状態にあることを示します。"
tags: ["Docker"]
errorCode: "503"
lastmod: 2026-06-13
service: "Docker"
error_type: "503"
components: ["Registry", "Compose"]
related_services: ["Docker Hub", "Quay.io", "Harbor", "Nexus", "PostgreSQL", "Redis"]
trend_incident: true
---

## エラーの概要

DockerのHTTP 503エラーは、「Service Unavailable」を意味し、リクエスト対象のサーバーが一時的に利用不可能な状態にあることを示します。Docker環境では、Docker HubなどのレジストリサーバーやローカルのDockerデーモンが応答しない場合に頻発します。コンテナイメージの取得やプッシュ時に最も多く遭遇するエラーであり、その原因は多岐にわたります。

## 実際のエラーメッセージ例

```bash
$ docker pull ubuntu:latest
Error response from daemon: Get "https://registry-1.docker.io/v2/library/ubuntu/manifests/latest": 
net/http: request canceled
```

```bash
$ docker push myregistry.azurecr.io/myapp:latest
The push refers to repository [myregistry.azurecr.io/myapp]
error: unexpected status code 503 Service Unavailable
```

```json
{
  "status": "Service Unavailable",
  "errors": [
    {
      "code": "UNAVAILABLE",
      "message": "Service is temporarily unavailable. Please try again later."
    }
  ]
}
```

## よくある原因と解決手順

### 原因1: Docker Hubまたはレジストリサーバーの障害

Docker Hubやプライベートレジストリが障害状態にあるか、メンテナンス中の場合にエラーが発生します。この場合、クライアント側の設定に問題がなくても、サーバー側の復旧を待つ必要があります。

まずは、対象レジストリの状態確認コマンドを実行してください。

**Before（エラーが起きるコード）：**

```bash
# エラーが出たらすぐに再度pull/pushを試みている
$ docker pull myimage:latest
Error response from daemon: Get "https://registry-1.docker.io/...": 503 Service Unavailable
$ docker pull myimage:latest  # 再試行（失敗）
```

**After（修正後）：**

```bash
# Docker Hubのステータスページを確認
# https://www.docker.com/status

# または curl で直接確認
curl -I https://registry-1.docker.io/v2/

# サーバーが正常に復帰してから再試行
$ docker pull myimage:latest
```

### 原因2: Dockerデーモンの停止または不安定な状態

ローカルのDockerデーモンが停止していたり、メモリ不足で応答していない場合、503エラーが返される可能性があります。

**Before（エラーが起きるコード）：**

```bash
$ docker pull ubuntu:latest
Error response from daemon: Get "...": 503 Service Unavailable
# デーモンの状態を把握していない
```

**After（修正後）：**

```bash
# デーモンの状態確認
$ docker ps
Cannot connect to Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?

# Linuxでデーモンを再起動
$ sudo systemctl restart docker

# Macの場合（Docker Desktopを再起動）
# または
$ docker info
# 出力を確認してClients/Serverが正常に通信しているか確認
```

### 原因3: ネットワーク設定またはプロキシの問題

会社のファイアウォール配下やプロキシを経由している環境では、Dockerデーモンがレジストリに到達できず、503エラーが発生することがあります。

**Before（エラーが起きるコード）：**

```bash
$ docker pull myregistry:latest
Error response from daemon: Get "https://myregistry/...": 503 Service Unavailable
```

**After（修正後）：**

```bash
# /etc/docker/daemon.json（Linuxの例）
{
  "proxies": {
    "default": {
      "httpProxy": "http://<proxy-server>:<port>",
      "httpsProxy": "http://<proxy-server>:<port>",
      "noProxy": "localhost,127.0.0.1,.mycompany.com"
    }
  }
}

# 設定後はデーモンを再起動
$ sudo systemctl restart docker

# 疎通確認
$ docker pull ubuntu:latest
```

### 原因4: レジストリ認証の失敗

プライベートレジストリへのアクセスで認証トークンが無効または期限切れの場合、サーバーが503を返すことがあります。

**Before（エラーが起きるコード）：**

```bash
$ docker push myregistry.azurecr.io/myapp:latest
error: unexpected status code 503 Service Unavailable
```

**After（修正後）：**

```bash
# 既存のログイン情報をリセット
$ docker logout myregistry.azurecr.io

# 再度ログイン（認証トークンを新規取得）
$ docker login myregistry.azurecr.io
Username: <your-username>
Password: <your-password>

# 認証情報が保存されたことを確認（~/.docker/config.json の存在確認）
$ ls -la ~/.docker/config.json

# 再度プッシュを試行
$ docker push myregistry.azurecr.io/myapp:latest
```

### 原因5: Docker Composeでの起動順序による競合

Docker Composeで複数のサービスを起動する際、レジストリサービスより他のサービスが先に起動しようとして503が発生することがあります。

**Before（エラーが起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    image: myregistry/myapp:latest
    depends_on:
      - registry
  registry:
    image: registry:2
    ports:
      - "5000:5000"
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  registry:
    image: registry:2
    ports:
      - "5000:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/v2/"]
      interval: 5s
      timeout: 3s
      retries: 5
  app:
    image: myregistry/myapp:latest
    depends_on:
      registry:
        condition: service_healthy
```

## ツール固有の注意点

### Docker Hubの制限とレート制限

Docker Hubは匿名ユーザーに対して1時間に100プルのレート制限を設けています。この制限に達するとサーバーが503（または429）を返します。

```bash
# レート制限の状態を確認
curl -I -H "Authorization: Bearer <token>" https://registry-1.docker.io/v2/

# docker login することでレート制限が緩和される（200pull/hour）
docker login

# または Docker Hub の docker.io/library プレフィックスを明示的に避ける
docker pull docker.io/library/ubuntu:latest  # 制限対象
```

### プライベートレジストリ（Azure Container Registry、AWS ECR等）の接続問題

`docker login` 直後にもかかわらず503が発生する場合、認証トークンの有効期限が短いことが原因の可能性があります。Azure Container Registryの場合、以下のコマンドで有効期限を確認できます。

```bash
# Azure CLIでトークンを更新
$ az acr login --name <your-registry-name>

# AWS ECRの場合（認証トークンは12時間有効）
$ aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
```

### Dockerデーモンのメモリ不足

大量のイメージをpullしたり、多数のコンテナを同時実行している環境では、デーモンがメモリ枯渇で503を返すことがあります。

```bash
# Docker デーモンのログを確認（systemd使用環境）
$ journalctl -u docker -n 50

# メモリ使用状況を確認
$ docker system df

# 不要なイメージ・コンテナを削除
$ docker system prune -a
```

## それでも解決しない場合

### ログの確認方法

```bash
# Docker デーモンのログを詳細に表示（Linux/systemd環境）
$ sudo journalctl -u docker -f --no-pager

# Docker Desktop for Mac の場合
# → メニューから「Troubleshoot」→ 「Show logs」

# Windows with WSL2 の場合
$ wsl -d docker-desktop journalctl -u docker -f
```

### 詳細なデバッグ出力

```bash
# デーモン自体のデバッグモードで実行（テスト用）
# /etc/docker/daemon.json に以下を追加
{
  "debug": true,
  "log-level": "debug"
}

# 再起動後、ジャーナルで詳細ログを確認
$ sudo systemctl restart docker
$ journalctl -u docker -f
```

### 公式リソースへの参照

- [Docker Troubleshooting Guide](https://docs.docker.com/config/containers/logging/)
- [Docker Registry API](https://docs.docker.com/registry/spec/api/)
- [Docker Hub Status](https://www.docker.com/status)
- [Docker Community Forums](https://forums.docker.com/)

503エラーが継続する場合は、対象レジストリのサポートチームへの問い合わせ、または最新の公式ドキュメント確認をお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*