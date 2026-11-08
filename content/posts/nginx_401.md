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

Nginx の `401 Authorization Required` は、[認証](/glossary/認証/)を求められている、または送った認証情報が受け付けられなかったことを示します。Basic [認証](/glossary/認証/)なら、認証情報の未送信、[ユーザー名](/glossary/ユーザー名/)の未登録、[パスワード](/glossary/パスワード/)の不一致を、[エラーログ](/glossary/エラーログ/)から切り分けられます。

`auth_request` を使っている場合は、別のサービスへ送った認証確認の結果を調べます。401 の画面だけを見て、パスワードファイルを作り直す必要があるとは判断しないでください。

## エラーの概要

Basic [認証](/glossary/認証/)は、[ユーザー名](/glossary/ユーザー名/)と[パスワード](/glossary/パスワード/)を使ってアクセスを制限する仕組みです。Nginx では `auth_basic` と `auth_basic_user_file` で[設定](/glossary/設定/)します。

```nginx
location / {
    auth_basic           "closed site";
    auth_basic_user_file /etc/nginx/htpasswd;
}
```

上の[パス](/glossary/パス/)は例です。`auth_basic_user_file` には、実際のパスワードファイルを指定してください。[公式資料](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html)によると、`auth_basic` の文字列は[認証](/glossary/認証/)の対象領域を示す `realm` に使われます。

