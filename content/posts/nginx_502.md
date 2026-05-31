---
title: "Nginx の 502 エラー：原因と解決策"
date: 2026-05-27
description: "502 Bad Gateway エラーは、Nginx がリバースプロキシとしてバックエンドサーバー（アプリケーションサーバーやアップストリームサーバー）から有効なレスポンスを受け取れないときに発生します。"
tags: ["Nginx"]
errorCode: "502"
lastmod: 2026-05-31
---

## エラーの概要

502 Bad Gateway エラーは、Nginx がリバースプロキシとしてバックエンドサーバー（アプリケーションサーバーやアップストリームサーバー）から有効な[レスポンス](/glossary/レスポンス/)を受け取れないときに発生します。クライアント側の[リクエスト](/glossary/リクエスト/)は正常に到達していますが、Nginx が[バックエンド](/glossary/バックエンド/)との通信に失敗した状態です。このエラーが出ているということは、Nginx 自体は稼働していますが、その背後のアプリケーションレイヤーに問題があることを示唆しています。

## 実際のエラーメッセージ例

ブラウザに表示されるデフォルトのエラーページ：

```
502 Bad Gateway

nginx/1.24.0
```

Nginx アクセスログの出力例：

```
192.168.1.100 - - [15/Jan/2025:10:23:45 +0900] "GET /api/users HTTP/1.1" 502 173 "-" "Mozilla/5.0"
```

エラーログ（`/var/log/nginx/error.log`）の出力例：

```
2025/01/15 10:23:45 [error] 1234#1234: *567 connect() failed (111: Connection refused) while connecting to upstream, client: 192.168.1.100, server: example.com, request: "GET /api/users HTTP/1.1", upstream: "http://127.0.0.1:8000/api/users"
```

## よくある原因と解決手順

### 原因1：バックエンドアプリケーションサーバーが起動していない

[バックエンド](/glossary/バックエンド/)のアプリケーションサーバー（Gunicorn、Node.js、Apache 等）がダウンしているか、完全に起動していない状況です。Nginx はその[ポート](/glossary/ポート/)への接続を試みますが、誰も応答していないため 502 が返されます。

**Before（エラーが起きている状態）**

```bash
# バックエンドサーバーが起動していない
$ ps aux | grep gunicorn
# → gunicorn のプロセスが見つからない

$ curl http://127.0.0.1:8000
# → Connection refused
```

**After（修正後）**

```bash
# アプリケーションサーバーを起動
$ cd /opt/myapp
$ gunicorn --bind 127.0.0.1:8000 --workers 4 wsgi:app &

# 起動確認
$ curl http://127.0.0.1:8000
# → 正常なレスポンスが返される
```

### 原因2：Nginx の upstream 設定でホスト名またはポート番号が誤っている

Nginx [設定ファイル](/glossary/設定ファイル/)内の `upstream` ブロックで指定されたアドレスや[ポート](/glossary/ポート/)が実際のバックエンドサーバーと異なる場合、接続に失敗します。

**Before（エラーが起きている状態）**

```nginx
upstream backend {
    server 127.0.0.1:9000;  # 間違ったポート
}

server {
    listen 80;
    server_name example.com;
    
    location /api/ {
        proxy_pass http://backend;
    }
}
```

実際のアプリケーションは[ポート](/glossary/ポート/) 8000 で稼働していますが、Nginx は[ポート](/glossary/ポート/) 9000 へ接続しようとします。

**After（修正後）**

```nginx
upstream backend {
    server 127.0.0.1:8000;  # 正しいポート
}

server {
    listen 80;
    server_name example.com;
    
    location /api/ {
        proxy_pass http://backend;
    }
}
```

修正後、Nginx を再読み込みします：

```bash
$ sudo nginx -t  # 設定ファイルの構文チェック
$ sudo systemctl reload nginx
```

### 原因3：バックエンドサーバーが遅延応答またはタイムアウトしている

アプリケーションサーバーが重い処理を実行中で応答が遅い場合、Nginx のデフォルトタイムアウト（通常 60 秒）に間に合わずエラーになります。または、[バックエンド](/glossary/バックエンド/)が一時的にハング状態に陥っているケースもあります。

