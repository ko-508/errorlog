---
title: "Nginx の 500 エラー：原因と解決策"
date: 2026-05-26
description: "Nginx が 500 Internal Server Error を返すのは、Nginx または バックエンドアプリケーション（PHP-FPM、uWSGI、Node.js など）で予期しない内部エラーが発生したことを示します。"
tags: ["Nginx"]
errorCode: "500"
lastmod: 2026-06-14
service: "Nginx"
error_type: "500"
components: []
related_services: ["PHP-FPM", "uWSGI", "Node.js", "Gunicorn", "Python", "Flask"]
top_queries:
- 'nginx 500エラー'
- '500 nginx'
---

## エラーの概要

Nginx が **500 Internal Server Error** を返すのは、Nginx またはバックエンドアプリケーション（PHP-FPM、uWSGI、Node.js など）で予期しない内部[エラー](/glossary/エラー/)が発生したことを示します。この[エラー](/glossary/エラー/)が出ると、クライアント側では画面が真っ白になるか、エラーページが表示されます。Nginx 自体は正常に動作していても、設定の誤りやバックエンドプロセスのクラッシュなど、複数の原因が考えられます。

## 実際のエラーメッセージ例

Nginx のアクセスログに以下のように記録されます。

```
192.168.1.100 - - [15/Jan/2024 10:23:45 +0900] "GET /api/users HTTP/1.1" 500 179 "-" "Mozilla/5.0"
```

ブラウザに表示される[レスポンス](/glossary/レスポンス/)：

```html
<html>
<head><title>500 Internal Server Error</title></head>
<body>
<center><h1>500 Internal Server Error</h1></center>
<hr><center>nginx/1.24.0</center>
</body>
</html>
```

Nginx [エラーログ](/glossary/エラーログ/)に記録される詳細情報の例：

```
2024/01/15 10:23:45 [error] 1234#1234: *567 connect() failed (111: Connection refused) while connecting to upstream, client: 192.168.1.100, server: example.com, request: "GET /api/users HTTP/1.1"
```

## よくある原因と解決手順

### 原因 1: バックエンドサーバーへの接続失敗

バックエンドプロセス（PHP-FPM、アプリサーバーなど）が起動していない、またはダウンしている場合、Nginx は接続できず 500 [エラー](/glossary/エラー/)を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```nginx
upstream backend {
    server 127.0.0.1:9000;
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
    }
}
```

この設定で `php-fpm` が起動していない場合、すべての[リクエスト](/glossary/リクエスト/)が 500 [エラー](/glossary/エラー/)になります。

**After（修正後）：**

```bash
# PHP-FPM の起動確認
sudo systemctl status php-fpm

# 起動していない場合は再起動
sudo systemctl restart php-fpm

# プロセス確認
ps aux | grep php-fpm
```

[ポート](/glossary/ポート/)番号が正しいか確認し、必要に応じて nginx 設定を修正：

```nginx
upstream backend {
    server 127.0.0.1:9000;  # PHP-FPM のリッスンポート確認
}

server {
    listen 80;
    server_name example.com;

    location ~ \.php$ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 原因 2: Nginx の upstram 設定エラー

upstram ブロックの指定ミスや、無効なアドレス形式により接続が失敗することがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```nginx
upstream backend {
    server backend_server;  # ホスト名が解決されない
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
    server 192.168.1.10:8080;  # IP アドレスで指定、またはホスト名解決を有効化
}

server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://backend;
        proxy_connect_timeout 5s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;
    }
}
```

または resolver を設定してホスト名解決を有効化：

```nginx
resolver 8.8.8.8 8.8.4.4;
upstream backend {
    server backend_server.example.com:8080;
}
```

### 原因 3: バックエンドアプリケーション内部エラー

PHP、Python、Node.js などの[アプリケーション](/glossary/アプリケーション/)内部で例外やクラッシュが発生している場合、[バックエンド](/glossary/バックエンド/)が 500 [レスポンス](/glossary/レスポンス/)を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```php
<?php
// PHP アプリケーション例
$db = new PDO('mysql:host=127.0.0.1', 'user', 'pass');
$result = $db->query("SELECT * FROM users WHERE id = ?");  // プリペアドステートメント使用忘れ
echo json_encode($result);
?>
```

**After（修正後）：**

```php
<?php
// 適切なエラーハンドリング
try {
    $db = new PDO('mysql:host=127.0.0.1', 'user', 'pass');
    $stmt = $db->prepare("SELECT * FROM users WHERE id = ?");
    $stmt->execute([$_GET['id']]);
    echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));
} catch (Exception $e) {
    http_response_code(500);
    error_log($e->getMessage());
    echo json_encode(['error' => 'Internal Server Error']);
}
?>
```

アプリケーションログを確認：

```bash
# PHP-FPM ログの確認
tail -f /var/log/php-fpm/error.log

# Python uWSGI ログ
tail -f /var/log/uwsgi/app.log

