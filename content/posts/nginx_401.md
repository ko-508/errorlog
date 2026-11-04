---
title: "Nginxの401：認証が通らない原因と対処法"
date: 2026-11-04
draft: false
description: "Nginxの401はパスワードの間違いだけで起きるものではありません。Basic認証のログとauth_requestの応答から、認証情報の未送信、ユーザー不在、パスワード不一致を切り分けます。"
tags: ["Nginx"]
images: ["og/posts/nginx_401.png"]
errorCode: "401"
urgency: "normal"
service: "Nginx"
error_type: "401"
components: ["ngx_http_auth_basic_module", "ngx_http_auth_request_module"]
related_services: ["HTTP Basic Authentication"]
trend_incident: false
---

## 冒頭まとめ

Nginx の `401 Authorization Required` は、認証を求められている、または送った認証情報が受け付けられなかったことを示します。Basic 認証なら、認証情報の未送信、ユーザー名の未登録、パスワードの不一致を、エラーログから切り分けられます。

`auth_request` を使っている場合は、別のサービスへ送った認証確認の結果を調べます。401 の画面だけを見て、パスワードファイルを作り直す必要があるとは判断しないでください。

## エラーの概要

Basic 認証は、ユーザー名とパスワードを使ってアクセスを制限する仕組みです。Nginx では `auth_basic` と `auth_basic_user_file` で設定します。

```nginx
location / {
    auth_basic           "closed site";
    auth_basic_user_file /etc/nginx/htpasswd;
}
```

上のパスは例です。`auth_basic_user_file` には、実際のパスワードファイルを指定してください。[公式資料](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html)によると、`auth_basic` の文字列は認証の対象領域を示す `realm` に使われます。

