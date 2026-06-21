---
title: "Nginx の 504 エラー：原因と解決策"
date: 2026-05-27
description: "504 Gateway Timeoutは、Nginxがリバースプロキシとしてバックエンドサーバー（アプリケーションサーバーやAPI）からのレスポンスを一定時間待ちきれず、タイムアウトした状況を示すエラーです。"
tags: ["Nginx"]
errorCode: "504"
lastmod: 2026-06-14
service: "Nginx"
error_type: "504"
components: []
related_services: ["Node.js", "MySQL", "systemd"]
top_queries:
- 'nginx 504'
---

## エラーの概要

504 Gateway Timeoutは、Nginxがリバースプロキシとしてバックエンドサーバー（アプリケーションサーバーや[API](/glossary/api/)[サーバー](/glossary/サーバー/)）からの[レスポンス](/glossary/レスポンス/)を一定時間待ちきれず、[タイムアウト](/glossary/タイムアウト/)した状況を示す[エラー](/glossary/エラー/)です。Nginxそのものは正常に動作していますが、[バックエンド](/glossary/バックエンド/)側の処理時間が長すぎるか、[サーバー](/glossary/サーバー/)が応答していない、あるいは[ネットワーク](/glossary/ネットワーク/)経路に問題がある可能性があります。

## 実際のエラーメッセージ例

ブラウザに表示される場合：
```
504 Gateway Timeout
```

Nginxの[エラーログ](/glossary/エラーログ/)（`/var/log/nginx/error.log`）に記録される例：
```
2024/01/15 14:32:10 [error] 1234#1234: *567 upstream timed out (110: Connection timed out) while connecting to upstream, client: 192.168.1.100, server: example.com, request: "GET /api/process HTTP/1.1"
```

Nginxアクセスログ（`/var/log/nginx/access.log`）の例：
```
192.168.1.100 - - [15/Jan/2024:14:32:10 +0900] "GET /api/process HTTP/1.1" 504 182 "-" "Mozilla/5.0"
```

## よくある原因と解決手順

### 原因1：proxy_connect_timeoutまたはproxy_read_timeoutが短すぎる

バックエンドサーバーの処理に時間がかかるのに対し、Nginxの[タイムアウト](/glossary/タイムアウト/)設定が短すぎる場合、504[エラー](/glossary/エラー/)が発生します。デフォルトでは60秒に設定されていることが多く、これを超える処理では必ず404が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```nginx
upstream backend {
    server 192.168.1.10:8080;
}

server {
    listen 80;
    server_name example.com;

    location /api/ {
        proxy_pass http://backend;
    }
}
```

**After（修正後）：**
```nginx
upstream backend {
    server 192.168.1.10:8080;
}

server {
    listen 80;
    server_name example.com;

    location /api/ {
        proxy_pass http://backend;
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 120s;
    }
}
```

`proxy_connect_timeout` は[バックエンド](/glossary/バックエンド/)との接続確立待ち時間、`proxy_read_timeout` は[レスポンス](/glossary/レスポンス/)受信待ち時間です。処理内容に応じて秒数を調整してください。

### 原因2：バックエンドサーバーがダウンしているか応答していない

バックエンドサーバー自体がクラッシュしているか、[ネットワーク](/glossary/ネットワーク/)で到達不可能な状態では、Nginxは[タイムアウト](/glossary/タイムアウト/)するまで待機し、504を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```nginx
upstream backend {
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
    }
}
```

**After（修正後）：**
```nginx
upstream backend {
    server 192.168.1.10:8080 max_fails=3 fail_timeout=30s;
    server 192.168.1.11:8080 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
        access_log /var/log/nginx/access.log;
        error_log /var/log/nginx/error.log debug;
    }
}
```

`max_fails` と `fail_timeout` を設定することで、失敗した[サーバー](/glossary/サーバー/)を一時的に除外できます。まずはバックエンドサーバーのステータスを確認してください。

```bash
curl -v http://192.168.1.10:8080/health
```

[レスポンス](/glossary/レスポンス/)がない場合、バックエンドサーバーのプロセスが停止していないか確認します。

### 原因3：バックエンド処理が実際に遅い（アプリケーション側の問題）

データベースクエリが遅い、外部[API](/glossary/api/)の呼び出しが遅い、或いはリソース不足によりバックエンドサーバーの処理時間が著しく長くなっている場合、504が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```nginx
upstream backend {
    server 192.168.1.10:8080;
}

server {
    listen 80;
    server_name example.com;

    location /api/report {
        proxy_pass http://backend;
        # タイムアウト設定なし
    }
}
```

