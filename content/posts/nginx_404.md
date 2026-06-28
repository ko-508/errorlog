---
title: "Nginx の 404 エラー：原因と解決策"
date: 2026-05-25
description: "Nginx が受け取ったリクエストに対して、指定されたパスにファイルやリソースが見つからないときに 404 エラーが返されます。"
tags: ["Nginx"]
errorCode: "404"
lastmod: 2026-05-31
service: "Nginx"
error_type: "404"
components: []
related_services: []
top_queries:
- '404 not found nginx'
- '404 not found nginx 原因'
- 'nginx 404 not found 原因'
---

## エラーの概要

Nginx が受け取った[リクエスト](/glossary/リクエスト/)に対して、指定されたパスにファイルやリソースが見つからないときに 404 [エラー](/glossary/エラー/)が返されます。[リクエスト](/glossary/リクエスト/)対象のファイルが存在しないか、Nginx の設定でそのパスへのアクセスが許可されていない場合に発生します。

## 実際のエラーメッセージ例

ブラウザに表示される例：
```
404 Not Found
The requested URL /api/users was not found on this server.
```

Nginx アクセスログの例：
```
192.168.1.100 - - [15/Jan/2024 10:23:45 +0000] "GET /api/users HTTP/1.1" 404 162 "-" "Mozilla/5.0"
```

## よくある原因と解決手順

### 原因1：root ディレクティブのパスが実際のファイル位置と異なっている

Nginx の `root` や `alias` ディレクティブで指定したパスが、実際のファイル配置と一致していないことが最も多い原因です。例えば設定では `/var/www/html` を指定しているが、実際のファイルは `/home/user/app/public` に存在する場合、404 が返されます。

**Before（[エラー](/glossary/エラー/)が起きる設定）：**
```nginx
server {
    listen 80;
    server_name example.com;
    
    location / {
        root /var/www/html;
    }
}
```

実際のファイル構造が `/home/app/public/index.html` にある場合、このままではアクセスできません。

**After（修正後）：**
```nginx
server {
    listen 80;
    server_name example.com;
    
    location / {
        root /home/app/public;
        try_files $uri $uri/ /index.html;
    }
}
```

### 原因2：try_files の設定が不正で、すべてのリクエストが 404 になる

`try_files` ディレクティブの最後に存在しないファイルを指定すると、すべての[リクエスト](/glossary/リクエスト/)が 404 になります。SPA（Single Page Application）やリライトルールで誤設定されることが多いです。

**Before（[エラー](/glossary/エラー/)が起きる設定）：**
```nginx
location / {
    root /var/www/html;
    try_files $uri $uri/ /notfound.html;
}
```

`/notfound.html` が存在しない場合、すべての[リクエスト](/glossary/リクエスト/)が 404 で返されます。

**After（修正後）：**
```nginx
location / {
    root /var/www/html;
    try_files $uri $uri/ /index.html =404;
}
```

このように修正すると、存在するファイルはそのまま返し、存在しないパスは `index.html` にフォールバックします。

### 原因3：location ブロックの alias ディレクティブで末尾のスラッシュを忘れている

`alias` を使用する場合、パスの末尾にスラッシュがない場合と末尾にスラッシュがある場合で動作が異なります。末尾のスラッシュを忘れるとパス結合に失敗し、404 が返されます。

**Before（[エラー](/glossary/エラー/)が起きる設定）：**
```nginx
location /static/ {
    alias /var/www/static;
}
```

`/static/css/style.css` への[リクエスト](/glossary/リクエスト/)が `/var/www/staticcss/style.css` に解決されてしまいます。

**After（修正後）：**
```nginx
location /static/ {
    alias /var/www/static/;
}
```

末尾にスラッシュを加えることで、正しく `/var/www/static/css/style.css` に解決されます。

## Nginx 固有の注意点

**[設定ファイル](/glossary/設定ファイル/)の文法チェック：** Nginx の設定を変更した直後は、必ず `nginx -t` [コマンド](/glossary/コマンド/)で文法を検証してください。構文[エラー](/glossary/エラー/)があると新しい設定が反映されず、古い設定で動作し続けるため、変更内容が反映されない錯覚に陥ります。

```bash
nginx -t
# output: nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
```

**[キャッシュ](/glossary/キャッシュ/)とリロード：** ブラウザキャッシュやプロキシキャッシュが古い[レスポンス](/glossary/レスポンス/)を保持していることがあります。Nginx の設定を変更した場合は、必ず `nginx -s reload` で再起動してください。

```bash
sudo nginx -s reload
```

**[アクセス権限](/glossary/アクセス権限/)の確認：** ファイルやディレクトリが存在しても、Nginx を実行しているユーザー（通常は `www-data` や `nginx`）に読み取り[権限](/glossary/権限/)がない場合も 404 になります。

```bash
ls -la /var/www/html
# 確認例: -rw-r--r-- 1 www-data www-data 1234 Jan 15 index.html
```

**location ブロックの優先度：** 複数の location ブロックが存在する場合、正規表現マッチングと完全一致マッチングの優先度を理解する必要があります。より具体的な location が先に評価されるため、順序に注意してください。

```nginx
location / { 
    try_files $uri $uri/ =404;
}
location ~ \.php$ {
    fastcgi_pass 127.0.0.1:9000;
}
```

## それでも解決しない場合

**Nginx [エラーログ](/glossary/エラーログ/)の確認：** `/var/log/nginx/error.log` に詳細な[エラー](/glossary/エラー/)情報が記録されています。

```bash
tail -f /var/log/nginx/error.log
```

**アクセスログの詳細確認：** `/var/log/nginx/access.log` で[リクエスト](/glossary/リクエスト/)内容と 404 のパターンを分析してください。

```bash
grep " 404 " /var/log/nginx/access.log | tail -20
```

**Nginx [設定ファイル](/glossary/設定ファイル/)の完全確認：** `include` ディレクティブで他のファイルが読み込まれている場合、すべての[設定ファイル](/glossary/設定ファイル/)を確認する必要があります。

```bash
nginx -T
# すべての設定ファイルの内容を表示
```

**公式ドキュメント参照：** Nginx の [HTTP](/glossary/http/) モジュール、location ディレクティブ、try_files の詳細な動作は [Nginx 公式ドキュメント](https://nginx.org/en/docs/) で確認できます。特に「Module ngx_http_core_module」のセクションが参考になります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*