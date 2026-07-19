---
title: "Nginx の 502 エラー：原因と解決策"
date: 2026-05-27
description: "Nginx の 502 Bad Gateway は、上流サーバーへの接続に失敗したか、上流から不正な応答を受け取ったことを示します。タイムアウトは502ではなく504であり、原因が異なります。エラーログの文言（Connection refused、no live upstreams、prematurely closed、too big header、SSL_do_handshake）から6つの原因を切り分けて解決します。"
tags: ["Nginx"]
errorCode: "502"
lastmod: 2026-07-15
service: "Nginx"
error_type: "502"
components: ["Reverse Proxy"]
related_services: ["PHP-FPM", "Gunicorn", "uWSGI"]
trend_incident: false
---

## 冒頭まとめ

Nginx の 502 Bad Gateway は、リバースプロキシとしての Nginx が上流（proxy_pass や fastcgi_pass の接続先）への接続に失敗したか、接続はできたものの応答として解釈できないデータを受け取ったことを示します。原因はほぼ確実に[エラーログ](/glossary/エラーログ/)の文言で特定できます。connect() failed (111: Connection refused) なら上流が起動していないか接続先の指定違い、unix ソケットへの (2: No such file or directory) や (13: Permission denied) ならソケットの[パス](/glossary/パス/)か[権限](/glossary/権限/)、no live upstreams なら全上流[サーバー](/glossary/サーバー/)の一時除外、upstream prematurely closed connection なら上流の応答途中の切断、upstream sent too big header なら応答[ヘッダー](/glossary/ヘッダー/)のバッファ超過、[SSL](/glossary/ssl/)_do_handshake() failed なら上流との [TLS](/glossary/tls/) ハンドシェイク失敗です。

502と誤解されやすい隣のコードも押さえておくと迷いません。上流の応答待ちの時間切れは502ではなく504です（[エラーログ](/glossary/エラーログ/)に upstream timed out と残ります）。limit_req などの制限超過は503、応答前に[クライアント](/glossary/クライアント/)側が切断した場合はアクセスログに499が残ります。「遅いから502」という説明を見かけますが、Nginx のソースコード上、時間切れは504に明示的に割り当てられており、502になるのはそれ以外の接続失敗と不正応答です。

## エラーの概要

Nginx は上流への中継に失敗したとき、失敗の種類ごとに返す[ステータスコード](/glossary/ステータスコード/)を割り当てます。この割り当てはソースコード（ngx_http_upstream.c の ngx_http_upstream_next）で確認でき、時間切れ（NGX_[HTTP](/glossary/http/)_UPSTREAM_FT_TIMEOUT）は504、接続失敗・不正な応答[ヘッダー](/glossary/ヘッダー/)・全[サーバー](/glossary/サーバー/)除外などそれ以外の失敗は既定の分岐として502になります。つまり502は「時間内に、しかし正常には、上流とやり取りできなかった」ことの総称です。

ブラウザに表示されるデフォルトのエラーページ：

```text
502 Bad Gateway
nginx
```

アクセスログの出力例：

```text
192.0.2.10 - - [15/Jul/2026:10:23:45 +0900] "GET /api/users HTTP/1.1" 502 157 "-" "Mozilla/5.0"
```

[エラーログ](/glossary/エラーログ/)（/var/log/nginx/error.log）の出力例。この upstream: に続く接続先と、括弧内の失敗理由が切り分けの起点です：

```text
2026/07/15 10:23:45 [error] 1234#1234: *567 connect() failed (111: Connection refused) while connecting to upstream, client: 192.0.2.10, server: example.com, request: "GET /api/users HTTP/1.1", upstream: "http://127.0.0.1:8000/api/users"
```

## まず最初に：エラーログの文言で6つに分岐する

