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

`Warning: Undefined array key "email"` は、配列に存在しない `email` [キー](/glossary/キー/)を読み取ったという警告です。まず警告に書かれた[ファイル](/glossary/ファイル/)と行を開き、どの配列の、どの[キー](/glossary/キー/)を読んでいるか[確認](/glossary/確認/)してください。

その[キー](/glossary/キー/)が必須なら、入力元やデータの作り方を[確認](/glossary/確認/)します。省略可能なら、`??` で既定値を用意できます。値が `null` でも[キー](/glossary/キー/)の存在を区別したい場合は `array_key_exists()` を使います。

## どんなときに表示されるか

例えば、フォームから `email` が送られていないのに、次のように直接読むと警告になります。

```php
<?php
$email = $_POST['email'];
```

```text
PHP Warning:  Undefined array key "email" in /var/www/app/form.php on line 8
```

`"email"` は見つからなかった[キー](/glossary/キー/)、後ろの[ファイル名](/glossary/ファイル名/)と[行番号](/glossary/行番号/)は読み取りを行った場所です。整数[キー](/glossary/キー/)の場合は `Undefined array key 3` のように表示されます。実際の表示形式は実行環境によって異なります。

この警告は `E_WARNING` です。通常は[処理](/glossary/処理/)が続き、読み取った値は `null` になります。ただし、独自のエラーハンドラーが警告を例外に変換する[環境](/glossary/環境/)では、[処理](/glossary/処理/)が中断されることもあります。

## PHP 7から8で何が変わったか

配列にない[キー](/glossary/キー/)を読む状況は PHP 7 にもありました。PHP 7.4 では文字列[キー](/glossary/キー/)に `Notice: Undefined index: email`、整数[キー](/glossary/キー/)に `Notice: Undefined offset: 3` のような[通知](/glossary/通知/)が出ます。PHP 8.0 ではこの扱いが Notice から Warning に引き上げられ、`Undefined array key` という文言になりました。

以前は[通知](/glossary/通知/)を表示しない[設定](/glossary/設定/)だった場合、PHP 8 への更新後に初めて目に入ることがあります。警告を非表示にしても、[キー](/glossary/キー/)がない状態そのものは変わりません。

## キーがない理由を確認する

警告の行で参照している配列をたどり、想定した名前の[キー](/glossary/キー/)が作られているか[確認](/glossary/確認/)します。フォームなら入力欄の `name` と送信内容、[データベース](/glossary/データベース/)の結果なら取得した列名や別名、[API](/glossary/api/) の結果なら受け取ったデータの形を調べます。

例えば、フォーム側が `name="mail"` なのに、PHP 側で `$_POST['email']` を読めば一致しません。[キー](/glossary/キー/)名を意図した名前にそろえてください。[ログ](/glossary/ログ/)に配列を記録するときは、個人情報や[パスワード](/glossary/パスワード/)を含めないよう注意します。

配列そのものが `null` である場合は、`Trying to access array offset on null` など別の警告になることがあります。その場合は[キー](/glossary/キー/)の前に、配列を取得する[処理](/glossary/処理/)の結果を[確認](/glossary/確認/)します。

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

この例はメールアドレスの書式までは検証していません。必要に応じて、[アプリケーション](/glossary/アプリケーション/)の[要件](/glossary/要件/)に合わせて検証を加えてください。

## 省略可能な値には既定値を使う

`??` は左側の[キー](/glossary/キー/)が存在しないか、値が `null` の場合に右側の値を使います。存在しない[キー](/glossary/キー/)をこの方法で[確認](/glossary/確認/)しても、`Undefined array key` は発生しません。

```php
<?php
$action = $_POST['action'] ?? 'default';
```

`false`、`0`、空文字列は `null` ではないため、そのまま使われます。空文字列も既定値に置き換えたい場合は、入力の条件を別に決めて検証してください。

## nullとキーの存在を区別する

`isset()` は[キー](/glossary/キー/)が存在し、値が `null` ではないときに `true` を返します。一方、`array_key_exists()` は、値が `null` でも[キー](/glossary/キー/)が存在すれば `true` を返します。

```php
<?php
$row = ['name' => null];

var_dump(isset($row['name']));             // false
var_dump(array_key_exists('name', $row));  // true
```

値を使えるか確かめたい場合と、[キー](/glossary/キー/)が送られてきたかだけを確かめたい場合で使い分けます。`array_key_exists()` の第2[引数](/glossary/引数/)は配列です。

## キーの型と集計処理を確認する

PHP の配列では、文字列の `"8"` は整数[キー](/glossary/キー/) `8` として扱われます。一方、`"08"` は文字列[キー](/glossary/キー/)のままです。データを作る側と読む側で、意図した[キー](/glossary/キー/)になっているか[確認](/glossary/確認/)してください。

また、存在しない[キー](/glossary/キー/)に対して `$count[$word]++` のように読みながら[更新](/glossary/更新/)すると、警告が出ます。件数を数える場合は、最初の値を用意できます。

```php
<?php
$count = [];
foreach ($words as $word) {
    $count[$word] = ($count[$word] ?? 0) + 1;
}
```

参考資料：[PHP配列の説明](https://www.php.net/manual/ja/language.types.array.php)、[null合体演算子](https://www.php.net/manual/ja/language.operators.comparison.php)、[array_key_exists](https://www.php.net/manual/ja/function.array-key-exists.php)、[PHP 8.0の変更点](https://github.com/php/php-src/blob/PHP-8.0/UPGRADING)、[PHP 8.5の配列アクセス実装](https://github.com/php/php-src/blob/php-8.5.12/Zend/zend_execute.c)、[PHP 7.4の実装](https://github.com/php/php-src/blob/php-7.4.33/Zend/zend_execute.c)。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご[確認](/glossary/確認/)ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
