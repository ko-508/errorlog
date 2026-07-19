---
title: "Nginx の 404 エラー：原因と解決策"
date: 2026-05-25
description: "Nginx の 404 Not Found は、リクエストされたリソースが見つからないときに返されます。root のパス違い、alias の末尾スラッシュ、try_files の誤設定、location の取り合い、upstream 由来の5つの原因を、エラーログの有無から切り分けて解決します。"
tags: ["Nginx"]
errorCode: "404"
lastmod: 2026-07-02
service: "Nginx"
error_type: "404"
components: []
related_services: []
top_queries:
- 'nginx 404'
- 'nginx 404 not found'
---

## 冒頭まとめ

Nginx の 404 Not Found は、[リクエスト](/glossary/リクエスト/)されたリソースが見つからないときに返されます。原因はほぼ次の5つのいずれかです。`root` の[パス](/glossary/パス/)が実際の[ファイル](/glossary/ファイル/)配置と合っていない、`alias` の末尾スラッシュの不一致で[パス](/glossary/パス/)結合がずれている、`try_files` の誤設定、意図しない `location` ブロックが[リクエスト](/glossary/リクエスト/)を処理している、そして `proxy_pass` 先の[アプリケーション](/glossary/アプリケーション/)自身が 404 を返しているケースです。調査の分かれ道は[エラーログ](/glossary/エラーログ/)です。`/var/log/nginx/error.log` に `No such file or directory` の行があれば Nginx 自身の[パス](/glossary/パス/)解決の問題(原因1〜3)、なければ振り分けか上流の問題(原因4〜5)を疑います。

## エラーの概要

404 Not Found は、[サーバー](/glossary/サーバー/)が[リクエスト](/glossary/リクエスト/)を受け取ったものの、対応するリソースを見つけられなかった状態です。アクセス自体を拒否された 403 Forbidden とは異なります。この2つは[エラーログ](/glossary/エラーログ/)の文言で区別できます。404 は `open()` の失敗として `(2: No such file or directory)` と記録され、403 は `(13: Permission denied)` や `is forbidden` と記録されます。[ファイル](/glossary/ファイル/)が実在しても読み取り[権限](/glossary/権限/)がなければ、返るのは 404 ではなく 403 です。

Nginx が自身の既定ページで 404 を返す場合、ブラウザには「404 Not Found」という見出しと nginx の署名だけが表示されます。もし「The requested [URL](/glossary/url/) /xxx was not found on this server.」のような説明文が表示されているなら、それは Nginx の既定ページの文言ではありません。上流の別の[サーバー](/glossary/サーバー/)や[アプリケーション](/glossary/アプリケーション/)が生成した 404 をそのまま中継している可能性が高く、これ自体が切り分けの手がかりになります(原因5)。

アクセスログ(既定の combined 形式)には次のように記録されます。日付と時刻はコロンで区切られます。

```
192.168.1.100 - - [02/Jul/2026:10:23:45 +0900] "GET /app/users HTTP/1.1" 404 162 "-" "Mozilla/5.0"
```

## まず最初に：エラーログを読む

アクセスログは「404 が起きた」ことしか教えてくれません。なぜ起きたかは[エラーログ](/glossary/エラーログ/)が示します。設定をいじる前に、まず[エラーログ](/glossary/エラーログ/)の該当行を確認します。

```bash
# 直近のエラーを表示
sudo tail -50 /var/log/nginx/error.log

# ファイル不存在に関する行だけを抽出
sudo grep -i "no such file" /var/log/nginx/error.log
```

見るべきポイントは2つです。

該当時刻に `open() "/var/www/html/app/users" failed (2: No such file or directory)` のような行があれば、Nginx が静的[ファイル](/glossary/ファイル/)としてその[パス](/glossary/パス/)を開こうとして失敗しています。[ログ](/glossary/ログ/)に出ている絶対[パス](/glossary/パス/)が「Nginx が実際に探した場所」なので、これを見れば `root` や `alias` の設定と実際の配置のどちらがずれているかを直接確認できます(原因1〜3)。

該当時刻に[エラーログ](/glossary/エラーログ/)の行がないのにアクセスログには 404 が残っている場合、Nginx は自分で[ファイル](/glossary/ファイル/)を探して失敗したのではありません。`try_files` の `=404` 指定で意図的に返しているか、`proxy_pass` 先の応答をそのまま中継しているかのどちらかが典型です(原因3〜5)。なお `log_not_found off;` が設定されていると[ファイル](/glossary/ファイル/)不存在が[エラーログ](/glossary/エラーログ/)に記録されなくなるため、設定を確認してから判断してください。

## よくある原因と解決手順

### 原因1：root のパスが実際のファイル配置と合っていない

公式ドキュメントのとおり、`root` を使う場合のファイルパスは「root の値 + [リクエスト](/glossary/リクエスト/) URI」の単純な連結で作られます。設定では `/var/www/html` を指しているのに実際の[ファイル](/glossary/ファイル/)が `/home/app/public` にある、といったずれがあれば 404 になります。

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