HTTP/1.1 の応答では、次のような状態コードと認証要求のヘッダーが手がかりになります。

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="closed site"
```

既定のエラーページの見出しは `401 Authorization Required` です。状態行の `Unauthorized` と本文の `Authorization Required` は表記が異なりますが、どちらも同じ 401 に関する表示です。これは Nginx の[状態行の実装](https://github.com/nginx/nginx/blob/master/src/http/ngx_http_header_filter_module.c)と[既定ページの実装](https://github.com/nginx/nginx/blob/master/src/http/ngx_http_special_response.c)で確認できます。独自のエラーページを設定している場合は表示が変わります。

## まず最初に：認証方式とログを確認する

対象の URL に `auth_basic` が適用されているか、`auth_request` が適用されているかを確認します。設定全体を表示する場合は、次のコマンドを使えます。

```bash
sudo nginx -T
```

[公式資料](https://nginx.org/en/docs/switches.html)では、`-T` は設定の検査に加えて設定ファイルを出力する指定です。設定に含まれる認証情報や内部の接続先を、そのまま外部へ共有しないでください。

Basic 認証では、失敗した時刻のエラーログを確認します。出力先は `error_log` の設定に従うため、必ずしも `/var/log/nginx/error.log` とは限りません。

認証情報の未送信は `info`、ユーザー不在とパスワード不一致は `error` のレベルで記録されます。[error_log の公式資料](https://nginx.org/en/docs/ngx_core_module.html#error_log)にある既定のレベルは `error` です。そのため、未送信のログが見当たらなくても、認証情報を送った証拠にはなりません。必要な場合は管理者が一時的に `info` を記録する設定へ変更し、調査後に戻します。

## よくある原因と解決手順

### 認証情報を送っていない

Basic 認証の実装では、利用できる認証情報がない場合に、ユーザー名とパスワードが提供されていない旨を記録し、認証を求める 401 を返します。パスワードの間違いとは別の状態です。

curl では次のようにユーザー名を指定して確認できます。パスワードは入力を求められたときに入力します。

```bash
curl -i --user alice https://example.com/
```

[curl の公式資料](https://curl.se/docs/manpage.html#-u)によると、ユーザー名だけを指定した場合はパスワードを対話的に入力できます。URL とユーザー名は実際の値に置き換えてください。パスワードをコマンドへ直接書く必要はありません。

### パスワードファイルにユーザーがいない

ログに `was not found in` を含む行がある場合は、指定したファイルの中にユーザーが見つかっていません。ログに出ているファイルが想定どおりか、ユーザー名の綴りが登録内容と一致するかを確認します。

正しいファイルへ登録したつもりでも、対象 URL の設定が別のファイルを指していれば認証は通りません。先に `auth_basic_user_file` の指定を確認してください。

### パスワードが一致しない

ログに `password mismatch` がある場合は、送ったパスワードと登録内容の照合に失敗しています。[Basic 認証の実装](https://github.com/nginx/nginx/blob/master/src/http/modules/ngx_http_auth_basic_module.c)では、ユーザー不在とは別のログになります。

パスワードファイルは、ユーザー名と対応するパスワードのハッシュ値を保存します。平文のパスワードを手書きするのではなく、環境で対応する保存方式と作成方法を確認してください。

既存ファイルの内容を確認する方法として、`htpasswd` が導入されていれば照合用の `-v` を利用できます。

```bash
sudo htpasswd -v /etc/nginx/htpasswd alice
```

これはファイルに記録されたパスワードを確認する操作です。成功しても、Nginx が同じファイルを参照し、同じ保存方式を扱えることまでは保証しません。Nginx 経由の要求も再確認してください。

[Apache の htpasswd の資料](https://httpd.apache.org/docs/2.4/programs/htpasswd.html)によると、`-c` は既存ファイルがあれば上書きします。既存ユーザーの確認や更新で、理由なく `-c` を付けてファイルを作り直さないでください。

### auth_request の認証確認先が 401 を返している

`auth_request` は、別の URL への認証確認の結果でアクセスを判断します。[公式資料](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html)によると、確認先が 2xx を返すと許可し、401 または 403 を返すと、その番号で拒否します。401 の場合は確認先の `WWW-Authenticate` ヘッダーも利用者へ渡します。

認証確認先のログと、そこへ渡している Cookie や認証ヘッダーの設定を確認してください。単に確認用 URL へアクセスするだけでなく、元の要求と同じ条件が渡っているかを見る必要があります。

確認先が成功時にログイン画面へリダイレクトするなど、2xx・401・403 以外を返していないかも調べます。[実装](https://github.com/nginx/nginx/blob/master/src/http/modules/ngx_http_auth_request_module.c)では、想定外の状態コードは 500 として扱われます。

### IP アドレスの許可と認証の両方が必要になっている

IP アドレスによる許可と Basic 認証などを併用している場合は、`satisfy` を確認します。[公式資料](https://nginx.org/en/docs/http/ngx_http_core_module.html#satisfy)によると、既定の `satisfy all` はすべての条件を満たす必要があり、`satisfy any` はいずれか一つが通れば許可します。

IP アドレスを許可したのに認証も求められる場合、`all` なら設定どおりの動作です。特定の接続元だけ認証を省略する方針である場合に限り、許可する範囲を確認して `any` を検討してください。401 を消すためだけに切り替えると、アクセスを許す条件も変わります。

## 補足：似ているが別のもの

パスワードファイルがない場合と、認証情報が一致しない場合は別です。Basic 認証の実装では、ファイルを開く処理で「存在しない」というエラーを受けると [403](/posts/nginx_403/)、権限など他の理由で開けないと [500](/posts/nginx_500/) を返します。

ただし、このファイルを開く処理は、ユーザー名とパスワードを受け取った後に行われます。ファイルがない環境でも、認証情報を付けない最初の要求では、先に 401 が返る場合があります。401 が返ったという事実だけでは、ファイルが存在することも確認できません。

また、`auth_request` の確認先が 403 を返す場合も、利用者への応答は 403 になります。401 と 403 のどちらかで、確認するログや処理が変わります。

## 切り分けの順序

まず設定から Basic 認証か `auth_request` かを確認します。Basic 認証なら認証情報付きで同じ URL に要求し、その時刻のログから、未送信・ユーザー不在・パスワード不一致を区別します。ログがない場合は、出力先と記録レベルも確認してください。

`auth_request` なら、認証確認先へ渡した情報と、そこで返した状態コードを調べます。IP 制限も併用している場合は、認証を省略する意図があるのかを含め、`satisfy` の条件を確認します。

## 確認コマンド集

利用者は認証情報を付けてアクセスを確認し、管理者は設定とログを調べます。以下は Nginx を実行できる管理環境向けの例です。

```bash
# 認証情報付きで、ヘッダーと本文を確認する
curl -i --user alice https://example.com/

# 設定全体を検査して表示する
sudo nginx -T

# 設定変更後、反映前に検査する
sudo nginx -t
```

検査に成功したら、実際に稼働している Nginx の管理方法に合わせて設定を再読み込みします。公式の制御方法の一つは `nginx -s reload` です。複数の設定や導入先がある環境では、実行したコマンドが対象の Nginx を操作しているか確認してください。

## Editor's Note

401 は、パスワードを交換する前に、認証情報が届いているか、どのファイルやサービスで判定しているかを調べると整理できます。特に、未送信のログが既定では見えない点と、ファイルの読み込みが認証情報の受信後に行われる点は、画面だけでは分からない違いです。

本記事のログや状態コードの説明は、確認時点の Nginx の公式資料と公開実装に基づきます。独自のエラーページや別のアプリを組み合わせた構成では、表示だけで認証の担当を決めず、設定とログを照合してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
