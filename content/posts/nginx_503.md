---
title: "Nginx の 503 エラー：原因と解決策"
date: 2026-05-27
description: "Nginx の 503 Service Unavailable の原因は、limit_req・limit_conn による制限超過、設定に残った return 503、上流アプリケーションが返す503の中継の3系統です。接続失敗は502、タイムアウトは504であり、503とは原因が異なります。エラーログの文言から切り分けて解決します。"
tags: ["Nginx"]
errorCode: "503"
lastmod: 2026-07-02
service: "Nginx"
error_type: "503"
components: []
related_services: []
top_queries:
- '503 service temporarily unavailable nginx'
- 'nginx 503'
- '503 nginx'
---

## 冒頭まとめ

Nginx の 503 Service Unavailable の原因は、ほぼ次の3系統のいずれかです。第一に、`limit_req`（[リクエスト](/glossary/リクエスト/)頻度の制限）や `limit_conn`（同時接続数の制限）の超過で、Nginx 自身が既定で 503 を返します。第二に、メンテナンス用に設定した `return 503` が設定内に残っているケースです。第三に、`proxy_pass` 先の上流[アプリケーション](/glossary/アプリケーション/)自身が 503 を返し、Nginx がそれをそのまま中継しているケースです。

注意すべき点として、「[バックエンド](/glossary/バックエンド/)に接続できない」ときに Nginx が返すのは 503 ではなく 502 Bad Gateway、応答待ちで時間切れになったときは 504 Gateway Timeout です。503 の調査だと思っていたものが実は 502 や 504 の問題だった、ということが起こりやすいので、まずアクセスログで実際の[ステータスコード](/glossary/ステータスコード/)を確かめ、次に[エラーログ](/glossary/エラーログ/)の文言で原因を絞り込みます。

## エラーの概要

503 Service Unavailable は、[サーバー](/glossary/サーバー/)が一時的に[リクエスト](/glossary/リクエスト/)を処理できない状態を示します。Nginx をリバースプロキシとして使っている場合、似た状況で返るコードが3つあり、区別が重要です。上流への接続自体に失敗した場合（プロセス停止、[ポート](/glossary/ポート/)違い、接続拒否など）は 502、接続はできたが応答が時間内に返らなかった場合は 504、そして上流が「処理できない」と自ら 503 を応答した場合はその 503 がそのまま中継されます。加えて、上流と無関係に Nginx 自身が制限機能によって 503 を返す場合があります。

Nginx が自身の既定ページで 503 を返す場合、ブラウザには「503 Service Temporarily Unavailable」という見出しだけが表示されます。「The server is temporarily unable to service your request due to maintenance downtime or capacity problems.」のような説明文が表示されているなら、それは Nginx の既定ページの文言ではなく、上流の別の[サーバー](/glossary/サーバー/)が生成した 503 を中継している可能性が高いです（原因3）。

アクセスログ（既定の combined 形式）には次のように記録されます。

```
192.168.1.100 - - [02/Jul/2026:10:45:32 +0900] "GET /api/users HTTP/1.1" 503 190 "-" "Mozilla/5.0"
```

## まず最初に：エラーログを読む

アクセスログで対象[リクエスト](/glossary/リクエスト/)のコードが本当に 503 であることを確かめたら、同時刻の[エラーログ](/glossary/エラーログ/)を見ます。503 の原因は[エラーログ](/glossary/エラーログ/)の文言でほぼ特定できます。

```bash
# 直近のエラーを表示
sudo tail -50 /var/log/nginx/error.log

# 制限機能による拒否の行だけを抽出
sudo grep "limiting" /var/log/nginx/error.log
```

`limiting requests, excess: ... by zone "..."` とあれば `limit_req` による拒否、`limiting connections by zone "..."` とあれば `limit_conn` による拒否です（原因1）。どのゾーンの制限に当たったかも同じ行に書かれています。

該当時刻に何も記録がない場合、設定内の `return 503`（原因2）か、上流からの 503 の中継（原因3）を疑います。どちらも Nginx にとっては[エラー](/glossary/エラー/)ではなく正常な処理なので、[エラーログ](/glossary/エラーログ/)には残りません。

