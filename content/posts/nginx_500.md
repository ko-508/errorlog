---
title: "Nginx の 500 エラー：原因と解決策"
date: 2026-01-01
description: "Nginx が返す 500 には、Nginx 自身が生成したものと、上流が返した 500 をそのまま中継しただけのものがあり、error.log に行が出るかどうかで見分けられます。上流への接続失敗や時間切れは 500 ではなく 502 と 504 です。Nginx 自身の 500 で最も多いのは内部リダイレクトの循環で、回数の上限は10回と定義されています。"
tags: ["Nginx"]
errorCode: "500"
lastmod: 2026-07-28
service: "Nginx"
error_type: "500"
components: ["HTTP Core", "Upstream"]
related_services: ["PHP-FPM", "uWSGI", "Reverse Proxy"]
trend_incident: false
---

## 冒頭まとめ

Nginx が返す 500 Internal Server Error には、出どころが2つあります。Nginx 自身が処理を続けられずに生成したものと、上流の[アプリケーション](/glossary/アプリケーション/)が返した 500 をそのまま中継しただけのものです。この2つは対処が完全に別なので、最初に切り分ける必要があります。

見分け方は単純です。Nginx 自身が生成した場合、`error.log` に必ず理由を書いた行が出ます。中継しただけの場合、`access.log` には 500 が記録されますが、`error.log` に Nginx 発の行は出ません。つまり、[ログ](/glossary/ログ/)を2つ並べて、同じ時刻に対応する行があるかどうかを見れば、責任の所在はその場で決まります。

先に否定しておくべき筋が1つあります。上流への接続が失敗した場合や、上流の応答が遅れて打ち切られた場合は 500 になりません。Nginx のソースでは、接続の失敗は 502 Bad Gateway、時間切れは 504 Gateway Timeout として確定されます。`connect() failed (111: Connection refused)` の行を見て 500 の原因だと考えるのは、この分岐と食い違います。502 と 504 の調べ方はそれぞれ別記事にあります（[Nginx の 502 の記事](/posts/nginx_502/)、[504 の記事](/posts/nginx_504/)）。

Nginx 自身が 500 を生成する場面で最も多いのは、内部リダイレクトの循環です。Nginx は1つの[リクエスト](/glossary/リクエスト/)の中で内部的に転送できる回数を10回と定めており、これを使い切ると循環とみなして 500 を返します。この上限は `NGX_HTTP_MAX_URI_CHANGES` として定義されています。

## エラーの概要

利用者側に表示されるのは、次の定型の応答です。この画面だけでは、Nginx 発か[アプリケーション](/glossary/アプリケーション/)発かは判別できません。

```html
<html>
<head><title>500 Internal Server Error</title></head>
<body>
<center><h1>500 Internal Server Error</h1></center>
<hr><center>nginx/1.28.0</center>
</body>
</html>
```

判別の材料は `error.log` です。内部リダイレクトの循環なら、次のいずれかの形で記録されます。

```text
2026/07/28 10:23:45 [error] 1234#1234: *567 rewrite or internal redirection cycle
while internally redirecting to "/index.html", client: 192.0.2.10,
server: example.com, request: "GET /page HTTP/1.1", host: "example.com"
```

一時[ファイル](/glossary/ファイル/)を作れない場合は、深刻度がさらに1段上の `[crit]` で記録されます。

```text
2026/07/28 10:23:45 [crit] 1234#1234: *567 open() "/var/lib/nginx/body/0000000001"
failed (13: Permission denied), client: 192.0.2.10, server: example.com
```

一方、上流が返した 500 を中継しただけの場合、`error.log` には何も出ません。`access.log` にだけ 500 が並びます。

```text
192.0.2.10 - - [28/Jul/2026:10:23:45 +0900] "POST /api/users HTTP/1.1" 500 179 "-" "curl/8.5.0"
```

この「`error.log` が沈黙している 500」は、Nginx の設定をいくら見直しても直りません。調べる先は[アプリケーション](/glossary/アプリケーション/)側の[ログ](/glossary/ログ/)です。

## まず最初に：error.log に行があるかを見る

第一に、`access.log` で 500 が出た時刻を特定します。第二に、同じ時刻の `error.log` を見ます。第三に、行があれば深刻度と文言を読み、無ければ上流の[ログ](/glossary/ログ/)へ移ります。

行があった場合、深刻度で当たりが付きます。`[error]` なら処理の流れの問題、`[crit]` なら[ファイル](/glossary/ファイル/)の作成や[権限](/glossary/権限/)といった環境側の問題です。一時[ファイル](/glossary/ファイル/)の作成失敗は `[crit]` で記録されると Nginx のソースで定義されています。

文言では次を目印にします。`rewrite or internal redirection cycle` なら原因1、`Permission denied` を含むなら原因2、`subrequests cycle` なら原因4です。`connect() failed` や `upstream timed out` が出ている場合、応答は 500 ではなく 502 か 504 のはずなので、そもそも見ている行が違います。

## よくある原因と解決手順

### 原因1：内部リダイレクトが循環している

