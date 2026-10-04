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

PostgreSQLで[SQL](/glossary/sql/)の実行や[データベース](/glossary/データベース/)の[復元](/glossary/復元/)を行ったとき、次の[エラー](/glossary/エラー/)が出ることがあります。

```text
ERROR:  role "app_user" does not exist
```

`app_user`という[ロール](/glossary/ロール/)を参照しましたが、接続先のPostgreSQLクラスタにその名前の[ロール](/glossary/ロール/)がありません。`GRANT ... TO app_user`、`ALTER TABLE ... OWNER TO app_user`、`SET ROLE app_user`、ダンプの[復元](/glossary/復元/)など、どの操作から発生したかによって直す場所は変わります。

まず、**[エラー](/glossary/エラー/)直前の[SQL](/glossary/sql/)**と接続先を確認してください。接続できる[ロール](/glossary/ロール/)で対象クラスタに入り、次の[SQL](/glossary/sql/)で[ロール](/glossary/ロール/)の存在を調べます。

```sql
SELECT rolname, rolcanlogin
FROM pg_roles
WHERE rolname = 'app_user';
```

結果が0行で、必要な[ロール](/glossary/ロール/)なら適切な[権限](/glossary/権限/)を持つ利用者が作成します。別名の[ロール](/glossary/ロール/)へ移行する設計なら、[SQL](/glossary/sql/)や復元時の所有者指定を見直します。必要のない[ロール](/glossary/ロール/)を[エラー](/glossary/エラー/)を消すためだけに作ると、意図しない所有者や[権限](/glossary/権限/)を残すことがあります。

## role does not existとは

