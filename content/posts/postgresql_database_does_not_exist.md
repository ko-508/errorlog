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

PostgreSQLへ接続するとき、次のエラーが出ることがあります。

```text
FATAL:  database "myapp" does not exist
```

通常は、接続しようとしたサーバーに`myapp`という名前のデータベースが見つかっていません。まず接続先と名前を確認します。別のサーバーへ接続している場合や、名前を省略したために意図しない名前が使われた場合もあります。

既存のデータを使うつもりなら、すぐに同名の空のデータベースを作らないでください。正しい接続先を確認し、新規作成が必要な場合だけ作成します。

## エラーが示すのは接続先のデータベース名

[PostgreSQLの接続初期化処理](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/utils/init/postinit.c)には、指定したデータベースが見つからないと接続を終了する処理があります。SQLSTATEという5文字のエラー識別子は`3D000`です。[公式のエラーコード表](https://www.postgresql.org/docs/18/errcodes-appendix.html)では`invalid_catalog_name`に対応します。

`myapp`は接続時に使われた名前です。エラーに書かれた名前が、設定したつもりの名前と一致するか確認してください。psqlやアプリが付ける前置き、接続先の表示はクライアントによって異なります。

このメッセージは、少なくともPostgreSQLサーバーから応答を受けたことを示します。ただし、そのサーバーが意図した接続先だとは限りません。

同じ文言に`DETAIL`が付き、接続中の削除・名前変更や、保存先ディレクトリの欠落が示される場合もあります。その場合は単なる作り忘れと決めつけず、詳細とサーバーログを確認します。

## 接続先を変えずに既存DBを一覧で確認する

アプリが接続するホスト、ポート、ユーザー名を確認し、同じサーバーの既存データベースへ接続します。次はローカルの5432番ポート、管理用ロール`postgres`を使う例です。

```bash
psql -h localhost -p 5432 -U postgres -d postgres -l
```

値は実際の構成に置き換えます。管理用ロールが`postgres`とは限らず、`postgres`データベースも削除されていれば使えません。その場合は、利用可能なロールと既存データベースを管理者に確認してください。

[psql公式文書](https://www.postgresql.org/docs/18/app-psql.html)によると、`-l`は一覧を表示して終了します。ここでは接続先データベースも`-d postgres`で明示しています。

接続後なら、一覧と現在の接続情報を次で確認できます。

```text
\l
\conninfo
```

一覧に目的の名前があれば、アプリ側の接続先や名前の食い違いを調べます。別のポートで動くローカルPostgreSQL、別のDockerコンテナ、開発用と本番用などを取り違えていないかも確認してください。

パスワードを含む接続URLを、調査のためにそのまま公開しないようにします。

## 名前を省略するとユーザー名が使われる

[libpqの接続パラメータの公式説明](https://www.postgresql.org/docs/18/libpq-connect.html#LIBPQ-PARAMKEYWORDS)では、`dbname`の既定は接続ユーザー名と同じです。psqlでも、ほかに指定がなければこの動作を使います。

たとえば次のコマンドでは、環境変数などに別の指定がなければ、`appuser`というデータベースへ接続しようとします。

```bash
psql -h localhost -p 5432 -U appuser
```

ロール`appuser`を作ることと、同名のデータベースを作ることは別です。既存の`myapp`を使いたいなら、名前を明示します。

```bash
psql -h localhost -p 5432 -U appuser -d myapp
```

`PGDATABASE`などの環境変数、接続サービスの設定、アプリの接続URLに名前が指定されている場合もあります。省略したから必ずOSのユーザー名になる、と一律には判断しません。

大文字・小文字にも注意します。[SQLの識別子の公式規則](https://www.postgresql.org/docs/18/sql-syntax-lexical.html#SQL-SYNTAX-IDENTIFIERS)では、二重引用符で囲まない名前は小文字へ変換されます。SQLで`CREATE DATABASE MyApp;`と書けば`myapp`、`CREATE DATABASE "MyApp";`なら大文字を含む`MyApp`です。

接続パラメータの名前はSQLの識別子とは扱いが異なります。シェルで引用符を付けるだけで小文字へ変換されるわけではありません。一覧にある実際の名前と接続設定を合わせてください。

## 新規DBが必要な場合だけ作成する

新しいアプリ用のデータベースをまだ作っていない場合は、既存のデータベースへ接続し、作成します。

```bash
psql -h localhost -p 5432 -U postgres -d postgres
```

psqlの中で、次を実行します。

```sql
CREATE DATABASE myapp;
```

[CREATE DATABASEの公式説明](https://www.postgresql.org/docs/18/sql-createdatabase.html)では、作成にはスーパーユーザーまたは`CREATEDB`権限が必要です。通常、作成したロールが所有者になります。アプリ用の別ロールを所有者にする場合は、その権限と運用も確認します。

作成後、接続先を明示して確認します。

```bash
psql -h localhost -p 5432 -U postgres -d myapp
```

`CREATE DATABASE`は空のアプリ用データベースを用意する操作で、失われたテーブルやデータを復元する操作ではありません。アプリに必要なテーブル作成や、バックアップからの復元は別途必要です。

以前あったはずのデータベースが突然見えなくなった場合は、接続先や保存領域、復旧手順を先に調べます。サーバーログにデータベースのディレクトリ欠落が示されている場合も、ファイルを手で作って済ませないでください。

## DockerのPOSTGRES_DBは初回作成用の設定

[PostgreSQL公式イメージの説明](https://github.com/docker-library/docs/blob/master/postgres/README.md)では、`POSTGRES_DB`は初回起動時に作るデータベース名の指定です。省略時は`POSTGRES_USER`と同じ名前となり、`POSTGRES_USER`の既定は`postgres`です。

重要なのは、これらが既存データを毎回変更する設定ではないことです。公式文書は、初期化用の環境変数が働くのは空のデータディレクトリで起動する場合に限ると説明しています。[起動スクリプト](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh)も、`PGDATA/PG_VERSION`を使って初期化済みかを判定しています。

既存ボリュームを使ったままComposeの`POSTGRES_DB`を変え、コンテナを作り直しても、追加のデータベースは自動作成されません。まずログを確認します。

```bash
docker logs my-postgres
```

`Skipping initialization`を含む表示は、初期化を飛ばした手がかりです。ただし、それだけで目的のデータベースの有無までは分からないため、一覧も確認します。

```bash
docker exec -it my-postgres psql -U postgres -d postgres -l
```

`my-postgres`はコンテナ名の例です。ロールと接続先は、初期化時に実際に作られたものに合わせます。

新規作成する方針なら、既存データを残したまま実行できます。

```bash
docker exec -it my-postgres psql -U postgres -d postgres -c "CREATE DATABASE myapp;"
```

ボリュームを削除すると、そこに保存された既存データを失います。このエラーへの通常の対処として、`docker compose down -v`などによる削除は行いません。

[公式イメージのIssue #453](https://github.com/docker-library/postgres/issues/453)には、環境変数で指定した名前のデータベースが見つからなかった報告があります。報告だけでボリューム再利用が原因だったと確定することはできません。初期化条件の説明は、公式文書と起動処理を根拠にしています。

## ロール・テーブル・接続拒否との違い

`role "appuser" does not exist`は、接続に使うロールが存在しないという別の問題です。ロール名とデータベース名は別々に確認します。Docker公式イメージには初期化時に両方を作る仕組みがありますが、通常のロール作成が同名データベースを常に作るわけではありません。

`relation "table_name" does not exist`は、接続後にテーブルなどを参照したときの問題です。今回のデータベース名の確認とは異なり、テーブル名やスキーマ、必要なテーブルの作成状態を調べます。

`connection refused`は、指定した接続先で接続を受け付けてもらえない状態です。今回のサーバー応答とは段階が違います。

`password authentication failed`や`no pg_hba.conf entry`は認証・接続許可に関する問題です。今回のエラーを消すために、パスワードの変更や接続許可の緩和を一律に行う必要はありません。

## 解決手順のまとめ

エラーに出たデータベース名と、ホスト・ポート・接続ロールを確認します。同じサーバーの既存データベースへ接続し、一覧に実際にどの名前があるか調べてください。

名前の省略や大文字・小文字の食い違いなら、接続設定を直します。新規作成が必要なら権限のあるロールで作成します。以前のデータを使いたい場合は、空のデータベースを作る前に、接続先と保存領域を確認します。

Dockerでは、初期化済みのデータ領域に対して`POSTGRES_DB`を変えるだけでは追加作成されない点を確認します。既存データを削除せずに調査と作成を進めてください。

この記事はPostgreSQL 18の公式文書、18系の接続初期化実装、Docker公式イメージの資料と起動処理を照合して作成しました。実行環境にPostgreSQL・Dockerがないため、掲載した接続・SQL・コンテナ操作は未実行です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
