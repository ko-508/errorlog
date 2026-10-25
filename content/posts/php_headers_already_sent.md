---
title: "PHPのheaders already sent対処法"
date: 2026-10-24
slug: php_headers_already_sent
draft: false
description: "Cannot modify header informationが出たら、output started atとheaderを呼んだ場所を読み分けます。読み込み先の空白、出力順序、headers_sentでの確認、出力バッファの注意点を説明します。"
tags: ["PHP"]
images: ["og/posts/php_headers_already_sent.png"]
errorCode: "headers already sent"
service: "PHP"
error_type: "Cannot modify header information"
components: ["header", "setcookie", "Output Control"]
related_services: ["HTTP"]
trend_incident: false
---

## 冒頭まとめ

PHPでリダイレクトや[クッキー](/glossary/クッキー/)の[設定](/glossary/設定/)をするとき、次の警告が出ることがあります。

```text
PHP Warning:  Cannot modify header information - headers already sent by (output started at /var/www/app/config.php:12) in /var/www/app/login.php on line 30
```

[HTTP](/glossary/http/)[ヘッダー](/glossary/ヘッダー/)を既に送ったため、それ以降の変更ができなかったことを示します。[ヘッダー](/glossary/ヘッダー/)は、転送先や[クッキー](/glossary/クッキー/)などを本文とは別に伝える情報です。

まず `output started at` の場所を確認し、意図しない出力を取り除くか、[ヘッダー](/glossary/ヘッダー/)を[設定](/glossary/設定/)する[処理](/glossary/処理/)を出力より前に移します。警告を隠すだけでは、送れなかったリダイレクトや[クッキー](/glossary/クッキー/)は直りません。

## 警告にある2つのファイル位置を読み分ける

例の `config.php:12` は、PHPが出力開始位置として記録した場所です。後ろの `login.php on line 30` は、既に[ヘッダー](/glossary/ヘッダー/)が送られた後で変更を試みた場所です。