connect() failed (111: Connection refused) なら原因1（上流が接続を受けていない）です。接続先が unix: で始まり (2: No such file or directory) または (13: Permission denied) なら原因2（ソケットの[パス](/glossary/パス/)・[権限](/glossary/権限/)）で、後者はログレベルが [crit] で記録されます。no live upstreams なら原因3（全[サーバー](/glossary/サーバー/)の一時除外）、upstream prematurely closed connection while reading response header from upstream なら原因4（上流の途中切断）、upstream sent too big header なら原因5（応答[ヘッダー](/glossary/ヘッダー/)のバッファ超過）、[SSL](/glossary/ssl/)_do_handshake() failed なら原因6（上流との [TLS](/glossary/tls/) 失敗）です。upstream timed out (110: Connection timed out) が出ている場合、それは502ではなく504の調査です（後述の補足へ）。

## よくある原因と解決手順

### 原因1：上流が接続を受けていない（Connection refused）

上流のアプリケーションサーバーが起動していないか、起動していても Nginx の接続先（アドレス・[ポート](/glossary/ポート/)）と一致していない状態です。両方を一度に確認できます。

**Before（[エラー](/glossary/エラー/)が起きている状態）：**

```bash
# 上流が実際にどこで待ち受けているかを確認
ss -ltnp
# → 8000 番で待ち受けるプロセスが存在しない、または別ポートで待ち受けている

# Nginx を介さず直接叩いて再現確認
curl -v http://127.0.0.1:8000/
# → Connection refused
```

**After（修正後）：**

```bash
# 上流を起動する（例：Gunicorn）
gunicorn --bind 127.0.0.1:8000 wsgi:app

# または Nginx 側の接続先を実際の待ち受けに合わせる
# upstream backend { server 127.0.0.1:8000; }  # 実際のポートに修正
sudo nginx -t && sudo systemctl reload nginx
```

[コンテナ](/glossary/コンテナ/)や別ホストの上流では、待ち受けアドレスの範囲も確認します。上流が 127.0.0.1 にのみバインドしていると、別のホストや[コンテナ](/glossary/コンテナ/)からの接続は届きません。ss -ltnp の Local Address 欄が 127.0.0.1:8000 か 0.0.0.0:8000 かで判別できます。

### 原因2：unix ソケットのパスまたは権限が合っていない

fastcgi_pass unix:/... や proxy_pass http://unix:/... の構成で、ソケットファイルが存在しない（2: No such file or directory）か、Nginx のワーカープロセスに読み書き[権限](/glossary/権限/)がない（13: Permission denied、ログレベル [crit]）状態です。PHP-FPM 構成の502で最も多い形です。

**Before（[エラー](/glossary/エラー/)が起きている状態）：**

```bash
# エラーログの unix: に書かれたパスをそのまま確認
ls -l /run/php/php-fpm.sock
# → 存在しない（パス違い）、または
# srw-rw---- 1 root root ... （nginx のワーカーが読めない所有権）
```

**After（修正後）：**

```ini
; PHP-FPM のプール設定（www.conf）で所有権を Nginx のワーカーに合わせる
listen = /run/php/php-fpm.sock
listen.owner = www-data
listen.group = www-data
listen.mode = 0660
```

```bash
sudo systemctl restart php-fpm
ls -l /run/php/php-fpm.sock
# srw-rw---- 1 www-data www-data ... となれば接続できる
```

[パス](/glossary/パス/)違いの場合は、Nginx 側とアプリ側の設定が指す[パス](/glossary/パス/)を突き合わせて一致させます。所有権と[権限](/glossary/権限/)が正しいのに (13) が消えない場合は、SELinux や AppArmor がソケットへのアクセスを遮断している可能性があり、監査[ログ](/glossary/ログ/)（audit.log）の確認に切り替えます。

### 原因3：全上流サーバーが一時除外されている（no live upstreams）

upstream ブロックに複数の[サーバー](/glossary/サーバー/)を並べた構成で、直近の失敗によりすべての[サーバー](/glossary/サーバー/)が「利用不可」と記録され、送る先がなくなった状態です。公式文書のとおり、各[サーバー](/glossary/サーバー/)は fail_timeout の期間内に max_fails 回失敗すると、fail_timeout の間だけ除外されます。既定は max_fails=1、fail_timeout=10秒 で、何を失敗と数えるかは proxy_next_upstream 系の設定に従います。既定値では1回の失敗で10秒間除外されるため、上流全体が短時間不安定になるだけで no live upstreams が連鎖的に発生します。

