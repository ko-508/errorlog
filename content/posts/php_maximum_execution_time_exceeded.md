---
title: "PHPの実行時間超過エラー対処法"
date: 2026-10-24
slug: php_maximum_execution_time_exceeded
draft: false
description: "Maximum execution time exceededはPHPの実行時間制限によるエラーです。有効な設定と遅い処理を確認し、set_time_limitでの数え直し、CLIの既定値、PHP-FPMやnginxの別の時間制限を区別して対処します。"
tags: ["PHP"]
images: ["og/posts/php_maximum_execution_time_exceeded.png"]
errorCode: "Maximum execution time exceeded"
service: "PHP"
error_type: "Maximum execution time exceeded"
components: ["max_execution_time", "set_time_limit"]
related_services: ["PHP-FPM", "nginx"]
trend_incident: false
---

## 冒頭まとめ

PHPで取り込みや集計などの処理を実行すると、次のエラーで止まることがあります。

```text
PHP Fatal error:  Maximum execution time of 30 seconds exceeded in /var/www/app/import.php on line 57
```

PHPに設定された実行時間の上限に達したことを示します。30は設定値の例です。まず失敗した実行環境で `max_execution_time` を確認し、時間のかかる処理を特定します。

必要な処理量に対して上限が短ければ調整します。ただし、OSやPHPの組み立て方によって時間の数え方が異なり、Webサーバー側にも別の制限があります。PHPの秒数を増やすだけで、必ず完了できるわけではありません。

## 30秒は必ずしも時計の30秒ではない

