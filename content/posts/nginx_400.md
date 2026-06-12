---
title: "Nginx の 400 エラー：原因と解決策"
date: 2026-05-25
description: "Nginx における 400 エラーは、クライアントから送信されたリクエストが HTTP 仕様に違反していることを示します。"
tags: ["Nginx"]
errorCode: "400"
lastmod: 2026-05-31
service: "Nginx"
error_type: "400"
components: []
related_services: ["JavaScript", "API", "HTTP", "HTTPS"]
top_queries:
- "nginx エラー"
---

## エラーの概要

Nginx における 400 [エラー](/glossary/エラー/)は、クライアントから送信された[リクエスト](/glossary/リクエスト/)が [HTTP](/glossary/http/) 仕様に違反していることを示します。リクエストヘッダーの形式が不正、サイズ超過、または URI の不正な文字エンコーディングなどが原因となり、[サーバー](/glossary/サーバー/)側で処理できない状態を意味します。本[エラー](/glossary/エラー/)はクライアント側の問題であるため、[サーバー](/glossary/サーバー/)設定と[リクエスト](/glossary/リクエスト/)内容の両面から原因特定が必要です。

## 実際のエラーメッセージ例

Nginx のアクセスログに記録される 400 [エラー](/glossary/エラー/)の典型的な出力は以下の通りです。

```
192.168.1.100 - - [15/Nov/2024:10:23:45 +0900] "GET /api/v1/users?name=<invalid_char> HTTP/1.1" 400 157 "-" "Mozilla/5.0"
```

また、Nginx の[エラーログ](/glossary/エラーログ/)には以下のように記録されることがあります。

```
2024/11/15 10:23:45 [info] 12345#12345: *1 client sent invalid request line: "GET /search?q=あああ HTTP/1.1"
```

## よくある原因と解決手順

### 原因1：リクエストヘッダーサイズの超過

**なぜ発生するか**  
Nginx は `large_client_header_buffers` で設定されたサイズ制限を超える[ヘッダー](/glossary/ヘッダー/)を受け取ると、400 [エラー](/glossary/エラー/)を返します。これはメモリ消費やバッファオーバーフロー攻撃を防ぐための保護機構です。特に Cookie やカスタムヘッダーが多い場合に発生しやすくなります。

**Before（デフォルト設定での問題）**
```nginx
# Nginx デフォルト設定
# large_client_header_buffers 4 8k; # 4個のバッファ、各8KB

# このサイズでクライアントが 32KB 以上のヘッダーを送信するとエラー
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
    }
}
```

**After（ヘッダーバッファサイズの拡大）**
```nginx
server {
    listen 80;
    server_name example.com;

    # ヘッダーバッファを拡大（4個 × 32KB = 最大128KB）
    large_client_header_buffers 4 32k;

    location / {
        proxy_pass http://backend;
    }
}
```

修正後、Nginx を再起動して設定を反映させます。
```bash
sudo nginx -t && sudo systemctl restart nginx
```

### 原因2：URI に含まれる不正な文字やエンコーディング

**なぜ発生するか**  
URL に日本語やマルチバイト文字が直接含まれていたり、%エンコーディングが不正な場合、Nginx が [HTTP](/glossary/http/) 仕様違反と判定します。ブラウザから自動的に送信される場合や[API](/glossary/api/) クライアントの設定ミスで発生することが多いです。

**Before（不正なエンコーディング例）**
```javascript
// JavaScript での API リクエスト - エンコーディングなし
fetch('http://example.com/api/search?query=ユーザー検索')
    .then(res => res.json());

// または不正な部分的エンコーディング
fetch('http://example.com/api/users?id=001&name=%');
```

**After（正しいエンコーディング）**
```javascript
// encodeURIComponent を使用した適切なエンコーディング
const query = 'ユーザー検索';
const encodedQuery = encodeURIComponent(query);
fetch(`http://example.com/api/search?query=${encodedQuery}`)
    .then(res => res.json());