なお、この文言は複数[サーバー](/glossary/サーバー/)構成でのみ発生します。公式文書のとおり、upstream 内の[サーバー](/glossary/サーバー/)が1台だけの場合は max_fails と fail_timeout が無視され、利用不可の扱いになりません。

**Before（[エラー](/glossary/エラー/)が起きている状態）：**

```text
2026/07/15 10:24:01 [error] 1234#1234: *570 no live upstreams while connecting to upstream, client: 192.0.2.10, server: example.com, request: "GET /api/users HTTP/1.1", upstream: "http://backend/api/users"
```

**After（考え方と設定例）：**

```nginx
upstream backend {
    # 一時的な失敗で即座に除外したくない場合は閾値を明示する
    server 10.0.0.11:8000 max_fails=3 fail_timeout=30s;
    server 10.0.0.12:8000 max_fails=3 fail_timeout=30s;
}
```

ただし本筋は、除外の引き金になった元の失敗（各[サーバー](/glossary/サーバー/)への connect 失敗や時間切れ）を解消することです。no live upstreams の直前の[ログ](/glossary/ログ/)に、個々の[サーバー](/glossary/サーバー/)に対する失敗が必ず記録されているので、そちらを原因1・2・4の手順で潰します。

### 原因4：上流が応答の途中で接続を閉じた（prematurely closed）

Nginx が応答[ヘッダー](/glossary/ヘッダー/)を待っている間に、上流側から接続が閉じられた状態です。Nginx 側で分かる事実は「応答が完成する前に接続が閉じた」ことまでで、なぜ閉じたのかは上流側の[ログ](/glossary/ログ/)にしか残りません。典型的には、[リクエスト](/glossary/リクエスト/)処理中の[アプリケーション](/glossary/アプリケーション/)のクラッシュ、[メモリ](/glossary/メモリ/)不足によるプロセスの強制終了（OOM Kill）、上流側のワーカー管理機構が処理時間超過のワーカーを強制終了するケースです。最後のケースは「重い[リクエスト](/glossary/リクエスト/)のときだけ502になる」という形で現れ、504と紛らわしいですが、上流の管理機構が Nginx より先にワーカーを打ち切ると prematurely closed の502になります。

**Before（[エラー](/glossary/エラー/)が起きている状態）：**

```text
2026/07/15 10:25:12 [error] 1234#1234: *580 upstream prematurely closed connection while reading response header from upstream, client: 192.0.2.10, server: example.com, request: "POST /api/report HTTP/1.1", upstream: "http://127.0.0.1:8000/api/report"
```

**After（調査の進め方）：**

```bash
# 該当時刻の上流側ログを確認する（例：systemd 管理のアプリ）
journalctl -u myapp --since "10:24" --until "10:26"
# クラッシュのトレースバック、ワーカー強制終了の記録、OOM の痕跡を探す

# OOM Kill の確認
dmesg -T | grep -i "out of memory"
```

対処は上流側の原因に応じて、クラッシュの修正、[メモリ](/glossary/メモリ/)割り当ての見直し、ワーカーの許容処理時間の延長（各アプリケーションサーバーの公式文書で設定名を確認）のいずれかになります。

### 原因5：応答ヘッダーがバッファに収まらない（too big header）

上流からの応答の最初の部分（応答[ヘッダー](/glossary/ヘッダー/)）を読むバッファは proxy_buffer_size で決まり、公式文書のとおり既定値は1メモリページ（環境により 4K または 8K）です。応答[ヘッダー](/glossary/ヘッダー/)がこれを超えると、公式文書に明記されているとおり応答は不正なものとして扱われ、502になります。巨大な Set-Cookie を発行するアプリや、セッション情報を[ヘッダー](/glossary/ヘッダー/)に詰め込む構成で発生します。

**Before（[エラー](/glossary/エラー/)が起きている状態）：**

```text
2026/07/15 10:26:30 [error] 1234#1234: *590 upstream sent too big header while reading response header from upstream, client: 192.0.2.10, server: example.com, request: "GET /login HTTP/1.1", upstream: "http://127.0.0.1:8000/login"
```