`try_files` や `rewrite`、`error_page` による転送先が、また同じ場所へ戻ってくる状態です。Nginx は転送のたびに残り回数を1つ減らし、0になると循環と判断して 500 を返します。上限は10回です。

文言が2種類あり、どちらが出たかで発生源が分かります。`rewrite or internal redirection cycle while processing "..."` は、書き換え後の[パス](/glossary/パス/)で処理をやり直した結果の循環です。`rewrite or internal redirection cycle while internally redirecting to "..."` は、`@名前` の形で指定した転送先へ移ろうとした際の循環です。ソースでも別々の箇所に定義されています。

最も多いのは、`try_files` の最後の候補が存在しない、あるいは自分自身に戻ってくる形です。

**Before（最後の候補が存在せず、循環する）：**

```nginx
server {
    root /var/www/html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
# /index.html が無いと、その要求がまた location / に入り、10回で 500
```

**After（存在する候補を最後に置く、または明示的に404を返す）：**

```nginx
server {
    root /var/www/html;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

[アプリケーション](/glossary/アプリケーション/)へ渡す構成なら、最後の候補を処理できる場所にします。

```nginx
location / {
    try_files $uri $uri/ /index.php$is_args$args;
}

location ~ \.php$ {
    try_files $uri =404;
    fastcgi_pass 127.0.0.1:9000;
    include fastcgi_params;
}
```

`location ~ \.php$` の側に `try_files $uri =404;` を置くのが要点です。これが無いと、存在しない `.php` への要求が[プロキシ](/glossary/プロキシ/)側へ渡り、そこから戻ってきてまた同じ場所に入る、という形の循環が起きえます。

なお、上流が `X-Accel-Redirect` で転送先を指示する構成でも同じ循環が起きます。指示された先がまた上流へ渡る設定になっていると、往復が続きます。転送先の[パス](/glossary/パス/)は `internal;` を付けた専用の場所にして、そこからは上流へ戻らないようにします。

### 原因2：一時ファイルを作れない

要求の本体や上流からの応答が大きい場合、Nginx はいったん一時[ファイル](/glossary/ファイル/)に書き出します。この作成や書き込みに失敗すると 500 になります。要求本体の処理で失敗した場合に 500 を返すことは、ソースにも定義されています。

原因のほとんどは[権限](/glossary/権限/)です。`error.log` に `[crit]` と `Permission denied` が出ていれば、この形です。

**Before（[ディレクトリ](/glossary/ディレクトリ/)の所有者が実行利用者と違う）：**

```bash
ls -ld /var/lib/nginx/body
# drwx------ 2 root root ... /var/lib/nginx/body
```

**After（実行利用者に合わせる）：**

```bash
grep -E "^user" /etc/nginx/nginx.conf     # 実行利用者を確認する
sudo chown -R www-data:www-data /var/lib/nginx
sudo nginx -s reload
```

置き場所は設定で変えられます。容量不足が原因の場合は、空きのある場所を指定します。

```nginx
client_body_temp_path /var/cache/nginx/client_temp;
proxy_temp_path       /var/cache/nginx/proxy_temp;
```

[容量](/glossary/容量/)も確認してください。書き込めない理由は[権限](/glossary/権限/)だけとは限りません。

```bash
df -h /var/lib/nginx
```

強制[アクセス制御](/glossary/アクセス制御/)が有効な[環境](/glossary/環境/)では、所有者と[権限](/glossary/権限/)が正しくても拒否されることがあります。その場合、記録は Nginx ではなく システム側の[ログ](/glossary/ログ/)に出ます。

### 原因3：上流が返した500を中継している

`error.log` に Nginx 発の行が無く、`access.log` にだけ 500 が並ぶ場合です。Nginx は正しく動いており、上流が 500 を返したのをそのまま渡しています。

この場合、Nginx の設定を触っても何も変わりません。調べる先は上流です。

```bash
# 上流へ直接要求して、同じ 500 が返るかを確かめる
curl -i http://127.0.0.1:9000/api/users

# 上流側のログを見る（例：PHP-FPM）
sudo tail -50 /var/log/php-fpm/error.log
```

上流へ直接要求して同じ結果になれば、Nginx は無関係だと確定します。切り分けとしてはこれが最も速い手です。

利用者に定型の画面を見せたい場合は、中継してくる 500 を差し替えられます。ただし、これは表示の問題を隠すだけで、原因は残ります。

```nginx
proxy_intercept_errors on;
error_page 500 /50x.html;

location = /50x.html {
    root /usr/share/nginx/html;
    internal;
}
```

### 原因4：サブリクエストが循環している

`ssi` や `auth_request`、`mirror` のように、1つの要求の中から別の要求を発生させる仕組みを使っている場合に起きます。Nginx はこの入れ子の上限を50回と定めており、これを超えると `subrequests cycle while processing "..."` を記録して処理を打ち切ります。

自分自身を含めてしまう指定が典型です。`auth_request` の宛先が、また `auth_request` の対象になっている場合などがこれにあたります。認証用の場所を分けて、その場所自体には[認証](/glossary/認証/)を掛けないようにします。

```nginx
location /private/ {
    auth_request /auth;
    proxy_pass http://backend;
}

