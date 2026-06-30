---
title: "Nginx の 403 エラー：原因と解決策"
date: 2026-05-25
description: "Nginx の 403 Forbidden は、サーバーがリクエストを理解したうえでアクセスを拒否したことを示します。ファイル権限、親ディレクトリの実行権限、index ファイルの欠落、deny ルール、SELinux/AppArmor、upstream の拒否という6つの原因を、エラーログの文言から切り分けて解決します。"
tags: ["Nginx"]
errorCode: "403"
lastmod: 2026-06-30
service: "Nginx"
error_type: "403"
components: []
related_services: ["PHP-FPM", "SELinux", "AppArmor"]
top_queries:
- '403 forbidden nginx'
- 'nginx 403 forbidden'
- 'nginx 403 forbidden 原因'
---

## 冒頭まとめ

Nginx の 403 Forbidden は、サーバーがリクエストを理解したうえで、アクセスを拒否したときに返されます。原因はほぼ次の6つのいずれかです。ファイル権限の不足、パスの途中の親ディレクトリに実行権限がない、index ファイルがなく autoindex も無効、設定の deny ルール、SELinux/AppArmor、そして upstream(PHP-FPM など)自身が 403 を返すケースです。調査は、設定をいじる前に、まず `/var/log/nginx/error.log` を読むことから始めます。ログの文言が、どの原因なのかの手がかりになります。

## エラーの概要

403 Forbidden は、Nginx がリクエスト自体は正しく受け取り、対象のリソースの場所も分かっているが、アクセスを拒否した状態です。認証情報が足りない 401 Unauthorized とは異なり、再認証しても解決しません。リソースが存在しない 404 Not Found とも異なります。

この違いはエラーログで明確に区別できます。404 はログに `No such file or directory` と記録され、403 は `Permission denied` や `is forbidden` と記録されます。アクセスログは「403 が起きた」ことだけを示し、なぜ起きたかはエラーログが示します。したがって、403 の調査は設定ファイルをいじる前に、まずエラーログを読むことから始めます。

## まず最初に：エラーログを読む

原因を切り分ける前に、エラーログの該当行を確認します。

```bash
# 直近のエラーを表示
sudo tail -50 /var/log/nginx/error.log

# 権限・拒否に関する行だけを抽出
sudo grep -iE "permission denied|forbidden|denied" /var/log/nginx/error.log
```

ログの文言と原因の対応は次のとおりです。

```text
# ファイルまたは親ディレクトリの権限不足
open() "/var/www/html/index.html" failed (13: Permission denied)

# index ファイルがなく autoindex も無効
directory index of "/var/www/html/" is forbidden

# upstream への接続が拒否された（SELinux でソケット接続が遮られた例）
connect() to 127.0.0.1:8080 failed (13: Permission denied) while connecting to upstream
```

この文言で、おおよその原因の見当がつきます。以下、6つの原因を、切り分けるべき順に説明します。

## よくある原因と解決手順

### 原因1：ファイルまたはディレクトリの権限が不足している

最も多い原因です。Nginx のワーカープロセスは、配信するファイルに読み取り権限が必要です。エラーログには `(13: Permission denied)` が出ます。

まず Nginx のワーカーユーザーを確認します。ディストリビューションによって異なります。

```bash
# ワーカープロセスのユーザーを確認
ps -o user,comm -C nginx
# root     nginx   ← master プロセス
# www-data nginx   ← worker プロセス（こちらが実際にファイルを読む）

# 設定上のユーザー指定を確認
grep -E "^\s*user" /etc/nginx/nginx.conf
# Ubuntu/Debian は www-data、CentOS/RHEL は nginx、Alpine は nginx が既定
```

権限を、ディレクトリ 755・ファイル 644 に揃え、所有者をワーカーユーザーにします。

```bash
# 所有者をワーカーユーザーに設定
sudo chown -R www-data:www-data /var/www/html

# ディレクトリは 755、ファイルは 644 に揃える
sudo find /var/www/html -type d -exec chmod 755 {} \;
sudo find /var/www/html -type f -exec chmod 644 {} \;

# 設定の文法確認とリロード
sudo nginx -t
sudo systemctl reload nginx

# 確認
curl -I http://localhost/
# HTTP/1.1 200 OK が返れば解決
```

