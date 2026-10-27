---
title: "PHPのUndefined array key：原因と対処法"
date: 2026-10-27
slug: php_undefined_array_key
draft: false
description: "PHPのUndefined array keyは、配列にないキーを読み取ったときの警告です。キーの確認方法と、必須入力、null、既定値の扱いを説明します。"
tags: ["PHP"]
images: ["og/posts/php_undefined_array_key.png"]
errorCode: "Undefined array key"
lastmod: 2026-10-27
service: "PHP"
error_type: "Undefined array key"
components: ["PHP arrays"]
related_services: []
trend_incident: false
---

## 結論

`Warning: Undefined array key "email"` は、配列に存在しない `email` キーを読み取ったという警告です。まず警告に書かれたファイルと行を開き、どの配列の、どのキーを読んでいるか確認してください。

そのキーが必須なら、入力元やデータの作り方を確認します。省略可能なら、`??` で既定値を用意できます。値が `null` でもキーの存在を区別したい場合は `array_key_exists()` を使います。

## どんなときに表示されるか

例えば、フォームから `email` が送られていないのに、次のように直接読むと警告になります。

```php
<?php
$email = $_POST['email'];
```

```text
PHP Warning:  Undefined array key "email" in /var/www/app/form.php on line 8
```

`"email"` は見つからなかったキー、後ろのファイル名と行番号は読み取りを行った場所です。整数キーの場合は `Undefined array key 3` のように表示されます。実際の表示形式は実行環境によって異なります。

この警告は `E_WARNING` です。通常は処理が続き、読み取った値は `null` になります。ただし、独自のエラーハンドラーが警告を例外に変換する環境では、処理が中断されることもあります。

## PHP 7から8で何が変わったか

配列にないキーを読む状況は PHP 7 にもありました。PHP 7.4 では文字列キーに `Notice: Undefined index: email`、整数キーに `Notice: Undefined offset: 3` のような通知が出ます。PHP 8.0 ではこの扱いが Notice から Warning に引き上げられ、`Undefined array key` という文言になりました。

以前は通知を表示しない設定だった場合、PHP 8 への更新後に初めて目に入ることがあります。警告を非表示にしても、キーがない状態そのものは変わりません。

## キーがない理由を確認する

警告の行で参照している配列をたどり、想定した名前のキーが作られているか確認します。フォームなら入力欄の `name` と送信内容、データベースの結果なら取得した列名や別名、API の結果なら受け取ったデータの形を調べます。

例えば、フォーム側が `name="mail"` なのに、PHP 側で `$_POST['email']` を読めば一致しません。キー名を意図した名前にそろえてください。ログに配列を記録するときは、個人情報やパスワードを含めないよう注意します。

配列そのものが `null` である場合は、`Trying to access array offset on null` など別の警告になることがあります。その場合はキーの前に、配列を取得する処理の結果を確認します。

## 必須の入力は値を検証する

必須項目を固定の値で補うと、入力漏れを見逃す場合があります。以下は `email` が送られ、空でない文字列かを確かめる例です。

```php
<?php
$email = $_POST['email'] ?? null;

if (!is_string($email) || trim($email) === '') {
    http_response_code(400);
    exit('email is required');
}

$email = trim($email);
```

この例はメールアドレスの書式までは検証していません。必要に応じて、アプリケーションの要件に合わせて検証を加えてください。

## 省略可能な値には既定値を使う

`??` は左側のキーが存在しないか、値が `null` の場合に右側の値を使います。存在しないキーをこの方法で確認しても、`Undefined array key` は発生しません。

```php
<?php
$action = $_POST['action'] ?? 'default';
```

`false`、`0`、空文字列は `null` ではないため、そのまま使われます。空文字列も既定値に置き換えたい場合は、入力の条件を別に決めて検証してください。

## nullとキーの存在を区別する

`isset()` はキーが存在し、値が `null` ではないときに `true` を返します。一方、`array_key_exists()` は、値が `null` でもキーが存在すれば `true` を返します。

```php
<?php
$row = ['name' => null];

var_dump(isset($row['name']));             // false
var_dump(array_key_exists('name', $row));  // true
```

値を使えるか確かめたい場合と、キーが送られてきたかだけを確かめたい場合で使い分けます。`array_key_exists()` の第2引数は配列です。

## キーの型と集計処理を確認する

PHP の配列では、文字列の `"8"` は整数キー `8` として扱われます。一方、`"08"` は文字列キーのままです。データを作る側と読む側で、意図したキーになっているか確認してください。

また、存在しないキーに対して `$count[$word]++` のように読みながら更新すると、警告が出ます。件数を数える場合は、最初の値を用意できます。

```php
<?php
$count = [];
foreach ($words as $word) {
    $count[$word] = ($count[$word] ?? 0) + 1;
}
```

参考資料：[PHP配列の説明](https://www.php.net/manual/ja/language.types.array.php)、[null合体演算子](https://www.php.net/manual/ja/language.operators.comparison.php)、[array_key_exists](https://www.php.net/manual/ja/function.array-key-exists.php)、[PHP 8.0の変更点](https://github.com/php/php-src/blob/PHP-8.0/UPGRADING)、[PHP 8.5の配列アクセス実装](https://github.com/php/php-src/blob/php-8.5.12/Zend/zend_execute.c)、[PHP 7.4の実装](https://github.com/php/php-src/blob/php-7.4.33/Zend/zend_execute.c)。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
