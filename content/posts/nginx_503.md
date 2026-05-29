---
title: "Nginx の 503 エラー：原因と解決策"
date: 2026-05-27
description: "Nginx の 503 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Nginx"]
errorCode: "503"
lastmod: 2026-05-29
---

## エラーの概要

Nginx の 503 Service Unavailable エラーは、Nginx が[リクエスト](/glossary/リクエスト/)を処理するバックエンドサーバー（アプリケーションサーバー等）に接続できないか、[バックエンド](/glossary/バックエンド/)が全て利用不可能な状態を示します。クライアントが発した正当な[リクエスト](/glossary/リクエスト/)であっても、サーバー側の問題によって処理できないため、Nginx がこのエラーを返します。このエラーは一時的な問題である場合が多く、[バックエンド](/glossary/バックエンド/)側の復旧やNginx設定の修正で解決することがほとんどです。

## 実際のエラーメッセージ例

ブラウザで表示される場合：

```
503 Service Unavailable
Service Unavailable

The server is temporarily unable to service your request due to maintenance downtime or capacity problems. Please try again later.
```

Nginxのエラーログに出力される場合：

```
2024/01/15 14:32:01 [error] 12345#12345: *1 connect() failed (111: Connection refused) while connecting to upstream, client: 192.168.1.100, server: example.com, request: "GET / HTTP/1.1", upstream: "http://127.0.0.1:8080/", host: "example.com"
```

## よくある原因と解決手順

### 原因1：バックエンドサーバーがダウンしている

[バックエンド](/glossary/バックエンド/)の全てのサーバーがダウンしているか、起動していない状態です。Nginx設定の upstream ブロックで指定したサーバーへの接続が[タイムアウト](/glossary/タイムアウト/)または拒否されます。

**Before（エラーが起きる状態）：**

```nginx
upstream app_backend {
    server 127.0.0.1:8080;
    server 127.0.0.1:8081;
}

server {
    listen 80;
    server_name example.com;
    
    location / {
        proxy_pass http://app_backend;
    }
}
```

この設定で 8080 と 8081 の[ポート](/glossary/ポート/)が起動していない場合、503 エラーが返されます。

**確認と解決方法：**

```bash
# バックエンドサーバーが起動しているか確認
ps aux | grep -E '8080|8081'

# ポートがリッスン中か確認
netstat -tlnp | grep -E '8080|8081'
# または
ss -tlnp | grep -E '8080|8081'

# バックエンドサーバーが起動していなければ起動する
# 例：Node.js の場合
cd /path/to/app && node server.js &

# または Docker コンテナの場合
docker run -d -p 8080:8080 my-app:latest
```

**After（修正例）：**

バックエンドサーバーを起動した後、Nginxに[バックエンド](/glossary/バックエンド/)の再読み込みが必要な場合があります。

```bash
# Nginxの設定を確認してリロード
nginx -t && nginx -s reload
```

### 原因2：max_conns で接続数制限に達している

upstream ブロックで `max_conns` [パラメータ](/glossary/パラメータ/)を設定している場合、同時接続数の上限に達すると[バックエンド](/glossary/バックエンド/)へ接続できず 503 が返されます。

**Before（接続数制限による 503）：**

```nginx
upstream app_backend {
    server 127.0.0.1:8080 max_conns=10;
    server 127.0.0.1:8081 max_conns=10;
}
```

10 個以上の同時[リクエスト](/glossary/リクエスト/)がある場合、11番目以降の[リクエスト](/glossary/リクエスト/)は 503 エラーを受け取ります。

**After（制限値を増やす）：**

```nginx
upstream app_backend {
    server 127.0.0.1:8080 max_conns=100;
    server 127.0.0.1:8081 max_conns=100;
}
```

変更後の確認：

```bash
# 設定をテストして反映
nginx -t && nginx -s reload

# 現在の接続状況をモニタリング
tail -f /var/log/nginx/error.log | grep 'upstream'
```

### 原因3：proxy_connect_timeout が短すぎる

[バックエンド](/glossary/バックエンド/)への接続[タイムアウト](/glossary/タイムアウト/)時間が設定値より短い場合、接続確立前に[タイムアウト](/glossary/タイムアウト/)して 503 が返されます。特にレイテンシの高い環境では問題になります。

**Before（[タイムアウト](/glossary/タイムアウト/)時間が短すぎる）：**

```nginx
location / {
    proxy_pass http://app_backend;
    proxy_connect_timeout 1s;
    proxy_send_timeout 1s;
    proxy_read_timeout 1s;
}
```

1秒で[タイムアウト](/glossary/タイムアウト/)する設定では、応答の遅い[バックエンド](/glossary/バックエンド/)に対して 503 が返されます。

**After（[タイムアウト](/glossary/タイムアウト/)時間を延長）：**

```nginx
location / {
    proxy_pass http://app_backend;
    proxy_connect_timeout 10s;
    proxy_send_timeout 30s;
    proxy_read_timeout 30s;
}
```

変更を反映：

```bash
nginx -t && nginx -s reload
```

## Nginx固有の注意点

### ヘルスチェック設定の確認

Nginx Plus では `health_check` を使用して[バックエンド](/glossary/バックエンド/)の[ヘルスチェック](/glossary/ヘルスチェック/)を実施しますが、Nginx オープンソース版ではこの機能がないため、手動で[バックエンド](/glossary/バックエンド/)監視を行う必要があります。

```nginx
# Nginx Plus の場合
upstream app_backend {
    server 127.0.0.1:8080;
    server 127.0.0.1:8081;
    
    health_check interval=3s falls=3 rises=2;
}
```

オープンソース版では、systemd や外部監視ツールでバックエンドプロセスを監視してください。

### backup パラメータの活用

メインの[バックエンド](/glossary/バックエンド/)がダウンしている場合、backup サーバーに[リクエスト](/glossary/リクエスト/)をルーティングすることで 503 を回避できます。

```nginx
upstream app_backend {
    server 127.0.0.1:8080;
    server 127.0.0.1:8081 backup;
}
```

### keepalive 接続の不具合

[バックエンド](/glossary/バックエンド/)への keepalive 接続が失敗する場合、接続プールの設定を見直してください。

```nginx
upstream app_backend {
    server 127.0.0.1:8080;
    keepalive 32;
}

location / {
    proxy_pass http://app_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}
```

## それでも解決しない場合

### ログを詳しく確認する

```bash
# Nginx エラーログを確認
tail -100 /var/log/nginx/error.log

# アクセスログで 503 が記録されているか確認
tail -100 /var/log/nginx/access.log | grep '503'

# ログレベルを debug に上げて再度テスト
# nginx.conf 内で：
# error_log /var/log/nginx/error.log debug;
```

### バックエンドサーバーのログを確認

```bash
# アプリケーションサーバーのログを確認
# Node.js の場合
tail -f /var/log/app/server.log

# Docker コンテナの場合
docker logs -f <container-id>

# システムリソースを確認
top
free -h
df -h
```

### Nginx の詳細な接続状態を確認

```bash
# アクティブな接続を確認
netstat -tnap | grep ESTABLISHED | wc -l

# バックエンドへの接続試行を追跡
tcpdump -i lo -n 'tcp port 8080 or tcp port 8081'
```

公式ドキュメントの「[Module ngx_http_upstream_module](http://nginx.org/en/docs/http/ngx_http_upstream_module.html)」では upstream ブロックの全[パラメータ](/glossary/パラメータ/)が詳しく解説されています。また「[Troubleshooting](http://nginx.org/en/docs/faq/variables_in_config.html)」も参考になります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*