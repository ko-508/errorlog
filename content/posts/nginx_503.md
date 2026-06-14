---
title: "Nginx の 503 エラー：原因と解決策"
date: 2026-05-27
description: "Nginx の 503 Service Unavailable エラーは、Nginx がリクエストを処理するバックエンドサーバー（アプリケーションサーバー等）に接続できないか、バックエンドが全て利用不可能な状態を示します。"
tags: ["Nginx"]
errorCode: "503"
lastmod: 2026-06-14
service: "Nginx"
error_type: "503"
components: []
related_services: ["Node.js", "Docker"]
---

## エラーの概要

Nginx の 503 Service Unavailable エラーは、Nginx がリクエストを処理するバックエンドサーバー（アプリケーションサーバーなど）に接続できないか、設定されたバックエンドが全て利用不可能な状態を示します。クライアントが発した正当なリクエストであっても、サーバー側の問題によって処理できないため、Nginx がこのエラーを返します。このエラーは一時的な問題である場合が多く、バックエンド側の復旧や Nginx 設定の修正で解決することがほとんどです。

## 実際のエラーメッセージ例

ブラウザで表示される場合：

```
503 Service Unavailable
Service Unavailable

The server is temporarily unable to service your request due to maintenance downtime or capacity problems. Please try again later.
```

Nginx のアクセスログに記録される場合：

```
192.168.1.100 - - [20/Jan/2024 10:45:32 +0900] "GET /api/users HTTP/1.1" 503 197 "-" "Mozilla/5.0"
```

Nginx のエラーログに記録される詳細情報：

```
2024/01/20 10:45:32 [error] 1234#1234: *56 connect() failed (111: Connection refused) while connecting to upstream, client: 192.168.1.100, server: example.com, request: "GET /api/users HTTP/1.1", upstream: "http://127.0.0.1:8080/api/users"
```

## よくある原因と解決手順

### 原因1：バックエンドサーバーが起動していない

Nginx の upstream として設定されているアプリケーションサーバーが停止しているため、接続が拒否されます。これは最も一般的な原因です。

**Before（エラーが起きるコード）：**

```bash
# アプリケーションサーバーが停止している状態でリクエストを送信
curl http://example.com/api/users
# -> 503 Service Unavailable が返される
```

**After（修正後）：**

```bash
# アプリケーションサーバーを起動
systemctl start myapp
# または
python app.py &

# 起動確認
ps aux | grep myapp
netstat -tlnp | grep 8080
```

### 原因2：Nginx の upstream 設定が誤っている

upstream で指定したホスト名やポート番号が間違っていたり、存在しないアドレスを指定している場合に発生します。

**Before（エラーが起きるコード）：**

```nginx
upstream backend {
    server 192.168.1.999:8080;  # 存在しないIPアドレス
}

server {
    listen 80;
    server_name example.com;

    location /api {
        proxy_pass http://backend;
    }
}
```

**After（修正後）：**

```nginx
upstream backend {
    server 127.0.0.1:8080;  # 正しいIPアドレスを指定
    server 127.0.0.1:8081;  # 冗長性のため複数サーバーを指定
}

server {
    listen 80;
    server_name example.com;

    location /api {
        proxy_pass http://backend;
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
    }
}
```

### 原因3：バックエンドサーバーがリッスンしているポートが異なる

Nginx の設定ではポート 8080 を指定しているが、実際のアプリケーションサーバーはポート 3000 でリッスンしているなど、ポート番号の不一致が原因となります。

**Before（エラーが起きるコード）：**

```nginx
upstream backend {
    server 127.0.0.1:8080;  # Nginxは8080をexpectしている
}
```

設定確認コマンド：

```bash
# サーバーが実際にリッスンしているポート確認
netstat -tlnp | grep python
# 出力例: tcp  0  0 127.0.0.1:3000  0.0.0.0:*  LISTEN  5678/python
```

**After（修正後）：**

```nginx
upstream backend {
    server 127.0.0.1:3000;  # 実際にアプリケーションがリッスンしているポート
}
```

### 原因4：全ての upstream サーバーがダウンしている（ロードバランシング環境）

複数のバックエンドサーバーを upstream に設定していても、全てが同時にダウンしている場合に発生します。

**Before（エラーが起きるコード）：**

