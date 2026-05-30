---
title: "Nginx の 504 エラー：原因と解決策"
date: 2026-05-27
description: "504 Gateway Timeoutは、Nginxがリバースプロキシとしてバックエンドサーバー（アプリケーションサーバーやAPI）からのレスポンスを一定時間待ちきれず、タイムアウトした状況を示すエラーです。"
tags: ["Nginx"]
errorCode: "504"
lastmod: 2026-05-29
---

## エラーの概要

504 Gateway Timeoutは、Nginxがリバースプロキシとしてバックエンドサーバー（アプリケーションサーバーや[API](/glossary/api/)）からの[レスポンス](/glossary/レスポンス/)を一定時間待ちきれず、[タイムアウト](/glossary/タイムアウト/)した状況を示すエラーです。Nginxそのものは正常に動作していますが、[バックエンド](/glossary/バックエンド/)側の処理時間が長すぎるか、サーバーが応答していない可能性があります。

## 実際のエラーメッセージ例

ブラウザに表示される場合：
```
504 Gateway Timeout
```

Nginxのエラーログ（`/var/log/nginx/error.log`）に記録される例：
```
2024/01/15 14:32:10 [error] 1234#1234: *567 upstream timed out (110: Connection timed out) while connecting to upstream, client: 192.168.1.100, server: example.com, request: "POST /api/process HTTP/1.1", upstream: "http://127.0.0.1:8000/api/process"
```

curlで確認した場合：
```json
{
  "status": 504,
  "error": "Gateway Timeout",
  "message": "The upstream server failed to respond in time"
}
```

## よくある原因と解決手順

### 原因1: proxy_read_timeout（デフォルト60秒）の設定が短すぎる

[バックエンド](/glossary/バックエンド/)の処理時間がNginxの[タイムアウト](/glossary/タイムアウト/)設定を超えています。データベースクエリの実行時間が長い、外部[API](/glossary/api/)の応答が遅い、ファイル処理に時間がかかるなど、様々な理由で発生します。

**Before（デフォルト設定）:**
```nginx
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name example.com;

    location /api/ {
        proxy_pass http://backend;
        # proxy_read_timeout のデフォルト値は60秒
    }
}
```

**After（[タイムアウト](/glossary/タイムアウト/)延長）:**
```nginx
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name example.com;

    location /api/ {
        proxy_pass http://backend;
        proxy_read_timeout 300s;        # 5分に設定
        proxy_connect_timeout 60s;      # 接続時のタイムアウト
        proxy_send_timeout 60s;         # リクエスト送信時のタイムアウト
    }
}
```

### 原因2: バックエンドサーバーが起動していない、またはクラッシュしている

アプリケーションサーバーがダウンしていたり、応答していなかったりする場合、Nginxは[タイムアウト](/glossary/タイムアウト/)まで待機してからエラーを返します。

**確認コマンド:**
```bash
# バックエンド（127.0.0.1:8000）が起動しているか確認
curl -v http://127.0.0.1:8000/health

# ポートがリッスンしているか確認
netstat -tlnp | grep 8000
ss -tlnp | grep 8000

# ログファイルを確認
tail -f /var/log/application.log
```

**Before（[バックエンド](/glossary/バックエンド/)が起動していない）:**
```bash
$ curl http://example.com/api/data
504 Gateway Timeout
```

**After（[バックエンド](/glossary/バックエンド/)再起動例：Node.js）:**
```bash
# アプリケーションが正常に起動しているか確認
$ node app.js
Server running on port 8000

# または systemd で管理している場合
$ sudo systemctl restart app-server
$ sudo systemctl status app-server
```

### 原因3: バックエンドのリソース不足（CPU/メモリ）またはハング

バックエンドサーバーのCPUやメモリが枯渇していたり、データベース接続がハングしていたりする場合、処理が完了せず[タイムアウト](/glossary/タイムアウト/)になります。

**確認コマンド:**
```bash
# リソース使用状況確認
top
free -h
df -h

# プロセスの詳細確認
ps aux | grep python  # Pythonアプリの場合

# バックエンドのログ確認
tail -100 /var/log/application/access.log
tail -100 /var/log/application/error.log

# データベース接続状況確認（例：MySQL）
mysql -u root -p -e "SHOW PROCESSLIST;"
```

