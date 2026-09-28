---
title: "role does not existの対処法"
date: 2026-09-28
draft: false
description: "PostgreSQLのERROR: role does not existは、SQLや復元処理で参照したロールが存在しない場合に発生します。実行中のSQL、pg_roles、ダンプの所有者や権限を確認し、適切な順序で対処する方法を解説します。"
tags: ["PostgreSQL"]
images: ["og/posts/postgresql_role_does_not_exist.png"]
errorCode: "ERROR: role does not exist"
urgency: "medium"
service: "PostgreSQL"
error_type: "undefined_object"
components: ["roles", "pg_restore", "GRANT"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

PostgreSQLでSQLの実行やデータベースの復元を行ったとき、次のエラーが出ることがあります。

```text
ERROR:  role "app_user" does not exist
```

`app_user`というロールを参照しましたが、接続先のPostgreSQLクラスタにその名前のロールがありません。`GRANT ... TO app_user`、`ALTER TABLE ... OWNER TO app_user`、`SET ROLE app_user`、ダンプの復元など、どの操作から発生したかによって直す場所は変わります。

まず、**エラー直前のSQL**と接続先を確認してください。接続できるロールで対象クラスタに入り、次のSQLでロールの存在を調べます。

```sql
SELECT rolname, rolcanlogin
FROM pg_roles
WHERE rolname = 'app_user';
```

結果が0行で、必要なロールなら適切な権限を持つ利用者が作成します。別名のロールへ移行する設計なら、SQLや復元時の所有者指定を見直します。必要のないロールをエラーを消すためだけに作ると、意図しない所有者や権限を残すことがあります。

## role does not existとは

PostgreSQLのロールはクラスタ全体で共有されます。`pg_roles`はロールの情報を参照できるビューで、パスワードを隠した`pg_authid`の内容を表示します。データベースに接続できているなら、[公式の`pg_roles`の説明](https://www.postgresql.org/docs/current/view-pg-roles.html)に従い、このビューで対象名を確認できます。

`ERROR: role "..." does not exist`は、すでに接続したセッションで、存在しないロール名をSQLが参照したときの一つの表示です。SQLSTATEは`42704`（`undefined_object`）です。PostgreSQL本体の[`get_role_oid()`](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/utils/adt/acl.c)など、ロール名を解決する処理で発生します。

ただし、**`role "..." does not exist`という文字列だけで接続後のエラーと決めることはできません**。接続時に存在しない利用者を指定した場合、認証方式などによっては`FATAL: role "..." does not exist`と表示されます。先頭が`ERROR`か`FATAL`か、接続が成立したかを先に確認してください。

## どのSQLがロールを参照したか確認する

同じエラー文でも、直前に実行したSQLによって原因が異なります。

| エラーが出た操作 | 最初に確認するもの |
|---|---|
| `GRANT ... TO app_user`、`REVOKE ... FROM app_user` | 権限の対象として指定したロールと作成順序 |
| `ALTER TABLE ... OWNER TO app_user` | 移行先の所有者名 |
| `CREATE DATABASE ... OWNER app_user` | 作成先クラスタのロール |
| `SET ROLE app_user` | アプリケーションが切り替えようとしているロール |
| `pg_restore`、`psql -f` | ダンプ内の所有者、権限、ロール設定 |

まず、実行されたSQLに書かれた名前の大文字・小文字や引用符を確認します。PostgreSQLでは引用符を付けない識別子は小文字へ変換されます。たとえば`app_user`と`"App_User"`は異なる名前です。[識別子の公式仕様](https://www.postgresql.org/docs/current/sql-syntax-lexical.html)も参照してください。

次に、調査中のサーバーとデータベースを確かめます。

```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
SELECT rolname FROM pg_roles WHERE rolname = 'app_user';
```

`inet_server_addr()`はUnixドメインソケット経由の接続では`NULL`になる場合があります。表示されないことだけで接続先を判断せず、接続文字列や`psql`の接続情報も照合してください。ロールはクラスタ単位なので、別データベースへ切り替えただけでは作成されません。

## 原因1：GRANTやSET ROLEより前に作成していない

マイグレーションに次のようなSQLがあっても、`app_user`が存在しなければ権限を付与できません。

```sql
GRANT USAGE ON SCHEMA app TO app_user;
```

そのロールを使う設計なら、ロール作成を先に行います。

```sql
CREATE ROLE app_user WITH LOGIN;
GRANT USAGE ON SCHEMA app TO app_user;
```

`LOGIN`が必要なのは、そのロールで直接接続する場合です。権限をまとめるグループ用のロールなら、用途に応じて`NOLOGIN`を使用します。`CREATE ROLE`の実行には適切な権限が必要です。パスワードや権限は運用方針に合わせて別途設定してください。[`CREATE ROLE`の公式文書](https://www.postgresql.org/docs/current/sql-createrole.html)に属性が記載されています。

`SET ROLE app_user`で失敗した場合も、まず存在を確認します。ただしロールを作るだけでは十分ではありません。存在しても、そのロールへの切り替え権限がなければ別の権限エラーになります。環境ごとに利用者名を変えているなら、アプリケーションの接続後に実行するSQLとロールの作成手順を合わせてください。

## 原因2：復元先に所有者のロールがない

別のクラスタへ`pg_dump`のバックアップを戻すと、ダンプに記録された所有者や`GRANT`の対象ロールが復元先にないことがあります。`pg_dump`は個別のデータベースを保存しますが、クラスタ共通のロール定義は保存しません。[PostgreSQLのバックアップ手順](https://www.postgresql.org/docs/current/backup-dump.html)でも、ロールなどのグローバルオブジェクトには`pg_dumpall --globals-only`を使うと説明されています。

カスタム形式のダンプなら、復元前に内容を確認できます。

```bash
pg_restore -l backup.dump
pg_restore -f restore-preview.sql backup.dump
```

生成した`restore-preview.sql`で`OWNER TO`、`SET SESSION AUTHORIZATION`、`GRANT`、`REVOKE`などを調べます。ダンプや生成したSQLには機密情報が含まれる場合があるため、公開リポジトリへ追加しないでください。

移行元のロールを引き継ぐ場合は、移行元からグローバルオブジェクトのダンプを取得し、内容と復元先の既存ロールを確認してから、データベース本体より先に適用します。

```bash
pg_dumpall -h source_host -U admin_user --globals-only -f globals.sql
psql -X -v ON_ERROR_STOP=1 -h target_host -U admin_user -d postgres -f globals.sql
pg_restore -h target_host -U admin_user -d target_db --exit-on-error backup.dump
```

`--globals-only`にはロールだけでなく表領域なども含まれます。復元先に同名のロールがすでにある場合や権限構成が異なる場合、`globals.sql`を無条件に実行せず、適用する定義を確認してください。グローバルオブジェクトの復元には通常、十分な管理権限が必要です。

## 所有者を引き継がない復元方法

移行先では新しい所有者を使い、元のロールを作らない設計もあります。カスタム形式のアーカイブであれば、`pg_restore --no-owner`を指定すると、元の所有者を設定するSQLを出さず、復元時の接続ロールが作成したオブジェクトを所有します。

```bash
pg_restore -h target_host -U target_owner -d target_db \
  --no-owner --exit-on-error backup.dump
```

ダンプに元のロール宛ての`GRANT`や`REVOKE`も含まれている場合、所有者指定だけを省いてもエラーが残ります。元の権限付与を復元しない方針なら、`--no-acl`も追加します。

```bash
pg_restore -h target_host -U target_owner -d target_db \
  --no-owner --no-acl --exit-on-error backup.dump
```

`--no-acl`は元のアクセス権限を復元しません。アプリケーションに必要な権限を復元後に改めて付与する必要があります。所有者と権限の省略はそれぞれ別の操作です。[`pg_restore`の公式文書](https://www.postgresql.org/docs/current/app-pgrestore.html)に両オプションの効果が明記されています。

上の例は`pg_dump -Fc`などで作られたアーカイブ向けです。平文SQLのダンプを`psql`で適用する場合、`pg_restore`のオプションは使えません。ダンプを作り直せるなら、必要に応じて`pg_dump --no-owner --no-acl`などの出力設定を検討してください。単純な文字列置換でダンプ中のロール名を変更すると、意図しないSQLや文字列まで変わるおそれがあります。

## 似たエラーとの違い

`FATAL: role "app_user" does not exist`は、接続時にロールが見つからない場合の表示です。まず接続先、`-U`で指定した利用者、環境変数や接続文字列の利用者名を確認します。本記事の`ERROR:`は、接続後にSQLが参照したロール名を調べる場面を中心に扱っています。

`FATAL: password authentication failed for user "app_user"`は認証に失敗した状態です。パスワード認証では、ロールが存在しない場合でも、利用者の存在を外部へ明かさないために同じ認証失敗の文言が返ることがあります。表示だけでロールの有無を断定せず、管理者が接続先の`pg_roles`を確認してください。

`ERROR: role "app_user" already exists`は、逆に同名のロールを作ろうとして重複した場合です。`DROP ROLE IF EXISTS app_user`で出る`role "app_user" does not exist, skipping`はNOTICEで、対象がなければ削除を飛ばして処理を続けます。`IF EXISTS`は存在しないロールへの`GRANT`や所有者の指定を直す手段ではありません。

## 解決手順のまとめ

先頭が`ERROR`か`FATAL`かを確認し、`ERROR`なら直前のSQLを特定します。接続先の`pg_roles`で名前が存在するか調べ、引用符と大文字・小文字も照合してください。

`GRANT`や`SET ROLE`なら、ロールの作成順序と設定を確認します。復元時のエラーなら、元の所有者や権限を引き継ぐのか、移行先のロールへ置き換えるのかを決めます。前者はロールを先に用意し、後者は復元形式に応じて`--no-owner`と`--no-acl`を使い分けます。

復元時にエラーが出ても、`pg_restore`は既定で処理を続けます。最後のエラー件数と復元されたオブジェクトを確認し、不完全な状態を放置しないでください。再実行する前には、復元先を作り直すか、どこまで適用されたかを確認します。

免責事項：本記事の内容は一般的なPostgreSQL環境を前提としています。ロール、所有者、権限、ダンプを本番環境で変更する前に、既存の権限構成と復元先への影響を確認してください。
