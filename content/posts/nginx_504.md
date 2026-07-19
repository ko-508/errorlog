---
title: "Nginx の 504 エラー：原因と解決策"
date: 2026-05-27
description: "Nginx の 504 Gateway Time-out は、上流（プロキシ先）からの応答を待ちきれずに打ち切ったことを示します。エラーログの文言で、接続確立の時間切れ（connect）か応答待ちの時間切れ（read）かが分かります。proxy_read_timeout の正確な意味（応答全体ではなく無送信の間隔）を踏まえ、遅い処理の特定と実効設定の確認で解決します。"
tags: ["Nginx"]
errorCode: "504"
lastmod: 2026-07-14
service: "Nginx"
error_type: "504"
components: []
related_services: []
top_queries:
- 'nginx 504'
- '504 gateway time-out nginx'
- 'proxy_read_timeout'
---

## 冒頭まとめ

Nginx の 504 Gateway Time-out は、リバースプロキシとして上流（proxy_pass や fastcgi_pass の先）の応答を待ったが、時間内に届かなかったことを示します。時間切れになるタイマーは2つあり、どちらかは[エラーログ](/glossary/エラーログ/)の文言で判別できます。文言が while connecting to upstream で終わっていれば、接続の確立自体が時間切れです（proxy_connect_timeout。原因は経路の問題が典型）。while reading response header from upstream で終わっていれば、接続はできたが応答が返らない時間切れです（proxy_read_timeout。原因は上流の処理の遅さが典型）。

対処の本筋は、時間を延ばすことではなく、どのタイマーがなぜ切れたかを特定することです。応答待ちの時間切れなら遅い処理の改善が本筋で、正当に時間のかかる処理に限って[タイムアウト](/glossary/タイムアウト/)を延ばします。その際、設定したのに効かないという定番の落とし穴（別の location が処理している、リロード漏れ）があるため、実効設定の確認までを対処に含めます。

## エラーの概要

Nginx が自身の既定ページで504を返す場合、ブラウザには「504 Gateway Time-out」（Time-out はハイフン入り）という見出しだけが表示されます。[エラーログ](/glossary/エラーログ/)には次のように記録されます。

```text
2026/07/14 14:32:10 [error] 1234#1234: *567 upstream timed out (110: Connection timed out)
while reading response header from upstream, client: 192.168.1.100, server: example.com,
request: "GET /api/report HTTP/1.1", upstream: "http://127.0.0.1:8080/api/report"
```

関係するタイマーの正確な仕様を押さえておくと、対処を誤りません。公式ドキュメントによると、proxy_connect_timeout（既定60秒）は上流との接続確立に対する制限で、通常75秒を超える値には設定できません。proxy_read_timeout（既定60秒）は応答の読み取りに対する制限ですが、応答全体の転送時間の上限ではなく、連続する2つの読み取り操作の間隔に適用されます。つまり上流が少しずつでもデータを送り続けていれば、全体が60秒を超えても切れません。切れるのは「この時間、何も送られてこなかった」ときです。proxy_send_timeout（既定60秒）は同様に、上流への書き込み操作の間隔に適用されます。PHP-FPM などの FastCGI 構成では、対応する fastcgi_read_timeout などが同じ意味を持ちます。

なお、似た状況で別のコードになる場合があります。上流への接続が即座に拒否された場合（プロセス停止・[ポート](/glossary/ポート/)違い）は504ではなく502です。また、Nginx が待っている間に[クライアント](/glossary/クライアント/)側が先に諦めて切断した場合は、誰にも何も返らず、アクセスログに499が記録されます。

## まず最初に：エラーログの文言でタイマーを特定する

```bash
sudo grep "upstream timed out" /var/log/nginx/error.log | tail -10
```

該当行の末尾近くの文言を読みます。while connecting to upstream なら接続確立の時間切れで、調べるのは経路です（原因2）。while reading response header from upstream なら応答待ちの時間切れで、調べるのは上流の処理時間です（原因1）。

