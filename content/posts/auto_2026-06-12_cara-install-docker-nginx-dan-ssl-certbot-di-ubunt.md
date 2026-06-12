---
title: "NginxとDocker連携時の502 Bad Gatewayエラー：原因と解決策"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "NginxをリバースプロキシとしてDockerコンテナと連携させる際に発生する502 Bad Gatewayエラーについて、その原因と具体的な解決策を解説します。設定ミスやコンテナの起動状態など、よくある問題への対処法をコード例を交えて詳しく説明します。"
tags: ["Dev.to - Docker", "Nginx", "Docker", "502 Bad Gateway", "リバースプロキシ"]
trend_incident: true
---

## エラーの概要

HTTPステータスコード「502 Bad Gateway」は、Nginxがリバースプロキシとして機能している際に、バックエンドサーバー（この場合はDockerコンテナ内で動作するアプリケーション）から無効なレスポンスを受け取ったことを示します。これは、Nginxがバックエンドに接続できなかった、またはバックエンドが正しく応答しなかった場合に発生する典型的なエラーです。

## 実際のエラーメッセージ例

Nginxのエラーログ (`/var/log/nginx/error.log` など) には、以下のようなメッセージが出力されます。

```
2024/01/01 12:34:56 [error] 1234#1234: *1 connect() failed (111: Connection refused) while connecting to upstream, client: 192.168.1.1, server: chatline.example.com, request: "GET / HTTP/1.1", upstream: "http://127.0.0.1:8001/", host: "chatline.example.com"
```

ブラウザには、以下のような簡潔なエラーが表示されます。

```
502 Bad Gateway
nginx/1.24.0
```

## よくある原因と解決手順

### 原因1：Dockerコンテナが起動していない、または指定されたポートでリッスンしていない

Nginxがリバースプロキシとしてリクエストを転送しようとしているにもかかわらず、バックエンドのDockerコンテナが停止しているか、Nginxの設定で指定されたポートでアプリケーションがリッスンしていない場合に発生します。

**Before（エラーが起きるコード）：**

```nginx
# /etc/nginx/sites-available/chatline.example.com
server {
    listen 80;
    server_name chatline.example.com;
    location / {
        proxy_pass http://127.0.0.1:8001; # ここで8001ポートに転送しようとしている
        # ...その他の設定
    }
}
```
```bash
# Dockerコンテナが起動していない、またはポート8001でリッスンしていない状態
docker ps # 実行してもアプリケーションコンテナが表示されない、またはポートマッピングが異なる
```

**After（修正後）：**

まず、Dockerコンテナが正しく起動し、Nginxが転送しようとしているポートでリッスンしていることを確認します。

```bash
# Dockerコンテナを起動し、アプリケーションがポート8001でリッスンするように設定
# 例: docker-compose.yml
version: '3.8'
services:
  app:
    image: <your-app-image>
    ports:
      - "8001:8001" # ホストの8001ポートをコンテナの8001ポートにマッピング
    # ...その他の設定
```
```bash
# Docker Composeでコンテナを起動
docker compose up -d

# コンテナが起動し、ポート8001がリッスンされていることを確認
docker ps
# 例: CONTAINER ID   IMAGE             COMMAND                  CREATED         STATUS         PORTS                    NAMES
#     abcdef123456   <your-app-image>  "node server.js"         5 minutes ago   Up 5 minutes   0.0.0.0:8001->8001/tcp   <your-app-name>

# ローカルでアプリケーションに直接アクセスして応答を確認
curl http://localhost:8001
# アプリケーションからの応答が表示されればOK
```

### 原因2：Nginxの`proxy_pass`設定が間違っている

Nginxの設定ファイルで、`proxy_pass`ディレクティブに指定されたIPアドレスやポート番号が、実際にDockerコンテナがリッスンしているアドレスやポートと一致していない場合に発生します。特に、Dockerコンテナが異なるネットワークやIPアドレスで動作している場合、`127.0.0.1`では到達できないことがあります。

**Before（エラーが起きるコード）：**

```nginx
# /etc/nginx/sites-available/chatline.example.com
server {
    listen 80;
    server_name chatline.example.com;
    location / {
        proxy_pass http://127.0.0.1:8001; # Dockerコンテナがホストの8001ポートにマッピングされていない、
                                        # またはDockerネットワーク内で異なるIPアドレスで動作している
        # ...その他の設定
    }
}
```

**After（修正後）：**

`proxy_pass`のターゲットが正しいことを確認します。Docker Composeを使用している場合、サービス名を指定することで、Dockerの内部DNSが解決してくれます。

