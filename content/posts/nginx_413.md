---
title: "Nginx の 413 エラー：原因と解決策"
date: 2026-07-08
description: "Nginx の 413 Request Entity Too Large は、リクエスト本文が client_max_body_size の上限（既定1MB）を超えたときに返されます。ファイルのアップロード失敗の定番原因です。エラーログに記録された実際のバイト数をもとに、適切な場所へ適切な上限を設定して解決します。"
tags: ["Nginx"]
errorCode: "413"
lastmod: 2026-07-08
service: "Nginx"
error_type: "413"
components: []
related_services: []
top_queries:
- '413 request entity too large nginx'
- 'nginx 413'
- 'client_max_body_size'
---

## 冒頭まとめ

Nginx の 413 Request Entity Too Large は、リクエスト本文の大きさが `client_max_body_size` の上限を超えたときに返されます。上限の既定値は 1MB と小さいため、ファイルのアップロード機能を作ると最初にぶつかりやすいエラーです。対処はほぼ `client_max_body_size` の調整に集約されますが、落とし穴が2つあります。1つは設定を書く場所で、より内側（location など）に別の指定があるとそちらが使われるため、書いたのに効かないという状況が起きます。もう1つは Nginx の先にいるアプリケーション側の上限で、Nginx の上限を上げるだけでは足りない場合があります。

必要な上限の値は推測しなくて済みます。Nginx が413を返したとき、エラーログに実際に送られようとしたバイト数が記録されるからです。まずエラーログを読み、実測値をもとに上限を決めます。

## エラーの概要

413 は、リクエストの本文（ファイルのアップロード内容やフォームの送信内容）が、サーバーの受け入れ上限を超えたことを示すコードです。Nginx では `client_max_body_size` がこの上限を定めており、公式ドキュメントのとおり既定値は 1m（1MB）です。なお、HTTP の現行仕様（RFC 9110）ではこのコードの名称は Content Too Large に改められていますが、Nginx の既定エラーページの文言は「413 Request Entity Too Large」です。

注意すべき点として、公式ドキュメントには、ブラウザはこのエラーを正しく表示できない場合があるという注記があります。つまり利用者の画面では、413のページが出るとは限らず、送信が途中で失敗した・接続が切れた、といった413と分からない形で現れることがあります。アップロードだけが原因不明で失敗するという相談を受けたら、まずサーバー側のログで413が出ていないかを確認する価値があります。

アクセスログ（既定の combined 形式）には次のように記録されます。

```
192.168.1.100 - - [08/Jul/2026:11:20:15 +0900] "POST /upload HTTP/1.1" 413 183 "-" "Mozilla/5.0"
```

## まず最初に：エラーログを読む

アクセスログで413を確認したら、同時刻のエラーログを見ます。

```bash
sudo grep "too large" /var/log/nginx/error.log | tail -10
```

`client intended to send too large body: 15728640 bytes` のような行があれば、Nginx 自身が `client_max_body_size` の検査で拒否しています。行末の数字が、実際に送られようとした本文のバイト数です（この例では15MB）。必要な上限をこの実測値から決められるので、原因1・2に進みます。チャンク転送（本文の大きさを事前に知らせない送り方）の場合は `client intended to send too large chunked body` という文言になります。

該当時刻にこの行がない場合、その413は Nginx が返したものではなく、`proxy_pass` 先のアプリケーションが返した413をそのまま中継している可能性が高いです（原因3）。

## よくある原因と解決手順

### 原因1：client_max_body_size が既定の1MBのまま

設定のどこにも `client_max_body_size` を書いていない場合、上限は既定の1MBです。1MBを超えるファイルのアップロードはすべて413になります。

**Before（既定のままの設定）：**