**After（修正後）：**

```nginx
location / {
    proxy_pass http://backend;
    proxy_buffer_size 16k;   # 実際のヘッダーサイズに合わせて引き上げる
}
```

```bash
# 実際のヘッダーサイズを確認してから値を決める
curl -s -D - -o /dev/null http://127.0.0.1:8000/login | wc -c
```

なお、応答本文が大きいこと自体は502の原因になりません。バッファに収まらない本文は一時[ファイル](/glossary/ファイル/)に書き出して処理される設計です。502に関係するのは[ヘッダー](/glossary/ヘッダー/)を読む proxy_buffer_size だけです。

### 原因6：上流との TLS ハンドシェイクに失敗している（SSL_do_handshake）

proxy_pass https://... の構成で、Nginx が [TLS](/glossary/tls/) [クライアント](/glossary/クライアント/)として上流とのハンドシェイクに失敗した状態です。頻出は2つで、いずれも[エラーログ](/glossary/エラーログ/)の括弧内の文言で見分けます。

第一に wrong version number です。文言に反して [TLS](/glossary/tls/) [バージョン](/glossary/バージョン/)設定の誤りであることはまれで、実態の多くは「https:// を指定した接続先が実際には平文 [HTTP](/glossary/http/) で待ち受けている」ケースです。[TLS](/glossary/tls/) の応答を期待した Nginx が平文の [HTTP](/glossary/http/) 応答を受け取り、解釈できずにこの文言になります。

第二に SNI の未送信です。接続先が SNI（接続時にホスト名を伝える [TLS](/glossary/tls/) の拡張）を前提に[証明書](/glossary/証明書/)を選ぶ[サーバー](/glossary/サーバー/)の場合、proxy_ssl_server_name on を明示しない限り Nginx は SNI を送らないため、ハンドシェイクが拒否されます。

**Before（[エラー](/glossary/エラー/)が起きている状態）：**

```text
2026/07/15 10:27:45 [error] 1234#1234: *600 SSL_do_handshake() failed (SSL: error:0A000410:SSL routines::ssl/tls alert handshake failure:SSL alert number 40) while SSL handshaking to upstream, client: 192.0.2.10, server: example.com, request: "GET / HTTP/1.1", upstream: "https://203.0.113.5:443/"
```

**After（修正後）：**

```nginx
location / {
    proxy_pass https://backend.example.com;
    proxy_ssl_server_name on;               # SNI を送る
    proxy_ssl_name backend.example.com;     # IP 直指定の場合は名前を明示
}
```

```bash
# Nginx の外から同じ条件で再現確認する
openssl s_client -connect 203.0.113.5:443 -servername backend.example.com
# -servername の有無で結果が変わるなら SNI の問題
# 平文で応答が返るなら wrong version number の構図（proxy_pass を http:// に直す）
```

なお、上流の証明書検証（proxy_ssl_verify）は既定で無効です。自己署名証明書が原因の502は、証明書検証を明示的に有効化している構成でのみ起こります。「とりあえず proxy_ssl_verify off を足す」という対処を見かけますが、既定が off である以上、明示的に on にしていない環境では意味を持ちません。

## 補足：このコードではない類似エラー

上流の応答待ちの時間切れは504です。[エラーログ](/glossary/エラーログ/)には upstream timed out (110: Connection timed out) と残り、調査対象は proxy_read_timeout などの時間設定と上流の処理時間になります（[Nginx の 504 の記事](/posts/nginx_504/)）。limit_req・limit_conn の制限超過や、設定に残った return 503 は503です（[Nginx の 503 の記事](/posts/nginx_503/)）。応答を返す前に[クライアント](/glossary/クライアント/)側から切断された場合はアクセスログに499が残ります。上流が遅いことが引き金になる点は502の原因4と似ていますが、切ったのが上流なら502、[クライアント](/glossary/クライアント/)なら499です（[Nginx の 499 の記事](/posts/nginx_499/)）。上流[アプリケーション](/glossary/アプリケーション/)の内部[エラー](/glossary/エラー/)は、上流が自分で500を返す限り Nginx はそれをそのまま中継します（[Nginx の 500 の記事](/posts/nginx_500/)）。また、ALB や [API](/glossary/api/) Gateway が返す502は Nginx とは別の仕組みで発生します（[AWS の 502 の記事](/posts/aws_502/)）。GitHub [API](/glossary/api/) など外部サービス側の502は、こちらの設定では解決できません（[GitHub API の 502 の記事](/posts/github_api_502/)）。

