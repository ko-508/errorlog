---
title: "Nginxの405：POSTが失敗する原因と対処法"
date: 2026-11-05
draft: false
description: "Nginxの405 Not Allowedは、静的ファイルへPOSTした場合などに返ります。要求のメソッドとURL、location、アプリへの転送設定を確認する手順を説明します。"
tags: ["Nginx"]
images: ["og/posts/nginx_405.png"]
errorCode: "405"
service: "Nginx"
error_type: "405"
components: ["ngx_http_static_module", "ngx_http_proxy_module"]
related_services: ["HTTP", "PHP-FPM"]
trend_incident: false
---

## 冒頭まとめ

Nginx で `405 Not Allowed` が返ったら、要求の方法を表す[メソッド](/glossary/メソッド/)と、送信先の [URL](/glossary/url/) を[確認](/glossary/確認/)してください。フォームや [API](/glossary/api/) の POST が、アプリではなく静的[ファイル](/glossary/ファイル/)の[処理](/glossary/処理/)へ渡っている可能性があります。

Nginx の静的[ファイル](/glossary/ファイル/)の[処理](/glossary/処理/)は、存在する通常の[ファイル](/glossary/ファイル/)への POST を 405 で拒否します。POST を禁止する[設定](/glossary/設定/)を書いていなくても起きます。送信内容を[保存](/glossary/保存/)・[処理](/glossary/処理/)したい場合は、その[処理](/glossary/処理/)を担当するアプリへ要求が届くように直します。

## エラーの概要

Nginx の既定のエラーページには、次の見出しが使われます。

```text
405 Not Allowed
```

