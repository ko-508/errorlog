---
title: "PostgreSQLのDB不存在エラー対処法"
date: 2026-10-17
slug: postgresql_database_does_not_exist
draft: false
description: "FATAL: database does not existで接続できないときは、接続先サーバーとデータベース名を確認します。名前省略時の既定値、既存DBの一覧、必要な場合の作成、Dockerの初期化済みボリュームを説明します。"
tags: ["PostgreSQL", "Docker"]
images: ["og/posts/postgresql_database_does_not_exist.png"]
errorCode: "database does not exist"
service: "PostgreSQL"
error_type: "database_not_found"
components: ["libpq", "psql"]
related_services: ["Docker"]
trend_incident: false
---

## 冒頭まとめ

PostgreSQLへ接続するとき、次の[エラー](/glossary/エラー/)が出ることがあります。

```text
FATAL:  database "myapp" does not exist
```

通常は、接続しようとした[サーバー](/glossary/サーバー/)に`myapp`という名前の[データベース](/glossary/データベース/)が見つかっていません。まず接続先と名前を確認します。別の[サーバー](/glossary/サーバー/)へ接続している場合や、名前を省略したために意図しない名前が使われた場合もあります。

既存のデータを使うつもりなら、すぐに同名の空の[データベース](/glossary/データベース/)を作らないでください。正しい接続先を確認し、新規作成が必要な場合だけ作成します。

## エラーが示すのは接続先のデータベース名