[PHP 8.5.12の実装](https://github.com/php/php-src/blob/php-8.5.12/main/SAPI.c)では、送信済みの[ヘッダー](/glossary/ヘッダー/)を変更しようとすると、記録されている出力開始位置を警告に含めて失敗します。位置が取れない場合は、括弧内の情報がない短い文言になります。

そのため、headerを書いた行だけでなく、先に読み込んだ[設定ファイル](/glossary/設定ファイル/)や表示用[ファイル](/glossary/ファイル/)も確認対象です。ただし、先の出力が正しいHTMLなら、それを[削除](/glossary/削除/)するのではなく、出力前に転送の要否を決めるよう処理順を直します。

これはWarningです。[標準](/glossary/標準/)の動作では警告の後も[処理](/glossary/処理/)が続くため、リダイレクトが失敗したまま後続のHTMLや[処理](/glossary/処理/)が実行されることがあります。独自の[エラー](/glossary/エラー/)[処理](/glossary/処理/)を使うアプリでは、警告の扱いも確認してください。

## echo以外の空白や読み込み先も確認する

[header()の公式説明](https://www.php.net/manual/en/function.header.php)は、[ヘッダー](/glossary/ヘッダー/)を実際の出力より前に呼ぶ必要があると説明しています。出力には `echo` や `print` だけでなく、PHP[タグ](/glossary/タグ/)の外のHTMLも含まれます。

`include` や `require` の読み込み先も確認します。自分の[ファイル](/glossary/ファイル/)にechoが無くても、読み込み先がHTMLや空白を出していれば、先に出力が進んでいる場合があります。

PHPだけを書く[設定ファイル](/glossary/設定ファイル/)や関数定義の[ファイル](/glossary/ファイル/)では、次のように開始[タグ](/glossary/タグ/)から書き、末尾の閉じ[タグ](/glossary/タグ/)を省きます。

```php
<?php
// config.php
$config = [
    'app_name' => 'Example',
];
```

[PHPタグの公式説明](https://www.php.net/manual/en/language.basic-syntax.phptags.php)も、末尾がPHP[コード](/glossary/コード/)なら閉じ[タグ](/glossary/タグ/)を省く方法を勧めています。閉じ[タグ](/glossary/タグ/)の後ろへ、意図せず空白などが追加されるのを防ぐためです。

先に別の警告が画面へ表示されていないかも、[ログ](/glossary/ログ/)をさかのぼって確認してください。診断のための `var_dump()` などを追加する場合も、その出力が[ヘッダー](/glossary/ヘッダー/)[設定](/glossary/設定/)より先にならないようにします。

## リダイレクトやクッキーの設定を表示より前に置く

HTMLを出してから転送先を決める構成なら、転送の判断を先に行います。次は出力と[ヘッダー](/glossary/ヘッダー/)[設定](/glossary/設定/)の順序を示す最小例です。

```php
<?php
// HTMLを出す前に実行する
header('Location: /mypage.php');
exit;
```

[公式のリダイレクト例](https://www.php.net/manual/en/function.header.php)も、Locationを指定した後にexitを置いています。headerで転送先を指定しても、その場でPHPの残りの[処理](/glossary/処理/)が自動的に終了するわけではありません。exitは後続の[処理](/glossary/処理/)を止めるためのものです。

[ログイン](/glossary/ログイン/)などの実際の[処理](/glossary/処理/)では、入力確認と必要な[保存](/glossary/保存/)を済ませ、転送を決めてから、画面を表示するかを判断します。共通のHTMLを読み込む[処理](/glossary/処理/)は、その後へ配置します。

[クッキー](/glossary/クッキー/)を[設定](/glossary/設定/)する場合も本文の出力前に行います。[setcookie()の公式説明](https://www.php.net/manual/en/function.setcookie.php)では、[クッキー](/glossary/クッキー/)は[HTTP](/glossary/http/)[ヘッダー](/glossary/ヘッダー/)として送られるため、ほかの[ヘッダー](/glossary/ヘッダー/)と同じ制約を受けます。

## headers_sentで送信済みかをログに記録する

どこで先に出力されたか分からない場合は、[ヘッダー](/glossary/ヘッダー/)を[設定](/glossary/設定/)する直前に確認します。

```php
<?php
if (headers_sent($file, $line)) {
    error_log("headers already sent: {$file}:{$line}");
    exit;
}

header('Location: /mypage.php');
exit;
```

[headers_sent()](https://www.php.net/manual/en/function.headers-sent.php)は、[ヘッダー](/glossary/ヘッダー/)が送られていればtrueを返し、出力開始位置を[引数](/glossary/引数/)の[変数](/glossary/変数/)へ入れます。PHP[コード](/glossary/コード/)の実行前の[エラー](/glossary/エラー/)などでは、[ファイル名](/glossary/ファイル名/)が空になる場合もあります。

この例は調査用です。送信済みなら[ヘッダー](/glossary/ヘッダー/)の変更を試みず停止しますが、転送できなかった原因そのものを解決する[処理](/glossary/処理/)ではありません。[ログ](/glossary/ログ/)で確認した出力元や処理順を[修正](/glossary/修正/)してください。

また、falseは、これまでechoが一度も実行されていないことを保証しません。出力が[バッファ](/glossary/バッファ/)内に残っていれば、まだ[ヘッダー](/glossary/ヘッダー/)が送られていない場合があります。

## 出力バッファは送信前から使う

出力[バッファ](/glossary/バッファ/)は、本文をすぐに送らず一時的にためる仕組みです。[ob_start()](https://www.php.net/manual/en/function.ob-start.php)で開始できます。次は、ためた本文を破棄してリダイレクトする仕組みの例です。

```php
<?php
ob_start();
echo 'This output is buffered.';

// この例で開始したバッファの内容を破棄する
ob_end_clean();

header('Location: /mypage.php');
exit;
```

[ob_end_clean()](https://www.php.net/manual/en/function.ob-end-clean.php)は、現在の[バッファ](/glossary/バッファ/)の内容を破棄して終了します。本文を送る操作とは異なります。

ただし、既に[送信](/glossary/送信/)した[ヘッダー](/glossary/ヘッダー/)を取り消すことはできません。途中まで本文を送った後にob_startを追加しても、元には戻りません。また、既存のアプリが管理する[バッファ](/glossary/バッファ/)を、内容を把握せず終了しないようにします。

[output_bufferingの設定](https://www.php.net/manual/en/outcontrol.configuration.php)や、途中で[バッファ](/glossary/バッファ/)を送る[処理](/glossary/処理/)によっても結果が変わります。同じ[コード](/glossary/コード/)が[開発環境](/glossary/開発環境/)では通り、本番では警告になる場合は、[バッファ](/glossary/バッファ/)の[設定](/glossary/設定/)と[送信](/glossary/送信/)のタイミングも確認してください。一定の文字数までは必ず安全、という前提では扱わないようにします。

## 警告が消えた後にHTTPの結果も確認する

修正後は、[ブラウザ](/glossary/ブラウザ/)の開発者[ツール](/glossary/ツール/)の[ネットワーク](/glossary/ネットワーク/)表示などで、最初の応答を確認します。リダイレクトなら転送用の状態[コード](/glossary/コード/)とLocation、[クッキー](/glossary/クッキー/)ならSet-Cookieが応答に含まれているかを見ます。転送後のページだけを見ると、最初の応答の失敗を見落とす場合があります。

[ヘッダー](/glossary/ヘッダー/)を変更できない問題が解消しても、[クッキー](/glossary/クッキー/)が[ブラウザ](/glossary/ブラウザ/)へ[保存](/glossary/保存/)されるかは別に確認が必要です。setcookieの呼び出しだけで、[保存](/glossary/保存/)や次回送信の成功まで保証されるわけではありません。

`Cannot set response code - headers already sent` や、`Session cannot be started after headers have already been sent` は関連する別の警告です。どの[関数](/glossary/関数/)で失敗したかを[ログ](/glossary/ログ/)で確認し、出力より前に行う必要がある[処理](/glossary/処理/)を整理します。

一方、[メモリ上限超過](/posts/php_allowed_memory_size_exhausted/)や[実行時間超過](/posts/php_maximum_execution_time_exceeded/)は、PHPの[処理](/glossary/処理/)が上限に達したFatal errorです。本件は上限を増やす対処ではなく、[ヘッダー](/glossary/ヘッダー/)と出力の順序を調べます。

## 解決手順のまとめ

警告の `output started at` と、後ろの[ヘッダー](/glossary/ヘッダー/)変更を試みた位置を読み分けます。読み込み先の空白やHTML、確認用の出力を調べ、リダイレクトなどを本文の出力より前に移してください。

出力[バッファ](/glossary/バッファ/)を使う場合も、[ヘッダー](/glossary/ヘッダー/)がまだ送られていないことが前提です。修正後は警告の有無に加えて、実際の[HTTP](/glossary/http/)応答まで確認します。

本記事は2026年10月24日に確認した公式資料とPHP 8.5.12の実装に基づきます。掲載[コード](/glossary/コード/)とWeb経由での警告・[ヘッダー](/glossary/ヘッダー/)[送信](/glossary/送信/)の挙動は、実行未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