逆に、該当時刻に `connect() failed (111: Connection refused) while connecting to upstream` や `upstream timed out` が記録されている場合、その[リクエスト](/glossary/リクエスト/)への応答は 503 ではなく 502 または 504 のはずです。調べているコードを取り違えていないか、アクセスログに戻って確認してください（後述の補足を参照）。

## よくある原因と解決手順

### 原因1：limit_req・limit_conn の制限超過

`limit_req` は、ゾーンに設定した頻度を超えた[リクエスト](/glossary/リクエスト/)を遅延させ、`burst`（超過分の待ち枠）も使い切ると拒否します。`limit_conn` は同時接続数が上限を超えたとき拒否します。どちらも拒否時の応答コードは既定で 503 です（`limit_req_status`、`limit_conn_status` の既定値）。

よくあるのが、burst を指定していないために正当な利用者まで拒否されるケースです。burst の既定は 0 なので、設定した頻度をわずかでも超えた瞬間に 503 が返ります。1つのページを開くとブラウザは CSS・画像・スクリプトなどを続けて取得するため、rate=1r/s のような厳しい設定では通常の閲覧でも即座に超過します。

**Before（正当な閲覧でも503が出やすい設定）：**

```nginx
http {
    limit_req_zone $binary_remote_addr zone=one:10m rate=1r/s;

    server {
        location / {
            limit_req zone=one;
        }
    }
}
```

**After（瞬間的な集中を burst で吸収する設定）：**

```nginx
http {
    limit_req_zone $binary_remote_addr zone=one:10m rate=10r/s;

    server {
        location / {
            limit_req zone=one burst=20 nodelay;
        }
    }
}
```

`nodelay` は、burst 枠内の[リクエスト](/glossary/リクエスト/)を遅延させずに即時処理するための指定です。また、拒否時のコードは `limit_req_status 429;` のように変更でき、[レート制限](/glossary/レート制限/)の応答として 429 Too Many Requests を返す運用も可能です。

もう1つの落とし穴が共有メモリゾーンの枯渇です。ゾーンの空きがなくなると最も古い状態から削除されますが、それでも新しい状態を作れない場合、その[リクエスト](/glossary/リクエスト/)は拒否されます。公式ドキュメントによると、状態1件は64ビット環境で128[バイト](/glossary/バイト/)を占め、1MB のゾーンに約8千件です。クライアント数に対してゾーンが小さすぎないか確認してください。

### 原因2：設定に残った return 503（メンテナンスモード）

メンテナンス作業のために `return 503` を入れ、戻し忘れているケースです。この場合、Nginx にとっては指示どおりの正常動作なので、[エラーログ](/glossary/エラーログ/)には何も残りません。

```bash
# 有効な設定全体から 503 に関わる記述を探す
sudo nginx -T | grep -nE "return 503|error_page 503|limit_req|limit_conn"
```

`return 503` が見つかったら、それが意図した設定かを確認します。メンテナンスページを整備したい場合は、`error_page` と `internal` を組み合わせるのが標準的な構成です。

```nginx
server {
    location / {
        return 503;
    }

    error_page 503 /maintenance.html;

    location = /maintenance.html {
        root /var/www/html;
        internal;
    }
}
```

`internal` を付けた location は内部処理専用になり、利用者が `/maintenance.html` を直接開くことはできなくなります。メンテナンス終了時は `return 503` の行を外し、文法確認のうえ反映します。

### 原因3：上流アプリケーションが503を返している

`proxy_pass` 構成では、上流の応答コードは既定でそのままクライアントに中継されます（`proxy_intercept_errors` の既定は off）。上流の[アプリケーション](/glossary/アプリケーション/)がメンテナンスモードだったり、過負荷への保護機能で自ら 503 を返していたりすれば、Nginx を経由した応答も 503 になります。

見分けるポイントは2つです。第一に、Nginx の[エラーログ](/glossary/エラーログ/)に該当時刻の記録がないこと。第二に、応答の本文が Nginx の既定ページ（「503 Service Temporarily Unavailable」のみ）と違うことです。上流に直接[リクエスト](/glossary/リクエスト/)を送って比べるのが確実です。