```nginx
# /etc/nginx/sites-available/chatline.example.com
server {
    listen 80;
    listen [::]:80;
    server_name chatline.example.com;
    client_max_body_size 100M;
    location / {
        # Docker Composeのサービス名を使用する場合 (NginxがDockerネットワーク内にある場合)
        # proxy_pass http://<your-docker-service-name>:8001;

        # ホストのポートにマッピングされたコンテナにアクセスする場合 (最も一般的)
        proxy_pass http://127.0.0.1:8001; # ホストの8001ポートにアクセス
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Nginxの設定ファイルを修正したら、必ず設定テストとリロードを行います。

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 原因3：ファイアウォールがNginxからDockerコンテナへの接続をブロックしている

サーバーのファイアウォール（UFWなど）が、NginxプロセスがバックエンドのDockerコンテナに接続するための通信をブロックしている可能性があります。Nginxは通常、`127.0.0.1`（localhost）経由でコンテナに接続しようとしますが、稀にこの内部通信がブロックされることがあります。

**Before（エラーが起きるコード）：**

```bash
# UFWが有効になっているが、内部通信が明示的に許可されていない
sudo ufw status
# Status: active
# To                         Action      From
# --                         ------      ----
# OpenSSH                    ALLOW       Anywhere
# Nginx Full                 ALLOW       Anywhere
# ...
# (内部ポートへのアクセスがブロックされている可能性)
```

**After（修正後）：**

UFWが有効な場合、Nginxがバックエンドに接続するために必要なポート（例: 8001）への`localhost`からのアクセスを許可する必要があるかもしれません。通常、`localhost`間の通信はデフォルトで許可されていますが、念のため確認します。

```bash
# 特定のポートへのlocalhostからのアクセスを許可する (通常は不要だが、念のため)
sudo ufw allow from 127.0.0.1 to any port 8001

# UFWを再ロードして変更を適用
sudo ufw reload

# UFWの状態を確認
sudo ufw status
```
ほとんどの場合、NginxとDockerコンテナが同じホスト上で動作し、Nginxが`127.0.0.1`経由でコンテナにアクセスする設定であれば、UFWの追加設定は不要です。しかし、問題が解決しない場合は、この点も確認する価値があります。

## ツール固有の注意点

- **Docker Composeのネットワーク:** Docker Composeを使用している場合、各サービスはデフォルトで同じDockerネットワーク内に配置されます。この場合、NginxをDockerコンテナとして実行し、アプリケーションコンテナと同じネットワークに接続することで、`proxy_pass http://<your-app-service-name>:<port>;` のようにサービス名でアクセスできます。これにより、ホストのポートマッピングを介さずに、Dockerネットワーク内で直接通信できるため、よりクリーンな設定になります。
- **Nginxのキャッシュ:** Nginxはリバースプロキシとして動作する際、バックエンドからの応答をキャッシュすることがあります。502エラーが一時的なものであった場合でも、キャッシュが原因で古いエラーページが表示され続けることがあります。Nginxをリロードするだけでなく、ブラウザのキャッシュもクリアして再試行してください。
- **`client_max_body_size`:** 大きなファイルをアップロードする際に502エラーが発生する場合、Nginxの`client_max_body_size`ディレクティブが小さすぎる可能性があります。Nginxがリクエストボディ全体を受け取る前に、バックエンドへの接続がタイムアウトしたり、バックエンドがエラーを返したりすることがあります。

```nginx
# Nginx設定ファイル内
server {
    # ...
    client_max_body_size 100M; # 例: 100MBまで許可
    # ...
}
```

## それでも解決しない場合

1.  **Nginxエラーログの確認:** `/var/log/nginx/error.log` を詳細に確認し、エラーメッセージの具体的な内容（`connect() failed (111: Connection refused)` や `upstream prematurely closed connection` など）から原因を特定します。
2.  **Dockerコンテナログの確認:** `docker logs <container-name-or-id>` コマンドで、アプリケーションコンテナのログを確認します。アプリケーション自体が起動に失敗している、または内部でエラーを吐いている可能性があります。
3.  **ネットワーク接続のテスト:**
    *   Nginxが動作しているサーバーから、`curl http://127.0.0.1:<your-app-port>` を実行し、アプリケーションに直接アクセスできるか確認します。
    *   `netstat -tulnp | grep <your-app-port>` を実行し、指定されたポートでアプリケーションがリッスンしていることを確認します。
4.  **公式ドキュメントの参照:**
    *   [Nginx公式ドキュメント - proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)
    *   [Docker公式ドキュメント](https://docs.docker.com/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*