[PostgreSQLの接続初期化処理](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/utils/init/postinit.c)には、指定した[データベース](/glossary/データベース/)が見つからないと接続を終了する処理があります。SQLSTATEという5文字の[エラー](/glossary/エラー/)識別子は`3D000`です。[公式のエラーコード表](https://www.postgresql.org/docs/18/errcodes-appendix.html)では`invalid_catalog_name`に[対応](/glossary/対応/)します。

`myapp`は接続時に使われた名前です。[エラー](/glossary/エラー/)に書かれた名前が、[設定](/glossary/設定/)したつもりの名前と一致するか確認してください。psqlやアプリが付ける前置き、接続先の表示は[クライアント](/glossary/クライアント/)によって異なります。

このメッセージは、少なくともPostgreSQL[サーバー](/glossary/サーバー/)から応答を受けたことを示します。ただし、その[サーバー](/glossary/サーバー/)が意図した接続先だとは限りません。

同じ文言に`DETAIL`が付き、接続中の[削除](/glossary/削除/)・名前変更や、保存先[ディレクトリ](/glossary/ディレクトリ/)の欠落が示される場合もあります。その場合は単なる作り忘れと決めつけず、詳細とサーバーログを確認します。

## 接続先を変えずに既存DBを一覧で確認する

アプリが接続するホスト、[ポート](/glossary/ポート/)、ユーザー名を確認し、同じ[サーバー](/glossary/サーバー/)の既存[データベース](/glossary/データベース/)へ接続します。次はローカルの5432番[ポート](/glossary/ポート/)、管理用[ロール](/glossary/ロール/)`postgres`を使う例です。

```bash
psql -h localhost -p 5432 -U postgres -d postgres -l
```

値は実際の構成に置き換えます。管理用[ロール](/glossary/ロール/)が`postgres`とは限らず、`postgres`[データベース](/glossary/データベース/)も[削除](/glossary/削除/)されていれば使えません。その場合は、利用可能な[ロール](/glossary/ロール/)と既存[データベース](/glossary/データベース/)を管理者に確認してください。

[psql公式文書](https://www.postgresql.org/docs/18/app-psql.html)によると、`-l`は一覧を表示して終了します。ここでは接続先[データベース](/glossary/データベース/)も`-d postgres`で明示しています。

接続後なら、一覧と現在の接続情報を次で確認できます。

```text
\l
\conninfo
```

一覧に目的の名前があれば、アプリ側の接続先や名前の食い違いを調べます。別の[ポート](/glossary/ポート/)で動くローカルPostgreSQL、別の[Docker](/glossary/docker/)[コンテナ](/glossary/コンテナ/)、開発用と本番用などを取り違えていないかも確認してください。

[パスワード](/glossary/パスワード/)を含む接続[URL](/glossary/url/)を、調査のためにそのまま公開しないようにします。

## 名前を省略するとユーザー名が使われる

[libpqの接続パラメータの公式説明](https://www.postgresql.org/docs/18/libpq-connect.html#LIBPQ-PARAMKEYWORDS)では、`dbname`の既定は接続ユーザー名と同じです。psqlでも、ほかに指定がなければこの動作を使います。

たとえば次の[コマンド](/glossary/コマンド/)では、[環境変数](/glossary/環境変数/)などに別の指定がなければ、`appuser`という[データベース](/glossary/データベース/)へ接続しようとします。

```bash
psql -h localhost -p 5432 -U appuser
```

[ロール](/glossary/ロール/)`appuser`を作ることと、同名の[データベース](/glossary/データベース/)を作ることは別です。既存の`myapp`を使いたいなら、名前を明示します。

```bash
psql -h localhost -p 5432 -U appuser -d myapp
```

`PGDATABASE`などの[環境変数](/glossary/環境変数/)、接続サービスの[設定](/glossary/設定/)、アプリの接続[URL](/glossary/url/)に名前が指定されている場合もあります。省略したから必ず[OS](/glossary/os/)のユーザー名になる、と一律には判断しません。

大文字・小文字にも注意します。[SQLの識別子の公式規則](https://www.postgresql.org/docs/18/sql-syntax-lexical.html#SQL-SYNTAX-IDENTIFIERS)では、二重引用符で囲まない名前は小文字へ変換されます。[SQL](/glossary/sql/)で`CREATE DATABASE MyApp;`と書けば`myapp`、`CREATE DATABASE "MyApp";`なら大文字を含む`MyApp`です。

接続[パラメータ](/glossary/パラメータ/)の名前は[SQL](/glossary/sql/)の識別子とは扱いが異なります。[シェル](/glossary/シェル/)で引用符を付けるだけで小文字へ変換されるわけではありません。一覧にある実際の名前と接続設定を合わせてください。

## 新規DBが必要な場合だけ作成する

新しいアプリ用の[データベース](/glossary/データベース/)をまだ作っていない場合は、既存の[データベース](/glossary/データベース/)へ接続し、作成します。

```bash
psql -h localhost -p 5432 -U postgres -d postgres
```

psqlの中で、次を実行します。

```sql
CREATE DATABASE myapp;
```

[CREATE DATABASEの公式説明](https://www.postgresql.org/docs/18/sql-createdatabase.html)では、作成にはスーパーユーザーまたは`CREATEDB`[権限](/glossary/権限/)が必要です。通常、作成した[ロール](/glossary/ロール/)が所有者になります。アプリ用の別[ロール](/glossary/ロール/)を所有者にする場合は、その[権限](/glossary/権限/)と運用も確認します。

作成後、接続先を明示して確認します。

```bash
psql -h localhost -p 5432 -U postgres -d myapp
```

`CREATE DATABASE`は空のアプリ用[データベース](/glossary/データベース/)を用意する操作で、失われた[テーブル](/glossary/テーブル/)やデータを[復元](/glossary/復元/)する操作ではありません。アプリに必要な[テーブル](/glossary/テーブル/)作成や、[バックアップ](/glossary/バックアップ/)からの[復元](/glossary/復元/)は別途必要です。

以前あったはずの[データベース](/glossary/データベース/)が突然見えなくなった場合は、接続先や保存領域、復旧手順を先に調べます。サーバーログに[データベース](/glossary/データベース/)の[ディレクトリ](/glossary/ディレクトリ/)欠落が示されている場合も、[ファイル](/glossary/ファイル/)を手で作って済ませないでください。

## DockerのPOSTGRES_DBは初回作成用の設定

[PostgreSQL公式イメージの説明](https://github.com/docker-library/docs/blob/master/postgres/README.md)では、`POSTGRES_DB`は初回起動時に作る[データベース](/glossary/データベース/)名の指定です。省略時は`POSTGRES_USER`と同じ名前となり、`POSTGRES_USER`の既定は`postgres`です。

重要なのは、これらが既存データを毎回変更する[設定](/glossary/設定/)ではないことです。公式文書は、初期化用の[環境変数](/glossary/環境変数/)が働くのは空のデータディレクトリで起動する場合に限ると説明しています。[起動スクリプト](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh)も、`PGDATA/PG_VERSION`を使って初期化済みかを判定しています。

既存ボリュームを使ったままComposeの`POSTGRES_DB`を変え、[コンテナ](/glossary/コンテナ/)を作り直しても、追加の[データベース](/glossary/データベース/)は自動作成されません。まず[ログ](/glossary/ログ/)を確認します。

```bash
docker logs my-postgres
```

`Skipping initialization`を含む表示は、[初期化](/glossary/初期化/)を飛ばした手がかりです。ただし、それだけで目的の[データベース](/glossary/データベース/)の有無までは分からないため、一覧も確認します。

```bash
docker exec -it my-postgres psql -U postgres -d postgres -l
```

`my-postgres`は[コンテナ](/glossary/コンテナ/)名の例です。[ロール](/glossary/ロール/)と接続先は、初期化時に実際に作られたものに合わせます。

新規作成する方針なら、既存データを残したまま実行できます。

```bash
docker exec -it my-postgres psql -U postgres -d postgres -c "CREATE DATABASE myapp;"
```

ボリュームを[削除](/glossary/削除/)すると、そこに[保存](/glossary/保存/)された既存データを失います。この[エラー](/glossary/エラー/)への通常の対処として、`docker compose down -v`などによる[削除](/glossary/削除/)は行いません。

[公式イメージのIssue #453](https://github.com/docker-library/postgres/issues/453)には、[環境変数](/glossary/環境変数/)で指定した名前の[データベース](/glossary/データベース/)が見つからなかった報告があります。報告だけでボリューム再利用が原因だったと確定することはできません。初期化条件の説明は、公式文書と起動処理を根拠にしています。

## ロール・テーブル・接続拒否との違い

`role "appuser" does not exist`は、接続に使う[ロール](/glossary/ロール/)が存在しないという別の問題です。[ロール](/glossary/ロール/)名と[データベース](/glossary/データベース/)名は別々に確認します。[Docker](/glossary/docker/)公式[イメージ](/glossary/イメージ/)には初期化時に両方を作る仕組みがありますが、通常の[ロール](/glossary/ロール/)作成が同名[データベース](/glossary/データベース/)を常に作るわけではありません。

`relation "table_name" does not exist`は、接続後に[テーブル](/glossary/テーブル/)などを参照したときの問題です。今回の[データベース](/glossary/データベース/)名の確認とは異なり、[テーブル](/glossary/テーブル/)名や[スキーマ](/glossary/スキーマ/)、必要な[テーブル](/glossary/テーブル/)の作成状態を調べます。

`connection refused`は、指定した接続先で接続を受け付けてもらえない状態です。今回の[サーバー](/glossary/サーバー/)応答とは段階が違います。

`password authentication failed`や`no pg_hba.conf entry`は[認証](/glossary/認証/)・接続許可に関する問題です。今回の[エラー](/glossary/エラー/)を消すために、[パスワード](/glossary/パスワード/)の変更や接続許可の緩和を一律に行う必要はありません。

## 解決手順のまとめ

[エラー](/glossary/エラー/)に出た[データベース](/glossary/データベース/)名と、ホスト・[ポート](/glossary/ポート/)・接続[ロール](/glossary/ロール/)を確認します。同じ[サーバー](/glossary/サーバー/)の既存[データベース](/glossary/データベース/)へ接続し、一覧に実際にどの名前があるか調べてください。

名前の省略や大文字・小文字の食い違いなら、接続設定を直します。新規作成が必要なら[権限](/glossary/権限/)のある[ロール](/glossary/ロール/)で作成します。以前のデータを使いたい場合は、空の[データベース](/glossary/データベース/)を作る前に、接続先と保存領域を確認します。

[Docker](/glossary/docker/)では、初期化済みのデータ領域に対して`POSTGRES_DB`を変えるだけでは追加作成されない点を確認します。既存データを[削除](/glossary/削除/)せずに調査と作成を進めてください。

この記事はPostgreSQL 18の公式文書、18系の接続初期化実装、[Docker](/glossary/docker/)公式[イメージ](/glossary/イメージ/)の資料と起動処理を照合して作成しました。実行環境にPostgreSQL・[Docker](/glossary/docker/)がないため、掲載した接続・[SQL](/glossary/sql/)・[コンテナ](/glossary/コンテナ/)操作は未実行です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
