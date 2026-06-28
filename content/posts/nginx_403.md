---
title: "Nginx の 403 エラー：原因と解決策"
date: 2026-05-25
description: "Nginx の 403 Forbidden エラーは、クライアント（ブラウザ）が特定のファイルやディレクトリへのアクセスを試みたとき、Nginx がそのリソースの存在は確認できるが、アクセス権限がないと判断したときに発生します。"
tags: ["Nginx"]
errorCode: "403"
lastmod: 2026-05-31
service: "Nginx"
error_type: "403"
components: []
related_services: []
top_queries:
- '403 forbidden nginx'
- 'nginx 403 forbidden'
- 'nginx 403'
---

## エラーの概要

Nginx の 403 Forbidden [エラー](/glossary/エラー/)は、クライアント（ブラウザ）が特定のファイルやディレクトリへのアクセスを試みたとき、Nginx がそのリソースの存在は確認できるが、[アクセス権限](/glossary/アクセス権限/)がないと判断したときに発生します。これは[認証](/glossary/認証/)の失敗（401）とは異なり、認証情報は正しいが[権限](/glossary/権限/)がないという状態です。実務では、ファイルパーミッション、ディレクトリ設定、または Nginx の設定ルールによって引き起こされることがほとんどです。

## 実際のエラーメッセージ例

ブラウザに表示される[エラー](/glossary/エラー/)表示例：

```
403 Forbidden
nginx/1.24.0

The server denied access to the requested resource.
```

アクセスログに記録される例（`/var/log/nginx/access.log`）：

```
192.168.1.100 - - [15/Jan/2025:10:23:45 +0900] "GET /admin/config.php HTTP/1.1" 403 162 "-" "Mozilla/5.0"
```

[エラーログ](/glossary/エラーログ/)に記録される例（`/var/log/nginx/error.log`）：

```
2025/01/15 10:23:45 [error] 1234#1234: *5 "/var/www/html/admin/config.php" is forbidden (13: Permission denied)
```

## よくある原因と解決手順

### 原因1：ファイル・ディレクトリのパーミッション不足

**なぜ発生するか：**
Nginx ワーカープロセスは通常 `www-data` または `nginx` というユーザーで動作しますが、ファイルのパーミッションがこのユーザーに読み取り権がない場合、403 [エラー](/glossary/エラー/)が発生します。特に新規配置したファイルや、開発環境から本番環境に移行したときに起きやすい問題です。

**Before（[エラー](/glossary/エラー/)が起きるパターン）：**

```bash
# ファイルのパーミッションを確認
ls -la /var/www/html/index.html
# -rw------- 1 root root 1234 Jan 15 10:00 index.html
# → root オーナーのみ読める設定。nginx ユーザーは読めない

# Nginx のワーカープロセスユーザーを確認
ps aux | grep nginx
# nginx   1234  0.0  0.1 ... nginx: worker process
```

**After（修正後）：**

```bash
# ファイルに読み取り権限を付与（所有者と同じグループに）
chown -R www-data:www-data /var/www/html
chmod -R 755 /var/www/html

# ディレクトリは実行権限も必要
chmod 755 /var/www/html
chmod 644 /var/www/html/index.html

# 確認
ls -la /var/www/html/
# drwxr-xr-x 2 www-data www-data 4096 Jan 15 10:00 .
# -rw-r--r-- 1 www-data www-data 1234 Jan 15 10:00 index.html
```

### 原因2：ディレクトリリスティング無効（autoindex off）とインデックスファイル欠落

**なぜ発生するか：**
ディレクトリへのアクセス時に、Nginx は順序どおり `index.html`、`index.htm`、`index.php` などのインデックスファイルを探します。これらが存在しない場合かつ `autoindex off`（デフォルト）の設定では、403 [エラー](/glossary/エラー/)になります。

**Before（[エラー](/glossary/エラー/)が起きるパターン）：**

```nginx
server {
    listen 80;
    server_name example.com;
    root /var/www/html;

    location / {
        # index ファイルが指定されていない
        # autoindex off がデフォルト
    }
}

# /var/www/html/ にはファイルがない
# http://example.com/ にアクセス → 403 エラー
```

**After（修正後）：**

```nginx
server {
    listen 80;
    server_name example.com;
    root /var/www/html;

    location / {
        # インデックスファイルを明示的に指定
        index index.html index.htm index.php;
        try_files $uri $uri/ =404;
    }
}
```

または、ディレクトリリスティングを有効化する場合：

```nginx
location / {
    autoindex on;
    autoindex_exact_size off;
    autoindex_localtime on;
}
```

### 原因3：Nginx 設定で deny all; ルールが適用されている

**なぜ発生するか：**
`nginx.conf` または `.htaccess` 相当の Nginx 設定で、特定の IP アドレスやパターンに対して明示的にアクセスを拒否するルール（`deny all;`）が設定されている場合、そのルールが評価優先度で先に適用されるとアクセスが拒否されます。