### 原因2：パスの途中の親ディレクトリに実行権限がない

ファイル自体が 644 で正しくても、ルート(`/`)から対象ファイルまでのパス上のどこかのディレクトリに、ワーカーユーザーの実行(検索)権限がないと、Nginx はそこを通り抜けられず 403 になります。見落としやすい典型例です。

`namei -l` を使うと、パスの各構成要素の権限を一覧でき、どこで止まっているかが分かります。ワーカーユーザーとして実行するのが確実です。

```bash
# パス全体の権限をワーカーユーザーの視点で確認
sudo -u www-data namei -l /var/www/site/index.html
# f: /var/www/site/index.html
# drwxr-xr-x root     root     /
# drwxr-xr-x root     root     var
# drwxr-xr-x root     root     www
# drwxr-x--- deploy   deploy   site        ← ここが原因。other に x がない
# -rw-r--r-- deploy   deploy   index.html
```

上の例では `/var/www/site` が 750 で、所有者と所有グループしか入れず、www-data は通れません。対象ディレクトリに、ワーカーユーザーが通れる実行権限を与えます。

```bash
# パス上のディレクトリに検索（実行）権限を付与
sudo chmod o+x /var/www/site

# または、グループ所有を www-data にしてグループに権限を与える
sudo chgrp www-data /var/www/site
sudo chmod g+rx /var/www/site
```

ユーザーのホームディレクトリ配下を配信しようとして 403 になるのも、この原因です。ホームディレクトリの既定権限が制限的(700 など)で、Nginx が通り抜けられないためです。

### 原因3：index ファイルがなく、autoindex も無効

ディレクトリへのリクエストに対し、`index` ディレクティブで指定したファイル(既定では index.html)が存在せず、`autoindex` も off(既定)の場合、Nginx は 403 を返します。エラーログには `directory index of "..." is forbidden` が出ます。

index ファイルを置くか、ディレクトリ一覧を見せてよい場面なら autoindex を有効にします。

```nginx
# 対処A：index ファイルを明示して配信する
server {
    listen 80;
    server_name example.com;
    root /var/www/html;

    location / {
        index index.html index.htm;
        try_files $uri $uri/ =404;
    }
}
```

```nginx
# 対処B：ディレクトリ一覧を見せてよい場合のみ autoindex を有効化
location /downloads/ {
    autoindex on;
    autoindex_exact_size off;   # サイズを読みやすい単位で表示
    autoindex_localtime on;     # ローカル時刻で表示
}
```

autoindex の有効化は、ディレクトリの中身を外部に晒すことになります。公開サーバーでは、見せてよいディレクトリに限定してください。

### 原因4：設定の deny ルールや auth_basic で拒否されている

`deny` ディレクティブ、`auth_basic`、`internal` などの設定が、リクエストを意図的に拒否しているケースです。設定全体を展開して、該当する行を探します。

```bash
# 展開後の設定全体から、アクセス制御に関わる行を探す
sudo nginx -T | grep -nE "deny|allow|auth_basic|internal"
```

たとえば次の設定は、特定 IP 以外を拒否します。

```nginx
location /admin/ {
    allow 192.168.1.0/24;   # 社内ネットワークのみ許可
    deny all;               # それ以外は拒否
}
```

意図した制限ならそのままです。意図せず拒否している場合は、allow の範囲を見直すか、deny ルールを修正します。アクセス元の IP が想定どおりか、ログで確認してください。

### 原因5：SELinux または AppArmor がアクセスを遮っている

Unix の権限が正しくても、強制アクセス制御(SELinux は RHEL/CentOS 系、AppArmor は Ubuntu 系)が、その下の層でアクセスを拒否することがあります。権限を直しても 403 が消えない場合に疑います。

SELinux(RHEL/CentOS 系)の確認と対処です。