[HTTP](/glossary/http/)/1.1 の応答では、次のような状態[コード](/glossary/コード/)と認証要求の[ヘッダー](/glossary/ヘッダー/)が手がかりになります。

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="closed site"
```

既定のエラーページの見出しは `401 Authorization Required` です。状態行の `Unauthorized` と本文の `Authorization Required` は表記が異なりますが、どちらも同じ 401 に関する表示です。これは Nginx の[状態行の実装](https://github.com/nginx/nginx/blob/master/src/http/ngx_http_header_filter_module.c)と[既定ページの実装](https://github.com/nginx/nginx/blob/master/src/http/ngx_http_special_response.c)で[確認](/glossary/確認/)できます。独自のエラーページを[設定](/glossary/設定/)している場合は表示が変わります。

## まず最初に：認証方式とログを確認する

対象の [URL](/glossary/url/) に `auth_basic` が適用されているか、`auth_request` が適用されているかを[確認](/glossary/確認/)します。設定全体を表示する場合は、次の[コマンド](/glossary/コマンド/)を使えます。

```bash
sudo nginx -T
```

[公式資料](https://nginx.org/en/docs/switches.html)では、`-T` は[設定](/glossary/設定/)の検査に加えて[設定ファイル](/glossary/設定ファイル/)を出力する指定です。[設定](/glossary/設定/)に含まれる認証情報や内部の接続先を、そのまま外部へ共有しないでください。

Basic [認証](/glossary/認証/)では、失敗した時刻の[エラーログ](/glossary/エラーログ/)を[確認](/glossary/確認/)します。出力先は `error_log` の[設定](/glossary/設定/)に従うため、必ずしも `/var/log/nginx/error.log` とは限りません。

認証情報の未送信は `info`、[ユーザー](/glossary/ユーザー/)不在と[パスワード](/glossary/パスワード/)不一致は `error` のレベルで記録されます。[error_log の公式資料](https://nginx.org/en/docs/ngx_core_module.html#error_log)にある既定のレベルは `error` です。そのため、未送信の[ログ](/glossary/ログ/)が見当たらなくても、認証情報を送った証拠にはなりません。必要な場合は管理者が一時的に `info` を記録する[設定](/glossary/設定/)へ変更し、調査後に戻します。

## よくある原因と解決手順

### 認証情報を送っていない

Basic [認証](/glossary/認証/)の実装では、利用できる認証情報がない場合に、[ユーザー名](/glossary/ユーザー名/)と[パスワード](/glossary/パスワード/)が提供されていない旨を記録し、[認証](/glossary/認証/)を求める 401 を返します。[パスワード](/glossary/パスワード/)の間違いとは別の状態です。

curl では次のように[ユーザー名](/glossary/ユーザー名/)を指定して[確認](/glossary/確認/)できます。[パスワード](/glossary/パスワード/)は入力を求められたときに入力します。

```bash
curl -i --user alice https://example.com/
```

[curl の公式資料](https://curl.se/docs/manpage.html#-u)によると、[ユーザー名](/glossary/ユーザー名/)だけを指定した場合は[パスワード](/glossary/パスワード/)を対話的に入力できます。[URL](/glossary/url/) と[ユーザー名](/glossary/ユーザー名/)は実際の値に置き換えてください。[パスワード](/glossary/パスワード/)を[コマンド](/glossary/コマンド/)へ直接書く必要はありません。

### パスワードファイルにユーザーがいない

[ログ](/glossary/ログ/)に `was not found in` を含む行がある場合は、指定した[ファイル](/glossary/ファイル/)の中に[ユーザー](/glossary/ユーザー/)が見つかっていません。[ログ](/glossary/ログ/)に出ている[ファイル](/glossary/ファイル/)が想定どおりか、[ユーザー名](/glossary/ユーザー名/)の綴りが登録内容と一致するかを[確認](/glossary/確認/)します。

正しい[ファイル](/glossary/ファイル/)へ[登録](/glossary/登録/)したつもりでも、対象 [URL](/glossary/url/) の[設定](/glossary/設定/)が別の[ファイル](/glossary/ファイル/)を指していれば[認証](/glossary/認証/)は通りません。先に `auth_basic_user_file` の指定を[確認](/glossary/確認/)してください。

### パスワードが一致しない

[ログ](/glossary/ログ/)に `password mismatch` がある場合は、送った[パスワード](/glossary/パスワード/)と登録内容の照合に失敗しています。[Basic 認証の実装](https://github.com/nginx/nginx/blob/master/src/http/modules/ngx_http_auth_basic_module.c)では、[ユーザー](/glossary/ユーザー/)不在とは別の[ログ](/glossary/ログ/)になります。

パスワードファイルは、[ユーザー名](/glossary/ユーザー名/)と[対応](/glossary/対応/)する[パスワード](/glossary/パスワード/)のハッシュ値を[保存](/glossary/保存/)します。平文の[パスワード](/glossary/パスワード/)を手書きするのではなく、[環境](/glossary/環境/)で[対応](/glossary/対応/)する保存方式と作成方法を[確認](/glossary/確認/)してください。

既存[ファイル](/glossary/ファイル/)の内容を[確認](/glossary/確認/)する方法として、`htpasswd` が導入されていれば照合用の `-v` を利用できます。

```bash
sudo htpasswd -v /etc/nginx/htpasswd alice
```

これは[ファイル](/glossary/ファイル/)に記録された[パスワード](/glossary/パスワード/)を[確認](/glossary/確認/)する操作です。成功しても、Nginx が同じ[ファイル](/glossary/ファイル/)を参照し、同じ保存方式を扱えることまでは保証しません。Nginx 経由の要求も再確認してください。

[Apache の htpasswd の資料](https://httpd.apache.org/docs/2.4/programs/htpasswd.html)によると、`-c` は既存[ファイル](/glossary/ファイル/)があれば上書きします。既存[ユーザー](/glossary/ユーザー/)の[確認](/glossary/確認/)や[更新](/glossary/更新/)で、理由なく `-c` を付けて[ファイル](/glossary/ファイル/)を作り直さないでください。

### auth_request の認証確認先が 401 を返している

`auth_request` は、別の [URL](/glossary/url/) への認証確認の結果でアクセスを判断します。[公式資料](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html)によると、確認先が 2xx を返すと許可し、401 または 403 を返すと、その番号で拒否します。401 の場合は確認先の `WWW-Authenticate` [ヘッダー](/glossary/ヘッダー/)も利用者へ渡します。

認証確認先の[ログ](/glossary/ログ/)と、そこへ渡している Cookie や[認証](/glossary/認証/)[ヘッダー](/glossary/ヘッダー/)の[設定](/glossary/設定/)を[確認](/glossary/確認/)してください。単に確認用 [URL](/glossary/url/) へアクセスするだけでなく、元の要求と同じ条件が渡っているかを見る必要があります。

確認先が成功時に[ログイン](/glossary/ログイン/)画面へリダイレクトするなど、2xx・401・403 以外を返していないかも調べます。[実装](https://github.com/nginx/nginx/blob/master/src/http/modules/ngx_http_auth_request_module.c)では、想定外の状態[コード](/glossary/コード/)は 500 として扱われます。

### IP アドレスの許可と認証の両方が必要になっている

[IP アドレス](/glossary/ip-アドレス/)による許可と Basic [認証](/glossary/認証/)などを併用している場合は、`satisfy` を[確認](/glossary/確認/)します。[公式資料](https://nginx.org/en/docs/http/ngx_http_core_module.html#satisfy)によると、既定の `satisfy all` はすべての条件を満たす必要があり、`satisfy any` はいずれか一つが通れば許可します。

[IP アドレス](/glossary/ip-アドレス/)を許可したのに[認証](/glossary/認証/)も求められる場合、`all` なら[設定](/glossary/設定/)どおりの動作です。特定の接続元だけ[認証](/glossary/認証/)を省略する方針である場合に限り、許可する範囲を[確認](/glossary/確認/)して `any` を検討してください。401 を消すためだけに切り替えると、アクセスを許す条件も変わります。

## 補足：似ているが別のもの

パスワードファイルがない場合と、認証情報が一致しない場合は別です。Basic [認証](/glossary/認証/)の実装では、[ファイル](/glossary/ファイル/)を開く[処理](/glossary/処理/)で「存在しない」という[エラー](/glossary/エラー/)を受けると [403](/posts/nginx_403/)、[権限](/glossary/権限/)など他の理由で開けないと [500](/posts/nginx_500/) を返します。

ただし、この[ファイル](/glossary/ファイル/)を開く[処理](/glossary/処理/)は、[ユーザー名](/glossary/ユーザー名/)と[パスワード](/glossary/パスワード/)を受け取った後に行われます。[ファイル](/glossary/ファイル/)がない[環境](/glossary/環境/)でも、認証情報を付けない最初の要求では、先に 401 が返る場合があります。401 が返ったという事実だけでは、[ファイル](/glossary/ファイル/)が存在することも[確認](/glossary/確認/)できません。

また、`auth_request` の確認先が 403 を返す場合も、利用者への応答は 403 になります。401 と 403 のどちらかで、[確認](/glossary/確認/)する[ログ](/glossary/ログ/)や[処理](/glossary/処理/)が変わります。

## 切り分けの順序

まず[設定](/glossary/設定/)から Basic [認証](/glossary/認証/)か `auth_request` かを[確認](/glossary/確認/)します。Basic [認証](/glossary/認証/)なら認証情報付きで同じ [URL](/glossary/url/) に要求し、その時刻の[ログ](/glossary/ログ/)から、未送信・[ユーザー](/glossary/ユーザー/)不在・[パスワード](/glossary/パスワード/)不一致を区別します。[ログ](/glossary/ログ/)がない場合は、出力先と記録レベルも[確認](/glossary/確認/)してください。

`auth_request` なら、認証確認先へ渡した情報と、そこで返した状態[コード](/glossary/コード/)を調べます。IP 制限も併用している場合は、[認証](/glossary/認証/)を省略する意図があるのかを含め、`satisfy` の条件を[確認](/glossary/確認/)します。

## 確認コマンド集

利用者は認証情報を付けてアクセスを[確認](/glossary/確認/)し、管理者は[設定](/glossary/設定/)と[ログ](/glossary/ログ/)を調べます。以下は Nginx を実行できる管理環境向けの例です。

```bash
# 認証情報付きで、ヘッダーと本文を確認する
curl -i --user alice https://example.com/

