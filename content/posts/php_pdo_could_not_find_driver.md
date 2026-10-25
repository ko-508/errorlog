---
title: "PHPのPDOドライバ不足の対処法"
date: 2026-10-25
slug: php_pdo_could_not_find_driver
draft: false
description: "PDOException: could not find driverは、接続に必要なPDOドライバが見つからないエラーです。DSNの先頭とドライバ一覧を照合し、CLI・Webの設定差、WindowsやDockerでの拡張の有効化を確認します。"
tags: ["PHP", "PDO"]
images: ["og/posts/php_pdo_could_not_find_driver.png"]
errorCode: "could not find driver"
service: "PHP"
error_type: "could not find driver"
components: ["PDO", "PDO drivers"]
related_services: ["MySQL", "PostgreSQL", "SQLite", "Docker"]
trend_incident: false
---

## 冒頭まとめ

PHPでPDOを使ってデータベースへ接続しようとすると、次の例外が出ることがあります。

```text
PDOException: could not find driver
```

接続文字列が指定する種類のPDOドライバを、実行中のPHPが見つけられなかったことを示します。PDOは、データベースを共通の方法で操作する仕組みです。PDO本体と、MySQLなどの種類ごとのドライバは分けて確認する必要があります。

まず接続文字列の先頭と `PDO::getAvailableDrivers()` の結果を照合します。必要なドライバが無ければ、エラーを出したPHPの環境へ導入・有効化してください。

## 接続前にDSNの先頭とドライバを照合する

DSNは、接続先を表す文字列です。たとえば `mysql:host=localhost;dbname=myapp` なら、最初のコロンより前の `mysql` がドライバ名です。

