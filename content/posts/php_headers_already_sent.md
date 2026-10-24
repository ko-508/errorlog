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

PHPでリダイレクトやクッキーの設定をするとき、次の警告が出ることがあります。

```text
PHP Warning:  Cannot modify header information - headers already sent by (output started at /var/www/app/config.php:12) in /var/www/app/login.php on line 30
```

HTTPヘッダーを既に送ったため、それ以降の変更ができなかったことを示します。ヘッダーは、転送先やクッキーなどを本文とは別に伝える情報です。

まず `output started at` の場所を確認し、意図しない出力を取り除くか、ヘッダーを設定する処理を出力より前に移します。警告を隠すだけでは、送れなかったリダイレクトやクッキーは直りません。

## 警告にある2つのファイル位置を読み分ける

例の `config.php:12` は、PHPが出力開始位置として記録した場所です。後ろの `login.php on line 30` は、既にヘッダーが送られた後で変更を試みた場所です。

[PHP 8.5.12の実装](https://github.com/php/php-src/blob/php-8.5.12/main/SAPI.c)では、送信済みのヘッダーを変更しようとすると、記録されている出力開始位置を警告に含めて失敗します。位置が取れない場合は、括弧内の情報がない短い文言になります。

そのため、headerを書いた行だけでなく、先に読み込んだ設定ファイルや表示用ファイルも確認対象です。ただし、先の出力が正しいHTMLなら、それを削除するのではなく、出力前に転送の要否を決めるよう処理順を直します。

これはWarningです。標準の動作では警告の後も処理が続くため、リダイレクトが失敗したまま後続のHTMLや処理が実行されることがあります。独自のエラー処理を使うアプリでは、警告の扱いも確認してください。

## echo以外の空白や読み込み先も確認する

[header()の公式説明](https://www.php.net/manual/en/function.header.php)は、ヘッダーを実際の出力より前に呼ぶ必要があると説明しています。出力には `echo` や `print` だけでなく、PHPタグの外のHTMLも含まれます。

`include` や `require` の読み込み先も確認します。自分のファイルにechoが無くても、読み込み先がHTMLや空白を出していれば、先に出力が進んでいる場合があります。

PHPだけを書く設定ファイルや関数定義のファイルでは、次のように開始タグから書き、末尾の閉じタグを省きます。

```php
<?php
// config.php
$config = [
    'app_name' => 'Example',
];
```

[PHPタグの公式説明](https://www.php.net/manual/en/language.basic-syntax.phptags.php)も、末尾がPHPコードなら閉じタグを省く方法を勧めています。閉じタグの後ろへ、意図せず空白などが追加されるのを防ぐためです。

先に別の警告が画面へ表示されていないかも、ログをさかのぼって確認してください。診断のための `var_dump()` などを追加する場合も、その出力がヘッダー設定より先にならないようにします。

## リダイレクトやクッキーの設定を表示より前に置く

HTMLを出してから転送先を決める構成なら、転送の判断を先に行います。次は出力とヘッダー設定の順序を示す最小例です。

```php
<?php
// HTMLを出す前に実行する
header('Location: /mypage.php');
exit;
```

[公式のリダイレクト例](https://www.php.net/manual/en/function.header.php)も、Locationを指定した後にexitを置いています。headerで転送先を指定しても、その場でPHPの残りの処理が自動的に終了するわけではありません。exitは後続の処理を止めるためのものです。

ログインなどの実際の処理では、入力確認と必要な保存を済ませ、転送を決めてから、画面を表示するかを判断します。共通のHTMLを読み込む処理は、その後へ配置します。

クッキーを設定する場合も本文の出力前に行います。[setcookie()の公式説明](https://www.php.net/manual/en/function.setcookie.php)では、クッキーはHTTPヘッダーとして送られるため、ほかのヘッダーと同じ制約を受けます。

## headers_sentで送信済みかをログに記録する

どこで先に出力されたか分からない場合は、ヘッダーを設定する直前に確認します。

```php
<?php
if (headers_sent($file, $line)) {
    error_log("headers already sent: {$file}:{$line}");
    exit;
}

header('Location: /mypage.php');
exit;
```

[headers_sent()](https://www.php.net/manual/en/function.headers-sent.php)は、ヘッダーが送られていればtrueを返し、出力開始位置を引数の変数へ入れます。PHPコードの実行前のエラーなどでは、ファイル名が空になる場合もあります。

この例は調査用です。送信済みならヘッダーの変更を試みず停止しますが、転送できなかった原因そのものを解決する処理ではありません。ログで確認した出力元や処理順を修正してください。

また、falseは、これまでechoが一度も実行されていないことを保証しません。出力がバッファ内に残っていれば、まだヘッダーが送られていない場合があります。

## 出力バッファは送信前から使う

出力バッファは、本文をすぐに送らず一時的にためる仕組みです。[ob_start()](https://www.php.net/manual/en/function.ob-start.php)で開始できます。次は、ためた本文を破棄してリダイレクトする仕組みの例です。

```php
<?php
ob_start();
echo 'This output is buffered.';

// この例で開始したバッファの内容を破棄する
ob_end_clean();

header('Location: /mypage.php');
exit;
```

[ob_end_clean()](https://www.php.net/manual/en/function.ob-end-clean.php)は、現在のバッファの内容を破棄して終了します。本文を送る操作とは異なります。

ただし、既に送信したヘッダーを取り消すことはできません。途中まで本文を送った後にob_startを追加しても、元には戻りません。また、既存のアプリが管理するバッファを、内容を把握せず終了しないようにします。

[output_bufferingの設定](https://www.php.net/manual/en/outcontrol.configuration.php)や、途中でバッファを送る処理によっても結果が変わります。同じコードが開発環境では通り、本番では警告になる場合は、バッファの設定と送信のタイミングも確認してください。一定の文字数までは必ず安全、という前提では扱わないようにします。

## 警告が消えた後にHTTPの結果も確認する

修正後は、ブラウザの開発者ツールのネットワーク表示などで、最初の応答を確認します。リダイレクトなら転送用の状態コードとLocation、クッキーならSet-Cookieが応答に含まれているかを見ます。転送後のページだけを見ると、最初の応答の失敗を見落とす場合があります。

ヘッダーを変更できない問題が解消しても、クッキーがブラウザへ保存されるかは別に確認が必要です。setcookieの呼び出しだけで、保存や次回送信の成功まで保証されるわけではありません。

`Cannot set response code - headers already sent` や、`Session cannot be started after headers have already been sent` は関連する別の警告です。どの関数で失敗したかをログで確認し、出力より前に行う必要がある処理を整理します。

一方、[メモリ上限超過](/posts/php_allowed_memory_size_exhausted/)や[実行時間超過](/posts/php_maximum_execution_time_exceeded/)は、PHPの処理が上限に達したFatal errorです。本件は上限を増やす対処ではなく、ヘッダーと出力の順序を調べます。

## 解決手順のまとめ

警告の `output started at` と、後ろのヘッダー変更を試みた位置を読み分けます。読み込み先の空白やHTML、確認用の出力を調べ、リダイレクトなどを本文の出力より前に移してください。

出力バッファを使う場合も、ヘッダーがまだ送られていないことが前提です。修正後は警告の有無に加えて、実際のHTTP応答まで確認します。

本記事は2026年10月24日に確認した公式資料とPHP 8.5.12の実装に基づきます。掲載コードとWeb経由での警告・ヘッダー送信の挙動は、実行未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