**Before（[エラー](/glossary/エラー/)が起きるパターン）：**

```nginx
server {
    listen 80;
    server_name example.com;
    root /var/www/html;

    location /admin/ {
        deny all;  # すべてのアクセスを拒否
    }

    location ~ \.php$ {
        deny all;  # PHP ファイルの直接実行を禁止
    }
}

# http://example.com/admin/ にアクセス → 403 エラー
```

**After（修正後）：**

```nginx
server {
    listen 80;
    server_name example.com;
    root /var/www/html;

    location /admin/ {
        # 特定の IP からのみアクセスを許可
        allow 192.168.1.0/24;
        allow 10.0.0.0/8;
        deny all;
    }

    location ~ \.php$ {
        # PHP ファイルの直接実行は禁止するが、FastCGI 経由はOK
        deny all;
    }

    location ~ \.php$ {
        include fastcgi_params;
        fastcgi_pass unix:/var/run/php-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    }
}
```

## Nginx 固有の注意点

### 1. location ブロックの優先順位

複数の `location` ブロックが存在する場合、評価順序が重要です。最初にマッチしたルールが優先されるわけではなく、正規表現ではない完全一致（`=`）→ プレフィックス一致の中で最長一致 → 正規表現の順で評価されます。そのため予期しない `deny` ルールが適用されることがあります。

```nginx
location /admin {
    deny all;  # ← これが最初に評価される可能性
}

location = /admin/index.html {
    allow all;  # ← これより後に評価
}
```

### 2. ディレクトリへのスラッシュ有無

`/admin` と `/admin/` は異なるパスとして扱われます。末尾のスラッシュがない場合、Nginx は 301 リダイレクトを返してからアクセス制御を評価することがあり、設定による意図しない403を回避できます。

```nginx
# スラッシュなしでアクセスした場合、末尾スラッシュへのリダイレクトが発生
location /admin/ {
    deny all;
}
```

### 3. try_files による暗黙的な許可

`try_files` ディレクティブを使用する場合、順序の後ろの[引数](/glossary/引数/)が評価されるときに再度 `location` ブロックが評価されます。無限ループを防ぐため、`=404` で終了させるのが一般的です。

```nginx
location / {
    try_files $uri $uri/ =404;
    # $uri/ を試すとき、ディレクトリとして評価される
}
```

### 4. SELinux との組み合わせ

CentOS/RHEL 環境で SELinux が有効な場合、Nginx ユーザーがファイルにアクセスするための SELinux コンテキストも正しく設定されている必要があります。ファイルパーミッションは正しくても、SELinux [ポリシー](/glossary/ポリシー/)で拒否されて 403 が発生することがあります。

```bash
# SELinux の制限を確認
getenforce  # Enforcing の場合、ポリシーチェックが有効

# httpd ユーザーがアクセス可能なファイルタイプを確認
semanage fcontext -l | grep httpd

# ファイルに正しいラベルを付与
restorecon -R /var/www/html
```

## それでも解決しない場合

### ステップ1：詳細なログを確認

```bash
# Nginx アクセスログで 403 ステータスを抽出
grep " 403 " /var/log/nginx/access.log

# エラーログで権限関連メッセージを確認
grep -i "permission\|forbidden" /var/log/nginx/error.log

# Nginx の詳細なデバッグログを有効化
# nginx.conf に以下を追加してリロード
error_log /var/log/nginx/error.log debug;

# Nginx リロード
nginx -s reload
```

### ステップ2：Nginx 設定の構文チェック

```bash
# 設定ファイルの構文エラーを確認
nginx -t

# 設定内容を展開して表示
nginx -T | grep -A 5 "location"
```

### ステップ3：プロセスユーザーとファイル所有権の再確認

```bash
# Nginx ワーカープロセスのユーザーを確認
ps aux | grep "nginx: worker"

# ファイルの所有者を確認
stat /var/www/html/index.html

# 両者が一致しているか確認
ls -l /var/www/html/
```

### ステップ4：公式ドキュメントの参照

Nginx 公式ドキュメント「Module ngx_http_access_module」では `allow` / `deny` ディレクティブの詳細な仕様が説明されています。また「Nginx Pitfalls」では設定ミスの典型パターンが紹介されており、特に `location` ブロックの優先順位に関する解説が参考になります。

### ステップ5：コミュニティリソース

stackoverflow の nginx [タグ](/glossary/タグ/)や、Nginx フォーラム（forum.nginx.org）で同様の問題報告が多数あります。[エラーログ](/glossary/エラーログ/)の `"is forbidden"` というメッセージとログレベル番号（13: Permission denied）を含めて検索すると、類似事例が見つかりやすいです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*