// または URL オブジェクトを使用
const url = new URL('http://example.com/api/users');
url.searchParams.set('id', '001');
url.searchParams.set('name', 'テスト');
fetch(url)
    .then(res => res.json());
```

### 原因3：HTTP と HTTPS の混在やプロトコル版の不一致

**なぜ発生するか**  
[HTTPS](/glossary/https/) [エンドポイント](/glossary/エンドポイント/)宛に [HTTP](/glossary/http/) で送信された[リクエスト](/glossary/リクエスト/)、または [HTTP](/glossary/http/)/1.0 での不正な[リクエスト](/glossary/リクエスト/)形式が、Nginx の `http_version` チェックで拒否されます。特にリバースプロキシ環境や[ロードバランサー](/glossary/ロードバランサー/)の背後で発生しやすくなります。

**Before（[プロトコル](/glossary/プロトコル/)不一致）**
```nginx
# HTTPS のみを要求する設定だが HTTP も受け付ける場合
server {
    listen 80;
    listen 443 ssl http2;
    server_name example.com;

    # HTTP からのアクセスを強制的にリダイレクトせず混在
    location / {
        proxy_pass http://backend;
    }
}
```

**After（[プロトコル](/glossary/プロトコル/)の統一）**
```nginx
# HTTP を HTTPS にリダイレクト
server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name example.com;

    # クライアントプロトコルを明示的に指定
    proxy_http_version 1.1;
    proxy_pass http://backend;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
}
```

## Nginx 固有の注意点

### location ブロック内での URI 検証

Nginx の `if` ディレクティブで URI パターンをチェックし、不正な[リクエスト](/glossary/リクエスト/)を事前に遮断できます。

```nginx
server {
    listen 80;
    server_name api.example.com;

    # 不正な文字を含むリクエストを明示的に拒否
    if ($request_uri ~* "[^-_./0-9a-zA-Z%]") {
        return 400;
    }

    location /api/ {
        proxy_pass http://backend;
    }
}
```

### プロキシヘッダーの設定ミス

[バックエンド](/glossary/バックエンド/)への[プロキシ](/glossary/プロキシ/)時に必要な[ヘッダー](/glossary/ヘッダー/)が不足すると、[バックエンド](/glossary/バックエンド/)側で 400 と判定される場合があります。

```nginx
# 推奨されるプロキシヘッダー設定
location /api/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
}
```

### client_max_body_size との併用

POST [リクエスト](/glossary/リクエスト/)のボディサイズ制限も 400 の原因になります。

```nginx
server {
    listen 80;
    server_name example.com;

    # ファイルアップロードに対応する場合はボディサイズも拡大
    client_max_body_size 100m;
    large_client_header_buffers 4 32k;

    location /upload {
        proxy_pass http://backend;
    }
}
```

## それでも解決しない場合

### ログの詳細確認

Nginx のエラーログレベルを上げて詳細情報を取得します。

```bash
# エラーログの確認
tail -f /var/log/nginx/error.log

# または実時間でストリーミング確認
journalctl -u nginx -f
```

nginx.conf のログレベルを debug に変更して再起動すれば、より詳しい情報が出力されます。

```nginx
error_log /var/log/nginx/error.log debug;
```

### 設定の検証

Nginx [設定ファイル](/glossary/設定ファイル/)の文法[エラー](/glossary/エラー/)がないか確認します。

```bash
# 設定ファイルの構文チェック
sudo nginx -t -c /etc/nginx/nginx.conf

# 詳細な出力
sudo nginx -T | head -50
```

### 公式ドキュメントの参照

- [Nginx http_core モジュール - large_client_header_buffers](http://nginx.org/en/docs/http/ngx_http_core_module.html#large_client_header_buffers)
- [Nginx ngx_http_proxy_module](http://nginx.org/en/docs/http/ngx_http_proxy_module.html)

### コミュニティリソース

Nginx のスタックオーバーフローやGitHub Issues で「400 bad request」を検索すると、環境固有の事例が見つかることがあります。特にリバースプロキシや[ロードバランサー](/glossary/ロードバランサー/)の背後での設定については参考になる質問が多く掲載されています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*