```bash
# SELinux が有効か確認
getenforce
# Enforcing なら有効

# Nginx に関する拒否ログを確認
sudo ausearch -m avc -ts recent | grep nginx

# 現在のセキュリティコンテキストを確認
ls -Z /var/www/html/

# Web コンテンツ用の正しいコンテキストを付与する
sudo semanage fcontext -a -t httpd_sys_content_t "/var/www/html(/.*)?"
sudo restorecon -Rv /var/www/html/
```

SELinux を無効化(`setenforce 0`)して解決するのは避けてください。原因のコンテキストを正すのが正しい対処です。

AppArmor(Ubuntu 系)の確認です。

```bash
# AppArmor の拒否がカーネルログに出ていないか確認
sudo dmesg | grep -i apparmor

# Nginx のプロファイル状態を確認
sudo aa-status | grep nginx
```

### 原因6：upstream(PHP-FPM やアプリサーバー)が 403 を返している

Nginx 自体ではなく、`proxy_pass` や `fastcgi_pass` の先(PHP-FPM やアプリケーションサーバー)が 403 を返し、それがそのままクライアントに伝わるケースです。この場合、Nginx の権限やコンテキストは正常で、原因は upstream 側にあります。

upstream 側のログを確認し、ソケットの所有権を点検します。

```bash
# PHP-FPM のログを確認
sudo tail -50 /var/log/php*-fpm.log

# FastCGI ソケットの所有権を確認（Nginx ワーカーが接続できるか）
ls -l /run/php/php-fpm.sock
```

Nginx のエラーログに権限の文言がなく、upstream への接続自体は成功しているのに 403 が返る場合は、この原因を疑います。

## 切り分けの順序

403 は、次の順で原因を一つずつ除外していくと、最短で特定できます。

エラーログを読む。`Permission denied` なら原因1か2、`directory index ... is forbidden` なら原因3。権限を点検する(`namei -l` で親ディレクトリの実行権限まで)。設定を点検する(`nginx -T | grep` で deny/auth_basic を確認)。権限も設定も正しいのに消えないなら SELinux/AppArmor を疑う。それでも残るなら upstream のログを見る。この順に進めれば、6つのどれかに必ず行き着きます。

## それでも解決しない場合

各段階で使う確認コマンドをまとめます。

```bash
# 1. エラーログの該当行
sudo grep -iE "permission denied|forbidden|denied" /var/log/nginx/error.log

# 2. ワーカーユーザーの視点でパス全体の権限を確認
sudo -u www-data namei -l /var/www/html/index.html

# 3. 設定中のアクセス制御を確認
sudo nginx -T | grep -nE "deny|allow|auth_basic|internal"

# 4. SELinux のコンテキストと拒否ログ
ls -Z /var/www/html/
sudo ausearch -m avc -ts recent | grep nginx

# 5. 設定の文法確認とリロード
sudo nginx -t && sudo systemctl reload nginx
```

## Editor's Note

実際の報告例として、ユーザーのホームディレクトリ配下を Nginx で配信しようとして 403 になった事例があります([GitHub gist の議論](https://gist.github.com/jhjguxin/6208474))。なお、この議論は2013年頃の古いもので、当時の Ubuntu 12.04 を前提としています。ただし、ここで扱われているパス権限の考え方は、現在の Nginx でも変わりません。報告者の環境では、ホームディレクトリの既定権限が制限的(700)で、Nginx のワーカーユーザーが親ディレクトリを通り抜けられず 403 になっていました。本記事の原因2にあたります。この議論では、配信対象のファイルすべてに読み取り権限を与えるだけでなく、ルートから対象までのパス上のすべての親ディレクトリに実行(検索)権限が必要だ、という点が解決の核心として挙げられています。ディレクトリ 755・ファイル 644 に揃える対処が広く有効だと共有されています。

この事例が示すとおり、403 の調査では「ファイル単体の権限」だけでなく「パス全体の通り抜け可否」を確認することが重要です。`namei -l` でパスの各段を一度に点検するのが、確実な近道です。