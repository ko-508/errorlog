---
title: "PHPのメモリ上限エラー対処法"
date: 2026-10-22
slug: php_allowed_memory_size_exhausted
draft: false
description: "Allowed memory size exhaustedはPHPのmemory_limitを超えたエラーです。上限と追加確保量の読み方、CLIとWebで有効な設定の確認、使用量の記録、Composerでの対処を説明します。"
tags: ["PHP"]
images: ["og/posts/php_allowed_memory_size_exhausted.png"]
errorCode: "Allowed memory size exhausted"
service: "PHP"
error_type: "Allowed memory size exhausted"
components: ["Zend Memory Manager", "memory_limit"]
related_services: ["Composer", "PHP-FPM"]
trend_incident: false
---

## 冒頭まとめ

PHPの[処理](/glossary/処理/)が、次の[エラー](/glossary/エラー/)で止まることがあります。

```text
PHP Fatal error:  Allowed memory size of 134217728 bytes exhausted (tried to allocate 20480 bytes) in /var/www/app/index.php on line 42
```

PHPに[設定](/glossary/設定/)された[メモリ](/glossary/メモリ/)の上限を超えたことを示します。まず、[エラー](/glossary/エラー/)を出した実行環境で有効な `memory_limit` を確認し、[処理](/glossary/処理/)のどこで[メモリ](/glossary/メモリ/)が増えるかを調べます。

必要な処理量に対して上限が足りなければ調整します。ただし、`memory_limit = -1` にするとPHP側の制限がなくなります。[エラー](/glossary/エラー/)を消すためだけに、Webアプリ全体の上限を外す方法は避けてください。

## 最初の数字は上限で括弧内は追加確保量

例の `134217728 bytes` は上限です。`128M` を[バイト](/glossary/バイト/)に直した値に当たります。`tried to allocate 20480 bytes` は、その時点で追加して確保しようとした量です。

