---
title: "Nginx の 500 エラー：原因と解決策"
date: 2026-05-26
description: "Nginx の 500 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Nginx"]
errorCode: "500"
lastmod: 2026-05-29
---

## エラーの概要

Nginx が **500 Internal Server Error** を返すのは、Nginx または バックエンドアプリケーション（PHP-FPM、uWSGI、Node.js など）で予期しない内部エラーが発生したことを示します。このエラーが出ると、クライアント側では画面が真っ白になるか、エラーページが表示されます。Nginx 自体は正常に動作していても、設定の誤りやバックエンドプロセスのクラッシュなど、複数の原因が考えられます。

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
<hr><center>nginx</center>
</body>
</html>
```

## よくある原因と解決手順

### 原因1：バックエンドプロセスが停止・クラッシュしている

バックエンドサーバー（PHP-FPM、uWSGI、Gunicorn など）が停止しているか、[リクエスト](/glossary/リクエスト/)処理中にクラッシュしていると、Nginx は接続先がないため 500 エラーを返します。

**Before（エラーが起きる状態）：**

```bash
# PHP-FPMが停止している
systemctl status php-fpm
# ● php-fpm.service - The PHP FastCGI Process Manager
#    Loaded: loaded
#    Active: inactive (dead)

# Nginxにリクエストが来ると502または500を返す
```

**After（修正後）：**

```bash
# PHP-FPMを起動
sudo systemctl start php-fpm
sudo systemctl enable php-fpm

# 起動状態を確認
sudo systemctl status php-fpm
# ● php-fpm.service - The PHP FastCGI Process Manager
#    Loaded: loaded
#    Active: active (running)
```

### 原因2：Nginx 設定ファイルの文法エラー

nginx.conf やサーバーブロック設定に文法エラーがあると、Nginx の再起動に失敗し、古い設定で動作している場合があります。その設定が不完全だと 500 エラーが発生します。

**Before（エラーが起きる設定）：**

```nginx
server {
    listen 80;
    server_name example.com;
    
    location / {
        proxy_pass http://backend;  # upstream定義がない
        proxy_set_header Host $host
        # セミコロン漏れ
    }
}
```

**After（修正後）：**

```nginx
upstream backend {
    server 127.0.0.1:3000;
    server 127.0.0.1:3001;
}

server {
    listen 80;
    server_name example.com;
    
    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

修正後は設定テストと再起動：

```bash
# 設定ファイルの文法をチェック
sudo nginx -t
# nginx: the configuration file /etc/nginx/nginx.conf syntax is ok

# Nginxを再起動
sudo systemctl reload nginx
```

### 原因3：バックエンドアプリケーションの例外エラー

バックエンドアプリケーション（Python、Node.js、PHP など）が例外を発生させて正常な[レスポンス](/glossary/レスポンス/)を返せていない場合、Nginx は 500 エラーを返します。

**Before（エラーが起きるコード）：**

```python
# Flask アプリケーション
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/data')
def get_data():
    # データベース接続エラーで例外が発生
    result = database.query("SELECT * FROM users")
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
```

**After（修正後）：**

```python
from flask import Flask, jsonify
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/api/data')
def get_data():
    try:
        # データベース接続をタイムアウト設定付きで実行
        result = database.query(
            "SELECT * FROM users",
            timeout=5
        )
        return jsonify(result), 200
    except Exception as e:
        logging.error(f"Database error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
```

### 原因4：upstream ホストの設定誤りまたは接続不可

proxy_pass で指定したバックエンドサーバーのホスト名・[ポート](/glossary/ポート/)が間違っていたり、[ネットワーク](/glossary/ネットワーク/)が到達不可能だと 500 エラーが返されます。

**Before（エラーが起きる設定）：**

```nginx
upstream backend {
    server backend.example.com:8080;  # DNS解決失敗またはホスト不存在
}

server {
    location / {
        proxy_pass http://backend;
        proxy_connect_timeout 1s;  # タイムアウトが短すぎる
    }
}
```

**After（修正後）：**

```nginx
upstream backend {
    server 127.0.0.1:3000;
    # または
    server localhost:3000 weight=1;
    server localhost:3001 weight=1;
    
    # 接続失敗時の対応
    keepalive 32;
}

server {
    location / {
        proxy_pass http://backend;
        proxy_connect_timeout 5s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;
        
        # バックエンド側で接続できなかった場合のフォールバック
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503;
    }
}
```

## Nginx 固有の注意点

### ログの確認方法

500 エラーの原因特定には、Nginx のエラーログを確認することが重要です。

```bash
# Nginx エラーログを確認
sudo tail -f /var/log/nginx/error.log

# よくあるエラー例：
# 2024/01/15 10:23:45 [error] 1234#1234: *56 connect() failed 
# (111: Connection refused) while connecting to upstream, 
# client: 192.168.1.100, server: example.com
```

### proxy_next_upstream の活用

[バックエンド](/glossary/バックエンド/)の一部がダウンしている場合、他のサーバーに[リクエスト](/glossary/リクエスト/)を[リトライ](/glossary/リトライ/)させることで 500 エラーを回避できます。

```nginx
upstream backend {
    server 127.0.0.1:3000 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:3001 max_fails=3 fail_timeout=30s;
}

server {
    location / {
        proxy_pass http://backend;
        # 以下の条件でリトライ
        proxy_next_upstream error timeout http_500 http_502 http_503;
        proxy_next_upstream_tries 2;
        proxy_next_upstream_timeout 10s;
    }
}
```

### リバースプロキシヘッダーの不足

バックエンドアプリケーションが クライアント IP や プロトコルを正しく取得できないと、セッション検証やセキュリティチェックで失敗して 500 エラーが発生することがあります。

```nginx
location / {
    proxy_pass http://backend;
    
    # 必須のヘッダー設定
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $server_name;
}
```

## それでも解決しない場合

### 確認すべきログの場所

```bash
# Nginx エラーログ（優先度：高）
sudo tail -100 /var/log/nginx/error.log

# アクセスログ（ステータスコード確認）
sudo tail -100 /var/log/nginx/access.log

# バックエンドアプリケーションのログ
# Python（Django/Flask）
sudo tail -100 /var/log/app/app.log

# Node.js（PM2使用時）
pm2 logs

# PHP-FPMのエラーログ
sudo tail -100 /var/log/php-fpm/error.log
```

### デバッグコマンド

```bash
# upstream への接続テスト
curl -v http://127.0.0.1:3000/

# Nginxプロセスの確認
ps aux | grep nginx

# ポート待ち受けの確認
sudo netstat -tlnp | grep -E '(nginx|:3000|:5000)'

# バックエンドプロセスの確認（Python）
ps aux | grep python
```

### 公式リソース

- Nginx 公式ドキュメント：[Module ngx_http_proxy_module](http://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [バックエンド](/glossary/バックエンド/)ごとのエラーログ確認方法をアプリケーション公式ドキュメントで検索
- デバッグが困難な場合は、Nginx のアクセスログに `$upstream_addr` `$upstream_status` を追加して詳細を確認

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*