処理時間の実測には、アクセスログに $request_time と $upstream_response_time を加えるのが確実です（設定例は [499 の記事](/posts/nginx_499/)の「処理時間を[ログ](/glossary/ログ/)に出す」を参照してください。504 の調査でもそのまま使えます）。504 の行の時間が proxy_read_timeout の値にほぼ一致していれば、そのタイマーで切れたことの裏付けになります。

## よくある原因と解決手順

### 原因1：上流の応答が遅い（応答待ちの時間切れ）

最も多い原因です。重い[データベース](/glossary/データベース/)処理、大きな[ファイル](/glossary/ファイル/)の生成、外部サービスの呼び出し待ちなどで、上流が proxy_read_timeout の間、何も送信できない状態になっています。

対処は2段階です。第一に、遅い処理の特定と改善です。$upstream_response_time 付きの[ログ](/glossary/ログ/)で、どの [URL](/glossary/url/) の処理が上限に張り付いているかを特定し、上流[アプリケーション](/glossary/アプリケーション/)側で改善します。恒常的に全体が遅いなら、上流の資源（CPU・[メモリ](/glossary/メモリ/)・ワーカー数）の見直しも対象です。

第二に、レポート生成のように正当に時間のかかる処理に限って、[タイムアウト](/glossary/タイムアウト/)を実態に合わせます。全体に長い値を設定すると、本当に異常なとき（上流の応答不能）に[クライアント](/glossary/クライアント/)を長時間待たせることになるため、該当の location に限定するのが安全です。

**Before（既定の60秒で切れる）：**

```nginx
location /api/report {
    proxy_pass http://127.0.0.1:8080;
}
```

**After（時間のかかる処理に限って延長）：**

```nginx
location /api/report {
    proxy_pass http://127.0.0.1:8080;
    proxy_read_timeout 300s;
}
```

PHP-FPM 構成なら、対応する指定は fastcgi_read_timeout です。あわせて、[アプリケーション](/glossary/アプリケーション/)側にも実行時間の制限（PHP の実行時間制限など）がある場合、そちらが先に発動すると症状は504ではなく別の[エラー](/glossary/エラー/)（応答が壊れて502など）に変わります。経路上の制限は Nginx だけでない点に注意してください。