これは[既定ページの実装](https://github.com/nginx/nginx/blob/master/src/http/ngx_http_special_response.c)にある文言です。ただし、画面に Nginx の名前が出ていても、Nginx の静的[ファイル](/glossary/ファイル/)[処理](/glossary/処理/)が拒否したとは限りません。転送先のアプリが返した[エラー](/glossary/エラー/)や、独自のエラーページが関わる構成もあります。

例えば、`/contact.html` を表示する [GET](/glossary/get/) が成功しても、同じ [URL](/glossary/url/) にフォームを POST できるとは限りません。[HTML](/glossary/html/) [ファイル](/glossary/ファイル/)を返す[処理](/glossary/処理/)と、フォームの内容を受け取る[処理](/glossary/処理/)は別です。

## まず最初に：送信先とメソッドを確認する

フォームなら `action` と `method`、JavaScript からの要求なら [URL](/glossary/url/) と `method` の指定を[確認](/glossary/確認/)します。送信先に `.html` や `.json` が付いているかだけで判断せず、その [URL](/glossary/url/) をどの[処理](/glossary/処理/)へ渡す[設定](/glossary/設定/)になっているかを調べてください。

管理者は、稼働中の Nginx の[設定](/glossary/設定/)を[確認](/glossary/確認/)します。

```bash
sudo nginx -T
```

[公式資料](https://nginx.org/en/docs/switches.html)によると、`-T` は[設定](/glossary/設定/)の検査に加えて[設定ファイル](/glossary/設定ファイル/)を出力します。秘密情報や内部の接続先が含まれる場合があるため、出力をそのまま外部へ共有しないでください。

対象の `server` と `location` をたどり、静的[ファイル](/glossary/ファイル/)を返す[設定](/glossary/設定/)か、`proxy_pass` や `fastcgi_pass` でアプリへ渡す[設定](/glossary/設定/)かを[確認](/glossary/確認/)します。[要求の処理方法の公式説明](https://nginx.org/en/docs/http/request_processing.html)では、接続先やホスト名、[URL](/glossary/url/) に基づいて[処理](/glossary/処理/)する[設定](/glossary/設定/)が選ばれることが説明されています。

## よくある原因と解決手順

### 静的ファイルへ POST している

[静的ファイル処理の実装](https://github.com/nginx/nginx/blob/master/src/http/modules/ngx_http_static_module.c)では、POST の場合、[ファイル](/glossary/ファイル/)を開く[処理](/glossary/処理/)の後に 405 を返す経路があります。通常の[ファイル](/glossary/ファイル/)が存在し、開ける場合でも、POST の内容を[処理](/glossary/処理/)するわけではありません。

フォームの送信先が表示用の [HTML](/glossary/html/) [ファイル](/glossary/ファイル/)になっているなら、アプリの受付 [URL](/glossary/url/) へ変更します。例えばアプリが `/api/contact` で POST を受ける設計なら、フォームや JavaScript の送信先もその [URL](/glossary/url/) に合わせます。

単に[ファイル](/glossary/ファイル/)を読みたいだけなら [GET](/glossary/get/) が適切ですが、[登録](/glossary/登録/)や[更新](/glossary/更新/)の要求を、405 を避けるためだけに [GET](/glossary/get/) へ変更しないでください。何を行う要求かに合わせて、受付側の[処理](/glossary/処理/)を用意します。

### アプリへ渡すはずの URL が静的ファイル処理へ回っている

Nginx の設定例として、アプリが同じ機器の `127.0.0.1:3000` で `/api/contact` を受け付けるなら、次のように `/api/` への要求を転送できます。既存の `server` の中に置く部分的な例です。

```nginx
location ^~ /api/ {
    proxy_pass http://127.0.0.1:3000;
}
```

接続先と[ポート番号](/glossary/ポート番号/)は例です。[Docker](/glossary/docker/) など別の構成では、Nginx から接続できる実際のアプリのアドレスに置き換えてください。

[proxy_pass の公式資料](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)によると、転送先に URI を付けない場合、元の要求 URI が転送されます。この例では `/api/contact` をアプリ側でも受け付ける必要があります。末尾に `/` を追加すると URI の扱いが変わるため、アプリが待ち受ける[パス](/glossary/パス/)に合わせて[設定](/glossary/設定/)します。

PHP の場合は、PHP を実行する[設定](/glossary/設定/)へ要求が渡る必要があります。既存のアプリの構成を[確認](/glossary/確認/)し、[HTML](/glossary/html/) や [JSON](/glossary/json/) を配置しただけで送信処理ができるとは考えないでください。

### PUT・DELETE・OPTIONS などが静的ファイル処理へ届いている

同じ実装では、[GET](/glossary/get/)・HEAD・POST 以外の[メソッド](/glossary/メソッド/)を、[ファイル](/glossary/ファイル/)の[確認](/glossary/確認/)より前に 405 にする経路があります。そのため、POST と違って、[ファイル](/glossary/ファイル/)の有無を[確認](/glossary/確認/)する前に拒否される場合があります。

[API](/glossary/api/) 用の PUT や DELETE、ブラウザーが送る OPTIONS で失敗した場合も、まずその要求を扱うアプリや[処理](/glossary/処理/)へ渡っているか[確認](/glossary/確認/)します。`limit_except` に POST などを書き足しても、静的[ファイル](/glossary/ファイル/)を[処理](/glossary/処理/)する機能がアプリの代わりになるわけではありません。

### WebDAV でファイル管理を行いたい

Nginx 自身に[ファイル](/glossary/ファイル/)の作成や[削除](/glossary/削除/)を担当させる目的なら、WebDAV の機能が別にあります。[公式資料](https://nginx.org/en/docs/http/ngx_http_dav_module.html)では、PUT・DELETE・MKCOL・COPY・MOVE を扱う[モジュール](/glossary/モジュール/)と `dav_methods` が説明されています。[標準](/glossary/標準/)のビルドでは有効にならない[モジュール](/glossary/モジュール/)です。

通常のフォームや [API](/glossary/api/) の 405 の対処として有効にするものではありません。[ファイル](/glossary/ファイル/)を変更できる機能なので、用途と[アクセス制限](/glossary/アクセス制限/)を決めたうえで構成します。

## 補足：似ているが別のもの

[404](/posts/nginx_404/) は対象が見つからない場合の状態[コード](/glossary/コード/)です。静的[ファイル](/glossary/ファイル/)への POST では、[ファイル](/glossary/ファイル/)が存在しない場合に、POST を拒否する判定より先に 404 になる経路があります。ただし、別の[処理](/glossary/処理/)や内部転送がある構成まで、この結果を一般化することはできません。

[403](/posts/nginx_403/) はアクセスが拒否された場合に[確認](/glossary/確認/)する状態[コード](/glossary/コード/)です。`limit_except` は指定した[メソッド](/glossary/メソッド/)以外に対する[アクセス制限](/glossary/アクセス制限/)を[設定](/glossary/設定/)する仕組みで、[ファイル](/glossary/ファイル/)への書き込みやフォーム[処理](/glossary/処理/)を実装するものではありません。

## 切り分けの順序

最初に、失敗した要求の [URL](/glossary/url/) と[メソッド](/glossary/メソッド/)を[確認](/glossary/確認/)します。次に、その [URL](/glossary/url/) が Nginx のどの `location` に入り、静的[ファイル](/glossary/ファイル/)[処理](/glossary/処理/)とアプリへの転送のどちらへ進むかを調べます。

アプリへ渡す設計なら、転送先の接続先と[パス](/glossary/パス/)、アプリが受け付ける[メソッド](/glossary/メソッド/)を[確認](/glossary/確認/)してください。アプリ側の[アクセスログ](/glossary/アクセスログ/)も同じ時刻で照合します。

`error_page` で 405 を 200 に変えることを、フォーム[処理](/glossary/処理/)の[修正](/glossary/修正/)の代わりにはできません。[公式資料](https://nginx.org/en/docs/http/ngx_http_core_module.html#error_page)によると、通常の別 URI への[エラー](/glossary/エラー/)[処理](/glossary/処理/)では [GET](/glossary/get/)・HEAD 以外が [GET](/glossary/get/) に変わります。[ファイル](/glossary/ファイル/)を表示できても、送信内容を[保存](/glossary/保存/)したことにはなりません。

## 確認コマンド集

次は、管理している検証環境の同じ静的[ファイル](/glossary/ファイル/)に、[GET](/glossary/get/) と POST を送って比較する例です。実在する[ファイル](/glossary/ファイル/)の [URL](/glossary/url/) に置き換えてください。本番の受付処理へ、確認目的の POST を無計画に送らないでください。

```bash
# GET の応答を確認する
curl -i https://example.com/index.html

# 空の POST を送り、応答を比較する
curl -i --data '' https://example.com/index.html

# 設定全体を確認する
sudo nginx -T

# 設定変更後に検査する
sudo nginx -t
```

curl の `--data` は、[公式マニュアル](https://curl.se/docs/manpage.html#-d)で説明されている POST の送信指定です。[設定](/glossary/設定/)の検査に成功したら、対象環境の管理方法に従って Nginx の[設定](/glossary/設定/)を再読み込みし、元の操作を[確認](/glossary/確認/)してください。

## Editor's Note

405 が出たときは、[メソッド](/glossary/メソッド/)を許可する[設定](/glossary/設定/)を探す前に、要求を受け取った[処理](/glossary/処理/)を[確認](/glossary/確認/)することが大切です。静的[ファイル](/glossary/ファイル/)を返す[処理](/glossary/処理/)へフォームの[送信](/glossary/送信/)が届いているなら、必要なのは送信先と受付処理をそろえることです。

本記事の静的[ファイル](/glossary/ファイル/)の判定順序は、確認時点の Nginx の公開実装に基づきます。[URL](/glossary/url/) が `/` で終わる場合や、内部転送、[認証](/glossary/認証/)、別の[モジュール](/glossary/モジュール/)が関わる構成では、同じ結果になるとは限りません。画面の文言だけで判断せず、対象の[設定](/glossary/設定/)と処理経路を[確認](/glossary/確認/)してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご[確認](/glossary/確認/)ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