[PHP 8.5.12の実装](https://github.com/php/php-src/blob/php-8.5.12/ext/pdo/pdo_dbh.c)では、この名前に対応する登録済みのドライバを探し、見つからなければ `could not find driver` を投げます。この段階では、そのドライバによる接続処理へ進んでいません。

そのため、このエラーからホスト名やパスワードの正しさは判断できません。先にドライバの問題を解消し、その後に接続先の確認へ進みます。

同じ実装のコメントには、パスワードが含まれる可能性があるためDSNをエラー文に入れないと書かれています。調査のためにDSN全体や認証情報を公開せず、必要なドライバ名を切り分けて確認してください。

## 実行中のPHPで利用できるドライバを確認する

CLIでエラーが出た場合は、同じPHPで次を実行します。

```bash
php -r "print_r(PDO::getAvailableDrivers());"
php -m
php --ini
```

[PDO::getAvailableDrivers()の公式説明](https://www.php.net/manual/en/pdo.getavailabledrivers.php)では、現在利用できるPDOドライバ名の配列が返ります。ドライバが無ければ空の配列になります。

DSNが `mysql:` なら一覧に `mysql` が必要です。`php -m` にPDOと表示されていても、それだけではMySQL用ドライバが使えるとは判断できません。また、mysqliとPDO_MYSQLは別の拡張なので、mysqliの有効化だけで済ませないようにします。

Webの処理で失敗する場合は、対象アプリの管理者用の診断処理やログで確認します。

```php
<?php
error_log('PHP=' . PHP_VERSION . ' SAPI=' . PHP_SAPI);
error_log('PDO drivers=' . implode(',', PDO::getAvailableDrivers()));
error_log('php.ini=' . (php_ini_loaded_file() ?: '(none)'));
```

CLIの結果と比較し、同じPHPの版と設定かを確認してください。もしここでPDOクラス自体が無いという別のエラーになるなら、各ドライバより先にPDO本体を確認します。

## DSNはmysql・pgsql・sqliteの名前に合わせる

使用するデータベースとDSNの先頭を確認します。[MySQL用の説明](https://www.php.net/manual/en/ref.pdo-mysql.connection.php)では `mysql:`、[PostgreSQL用の説明](https://www.php.net/manual/en/ref.pdo-pgsql.connection.php)では `pgsql:`、[SQLite用の説明](https://www.php.net/manual/en/ref.pdo-sqlite.connection.php)では `sqlite:` を使います。

PostgreSQLだから `postgresql:`、という指定にはしません。必要な拡張が入っていても、登録名と異なる指定なら見つかりません。公式の小文字の表記に合わせてください。

対応する拡張名は、MySQLなら `pdo_mysql`、PostgreSQLなら `pdo_pgsql`、SQLiteなら `pdo_sqlite` です。設定ファイルに書く拡張名と、DSNに書く名前は同じ文字列ではありません。

フレームワークを使っている場合は、アプリの設定からどのデータベース用のDSNが生成されているかを確認します。エラーを消すために実際の接続先とは違う種類へ変更するのではなく、意図した接続先とドライバを合わせます。

## Windowsでは読み込むphp.iniと拡張ファイルを確認する

[PDOの導入手順](https://www.php.net/manual/en/pdo.installation.php)では、WindowsのPDO本体は既定で有効で、データベースごとのドライバをphp.iniで有効にするよう案内されています。MySQL用の例は次です。

```ini
extension=pdo_mysql
```

既存の行が `;extension=pdo_mysql` なら、先頭のセミコロンはコメントを意味します。必要な拡張ファイルが `extension_dir` に存在することを確認してから有効にしてください。行を追加するだけで、存在しない拡張ファイルが導入されるわけではありません。

CLIなら `php --ini`、Webなら対象アプリでの `php_ini_loaded_file()` の結果を使い、実際に読むファイルを確認します。[PHPの設定ファイルの説明](https://www.php.net/manual/en/configuration.file.php)には、実行方式ごとの指定と、追加iniファイルの読み込みがあります。名前が同じphp.iniを別の場所で編集していないかも確認してください。

変更後はPHPを再起動します。Webで常駐しているPHP-FPMやApacheなどは、利用環境の管理手順に従って設定を反映してください。CLIは新たに起動したPHPで確認します。

起動時に拡張を読み込めない警告が出る場合は、その警告を先に調べます。最終的に対象のPHPでドライバ名が一覧に現れたかまで確認してください。

## LinuxとDockerはPHPの導入方法に合わせる

LinuxでOSのパッケージとしてPHPを導入している場合は、同じ配布元・PHPの版に対応するPDOドライバのパッケージを確認します。パッケージ名は環境によって異なるため、別の版向けの名前をそのまま使わないでください。

Docker公式PHPイメージでは、[公式の拡張導入手順](https://hub.docker.com/_/php)にある `docker-php-ext-install` などを使います。MySQL用ドライバを追加するDockerfileの構成例です。

```dockerfile
FROM php:8.5.12-apache
RUN docker-php-ext-install pdo_mysql
```

このベースイメージのタグは、確認時点の[公式のタグ一覧](https://github.com/docker-library/docs/blob/master/php/README.md)に記載されています。実際のプロジェクトでは、利用中の実行方式と更新方針に合うベースイメージへ変更してください。拡張によっては、組み立てるための追加ライブラリも必要です。

Dockerfileを変えた後はイメージを作り直し、そのイメージを使うコンテナへ反映します。稼働中のコンテナの中だけで手作業すると、作り直した際に変更が失われるため、構成ファイルへ記録します。

Docker公式PHPイメージへOS配布のPHPパッケージを追加すると、別のPHPが混在する問題があります。公式説明もこの組み合わせを区別しているため、OSのPHPと公式PHPイメージの手順を混ぜないようにします。

## ドライバが見えた後に接続結果を確認する

必要な名前が `PDO::getAvailableDrivers()` に現れたら、同じWeb処理やCLIコマンドで接続を再試行します。CLIだけ成功してWebが同じエラーなら、Web側の設定や起動中のPHPを再確認します。

ドライバが見つかった後は、認証や接続先の問題が別のエラーとして現れる場合があります。[PostgreSQLのconnection refused](/posts/postgresql_connection_refused/)は接続先に到達できない問題、[password authentication failed](/posts/postgresql_password_authentication_failed/)は認証の問題です。

[database does not exist](/posts/postgresql_database_does_not_exist/)は、サーバー側に指定のデータベースが無い場合です。本件のドライバ不足とは、確認する段階が異なります。

エラーメッセージが変わった場合は、新しい文言を記録して次の問題を調べてください。ドライバの有効化と、データベース接続の成功は分けて確認します。

## 解決手順のまとめ

DSNの先頭と、エラーを出したPHPの利用可能なドライバ名を照合します。必要なドライバが無ければ、Windowsの拡張設定、Linuxの対応パッケージ、Dockerのイメージ構成など、導入方法に合わせて追加します。

設定反映後は同じ実行環境でドライバ一覧を再確認し、接続を試します。CLIでの確認だけでWeb側も直ったと判断せず、実際に失敗していた処理の結果まで確認してください。

本記事は2026年10月25日に確認した公式資料とPHP 8.5.12の実装に基づきます。掲載コード・コマンド、Dockerイメージの組み立てと接続処理は実行未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