設定後は反映と実効確認までを1セットにします。

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo nginx -T | grep -nE "read_timeout|connect_timeout|send_timeout"
```

「設定したのに60秒で切れ続ける」場合、その60秒という値自体が、書いた設定がその[リクエスト](/glossary/リクエスト/)に効いていないこと（既定値で動いていること）を示しています。対象[リクエスト](/glossary/リクエスト/)を実際に処理している location はどれか（[404 の記事](/posts/nginx_404/)の location 優先順位を参照）、リロードは成功したかを確認してください。

### 原因2：接続の確立が時間切れになる（経路の問題）

while connecting to upstream の504は、上流に接続の要求を送ったのに応答（受諾も拒否も）が返らないまま proxy_connect_timeout が過ぎた状態です。典型は、[ファイアウォール](/glossary/ファイアウォール/)が[通信](/glossary/通信/)を黙って破棄している、経路がなく到達できない、上流ホストが電源断などで無応答、というケースです。上流のプロセスが停止しているだけなら接続は即座に拒否されて502になるため、「504で、しかも connecting」という組み合わせは、拒否すら返ってこない経路の問題を指しています。

切り分けは、Nginx の[サーバー](/glossary/サーバー/)から上流へ直接接続を試すことです。

```bash
curl -m 5 -i http://<上流のアドレス>:<ポート>/
```

即座に拒否されるなら502系の問題（上流のプロセス・[ポート](/glossary/ポート/)）、応答がないまま待たされるなら経路（[ファイアウォール](/glossary/ファイアウォール/)、セキュリティグループ、ルーティング）を疑います。proxy_connect_timeout を延ばすのは対処になりません。健全な経路なら接続確立は一瞬で終わるためで、この504で調整すべきは時間ではなく経路です。

### 原因3：多段構成でのタイマーの不整合

Nginx の手前に別の中継役（[CDN](/glossary/cdn/)、[ロードバランサー](/glossary/ロードバランサー/)、もう1段の Nginx）がいる構成では、どの段のタイマーが最初に切れるかで症状の出方が変わります。手前のタイマーが Nginx の proxy_read_timeout より短ければ、Nginx が待っている間に手前が先に504を返し（このとき Nginx 側には[クライアント](/glossary/クライアント/)切断として499が残ります）、Nginx 側だけ調整しても直りません。原則は、外側ほどタイマーを長くすることです（[クライアント](/glossary/クライアント/) > 手前の中継役 > Nginx > 上流アプリの実行制限）。この整合が取れていると、時間切れは常に最も内側で起き、調査の場所が安定します。

## 切り分けの順序

1. [エラーログ](/glossary/エラーログ/)の upstream timed out の行を読み、connecting（原因2）か reading response header（原因1）かを確定する。行がないのに504が返る場合は、504を返したのが手前の中継役でないか（原因3）、上流自身が504を応答していないかを確認する。
2. reading 側なら、$upstream_response_time 付きの[ログ](/glossary/ログ/)で遅い処理を特定し、上流側で改善する。正当な長時間処理は該当 location に限って read 系[タイムアウト](/glossary/タイムアウト/)を延ばし、nginx -T で実効値を確認する。
3. connecting 側なら、上流への直接接続で経路を確認する。即拒否なら502の問題として切り替える。
4. 多段構成なら、各段のタイマーが外側ほど長い並びになっているかを確認する。

## 確認コマンド集

```bash
# 1. タイムアウトの発生状況と文言（connecting か reading か）を確認
sudo grep "upstream timed out" /var/log/nginx/error.log | tail -10

# 2. アクセスログの 504 の傾向を確認
sudo grep " 504 " /var/log/nginx/access.log | tail -20

# 3. タイムアウト関連の実効設定を確認（include 含む全体から）
sudo nginx -T | grep -nE "read_timeout|connect_timeout|send_timeout"

# 4. 上流への直接接続で、遅いのか・無応答なのか・即拒否なのかを確認
curl -m 5 -o /dev/null -s -w "HTTP:%{http_code} 合計:%{time_total}s\n" http://<上流のアドレス>:<ポート>/

# 5. 設定の文法確認とリロード
sudo nginx -t && sudo systemctl reload nginx
```

## Editor's Note

「設定したのに効かない」の実例として、海外の技術 Q&A サイトの報告があります（[qna.habr.com の質問](https://qna.habr.com/q/156375)、2014年）。約3分かかるスクリプトのために fastcgi_read_timeout 600 を設定したのに、ブラウザにはちょうど1分で 504 Gateway Time-out が表示され、[エラーログ](/glossary/エラーログ/)には upstream timed out (110: Connection timed out) while reading response header from upstream が記録されている、という内容です。注目すべきは時間です。切れているのは設定した600秒ではなく、既定値と同じ60秒です。つまりこの記録は、書いた設定がその[リクエスト](/glossary/リクエスト/)の処理に使われていない（別の location が処理しているか、設定が読み込まれていない）ことを、[ログ](/glossary/ログ/)の数字そのものが示している実例です。古い報告ですが、fastcgi_read_timeout と proxy_read_timeout のこの挙動は現行の公式ドキュメントの仕様と変わりません。504 の調査で値を延ばす前に実効設定を確認すべき理由が、ここに凝縮されています。

504 は「どのタイマーが切れたか」を[ログ](/glossary/ログ/)が名指ししてくれる[エラー](/glossary/エラー/)です。文言と実測時間を読み、経路・処理・設定の三択のどれかを確定してから手を打つことが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*