**Before（応答が遅い状態）:**
```nginx
# ステータスコード200が返るが、時間がかかるため504になる
location /api/heavy-query {
    proxy_pass http://backend;
    # proxy_read_timeout のままでは60秒で切られる
}
```

**After（最適化と[タイムアウト](/glossary/タイムアウト/)調整）:**
```nginx
location /api/heavy-query {
    proxy_pass http://backend;
    proxy_read_timeout 300s;
    
    # 追加の最適化設定
    proxy_buffering off;                # リアルタイムレスポンスが必要な場合
    proxy_request_buffering off;
    client_body_timeout 300s;
    send_timeout 300s;
}
```

## Nginx固有の注意点

### upstream設定での複数バックエンド管理

複数のバックエンドサーバーを設定している場合、一部のみダウンしていると504が頻発します。

```nginx
upstream backend_pool {
    least_conn;  # 最も接続数が少ないサーバーへ分散
    
    server 127.0.0.1:8000 weight=5;
    server 127.0.0.1:8001 weight=5;
    server 127.0.0.1:8002 backup;  # メインサーバーがダウン時に使用
    
    # ヘルスチェック（Nginx Plus機能の場合）
    keepalive 32;
}
```

### location設定での段階的タイムアウト調整

[エンドポイント](/glossary/エンドポイント/)ごとに[タイムアウト](/glossary/タイムアウト/)を変更すべきです：

```nginx
server {
    listen 80;
    server_name example.com;
    
    # 短期処理向け（デフォルト）
    location /api/fast {
        proxy_pass http://backend;
        proxy_read_timeout 30s;
    }
    
    # 中期処理向け
    location /api/normal {
        proxy_pass http://backend;
        proxy_read_timeout 120s;
    }
    
    # 長時間処理向け（ファイルアップロードなど）
    location /api/upload {
        proxy_pass http://backend;
        proxy_read_timeout 600s;
        client_max_body_size 1000M;
    }
}
```

### プロキシバッファ設定との相互作用

バッファ設定が不適切だと、大きな[レスポンス](/glossary/レスポンス/)の処理時間が増加します：

```nginx
location /api/ {
    proxy_pass http://backend;
    proxy_buffering on;
    proxy_buffer_size 4k;
    proxy_buffers 8 4k;
    proxy_busy_buffers_size 8k;
    
    # 大きなレスポンスの場合
    proxy_max_temp_file_size 2048m;
    proxy_temp_file_write_size 32k;
}
```

## それでも解決しない場合

### ログの詳細確認

```bash
# Nginxのエラーログを詳細表示
tail -50 /var/log/nginx/error.log

# アクセスログで遅いリクエストを特定
tail -50 /var/log/nginx/access.log | grep " 504 "

# アクセスログのフォーマットで応答時間を確認
# log_format に $upstream_response_time を追加することで詳細化可能
```

### デバッグ用のNginx設定

```nginx
# デバッグログレベルを有効化（error.log が大きくなります）
error_log /var/log/nginx/error.log debug;

# upstreamの詳細ログ
location /api/ {
    proxy_pass http://backend;
    proxy_read_timeout 300s;
    
    # デバッグ用ヘッダー付与
    proxy_set_header X-Debug-Time $date_gmt;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 設定の文法確認と再読み込み

```bash
# 設定ファイルの文法チェック
sudo nginx -t

# 設定に問題がないことを確認してから再読み込み
sudo systemctl reload nginx
# または
sudo killall -HUP nginx
```

### 公式ドキュメント参照

- [Module ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) - proxy_read_timeout、proxy_connect_timeout等の詳細
- [Module ngx_http_upstream_module](https://nginx.org/en/docs/http/ngx_http_upstream_module.html) - upstream設定の最適化
- [Debugging](https://nginx.org/en/docs/debugging_log.html) - デバッグログ設定方法

### コミュニティリソース

- [Nginx公式フォーラム](https://forum.nginx.org/)
- [Stack Overflow - nginx タグ](https://stackoverflow.com/questions/tagged/nginx)
- [バックエンド](/glossary/バックエンド/)側のログも併せて確認してください（Python Flask、Django、Node.js、Java等、言語・フレームワークによってログ場所が異なります）

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*