[PHPの公式説明](https://www.php.net/manual/en/info.configuration.php#ini.max-execution-time)では、`max_execution_time` の既定値は30秒、CLIの既定値は0です。0はPHP側の実行時間制限を設けない指定です。

一般的な `setitimer(ITIMER_PROF)` を使う環境ではCPU時間を計ります。この場合、データベースの問い合わせや入出力などで待っている時間は、経過した実時間と同じようには加算されません。

一方、Windowsや、`--enable-zend-max-execution-timers` を有効にして組み立てたPHPでは実時間を計ります。後者はPHP 8.3以降のスレッド対応の組み立てで既定です。[PHP 8.5.12の実装](https://github.com/php/php-src/blob/php-8.5.12/Zend/zend_execute_API.c)には、Apple SiliconのmacOSなどで実時間のタイマーを使う分岐もあります。

したがって、Linuxなら待ち時間は必ず除外される、Windows以外なら同じ結果になる、とも言い切れません。利用しているOSとPHPの構成を合わせて確認してください。

## エラーが出た環境の有効値を確認する

Webで失敗した処理と、ターミナルから実行した処理では、実行方式や設定が異なる場合があります。WebのエラーをCLIの設定だけで判断しないようにします。

対象の処理で、次のように実行方式と上限をログへ記録します。

```php
<?php
error_log('PHP=' . PHP_VERSION . ' SAPI=' . PHP_SAPI);
error_log('max_execution_time=' . ini_get('max_execution_time'));
```

CLI側の確認は次です。

```bash
php -v
php --ini
php -r "echo ini_get('max_execution_time'), PHP_EOL;"
```

CLIの0は変更できない固定値ではありません。[PHPのコマンドライン引数の説明](https://www.php.net/manual/en/features.commandline.options.php)には、`-d max_execution_time=20` で値を指定する例もあります。アプリ内の `set_time_limit()` などによって変わっていないかも確認してください。

確認用のコードをWebから誰でも使える状態で残さず、既存のログや管理者用の確認手段を使います。

## 時間を使っている処理を区切って調べる

エラーにあるファイルと行番号を手がかりに、処理の前後へログを追加します。ただし、その行だけが遅いとは限りません。前の処理から積み重なった時間も確認対象です。

実際の経過時間を記録する例です。

```php
<?php
$started = hrtime(true);
error_log('import: start');

// 調べたい処理をここに置く

$elapsed = (hrtime(true) - $started) / 1_000_000_000;
error_log('import: elapsed=' . $elapsed . ' seconds');
```

[hrtime()](https://www.php.net/manual/en/function.hrtime.php)は時間の計測に使う関数です。この例は経過時間を測るため、PHPの上限がCPU時間を計る環境では、その上限と同じ値にはなりません。

処理が途中で止まれば後のログは出ません。取り込み、変換、保存などの区切りにも記録を置き、最後に完了した段階を確認します。入力件数も合わせて記録し、件数を減らすと完了するのか、特定の問い合わせや通信で長く待つのかを切り分けます。

大量のデータを一括で処理しているなら分割し、無駄な繰り返しや同じ問い合わせを重ねていないかを確認します。再実行する際は、途中まで保存したデータを重複登録しないよう、処理済みの範囲も把握してください。

## set_time_limitは呼んだ時点から数え直す

必要な時間が確認できた場合は、対象処理の前で上限を変える方法があります。120秒は指定方法を示す例です。

```php
<?php
if (!set_time_limit(120)) {
    error_log('set_time_limit failed');
}
error_log('max_execution_time=' . ini_get('max_execution_time'));

// 時間のかかる処理
```

[set_time_limit()の公式説明](https://www.php.net/manual/en/function.set-time-limit.php)では、この関数は呼び出した時点からタイマーを数え直します。公式の例では、開始から25秒の時点で `set_time_limit(20)` を呼ぶと、合計45秒になります。処理全体の上限を開始時から20秒へ変更する意味ではありません。

繰り返しの中で呼び続けると、そのたびに数え直します。全体を一定時間内に終えたい処理で、無条件に呼び続ける方法は目的に合いません。

php.iniで指定する場合は、次の形です。

```ini
max_execution_time = 120
```

設定変更後は、実行方式に応じた再読み込みなどを行い、対象の処理で有効な値を確認します。[PHP-FPMの管理者設定](https://www.php.net/manual/en/install.fpm.configuration.php)など、アプリから上書きできない指定がある場合は管理側を確認してください。

`set_time_limit(0)` はPHPの時間制限を外しますが、処理を速くする指定ではありません。常時無制限にする前に、処理量と実行場所を見直します。

## 長い取り込みはWebの応答と分ける

時間のかかる取り込みや集計は、CLIでの実行や、Webから依頼を受け付けて別の処理で実行する構成を検討できます。ブラウザが結果を待ち続ける必要を減らすためです。

CLIで実行する場合の例です。

```bash
php import.php
```

ただし、CLIの既定が0でも、アプリが制限を設定する場合や、実行を管理するサービスが時間制限を持つ場合があります。CLIなら絶対に止まらない、とは判断しないでください。

CLIで明示的に120秒を指定する例は次です。

```bash
php -d max_execution_time=120 import.php
```

Webアプリの処理をそのままCLIに移せるとは限りません。ログイン情報やWebの入力を前提にした部分を確認し、実行に必要な引数や設定を用意します。長い処理では、進捗と途中結果を記録し、中断後に再開できる形にすると調査もしやすくなります。

## PHP-FPMやnginxの制限とは分けて確認する

PHP側の値を増やした後もWebで処理が切れる場合は、PHP-FPMやWebサーバーのログを照合します。

[PHP-FPMのrequest_terminate_timeout](https://www.php.net/manual/en/install.fpm.configuration.php#request-terminate-timeout)は、1件のリクエストの時間が上限を超えた場合にワーカーを終了させる設定です。既定の0では無効です。PHPの `max_execution_time` と同じ設定ではありません。

nginxからPHP-FPMへ接続している場合は、[fastcgi_read_timeout](https://nginx.org/en/docs/http/ngx_http_fastcgi_module.html#fastcgi_read_timeout)も関わります。これは応答全体の総時間ではなく、連続する読み取りの間の待ち時間です。PHPの120秒と同じ意味の120秒として扱わないでください。

利用者に[nginxの504](/posts/nginx_504/)が表示されても、それだけでPHPが本件のエラーで終了したとは分かりません。nginxが待つのをやめたのか、PHPが実行時間超過で停止したのかをログで区別します。

また、`Maximum execution time of 30+2 seconds exceeded (terminated)` のような表示は、通常の制限後の後片付けも制限に達した場合の別の文言です。[hard_timeoutの公式説明](https://www.php.net/manual/en/ini.core.php#ini.hard-timeout)に例があり、通常の30秒の表示と分けて記録します。

[Allowed memory size exhausted](/posts/php_allowed_memory_size_exhausted/)はメモリ量の制限です。実行時間の上限を増やしても、メモリ不足への対処にはなりません。

## 解決手順のまとめ

最初に、失敗した実行環境の `max_execution_time` と、処理のどこで時間を使っているかを確認します。OSやPHPの構成によって、待ち時間が上限に含まれるかが異なる点も考慮してください。

処理を改善・分割し、必要な場合は対象を限定して上限を調整します。Webから長い処理を実行しているならCLIなどへの移行を検討し、PHP-FPMやWebサーバーの別の制限も確認します。

本記事は2026年10月24日に確認した公式資料とPHP 8.5.12の実装に基づきます。掲載したPHPのコード・コマンドと時間超過の挙動は、実行未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