実際の[ファイル](/glossary/ファイル/)が `/home/app/public/index.html` にある場合、Nginx は `/var/www/html/index.html` を探して失敗します。[エラーログ](/glossary/エラーログ/)にはその探した[パス](/glossary/パス/)がそのまま記録されます。

**After（修正後）：**

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        root /home/app/public;
    }
}
```

修正の際は、推測ではなく[エラーログ](/glossary/エラーログ/)の[パス](/glossary/パス/)と `ls` の結果を突き合わせてください。Linux の一般的なファイルシステムは[パス](/glossary/パス/)の大文字小文字を区別するため、`Index.html` と `index.html` の違いでも 404 になります。

### 原因2：alias の末尾スラッシュの不一致でパス結合がずれる

`alias` は `root` と結合規則が異なります。[リクエスト](/glossary/リクエスト/) URI のうち location に一致した部分が、alias の値に「置き換え」られます。このため location とalias の末尾のスラッシュの有無が揃っていないと、置き換え結果の[パス](/glossary/パス/)が崩れます。

**Before（[エラー](/glossary/エラー/)が起きる設定）：**

```nginx
location /static/ {
    alias /var/www/static;
}
```

`/static/css/style.css` への[リクエスト](/glossary/リクエスト/)では、一致部分 `/static/`（スラッシュ含む）が `/var/www/static` に置き換わり、結果は `/var/www/staticcss/style.css` になります。[ディレクトリ](/glossary/ディレクトリ/)区切りが消えてしまい、存在しない[パス](/glossary/パス/)として 404 が返ります。

**After（修正後）：**

```nginx
location /static/ {
    alias /var/www/static/;
}
```

末尾を揃えることで `/var/www/static/css/style.css` に正しく解決されます。なお公式ドキュメントは、alias の値の末尾が location と同じ文字列で終わる場合（例：`location /images/` に対して `alias /data/w3/images/`）は、`alias` ではなく `root /data/w3;` と書くほうがよいとしています。

### 原因3：try_files の誤設定

`try_files` は列挙した[パス](/glossary/パス/)の存在を順に確認し、最初に見つかったもので[リクエスト](/glossary/リクエスト/)を処理します。よくある誤解が2つあります。

1つ目は `=404` の意味です。`try_files $uri =404;` は「$uri が存在しなければ 404 を返す」という意図的な指定です。シングルページアプリケーション（1枚の HTML に画面遷移をまとめる作りのウェブアプリ）のように、どの[パス](/glossary/パス/)でも `index.html` を返したい場合にこの設定のままだと、直リンクやリロードがすべて 404 になります。

**Before（SPA で 404 になる設定）：**

```nginx
location / {
    root /var/www/html;
    try_files $uri $uri/ =404;
}
```

**After（存在しない[パス](/glossary/パス/)を index.html に転送）：**

```nginx
location / {
    root /var/www/html;
    try_files $uri $uri/ /index.html;
}
```

2つ目は最後の[引数](/glossary/引数/)の扱いです。公式ドキュメントのとおり、最後の[引数](/glossary/引数/)だけは存在確認の対象ではなく「どれも見つからなかったときの内部転送先」です。ここに存在しない URI（例：`/notfound.html`）を書くと、転送先でまた同じ location が処理して転送し……という循環になります。Nginx は内部転送を1[リクエスト](/glossary/リクエスト/)あたり10回までに制限しており、超えると返るのは 404 ではなく 500 Internal Server Error で、[エラーログ](/glossary/エラーログ/)には `rewrite or internal redirection cycle` と記録されます。「404 対策のつもりの設定が 500 を生む」典型なので、転送先の[ファイル](/glossary/ファイル/)が実在することを必ず確認してください。

### 原因4：意図しない location ブロックがリクエストを処理している

404 の対象[リクエスト](/glossary/リクエスト/)を、想定と別の location が処理していることがあります。location の選択は記述順ではなく次の優先順位で決まります。まず `=`（完全一致）が最優先、次に前方一致の中で最長のものが記憶され、その location に `^~` が付いていれば確定、付いていなければ正規表現（`~`、`~*`）が[設定ファイル](/glossary/設定ファイル/)の記述順に評価され、最初に一致したものが勝ちます。正規表現がどれも一致しなければ、記憶していた前方一致が使われます。

例えば次の設定では、`/downloads/manual.png` は `location /downloads/` ではなく正規表現の location が処理します。そちらに `root` の指定がなければ、意図しない場所（継承された root）を探して 404 になります。

```nginx
location /downloads/ {
    root /data/files;
}