[PHP 8.4.27の実装](https://github.com/php/php-src/blob/php-8.4.27/Zend/zend_alloc.c)では、文言の最初に[メモリ](/glossary/メモリ/)の上限、括弧内に追加確保量を渡しています。括弧内の量が小さくても、それまでに確保した量が上限近くに達していれば失敗します。

表示された[ファイル](/glossary/ファイル/)と[行番号](/glossary/行番号/)は調査の手がかりですが、その行だけが大量に[メモリ](/glossary/メモリ/)を使ったとは限りません。前の[処理](/glossary/処理/)から保持しているデータも確認対象です。

[PHPマニュアル](https://www.php.net/manual/en/ini.core.php#ini.memory-limit)に記載された `memory_limit` の既定値は `128M` です。ただし、配布元や[サーバー](/glossary/サーバー/)、アプリの[設定](/glossary/設定/)で変更されるため、実際の値を確認してください。

## CLIとWebで有効な設定をそれぞれ確認する

[コマンドライン](/glossary/コマンドライン/)で実行した[処理](/glossary/処理/)なら、次でPHPの版、読み込む[設定ファイル](/glossary/設定ファイル/)、現在の上限を確認します。

```bash
php -v
php --ini
php -r "echo ini_get('memory_limit'), PHP_EOL;"
```

[設定ファイルの公式説明](https://www.php.net/manual/en/configuration.file.php)では、PHPの実行方法による[設定ファイル](/glossary/設定ファイル/)の指定や、追加のini[ファイル](/glossary/ファイル/)の読み込みが説明されています。[CLI](/glossary/cli/)の値を見ただけで、Web経由でも同じ[設定](/glossary/設定/)とは判断できません。

Webの[処理](/glossary/処理/)で失敗する場合は、そのアプリの診断機能や、管理者だけが実行できる確認処理を使います。たとえば対象の処理内で、次の値を[ログ](/glossary/ログ/)に記録します。

```php
<?php
error_log('PHP=' . PHP_VERSION . ' SAPI=' . PHP_SAPI);
error_log('memory_limit=' . ini_get('memory_limit'));
error_log('php.ini=' . (php_ini_loaded_file() ?: '(none)'));
```

確認用の[処理](/glossary/処理/)は公開したまま残さず、調査後に外してください。[設定ファイル](/glossary/設定ファイル/)を編集した場合も、同じ実行経路で値が変わったかを確認します。必要な再読み込みや再起動は、PHP-FPMやApacheなどの実行方式に合わせて行います。

## メモリが増える処理を記録して絞り込む

[処理](/glossary/処理/)の前後で使用量を記録します。[memory_get_usage()](https://www.php.net/manual/en/function.memory-get-usage.php)は現在の使用量、[memory_get_peak_usage()](https://www.php.net/manual/en/function.memory-get-peak-usage.php)は最大使用量を返します。

```php
<?php
function logMemory(string $label): void
{
    error_log(sprintf(
        '%s: usage=%d peak=%d bytes',
        $label,
        memory_get_usage(true),
        memory_get_peak_usage(true)
    ));
}

logMemory('before');
// 調べたい処理をここに置く
logMemory('after');
```

`true` を渡した場合は、PHPがシステムから確保した領域の量を返します。ただし、拡張機能がPHPの[メモリ](/glossary/メモリ/)管理を通さずに確保した領域などは含まれず、[OS](/glossary/os/)が見る[プロセス](/glossary/プロセス/)全体の使用量とは一致しません。

途中で停止すると後の[ログ](/glossary/ログ/)は出ないため、大きな[処理](/glossary/処理/)を小さな区切りに分けて記録します。入力件数と使用量を照合し、大量のデータをまとめて保持している場合は、分割して[処理](/glossary/処理/)できるかを検討してください。必要な量が多いのか、不要なデータを保持し続けているのかで対処が変わります。

## 上限を変えるなら実際に反映された値を見る

[コマンドライン](/glossary/コマンドライン/)の特定の[処理](/glossary/処理/)だけ上限を変える例です。`script.php` は実行する[ファイル](/glossary/ファイル/)に置き換えます。

```bash
php -d memory_limit=256M script.php
```

php.iniに書く場合は、次の形です。

```ini
memory_limit = 256M
```

256Mは例です。必要量と実行環境の[容量](/glossary/容量/)を確認して決めてください。Webで複数の[処理](/glossary/処理/)が同時に走る場合、1回の[処理](/glossary/処理/)の上限だけで[サーバー](/glossary/サーバー/)全体の使用量を判断しないようにします。

アプリ内で変更する場合は、[メモリ](/glossary/メモリ/)を使い切る前に[設定](/glossary/設定/)し、変更後の値を確認します。

```php
<?php
$previous = ini_set('memory_limit', '256M');
if ($previous === false) {
    error_log('memory_limit could not be changed');
}
error_log('effective memory_limit=' . ini_get('memory_limit'));
```

変更できない場合は管理側の制限を確認します。[PHP-FPMの公式説明](https://www.php.net/manual/en/install.fpm.configuration.php)では、`php_admin_value` で指定した値は `ini_set()` で上書きできません。

PHP 8.5以降には、`memory_limit` に指定できる最大値を決める `max_memory_limit` もあります。これを超える値は警告とともに上限へ制限されます。アプリ側の指定を繰り返す前に、[管理側の設定](https://www.php.net/manual/en/ini.core.php#ini.max-memory-limit)を確認してください。

## Composerの場合はComposer自身の設定を確認する

[Composerの公式の対処手順](https://getcomposer.org/doc/articles/troubleshooting.md#memory-limit-errors)は、まずComposer 2を使っているかを確認するよう案内しています。

```bash
composer --version
```

同文書では、Composerが内部で `memory_limit` を1.5Gへ引き上げることと、`COMPOSER_MEMORY_LIMIT` を参照することが説明されています。通常の `php -r` で見た値が、そのままComposer実行中の値になるとは限りません。

上限を指定して実行する例です。2Gは必要量を示す推奨値ではなく、指定方法を示す例です。

```bash
# Linux / macOSのシェル
COMPOSER_MEMORY_LIMIT=2G composer install
```

`composer.phar` を直接実行する場合は、PHPの[引数](/glossary/引数/)でも指定できます。

```bash
php -d memory_limit=2G composer.phar install
```

公式文書には `-1` で制限を外す方法もありますが、[メモリ](/glossary/メモリ/)の[容量](/glossary/容量/)を増やす指定ではありません。また、Composerが呼び出す外部[コマンド](/glossary/コマンド/)や子[プロセス](/glossary/プロセス/)では、別の設定確認が必要な場合があります。

## OOMKilledとの違いとPHP更新の確認

[KubernetesのOOMKilled](/posts/kubernetes_oomkilled/)は[コンテナ](/glossary/コンテナ/)側で確認する終了理由です。本件の `Allowed memory size ... exhausted` はPHPの上限による[エラー](/glossary/エラー/)なので、まずPHPの[設定](/glossary/設定/)と[ログ](/glossary/ログ/)を確認します。PHPの上限を増やしても、[コンテナ](/glossary/コンテナ/)や[OS](/glossary/os/)側の[容量](/glossary/容量/)は増えません。

PHP 8.4.27の実装には、さらに上の制限に達したときに `Hard memory limit of ... exhausted` を出す[処理](/glossary/処理/)もあります。この別の表示が出ている場合は、通常の上限超過と区別してPHPの版と[ログ](/glossary/ログ/)を確認してください。

2026年10月21日には、[メモリ](/glossary/メモリ/)不足時の内部処理に関わる脆弱性を含む[公式の更新勧告](https://www.php.net/archive/2026.php#2026-10-21-5)が公開されています。修正版は8.2.35、8.3.36、8.4.27、8.5.12です。該当する系列では修正版以降への[更新](/glossary/更新/)を確認してください。

公式勧告は、[更新](/glossary/更新/)だけが完全な対策であると説明しています。一時的な措置として示された `memory_limit=-1` を、一般的な[メモリ](/glossary/メモリ/)不足の解決策として常設しないようにします。また、本件の[エラー](/glossary/エラー/)が出ただけで攻撃を受けたとは判断できません。

## 解決手順のまとめ

最初に、失敗した実行環境の上限と[設定ファイル](/glossary/設定ファイル/)を確認します。括弧内の追加確保量だけを見ず、[処理](/glossary/処理/)の途中の使用量と最大値を記録してください。

[処理](/glossary/処理/)の分割などで使用量を減らすか、必要量を確認して上限を調整します。設定後は有効な値と処理結果を確認し、PHP自体の修正版への[更新](/glossary/更新/)も別に確認します。

本記事は2026年10月22日に確認した公式資料とPHP 8.4.27の実装に基づきます。掲載したPHP・Composerの[コマンド](/glossary/コマンド/)と[コード](/glossary/コード/)は実行未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
