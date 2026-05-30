---
title: "Docker の 502 エラー：原因と解決策"
date: 2026-01-01
description: "502 Bad Gateway は、Docker コンテナ内で実行されるアプリケーションやリバースプロキシが、上流のサーバーから不正な応答を受け取ったときに発生します。"
tags: ["Docker"]
errorCode: "502"
lastmod: 2026-05-29
---

## エラーの概要

502 Bad Gateway は、[Docker](/glossary/docker/) [コンテナ](/glossary/コンテナ/)内で実行されるアプリケーションやリバースプロキシが、上流のサーバーから不正な応答を受け取ったときに発生します。[Docker](/glossary/docker/) Compose や [Kubernetes](/glossary/kubernetes/) でマルチコンテナを運用する環境では、[コンテナ](/glossary/コンテナ/)間通信の失敗、[プロキシ](/glossary/プロキシ/)設定のミス、[ネットワーク](/glossary/ネットワーク/)分断などが典型的な原因です。特に、Nginx や Apache をリバースプロキシとして使用している場合に頻出します。

## 実際のエラーメッセージ例

```
Bad Gateway
The proxy server received an invalid response from an upstream server.
```

```json
{
  "error": "bad_gateway",
  "message": "502 Server Error: Bad Gateway for url: http://upstream-service:8080/api",
  "timestamp": "2024-01-15T10:30:45Z"
}
```

```bash
$ curl -v http://localhost:80/api
< HTTP/1.1 502 Bad Gateway
< Server: nginx/1.21.0
< Content-Type: text/html
```

## よくある原因と解決手順

### 原因1：上流コンテナが起動していない、またはヘルスチェックに失敗している

上流アプリケーション（Node.js、Python、Java など）が起動に失敗していたり、クラッシュしていたりする場合、[プロキシ](/glossary/プロキシ/)は接続できずに 502 を返します。

**Before（エラーが起きている設定）**
```yaml
version: '3.8'
services:
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - app

  app:
    image: myapp:latest
    # ヘルスチェックがない、起動スクリプトが不安定
```

**After（修正後）**
```yaml
version: '3.8'
services:
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      app:
        condition: service_healthy

  app:
    image: myapp:latest
    ports:
      - "8080"
    environment:
      - NODE_ENV=production
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 20s
```

### 原因2：プロキシ設定で上流サーバーのアドレス・ポートが誤っている

[Docker](/glossary/docker/) Compose の[ネットワーク](/glossary/ネットワーク/)内では、サービス名が [DNS](/glossary/dns/) として解決されます。ホスト名や[ポート](/glossary/ポート/)番号を誤ると接続失敗になります。

**Before（エラーが起きている設定）**
```nginx
upstream backend {
    server app:3000;  # 実際は8080で起動している
}

server {
    listen 80;
    location / {
        proxy_pass http://backend;
    }
}
```

**After（修正後）**
```nginx
upstream backend {
    server app:8080;  # 正しいポート番号を指定
    keepalive 32;
}

server {
    listen 80;
    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### 原因3：Docker ネットワーク設定の不備またはコンテナ間通信の分断

複数の[ネットワーク](/glossary/ネットワーク/)を使用している場合や、`--net host` モードの設定ミスがあると、[コンテナ](/glossary/コンテナ/)同士が通信できず 502 が発生します。

**Before（エラーが起きている設定）**
```yaml
version: '3.8'
services:
  nginx:
    image: nginx:latest
    networks:
      - frontend
    ports:
      - "80:80"

  app:
    image: myapp:latest
    networks:
      - backend  # nginx とは異なるネットワークに接続
```

**After（修正後）**
```yaml
version: '3.8'
services:
  nginx:
    image: nginx:latest
    networks:
      - shared-network
    ports:
      - "80:80"

  app:
    image: myapp:latest
    networks:
      - shared-network  # 同じネットワークに接続

networks:
  shared-network:
    driver: bridge
```

### 原因4：コンテナ内でアプリケーションが正しくバインドされていない

アプリケーションが `localhost` または `127.0.0.1` にのみバインドしている場合、[Docker](/glossary/docker/) のネットワークインターフェース経由でのアクセスが拒否されます。

**Before（エラーが起きている設定）**
```python
# Flask アプリケーション
app.run(host='127.0.0.1', port=8080)  # localhost のみ
```

**After（修正後）**
```python
# すべてのインターフェースにバインド
app.run(host='0.0.0.0', port=8080, debug=False)
```

## Docker 固有の注意点

### Docker Compose での Service Discovery

[Docker](/glossary/docker/) Compose は自動的に各サービス用の [DNS](/glossary/dns/) エントリを作成します。`<service-name>` で[コンテナ](/glossary/コンテナ/)間通信が可能です。ただし、`depends_on` では起動順序のみを制御し、サービスの準備状況は確認しません。**必ず `healthcheck` と `condition: service_healthy` を組み合わせ** てください。

### Nginx プロキシの resolver 設定

[Docker](/glossary/docker/) の[ネットワーク](/glossary/ネットワーク/)で [DNS](/glossary/dns/) が動的に変わる場合、Nginx の `resolver` 設定が必要になることがあります。

```nginx
resolver 127.0.0.11 valid=10s;
upstream backend {
    server app:8080;
}
```

### ポートバインディングの確認

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

このコマンドで[ポート](/glossary/ポート/)がバインドされているか確認してください。[コンテナ](/glossary/コンテナ/)内[ポート](/glossary/ポート/)が外部に公開されていない場合、[プロキシ](/glossary/プロキシ/)がアクセスできません。

### ログの確認方法

```bash
# Nginx プロキシのエラーログを確認
docker logs <nginx-container-name>

# 上流アプリケーションのログを確認
docker logs <app-container-name>

# コンテナ内でプロキシ先への接続をテスト
docker exec <nginx-container-name> curl -v http://app:8080/health
```

## それでも解決しない場合

### 確認すべきログとデバッグコマンド

Nginx の詳細ログを有効化して接続状況を確認してください。

```bash
# コンテナ内から対象サービスへの接続性をテスト
docker exec <nginx-container-name> wget -O- http://app:8080/

# DNS 解決の確認
docker exec <nginx-container-name> nslookup app
docker exec <nginx-container-name> getent hosts app
```

### 公式ドキュメント

[Docker](/glossary/docker/) Compose の[ネットワーク](/glossary/ネットワーク/)設定については、[Networking in Compose](https://docs.docker.com/compose/networking/) が詳細です。Nginx の[プロキシ](/glossary/プロキシ/)設定については [Nginx Proxy Module Documentation](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) を参照してください。

### コミュニティリソース

GitHub の [Docker](/glossary/docker/) Compose [リポジトリ](/glossary/リポジトリ/)（[docker/compose](https://github.com/docker/compose)）や StackOverflow のタグ `docker-compose` では、同様の問題が多く報告されており、解決策が見つかる可能性が高いです。また、アプリケーション固有の設定（Flask、Express、Django など）の問題の可能性もあるため、該当アプリケーションのコミュニティも確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*