location = /auth {
    internal;
    proxy_pass http://auth-backend;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
}
```

## 補足：500ではないもの

上流への接続が確立できない場合は 502 です。`connect() failed (111: Connection refused)` や `no live upstreams` が該当します。上流の応答が設定した時間内に返らない場合は 504 で、`upstream timed out` が記録されます。この2つの分岐は Nginx のソースで確定しており、500 とは別物です（[Nginx の 502 の記事](/posts/nginx_502/)、[504 の記事](/posts/nginx_504/)）。

上流が返した応答の見出し部分が大きすぎる場合、Nginx は `upstream sent too big header` を記録しますが、この場合も 500 ではなく、別の上流へ回すか 502 として扱われます。緩和するには `proxy_buffer_size` を大きくします。

要求された[ファイル](/glossary/ファイル/)が存在しない場合は 404、読み取り[権限](/glossary/権限/)が無い場合は 403 です（[Nginx の 404 の記事](/posts/nginx_404/)、[403 の記事](/posts/nginx_403/)）。ただし、`try_files` の転送先が存在しないことによる循環は 404 ではなく 500 になります。ここは間違えやすい境界です。

同時接続数や要求数の制限に掛かった場合は 503 です（[Nginx の 503 の記事](/posts/nginx_503/)）。

## 切り分けの順序

1. `access.log` で 500 の時刻を特定する。
2. 同じ時刻の `error.log` を見る。行が無ければ上流発の 500 なので、上流の[ログ](/glossary/ログ/)へ移る。
3. 行があれば深刻度を見る。`[error]` なら処理の流れ、`[crit]` なら[ファイル](/glossary/ファイル/)や[権限](/glossary/権限/)。
4. `rewrite or internal redirection cycle` なら、文言の後半で発生源を絞る。`while processing` は書き換え後の再処理、`while internally redirecting to` は `@名前` への転送。
5. 循環なら `try_files` の最後の候補を確認する。存在しない[パス](/glossary/パス/)を最後に置いていないか、自分自身に戻っていないかを見る。
6. `Permission denied` なら、一時[ファイル](/glossary/ファイル/)の置き場所の所有者と空き[容量](/glossary/容量/)を確認する。
7. `connect() failed` や `upstream timed out` が出ているなら、それは 500 の行ではない。502 か 504 の調査に切り替える。

## 確認コマンド集

```bash
# 1. 設定の文法と、読み込まれている設定ファイルを確認する
sudo nginx -t

# 2. 500 が出た時刻の error.log を見る
sudo grep -n " 500 " /var/log/nginx/access.log | tail -5
sudo tail -100 /var/log/nginx/error.log

# 3. 循環と権限の行だけを抜き出す
sudo grep -E "redirection cycle|subrequests cycle|Permission denied" /var/log/nginx/error.log

# 4. 一時ファイルの置き場所の所有者と空き容量を確認する
grep -E "^user" /etc/nginx/nginx.conf
ls -ld /var/lib/nginx/body /var/lib/nginx/proxy
df -h /var/lib/nginx

# 5. 上流へ直接要求して、Nginx の関与を切り分ける
curl -i http://127.0.0.1:9000/api/users

# 6. 実行中の設定で、どの location に入るかを追う
sudo nginx -T | grep -A5 "location /"
```

## Editor's Note

原因1で挙げた2つの文言の違いは、Nginx の内部の作りに根ざしています。これを外側から裏付ける記録が、Nginx 向けの第三者拡張である ModSecurity の改修提案に残っています（[fix: reset context in internal redirect](https://github.com/owasp-modsecurity/ModSecurity-nginx/pull/273)）。

この提案の説明には、Nginx の2つの転送の仕組みが、それぞれ異なる段階から処理をやり直すことが書かれています。[パス](/glossary/パス/)を書き換える側は、[サーバー](/glossary/サーバー/)単位の書き換えの段階から。`@名前` の形の転送は、場所単位の書き換えの段階から。拡張側から見ると、どちらの場合も自分が保持していた文脈が消えるため、同じ要求なのに新しい要求として扱われてしまう、という不具合につながっていました。2022年に提案され、その後も議論が続いています。

利用する側にとっての含意は2つあります。1つは、循環の文言が2種類あるのは表記の揺れではなく、通ってきた経路が本当に違うということ。もう1つは、内部リダイレクトを挟むと、第三者の拡張から見た状態が[初期化](/glossary/初期化/)されうるということです。[認証](/glossary/認証/)や検査の拡張を入れている構成で、転送を経由した要求だけ挙動が変わる場合は、この性質を疑う価値があります。

500 は、Nginx が出す[エラー](/glossary/エラー/)の中では情報が少なく見えます。しかし、`error.log` に行があるかどうかという一点だけで、調べる相手が Nginx なのか[アプリケーション](/glossary/アプリケーション/)なのかは決まります。設定を触り始める前に、まずそこを確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*