```nginx
server {
    listen 80;
    server_name example.com;

    location /upload {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

**After（アップロード先にだけ20MBの上限を設定）：**

```nginx
server {
    listen 80;
    server_name example.com;

    location /upload {
        client_max_body_size 20m;
        proxy_pass http://127.0.0.1:8080;
    }
}
```

上限の値は、エラーログに記録された実測のバイト数と、想定する最大ファイルサイズから決めます。サイト全体ではなく、必要な location だけ上げるのが安全です。なお `client_max_body_size 0;` で検査自体を無効にできますが、上限がなくなるため、値を決めて設定するほうが確実です。

設定後は文法確認をしてから反映します。

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 原因2：設定した場所が違う・内側の指定に上書きされている

`client_max_body_size` は http・server・location の3か所に書けます。同じ指定が複数の場所にある場合、リクエストに対してより内側の指定が使われます。http ブロックで大きな値を設定していても、該当の server や location に小さい指定が残っていれば、そちらが効きます。設定ファイルが include で分割されていると、この見落としが起きやすくなります。

書いたはずなのに効かないときは、実際に読み込まれている設定の全体を確認します。

```bash
sudo nginx -T | grep -n "client_max_body_size"
```

出力されたすべての指定と、その場所（どの server・どの location か）を確認し、対象リクエストを処理するブロックに意図した値が届いているかを確かめてください。もう1つの見落としが、設定を反映していないケースです。編集後に `sudo systemctl reload nginx` を実行したか、また `nginx -t` が成功しているか（文法エラーがあると古い設定のまま動き続けます）を確認します。

### 原因3：上流アプリケーション側の上限を超えている

Nginx をリバースプロキシとして使っている場合、Nginx の検査を通っても、その先のアプリケーション自身の受け入れ上限で拒否されることがあります。アプリケーションが413を返した場合、既定ではそのままクライアントに中継されます（`proxy_intercept_errors` の既定は off）。

見分け方は原因1・2と同じで、Nginx のエラーログです。`client intended to send too large body` の行がないのに413が返っているなら、発生源は上流です。この場合、`client_max_body_size` をいくら上げても解決しません。対処する場所は上流アプリケーションの設定で、アップロード上限にあたる項目はフレームワークやアプリケーションごとに異なるため、使っているアプリケーションの公式ドキュメントで確認してください。

逆に、上流の上限を上げたのに413が続く場合は、手前の Nginx の `client_max_body_size` が小さいままというケースが典型です。経路上のすべての段階（Nginx が多段になっていれば各段）に、それぞれ上限があることを前提に確認します。

## 切り分けの順序

1. アクセスログで対象リクエストのコードが413であることを確認する。
2. エラーログを見る。`too large body` の行があれば Nginx 自身の拒否で、記録されたバイト数が必要サイズの実測値になる。行がなければ上流由来（原因3）。
3. Nginx 自身の拒否なら、`nginx -T` で `client_max_body_size` の指定箇所をすべて洗い出し、対象リクエストを処理するブロックに効いている値を特定する（原因1・2）。
4. 適切な場所に適切な値を設定し、`nginx -t` で文法確認のうえ反映する。再度アップロードして、エラーログの `too large body` が消えたことを確認する。

## 確認コマンド集

```bash
# 1. アクセスログの 413 の傾向を確認
sudo grep " 413 " /var/log/nginx/access.log | tail -20

# 2. エラーログから本文サイズ超過の行を抽出（実際のバイト数が分かる）
sudo grep "too large" /var/log/nginx/error.log | tail -10

# 3. 有効な設定全体から client_max_body_size の指定箇所を洗い出す
sudo nginx -T | grep -n "client_max_body_size"

# 4. 上限超過を再現して確認（10MBのテストファイルを送信）
dd if=/dev/zero of=/tmp/test10m.bin bs=1M count=10
curl -o /dev/null -s -w "%{http_code}\n" -F "file=@/tmp/test10m.bin" http://localhost/upload

# 5. 設定の文法確認とリロード
sudo nginx -t && sudo systemctl reload nginx
```

## Editor's Note

手前の上限と奥の上限が別々に存在することを示す実例として、Atlassian の公開課題管理システムへの報告があります（[CONFSERVER-52301](https://jira.atlassian.com/browse/CONFSERVER-52301)、2017年）。Confluence（社内向けの情報共有ツール）を Nginx のリバースプロキシ経由で使う構成で、Nginx が既定の1MBのままだと、Confluence 側で設定した添付ファイルの上限より小さいファイルでも413で失敗する、という内容です。報告では、Nginx の `client_max_body_size` を Confluence 側の添付上限と揃えるべきこと、揃えれば上限超過時に Confluence 自身の分かりやすいエラー表示が機能することが指摘されています。また、添付ファイルだけでなくページ編集の通信でも、既定の1MBでは足りず413になる場合があることも記録されています。2017年の報告と古いものですが、`client_max_body_size` の仕様（既定1MB、超過で413）は現行の公式ドキュメントと変わっていません。

413の対処は一見「上限を上げるだけ」ですが、実際には、どこの上限に当たったのかを特定することが本題です。エラーログの実測バイト数と `nginx -T` の洗い出しを使えば、推測に頼らずに特定できます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*