# Node.js PM2 ログ
pm2 logs
```

### 原因 4: メモリ不足またはリソース枯渇

バックエンドプロセスが[メモリ](/glossary/メモリ/)不足やファイルディスクリプタ不足により動作不可になっている場合があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```nginx
upstream backend {
    server 127.0.0.1:9000 max_fails=3 fail_timeout=30s;
    # ヘルスチェックなし
}
```

**After（修正後）：**

```nginx
upstream backend {
    server 127.0.0.1:9000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

server {
    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";  # keepalive 接続
    }
}
```

リソース確認：

```bash
# メモリ使用状況
free -h

# ファイルディスクリプタ確認
ulimit -n

# プロセスごとのメモリ使用量
ps aux --sort=-%mem | head -10
```

### 原因 5: Nginx の location ブロック設定エラー

location 設定の正規表現[エラー](/glossary/エラー/)やリダイレクトループにより 500 [エラー](/glossary/エラー/)が発生することもあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```nginx
server {
    listen 80;
    server_name example.com;

    location ~ ^/api/(.*)$ {
        rewrite ^/api/(.*) /backend/$1;  # リダイレクトループの可能性
    }

    location ~ /backend/ {
        return 500;  # 意図しないエラー返却
    }
}
```

**After（修正後）：**

```nginx
server {
    listen 80;
    server_name example.com;

    location ~ ^/api/(.*)$ {
        proxy_pass http://backend/api/$1;  # 直接プロキシ
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Nginx 固有の注意点

### FastCGI バックエンド（PHP-FPM）での特有エラー

PHP-FPM を使用する場合、FastCGI [プロトコル](/glossary/プロトコル/)の設定ミスが 500 [エラー](/glossary/エラー/)の原因になります。

```nginx
location ~ \.php$ {
    fastcgi_pass 127.0.0.1:9000;
    fastcgi_index index.php;
    fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    fastcgi_connect_timeout 5s;
    fastcgi_send_timeout 10s;
    fastcgi_read_timeout 10s;
}
```

`SCRIPT_FILENAME` [パラメータ](/glossary/パラメータ/)が正しく設定されないと、PHP-FPM がファイルを見つけられず 500 [エラー](/glossary/エラー/)になります。

### リバースプロキシの ヘッダー設定不足

バックエンドアプリケーションが [HTTP](/glossary/http/) [ヘッダー](/glossary/ヘッダー/)情報（Host、X-Forwarded-For など）を期待している場合、Nginx でこれらを明示的に設定する必要があります。

```nginx
location / {
    proxy_pass http://backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
}
```

これらの[ヘッダー](/glossary/ヘッダー/)がないと、[アプリケーション](/glossary/アプリケーション/)側で不正な[リクエスト](/glossary/リクエスト/)と判定し 500 [エラー](/glossary/エラー/)を返すことがあります。

### エラーログレベルの設定

本番環境では error レベルで[ログ](/glossary/ログ/)を記録し、開発環境では debug レベルに設定することで、トラブルシューティングが容易になります。

```nginx
# 本番環境
error_log /var/log/nginx/error.log error;

# 開発・デバッグ環境
error_log /var/log/nginx/error.log debug;
```

## それでも解決しない場合

### ステップバイステップのデバッグ方法

1. **Nginx 構文チェック**：

```bash
sudo nginx -t
```

[設定ファイル](/glossary/設定ファイル/)の文法[エラー](/glossary/エラー/)がないか確認します。

2. **Nginx [エラーログ](/glossary/エラーログ/)の詳細確認**：

```bash
tail -f /var/log/nginx/error.log
```

接続[エラー](/glossary/エラー/)、[タイムアウト](/glossary/タイムアウト/)、ファイルパーミッション [エラー](/glossary/エラー/)などを確認します。

3. **[バックエンド](/glossary/バックエンド/)接続[テスト](/glossary/テスト/)**：

```bash
curl -v http://127.0.0.1:9000
telnet 127.0.0.1 9000
```

バックエンドサーバーが実際にリッスンしているか確認します。

4. **Nginx アクセスログと [エラーログ](/glossary/エラーログ/)の時刻対応**：

```bash
tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

同じタイミングで 500 [エラー](/glossary/エラー/)が記録されているか確認します。

5. **バックエンドアプリケーションログの確認**：

```bash
# PHP-FPM
tail -f /var/log/php-fpm/error.log /var/log/php-fpm/www.log

# Python アプリケーション
tail -f /var/log/application/app.log
```

### 公式ドキュメント参照

- [Nginx 公式ドキュメント - Pitfalls and Common Mistakes](http://nginx.org/en/docs/http/server_names.html)
- [Nginx HTTP プロキシ設定](http://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [FastCGI プロキシ設定](http://nginx.org/en/docs/http/ngx_http_fastcgi_module.html)

### コミュニティリソース

- [Nginx GitHub Issues](https://github.com/nginx/nginx)
- [Stack Overflow nginx タグ](https://stackoverflow.com/questions/tagged/nginx)
- 各ディストリビューション（Ubuntu、CentOS）の Nginx パッケージドキュメント

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*