**Before（エラーが起きている状態）**

```nginx
server {
    listen 80;
    server_name example.com;
    
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        # タイムアウト設定がデフォルト（60秒）のため、
        # それを超える処理で 502 が発生
    }
}
```

**After（修正後）**

```nginx
server {
    listen 80;
    server_name example.com;
    
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 90s;  # 長い処理に対応
    }
}
```

変更後、構文チェック＆リロード：

```bash
$ sudo nginx -t
$ sudo systemctl reload nginx
```

### 原因4：バックエンドサーバーがリッスンしているインターフェースが限定されている

アプリケーションサーバーが `127.0.0.1` ではなく `0.0.0.0` でバインドされていない、または特定の IP にのみバインドされている場合、Nginx が別のネットワークインターフェースから接続する際に失敗します。

**Before（エラーが起きている状態）**

```bash
$ gunicorn --bind 127.0.0.1:8000 wsgi:app
# このバインドでは、同じホスト上でも別のプロセスから
# 異なるネットワークインターフェース経由ではアクセス不可
```

**After（修正後）**

```bash
$ gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app
# または特定の IP を明示
$ gunicorn --bind 192.168.1.10:8000 --workers 4 wsgi:app
```

## Nginx 固有の注意点

### upstream 設定での複数バックエンド管理

複数のバックエンドサーバーを設定している場合、全ての[サーバー](/glossary/サーバー/)が応答不可になると 502 が発生します。[ヘルスチェック](/glossary/ヘルスチェック/)機能を活用して、障害[サーバー](/glossary/サーバー/)を自動的に除外することができます：

```nginx
upstream backend {
    server app1.example.com:8000 max_fails=3 fail_timeout=30s;
    server app2.example.com:8000 max_fails=3 fail_timeout=30s;
}
```

### proxy_buffering とメモリ不足

[バックエンド](/glossary/バックエンド/)からのレスポンスサイズが大きい場合、Nginx がバッファにしきい値を超えるデータを受け取ると 502 エラーになることがあります。以下で対応します：

```nginx
location /api/ {
    proxy_pass http://backend;
    proxy_buffering on;
    proxy_buffer_size 16k;
    proxy_buffers 4 32k;
}
```

### SSL/TLS 通信でのホスト名検証

[バックエンド](/glossary/バックエンド/)が [HTTPS](/glossary/https/) の場合、ホスト名検証エラーで 502 が発生することがあります：

```nginx
location /secure/ {
    proxy_pass https://backend;
    proxy_ssl_verify off;  # 自己署名証明書の場合
    proxy_ssl_session_reuse on;
}
```

## それでも解決しない場合

### ログの確認

Nginx エラーログを詳細に確認します：

```bash
$ tail -100 /var/log/nginx/error.log
# または リアルタイム監視
$ tail -f /var/log/nginx/error.log
```

バックエンドアプリケーションの[ログ](/glossary/ログ/)も同時に確認：

```bash
# Gunicorn の場合
$ journalctl -u gunicorn -n 50 -f

# Docker コンテナの場合
$ docker logs -f <container_name>
```

### デバッグモードでの起動確認

```bash
$ curl -v http://example.com/api/test
# -v フラグでレスポンスヘッダーとステータスコードを確認
```

### Nginx 設定の詳細な検証

```bash
$ sudo nginx -T  # 全ての設定ファイルを展開表示
$ sudo nginx -t -v  # 詳細な構文チェック
```

### 公式ドキュメント参照

Nginx 公式ドキュメント「[Debugging](http://nginx.org/en/docs/debugging_log.html)」では、ログレベルの詳細な設定方法が記載されています。また「[Module ngx_http_upstream_module](http://nginx.org/en/docs/http/ngx_http_upstream_module.html)」では upstream ディレクティブの全オプションが説明されています。

### コミュニティリソース

- Nginx GitHub Issues：`https://github.com/nginx/nginx/issues`
- Nginx 日本語ドキュメント：複数の有志翻訳サイトが存在
- Stack Overflow タグ「nginx」で同様の事例が多数報告されており、検索に有効です

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*