## 切り分けの順序

1. [エラーログ](/glossary/エラーログ/)を開き、該当時刻の行の括弧内の文言を読む。timed out なら504の調査へ、それ以外なら文言で原因1〜6に分岐する。
2. Connection refused と unix ソケット系は、[エラーログ](/glossary/エラーログ/)の upstream: に書かれた接続先を ss・ls -l・curl でそのまま検証する（原因1・2）。
3. no live upstreams は、直前の[ログ](/glossary/ログ/)にある個々の[サーバー](/glossary/サーバー/)への失敗を先に解決する（原因3）。
4. prematurely closed は同時刻の上流側[ログ](/glossary/ログ/)に調査を移す（原因4）。
5. too big header は実際のヘッダーサイズを測ってから proxy_buffer_size を決める（原因5）。
6. [SSL](/glossary/ssl/)_do_handshake は openssl s_client で Nginx の外から再現し、平文/[TLS](/glossary/tls/) の取り違えか SNI かを特定する（原因6）。

## 確認コマンド集

```bash
# 1. エラーログから502の原因文言を抽出
grep -E "connect\(\) (to|failed)|no live upstreams|prematurely closed|too big header|SSL_do_handshake" /var/log/nginx/error.log | tail -20

# 2. アクセスログで502の発生パターンを確認
awk '$9 == 502 {print $4, $7}' /var/log/nginx/access.log | tail -20

# 3. 上流の待ち受け状態を確認
ss -ltnp

# 4. Nginx を介さず上流を直接叩く
curl -v http://127.0.0.1:8000/

# 5. unix ソケットの存在と権限を確認
ls -l /run/php/php-fpm.sock

# 6. 実効設定から upstream 定義とバッファ設定を確認
sudo nginx -T | grep -E "upstream|server |proxy_buffer|proxy_ssl" 

# 7. 上流との TLS を外から再現
openssl s_client -connect <上流アドレス>:443 -servername <ホスト名>
```

## Editor's Note

原因2の実例として、2014年に公開された詳細な記録があります（[How to fix connect() to php5-fpm.sock failed (13: Permission denied)](https://websistent.com/fix-connect-to-php5-fpm-sock-failed-13-permission-denied-while-connecting-to-upstream-nginx-error/)）。PHP を 5.5.12 に更新した直後からサイトが 502 Bad Gateway になり、[エラーログ](/glossary/エラーログ/)には connect() to unix:/var/run/php5-fpm.sock failed (13: Permission denied) が [crit] で記録されていた、という事例です。原因は設定ミスではなく、PHP 側の仕様変更でした。PHP 5.5.12 は権限昇格の脆弱性（CVE-2014-0185）の修正として、FPM のソケットの既定権限を誰でも書き込める 0666 から 0660 に変更しており（PHP 公式 ChangeLog と php-src の修正[コミット](/glossary/コミット/)で確認できます）、所有者を明示していなかった環境では更新した瞬間に Nginx がソケットへ接続できなくなりました。解決は listen.owner と listen.group の明示です。10年以上前の事例ですが、ソケットの所有権と[権限](/glossary/権限/)が接続の可否を決める仕組み、listen.owner・listen.group・listen.mode で解決するという対処は、現行の PHP-FPM でもそのまま一致します。「何も設定を変えていないのに、更新したら502」という症状の裏に既定値の変更がある、という更新起因の定番の構図を示す記録です。

502の[エラーログ](/glossary/エラーログ/)は、接続先・失敗理由・タイミングをすべて一行に記録してくれます。推測で設定をいじる前に、まず括弧内の文言を読むことが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*