location ~* \.(gif|jpg|png)$ {
    # root の指定がない場合、上位の root（既定は html）を継承する
    expires 30d;
}
```

どの location が処理しているか不明なときは、`nginx -T` で実際に読み込まれている設定の全体（include された[ファイル](/glossary/ファイル/)を含む）を確認し、上記の優先順位に沿って追ってください。

### 原因5：proxy_pass 先のアプリケーションが 404 を返している

Nginx をリバースプロキシとして使っている場合、404 の発生源が Nginx ではなく上流（[プロキシ](/glossary/プロキシ/)先）の[アプリケーション](/glossary/アプリケーション/)であることは珍しくありません。[エラーログ](/glossary/エラーログ/)に `open()` の失敗が残っていないのにアクセスログに 404 がある、既定ページと違う本文が返っている、という場合はまずこれを疑います。上流の応答コードは既定でそのまま[クライアント](/glossary/クライアント/)に中継されます（`proxy_intercept_errors` の既定は off）。

このとき確認すべきなのが、`proxy_pass` の[パス](/glossary/パス/)書き換えです。公式ドキュメントのとおり、`proxy_pass` に URI 部分を付けた場合、[リクエスト](/glossary/リクエスト/) URI のうち location に一致した部分がその URI に置き換えられて上流に渡ります。URI 部分を付けない場合は、[リクエスト](/glossary/リクエスト/) URI がそのまま渡ります。

```nginx
# パターンA：/api/users へのリクエストは、上流に /users として渡る
location /api/ {
    proxy_pass http://127.0.0.1:3000/;
}

# パターンB：/api/users へのリクエストは、上流にも /api/users のまま渡る
location /api/ {
    proxy_pass http://127.0.0.1:3000;
}
```

上流アプリのルート定義が `/users` なのにパターンBで `/api/users` を渡していれば、アプリ側のルーティングに一致せず 404 が返ります。逆も同様です。切り分けは、上流アプリのアクセスログで「実際にどの[パス](/glossary/パス/)が届いたか」を確認するのが確実です。

## 切り分けの順序

手当たり次第に設定を変えるのではなく、次の順で範囲を狭めます。

1. [エラーログ](/glossary/エラーログ/)を見る。`(2: No such file or directory)` の行があれば、そこに出ている[パス](/glossary/パス/)と実際の配置を突き合わせる（原因1〜3）。行がなければ 2 へ。
2. `nginx -T` で有効な設定の全体を確認し、対象[リクエスト](/glossary/リクエスト/)をどの server・location が処理するかを優先順位に沿って特定する（原因4）。
3. その location が `proxy_pass` なら、上流アプリの[ログ](/glossary/ログ/)で届いた[パス](/glossary/パス/)と応答コードを確認する（原因5）。
4. `try_files` がある場合は、`=404` の意図と、最後の転送先の実在を確認する（原因3）。

設定を修正したら、文法確認をしてから反映します。文法[エラー](/glossary/エラー/)があると古い設定のまま動き続け、修正が反映されない錯覚に陥ります。

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 確認コマンド集

```bash
# 1. エラーログからファイル不存在の行を抽出（実際に探したパスが分かる）
sudo grep -i "no such file" /var/log/nginx/error.log | tail -20

# 2. アクセスログの 404 の傾向を確認
sudo grep " 404 " /var/log/nginx/access.log | tail -20

# 3. 実際に読み込まれている設定の全体を確認（include 含む）
sudo nginx -T

# 4. 設定内の root / alias / try_files / proxy_pass を一覧
sudo nginx -T | grep -nE "root|alias|try_files|proxy_pass|location"

# 5. 対象パスの実在と名前（大文字小文字）を確認
ls -la /var/www/html/

# 6. 応答を再現して確認
curl -I http://localhost/app/users

# 7. 設定の文法確認とリロード
sudo nginx -t && sudo systemctl reload nginx
```

## Editor's Note

実際の報告例として、`try_files` の設定が原因でサイト全体が閲覧できなくなった事例があります（[DigitalOcean コミュニティの質問](https://www.digitalocean.com/community/questions/php-nginx-500-error-help-fix-please)）。なお、この議論は2015年頃の古いもので、PHP 5 時代の環境を前提としていますが、ここで扱われている `try_files` の挙動は現在の Nginx 公式ドキュメントの記述と変わりません。報告者の環境では `try_files $uri $uri/ /index.html;` と設定していたものの、転送先の `/index.html` が実在せず、[エラーログ](/glossary/エラーログ/)に `rewrite or internal redirection cycle while internally redirecting to "/index.html"` が記録されて 500 になっていました。本記事の原因3で述べた「最後の[引数](/glossary/引数/)は存在確認されない」ことの実例です。回答では、PHP アプリなら転送先を `/index.php` にする、静的サイトなら `index.html` が実在し読み取れることを確認する、という切り分けが示されています。

この事例が示すとおり、404 と try_files をめぐる設定ミスは、症状が 404 ではなく 500 として現れることがあります。エラーコードの見た目だけで判断せず、[エラーログ](/glossary/エラーログ/)の文言から原因をたどることが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*