# 設定全体を検査して表示する
sudo nginx -T

# 設定変更後、反映前に検査する
sudo nginx -t
```

検査に成功したら、実際に稼働している Nginx の管理方法に合わせて[設定](/glossary/設定/)を再読み込みします。公式の制御方法の一つは `nginx -s reload` です。複数の[設定](/glossary/設定/)や導入先がある[環境](/glossary/環境/)では、実行した[コマンド](/glossary/コマンド/)が対象の Nginx を操作しているか[確認](/glossary/確認/)してください。

## Editor's Note

401 は、[パスワード](/glossary/パスワード/)を交換する前に、認証情報が届いているか、どの[ファイル](/glossary/ファイル/)やサービスで判定しているかを調べると整理できます。特に、未送信の[ログ](/glossary/ログ/)が既定では見えない点と、[ファイル](/glossary/ファイル/)の読み込みが認証情報の受信後に行われる点は、画面だけでは分からない違いです。

本記事の[ログ](/glossary/ログ/)や状態[コード](/glossary/コード/)の説明は、確認時点の Nginx の公式資料と公開実装に基づきます。独自のエラーページや別のアプリを組み合わせた構成では、表示だけで[認証](/glossary/認証/)の担当を決めず、[設定](/glossary/設定/)と[ログ](/glossary/ログ/)を照合してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご[確認](/glossary/確認/)ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