```bash
# Nginx 経由の応答
curl -i http://example.com/api/users

# 上流に直接送った応答（同じ503が返れば上流由来と確定）
curl -i http://127.0.0.1:8080/api/users
```

原因が上流由来と確定したら、対処の場所は Nginx ではなく上流[アプリケーション](/glossary/アプリケーション/)側です。上流の[ログ](/glossary/ログ/)と稼働状態を確認してください。どの[リクエスト](/glossary/リクエスト/)で上流が何を返したかを Nginx 側にも残したい場合は、`log_format` に `$upstream_status`（上流から得た応答コードを保持する[変数](/glossary/変数/)）を加えておくと、以後の切り分けが楽になります。

上流の 503 をそのまま見せたくない場合は、`proxy_intercept_errors on;` と `error_page` を組み合わせて、Nginx 側で用意したページに差し替えられます。

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_intercept_errors on;
    error_page 503 /maintenance.html;
}

location = /maintenance.html {
    root /var/www/html;
    internal;
}
```

## 補足：503だと思っていたら502・504だったとき

「[バックエンド](/glossary/バックエンド/)が落ちると503になる」という説明を見かけますが、Nginx では正しくありません。上流への接続に失敗した場合（プロセス停止、[ポート](/glossary/ポート/)違い、全[サーバー](/glossary/サーバー/)利用不可）に返るのは 502 で、[エラーログ](/glossary/エラーログ/)には `connect() failed` や `no live upstreams` が記録されます。応答待ちの時間切れは 504 で、`upstream timed out` が記録されます。これらに該当する場合は、[Nginx の 502 エラー](/posts/nginx_502/)、[Nginx の 504 エラー](/posts/nginx_504/)の記事を参照してください。

## 切り分けの順序

1. アクセスログで対象[リクエスト](/glossary/リクエスト/)のコードを確認する。503 でなければ該当コードの調査に切り替える。
2. [エラーログ](/glossary/エラーログ/)の該当時刻を見る。`limiting requests` / `limiting connections` があれば原因1。どのゾーンかも行内で特定できる。
3. 記録がなければ `nginx -T` で `return 503`・`error_page 503` の有無を確認する（原因2）。
4. それも見つからなければ、上流への直接[リクエスト](/glossary/リクエスト/)で応答を比較する（原因3）。上流由来なら対処は上流側で行う。

設定を修正したら、文法確認をしてから反映します。

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 確認コマンド集

```bash
# 1. アクセスログの 503 の傾向を確認
sudo grep " 503 " /var/log/nginx/access.log | tail -20

# 2. エラーログから制限機能による拒否を抽出
sudo grep "limiting" /var/log/nginx/error.log | tail -20

# 3. 有効な設定全体から 503 に関わる記述を探す（include 含む）
sudo nginx -T | grep -nE "return 503|error_page 503|limit_req|limit_conn"

# 4. Nginx 経由と上流直接の応答を比較
curl -i http://example.com/api/users
curl -i http://127.0.0.1:8080/api/users

# 5. 設定の文法確認とリロード
sudo nginx -t && sudo systemctl reload nginx
```

## Editor's Note

`limit_req` の挙動を実測付きで確かめた例として、2024年1月の技術ブログ記事があります（[Request limiting in Nginx - iBug](https://ibug.io/blog/2024/01/nginx-limit-req/)）。筆者が rate=1r/s、burst=5 の設定に対して10件の[リクエスト](/glossary/リクエスト/)を連続送信したところ、burst 枠に収まった最初の6件は 200 が返り（一部は遅延あり）、枠を超えた7件目以降は即座に 503 で拒否される出力が記録されています。本記事の原因1で述べた「burst を超えた分が既定で 503 になる」挙動そのものの実例です。なお筆者は最終的に `limit_req_status 403` で応答コードを変更する構成を採っており、拒否時のコードが運用に合わせて変更可能であることの実例にもなっています。個人の技術ブログですが、実測出力の内容は現行の公式ドキュメントの記述と一致しており、挙動の説明として信頼できると判断しました。

503 は「Nginx 自身の制限」「意図的な設定」「上流の応答」のどれなのかで対処の場所がまったく変わります。コードの見た目で判断せず、[エラーログ](/glossary/エラーログ/)の文言と上流への直接確認から原因の所在を特定することが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*