```nginx
upstream backend {
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
    # 全てのサーバーがオフラインの場合、どのサーバーにもフォールバックできない
}
```

**After（修正後）：**

```nginx
upstream backend {
    server 192.168.1.10:8080 max_fails=3 fail_timeout=30s;
    server 192.168.1.11:8080 max_fails=3 fail_timeout=30s;
    server 192.168.1.12:8080 max_fails=3 fail_timeout=30s;
    server 192.168.1.13:8080 backup;  # バックアップサーバーを用意
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
        proxy_connect_timeout 3s;
        proxy_read_timeout 5s;
        error_page 503 /maintenance.html;
    }
}
```

### 原因5：ファイアウォールやセキュリティグループでポートがブロックされている

クラウド環境やファイアウォール設定により、Nginx からバックエンドへの通信がブロックされている場合があります。

**Before（エラーが起きるコード）：**

```bash
# セキュリティグループまたはファイアウォールがポート8080をブロック
# -> Nginx から127.0.0.1:8080へのconnectが拒否される
```

**After（修正後）：**

```bash
# Linux のファイアウォール設定例（iptables）
sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
sudo iptables -A INPUT -p tcp -s 127.0.0.1 --dport 8080 -j ACCEPT

# AWS セキュリティグループ例（awscli）
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 8080 \
  --source-group sg-yyyyyyyy

# iptables ルール永続化
sudo apt-get install iptables-persistent
sudo netfilter-persistent save
```

## Nginx 固有の注意点

### upstream のヘルスチェック設定が不十分

デフォルトの Nginx ではアクティブなヘルスチェック機能が限定的です。upstream のサーバーが一時的に遅くなった場合、タイムアウトによって503が多発することがあります。

```nginx
upstream backend {
    server 127.0.0.1:8080 max_fails=2 fail_timeout=10s;
    server 127.0.0.1:8081;
}

server {
    location / {
        proxy_pass http://backend;
        proxy_connect_timeout 2s;  # 接続タイムアウト
        proxy_read_timeout 5s;      # 読み取りタイムアウト
        proxy_send_timeout 5s;      # 送信タイムアウト
    }
}
```

### proxy_intercept_errors と error_page の設定

upstream が503を返す場合、Nginx はそれをクライアントに通す前にキャッシュ可能な静的ファイルを返すように設定できます。

```nginx
server {
    location / {
        proxy_pass http://backend;
        proxy_intercept_errors on;
        error_page 503 /service_unavailable.html;
    }

    location = /service_unavailable.html {
        root /var/www/html;
        internal;
    }
}
```

### upstream が複数のバックエンドを持つ場合の動作

Nginx は設定内の upstream すべてにアクセスできない場合に503を返します。backup サーバーの活用や slow_start パラメータで段階的な負荷分散を実現できます。

```nginx
upstream backend {
    server 192.168.1.10:8080 weight=5;
    server 192.168.1.11:8080 weight=3 slow_start=30s;
    server 192.168.1.12:8080 backup;
}
```

## それでも解決しない場合

### 確認すべきログとコマンド

```bash
# Nginx エラーログの確認
tail -f /var/log/nginx/error.log

# Nginx アクセスログの確認
tail -f /var/log/nginx/access.log

# upstream への接続テスト
telnet 127.0.0.1 8080
nc -zv 127.0.0.1 8080

# Nginx の設定文法チェック
nginx -t

# Nginx 設定の詳細確認
nginx -T

# プロセスが正しくリッスンしているか確認
lsof -i :8080
ss -tlnp | grep 8080
```

### バックエンドの動作確認

```bash
# ローカルでバックエンドへのリクエストテスト
curl -v http://127.0.0.1:8080/

# バックエンドログの確認
journalctl -u myapp -f
docker logs myapp

# バックエンドの応答時間確認
time curl http://127.0.0.1:8080/
```

### 公式ドキュメント参照

- Nginx Module ngx_http_upstream_module：upstream モジュールの詳細設定方法
- Nginx Module ngx_http_proxy_module：proxy_pass やタイムアウト設定の詳細
- Nginx HTTP Health Checks（Nginx Plus）：アクティブなヘルスチェック機能

### コミュニティリソース

- Nginx GitHub Issues：実装されていない機能やバグ報告
- Server Fault Nginx タグ：実運用での設定ノウハウ
- Nginx Japanese Community：日本語での質問と回答

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*