**After（修正後）：**
```nginx
upstream backend {
    server 192.168.1.10:8080;
}

server {
    listen 80;
    server_name example.com;

    location /api/report {
        proxy_pass http://backend;
        proxy_read_timeout 300s;
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }
}
```

同時に、アプリケーション側で[クエリ](/glossary/クエリ/)の最適化、[キャッシュ](/glossary/キャッシュ/)の導入、非同期処理化などを検討してください。

### 原因4：upstream接続の設定ミス

upstreamのサーバーアドレスが間違っている、[ポート](/glossary/ポート/)番号が誤っている、あるいは名前解決が失敗している場合も504が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```nginx
upstream backend {
    server backend-service:8080;  # DNSで解決できない場合
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
    }
}
```

**After（修正後）：**
```nginx
upstream backend {
    server 192.168.1.10:8080;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
    }
}
```

または具体的な[IPアドレス](/glossary/ipアドレス/)を指定するか、`resolver` ディレクティブで名前解決を明示的に設定してください。

## Nginx固有の注意点

### connection_resetが記録される場合

[エラーログ](/glossary/エラーログ/)に「connection reset by peer」と出力されている場合、バックエンドサーバーが異常に終了しているか、[ファイアウォール](/glossary/ファイアウォール/)・[ロードバランサー](/glossary/ロードバランサー/)が接続を切断している可能性があります。

```nginx
location / {
    proxy_pass http://backend;
    proxy_next_upstream error timeout http_502 http_503;
    proxy_next_upstream_tries 2;
}
```

`proxy_next_upstream` と `proxy_next_upstream_tries` を使用すると、失敗時に別のupstream[サーバー](/glossary/サーバー/)へ自動的に[リトライ](/glossary/リトライ/)します。

### keep-aliveとコネクションプーリング

バックエンドサーバーとの[通信](/glossary/通信/)がkeep-aliveで接続を保持していない場合、接続確立の遅延が蓄積します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```nginx
upstream backend {
    server 192.168.1.10:8080;
}
```

**After（修正後）：**
```nginx
upstream backend {
    server 192.168.1.10:8080;
    keepalive 32;
}

server {
    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

`keepalive` でコネクションプーリングを有効化し、`proxy_http_version 1.1` と `Connection` [ヘッダー](/glossary/ヘッダー/)削除で接続の再利用を促進します。

### ロードバランサーのヘルスチェック

複数のバックエンドサーバーがある場合、`upstream` 内で `check` モジュール（Nginxの有志開発版）を使用するか、外部のロードバランシングツール（例：HAProxy）と組み合わせることで、より堅牢な構成が実現できます。通常のNginxではアクティブな[ヘルスチェック](/glossary/ヘルスチェック/)が非標準のため、まず[エラーログ](/glossary/エラーログ/)を確認して個別[サーバー](/glossary/サーバー/)の状態を把握してください。

## それでも解決しない場合

### ログの詳細確認

Nginxをデバッグモードで再起動し、詳細な[ログ](/glossary/ログ/)を記録してください。

```bash
# nginx.confでdebugレベルを設定
error_log /var/log/nginx/error.log debug;

# Nginxをリロード
sudo systemctl reload nginx

# エラーログの末尾を監視
sudo tail -f /var/log/nginx/error.log
```

[エラーメッセージ](/glossary/エラーメッセージ/)の「upstream timed out」に続く詳細情報（ホスト、[ポート](/glossary/ポート/)、[エラー](/glossary/エラー/)番号）を確認し、どの段階で失敗しているか特定してください。

### バックエンドサーバーの動作確認

バックエンドサーバーのプロセス状態とリスニングポートを確認します。

```bash
# バックエンドサーバー上で実行
netstat -tlnp | grep 8080
ps aux | grep application
```

プロセスが起動していない、[ポート](/glossary/ポート/)にバインドしていない場合は、アプリケーション自体の起動を確認してください。

### ネットワーク疎通確認

Nginx[サーバー](/glossary/サーバー/)からバックエンドサーバーへのTCP接続確認：

```bash
# Nginxサーバー上で実行
nc -zv 192.168.1.10 8080
curl -v --connect-timeout 5 http://192.168.1.10:8080/health
```

接続できない場合は、[ファイアウォール](/glossary/ファイアウォール/)設定（`iptables`, `ufw`）を確認し、必要に応じてルールを追加してください。

### 公式ドキュメント

Nginxの公式ドキュメント「Reverse Proxy」（https://nginx.org/en/docs/http/ngx_http_proxy_module.html）で `proxy_*_timeout` [パラメータ](/glossary/パラメータ/)の詳細仕様を確認できます。また、「[HTTP](/glossary/http/) Upstream Module」では upstream設定のベストプラクティスが記載されています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*