PostgreSQLの[ロール](/glossary/ロール/)はクラスタ全体で共有されます。`pg_roles`は[ロール](/glossary/ロール/)の情報を参照できるビューで、[パスワード](/glossary/パスワード/)を隠した`pg_authid`の内容を表示します。[データベース](/glossary/データベース/)に接続できているなら、[公式の`pg_roles`の説明](https://www.postgresql.org/docs/current/view-pg-roles.html)に従い、このビューで対象名を確認できます。

`ERROR: role "..." does not exist`は、すでに接続した[セッション](/glossary/セッション/)で、存在しない[ロール](/glossary/ロール/)名を[SQL](/glossary/sql/)が参照したときの一つの表示です。SQLSTATEは`42704`（`undefined_object`）です。PostgreSQL本体の[`get_role_oid()`](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/utils/adt/acl.c)など、[ロール](/glossary/ロール/)名を解決する処理で発生します。

ただし、**`role "..." does not exist`という文字列だけで接続後の[エラー](/glossary/エラー/)と決めることはできません**。接続時に存在しない利用者を指定した場合、認証方式などによっては`FATAL: role "..." does not exist`と表示されます。先頭が`ERROR`か`FATAL`か、接続が成立したかを先に確認してください。

## どのSQLがロールを参照したか確認する

同じ[エラー](/glossary/エラー/)文でも、直前に実行した[SQL](/glossary/sql/)によって原因が異なります。

| [エラー](/glossary/エラー/)が出た操作 | 最初に確認するもの |
|---|---|
| `GRANT ... TO app_user`、`REVOKE ... FROM app_user` | [権限](/glossary/権限/)の対象として指定した[ロール](/glossary/ロール/)と作成順序 |
| `ALTER TABLE ... OWNER TO app_user` | 移行先の所有者名 |
| `CREATE DATABASE ... OWNER app_user` | 作成先クラスタの[ロール](/glossary/ロール/) |
| `SET ROLE app_user` | [アプリケーション](/glossary/アプリケーション/)が切り替えようとしている[ロール](/glossary/ロール/) |
| `pg_restore`、`psql -f` | ダンプ内の所有者、[権限](/glossary/権限/)、[ロール](/glossary/ロール/)[設定](/glossary/設定/) |

まず、実行された[SQL](/glossary/sql/)に書かれた名前の大文字・小文字や引用符を確認します。PostgreSQLでは引用符を付けない識別子は小文字へ変換されます。たとえば`app_user`と`"App_User"`は異なる名前です。[識別子の公式仕様](https://www.postgresql.org/docs/current/sql-syntax-lexical.html)も参照してください。

次に、調査中の[サーバー](/glossary/サーバー/)と[データベース](/glossary/データベース/)を確かめます。

```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
SELECT rolname FROM pg_roles WHERE rolname = 'app_user';
```

`inet_server_addr()`はUnixドメインソケット経由の接続では`NULL`になる場合があります。表示されないことだけで接続先を判断せず、接続文字列や`psql`の接続情報も照合してください。[ロール](/glossary/ロール/)はクラスタ単位なので、別[データベース](/glossary/データベース/)へ切り替えただけでは作成されません。

## 原因1：GRANTやSET ROLEより前に作成していない

マイグレーションに次のような[SQL](/glossary/sql/)があっても、`app_user`が存在しなければ[権限](/glossary/権限/)を付与できません。

```sql
GRANT USAGE ON SCHEMA app TO app_user;
```

その[ロール](/glossary/ロール/)を使う設計なら、[ロール](/glossary/ロール/)作成を先に行います。

```sql
CREATE ROLE app_user WITH LOGIN;
GRANT USAGE ON SCHEMA app TO app_user;
```

`LOGIN`が必要なのは、その[ロール](/glossary/ロール/)で直接接続する場合です。[権限](/glossary/権限/)をまとめるグループ用の[ロール](/glossary/ロール/)なら、用途に応じて`NOLOGIN`を使用します。`CREATE ROLE`の実行には適切な[権限](/glossary/権限/)が必要です。[パスワード](/glossary/パスワード/)や[権限](/glossary/権限/)は運用方針に合わせて別途設定してください。[`CREATE ROLE`の公式文書](https://www.postgresql.org/docs/current/sql-createrole.html)に[属性](/glossary/属性/)が記載されています。

`SET ROLE app_user`で失敗した場合も、まず存在を確認します。ただし[ロール](/glossary/ロール/)を作るだけでは十分ではありません。存在しても、その[ロール](/glossary/ロール/)への切り替え[権限](/glossary/権限/)がなければ別の[権限](/glossary/権限/)[エラー](/glossary/エラー/)になります。[環境](/glossary/環境/)ごとに利用者名を変えているなら、[アプリケーション](/glossary/アプリケーション/)の接続後に実行する[SQL](/glossary/sql/)と[ロール](/glossary/ロール/)の作成手順を合わせてください。

## 原因2：復元先に所有者のロールがない

別のクラスタへ`pg_dump`の[バックアップ](/glossary/バックアップ/)を戻すと、ダンプに記録された所有者や`GRANT`の対象[ロール](/glossary/ロール/)が復元先にないことがあります。`pg_dump`は個別の[データベース](/glossary/データベース/)を[保存](/glossary/保存/)しますが、クラスタ共通の[ロール](/glossary/ロール/)定義は[保存](/glossary/保存/)しません。[PostgreSQLのバックアップ手順](https://www.postgresql.org/docs/current/backup-dump.html)でも、[ロール](/glossary/ロール/)などのグローバルオブジェクトには`pg_dumpall --globals-only`を使うと説明されています。

カスタム形式のダンプなら、復元前に内容を確認できます。

```bash
pg_restore -l backup.dump
pg_restore -f restore-preview.sql backup.dump
```

生成した`restore-preview.sql`で`OWNER TO`、`SET SESSION AUTHORIZATION`、`GRANT`、`REVOKE`などを調べます。ダンプや生成した[SQL](/glossary/sql/)には機密情報が含まれる場合があるため、公開[リポジトリ](/glossary/リポジトリ/)へ追加しないでください。

移行元の[ロール](/glossary/ロール/)を引き継ぐ場合は、移行元からグローバルオブジェクトのダンプを取得し、内容と復元先の既存[ロール](/glossary/ロール/)を確認してから、[データベース](/glossary/データベース/)本体より先に適用します。

```bash
pg_dumpall -h source_host -U admin_user --globals-only -f globals.sql
psql -X -v ON_ERROR_STOP=1 -h target_host -U admin_user -d postgres -f globals.sql
pg_restore -h target_host -U admin_user -d target_db --exit-on-error backup.dump
```

`--globals-only`には[ロール](/glossary/ロール/)だけでなく表領域なども含まれます。復元先に同名の[ロール](/glossary/ロール/)がすでにある場合や権限構成が異なる場合、`globals.sql`を無条件に実行せず、適用する定義を確認してください。グローバルオブジェクトの[復元](/glossary/復元/)には通常、十分な管理権限が必要です。

## 所有者を引き継がない復元方法

移行先では新しい所有者を使い、元の[ロール](/glossary/ロール/)を作らない設計もあります。カスタム形式の[アーカイブ](/glossary/アーカイブ/)であれば、`pg_restore --no-owner`を指定すると、元の所有者を[設定](/glossary/設定/)する[SQL](/glossary/sql/)を出さず、復元時の接続[ロール](/glossary/ロール/)が作成した[オブジェクト](/glossary/オブジェクト/)を所有します。

```bash
pg_restore -h target_host -U target_owner -d target_db \
  --no-owner --exit-on-error backup.dump
```

ダンプに元の[ロール](/glossary/ロール/)宛ての`GRANT`や`REVOKE`も含まれている場合、所有者指定だけを省いても[エラー](/glossary/エラー/)が残ります。元の権限付与を[復元](/glossary/復元/)しない方針なら、`--no-acl`も追加します。

```bash
pg_restore -h target_host -U target_owner -d target_db \
  --no-owner --no-acl --exit-on-error backup.dump
```

`--no-acl`は元の[アクセス権限](/glossary/アクセス権限/)を[復元](/glossary/復元/)しません。[アプリケーション](/glossary/アプリケーション/)に必要な[権限](/glossary/権限/)を復元後に改めて付与する必要があります。所有者と[権限](/glossary/権限/)の省略はそれぞれ別の操作です。[`pg_restore`の公式文書](https://www.postgresql.org/docs/current/app-pgrestore.html)に両オプションの効果が明記されています。

上の例は`pg_dump -Fc`などで作られた[アーカイブ](/glossary/アーカイブ/)向けです。平文[SQL](/glossary/sql/)のダンプを`psql`で適用する場合、`pg_restore`のオプションは使えません。ダンプを作り直せるなら、必要に応じて`pg_dump --no-owner --no-acl`などの出力設定を検討してください。単純な文字列置換でダンプ中の[ロール](/glossary/ロール/)名を変更すると、意図しない[SQL](/glossary/sql/)や文字列まで変わるおそれがあります。

## 似たエラーとの違い

`FATAL: role "app_user" does not exist`は、接続時に[ロール](/glossary/ロール/)が見つからない場合の表示です。まず接続先、`-U`で指定した利用者、[環境変数](/glossary/環境変数/)や接続文字列の利用者名を確認します。本記事の`ERROR:`は、接続後に[SQL](/glossary/sql/)が参照した[ロール](/glossary/ロール/)名を調べる場面を中心に扱っています。

`FATAL: password authentication failed for user "app_user"`は[認証](/glossary/認証/)に失敗した状態です。[パスワード](/glossary/パスワード/)[認証](/glossary/認証/)では、[ロール](/glossary/ロール/)が存在しない場合でも、利用者の存在を外部へ明かさないために同じ認証失敗の文言が返ることがあります。表示だけで[ロール](/glossary/ロール/)の有無を断定せず、管理者が接続先の`pg_roles`を確認してください。

`ERROR: role "app_user" already exists`は、逆に同名の[ロール](/glossary/ロール/)を作ろうとして重複した場合です。`DROP ROLE IF EXISTS app_user`で出る`role "app_user" does not exist, skipping`はNOTICEで、対象がなければ[削除](/glossary/削除/)を飛ばして処理を続けます。`IF EXISTS`は存在しない[ロール](/glossary/ロール/)への`GRANT`や所有者の指定を直す手段ではありません。

## 解決手順のまとめ

先頭が`ERROR`か`FATAL`かを確認し、`ERROR`なら直前の[SQL](/glossary/sql/)を特定します。接続先の`pg_roles`で名前が存在するか調べ、引用符と大文字・小文字も照合してください。

`GRANT`や`SET ROLE`なら、[ロール](/glossary/ロール/)の作成順序と[設定](/glossary/設定/)を確認します。復元時の[エラー](/glossary/エラー/)なら、元の所有者や[権限](/glossary/権限/)を引き継ぐのか、移行先の[ロール](/glossary/ロール/)へ置き換えるのかを決めます。前者は[ロール](/glossary/ロール/)を先に用意し、後者は復元形式に応じて`--no-owner`と`--no-acl`を使い分けます。

復元時に[エラー](/glossary/エラー/)が出ても、`pg_restore`は既定で処理を続けます。最後の[エラー](/glossary/エラー/)件数と[復元](/glossary/復元/)された[オブジェクト](/glossary/オブジェクト/)を確認し、不完全な状態を放置しないでください。再実行する前には、復元先を作り直すか、どこまで適用されたかを確認します。

免責事項：本記事の内容は一般的なPostgreSQL[環境](/glossary/環境/)を前提としています。[ロール](/glossary/ロール/)、所有者、[権限](/glossary/権限/)、ダンプを[本番環境](/glossary/本番環境/)で変更する前に、既存の権限構成と復元先への影響を確認してください。
