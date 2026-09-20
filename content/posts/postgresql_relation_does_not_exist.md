---
title: "PostgreSQL の relation does not exist：原因と解決策"
date: 2026-09-15
description: "relation does not exist は対象が無いという意味ではなく、今の接続から名前を解決できなかったという意味なので、文言にスキーマ名が入っているかどうかを起点に切り分けます。"
tags: ["PostgreSQL"]
images: ["og/posts/postgresql_relation_does_not_exist.png"]
errorCode: "relation does not exist"
error_name: "relation \"<name>\" does not exist"
error_aliases:
  - "relation does not exist"
  - "relation \"<schema>.<name>\" does not exist"
  - "42P01"
  - "undefined_table"
lastmod: 2026-09-15
service: "PostgreSQL"
error_type: "relation does not exist"
components: ["Parser", "Namespace"]
related_services: ["psql"]
error_cases:
  - id: "search-path-not-including-schema"
    situation: "スキーマ名を付けて実行すると成功し、付けないと失敗する"
    messages:
      - "relation \"<name>\" does not exist"
    cause: "対象が別のスキーマにあり、今の検索経路に含まれていない"
    check: "SHOW search_path; を実行し、pg_class と pg_namespace の照会で対象が実際にどのスキーマにあるかを確認する"
    fix: "スキーマ名を付けて指定するか、そのスキーマを検索経路へ加える"
  - id: "schema-usage-not-granted"
    situation: "別の利用者では成功し、今の利用者だけが失敗する"
    messages:
      - "relation \"<name>\" does not exist"
    cause: "そのスキーマへの USAGE 権限が無く、検索経路から黙って外れている"
    check: "has_schema_privilege で USAGE の有無を確認し、スキーマ名を付けて実行したときに文言が permission denied for schema へ変わるかを見る"
    fix: "そのスキーマへ USAGE 権限を与える"
  - id: "quoted-identifier-case"
    situation: "作成時に二重引用符で囲んだ名前を、囲まずに参照している"
    messages:
      - "relation \"<name>\" does not exist"
    cause: "囲まない名前は小文字に畳まれるため、大文字を含む名前と一致しない"
    check: "pg_class を ILIKE で照会し、実際に登録されている綴りを確認する"
    fix: "参照する側も二重引用符で囲むか、小文字だけの名前へ変更する"
  - id: "different-database-or-not-created"
    situation: "接続先を変えると成功する、または一覧そのものに出てこない"
    messages:
      - "relation \"<name>\" does not exist"
    cause: "別のデータベースに接続している、または対象がまだ作られていない"
    check: "current_database() で接続先を確認し、pg_class の照会で行が返るかを見る"
    fix: "接続先を合わせるか、作成する手順を実行する"
trend_incident: false
---

## 結論

`relation "users" does not exist` は、対象がこの世に無いという意味ではありません。指定した名前を、今の接続から解決できなかったという意味です。[SQL](/glossary/sql/) の状態[コード](/glossary/コード/)は 42P01、名称は undefined_table です。

relation は[テーブル](/glossary/テーブル/)だけを指しません。公式ドキュメントは、pg_class が[インデックス](/glossary/インデックス/)、シーケンス、ビュー、実体化ビューなども扱い、これらをまとめて relation と呼ぶと説明しています。

読み分けの起点は、文言の中に点があるかどうかです。[スキーマ](/glossary/スキーマ/)名を自分で書いた場合は `relation "public.users" does not exist` と点付きになり、書かなかった場合は `relation "users" does not exist` と名前だけになります。前者は指定した[スキーマ](/glossary/スキーマ/)の中で見つからず、後者は検索経路をたどって見つからなかったという意味です。

そして、この文言は「無い」と「見えない」を区別しません。[権限](/glossary/権限/)が足りずに検索経路から外れた[スキーマ](/glossary/スキーマ/)も、存在しない[スキーマ](/glossary/スキーマ/)も同じ結果です。

## 最初に確認すること

今の接続がどこを見ているかを確認します。

```sql
SELECT current_database(), current_user;
SHOW search_path;
```

初期状態の検索経路は `"$user", public` です。先頭は利用者名と同じ[スキーマ](/glossary/スキーマ/)を指します。

次に、対象の所在を調べます。

```sql
SELECT n.nspname, c.relname, c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relname = 'users';
```

[行](/glossary/行/)が返らなければ、この[データベース](/glossary/データベース/)には登録されていません。返るのに参照できないなら、[スキーマ](/glossary/スキーマ/)か綴りの問題です。

## 原因別の確認方法と解決策

### 原因1：対象が検索経路に入っていないスキーマにある {#search-path-not-including-schema}

上の照会で `nspname` が `public` 以外になっている場合です。修飾しない参照は検索経路を順にたどり、最初に一致したものを使います。経路に入っていない[スキーマ](/glossary/スキーマ/)の中身は参照できません。

対処は、呼び出し側で修飾するか経路へ加えるかです。

```sql
SELECT * FROM app.users;
SET search_path TO app, public;
```

`SET` はその[セッション](/glossary/セッション/)の間だけ有効です。毎回同じ状態にしたい場合は、[ロール](/glossary/ロール/)や[データベース](/glossary/データベース/)へ既定値を[設定](/glossary/設定/)します。

### 原因2：スキーマへの USAGE 権限が無い {#schema-usage-not-granted}

同じ[クエリ](/glossary/クエリ/)が、利用者を変えると成功する場合です。公式ドキュメントは、自分が所有していない[スキーマ](/glossary/スキーマ/)の中身へ既定では触れられず、所有者が USAGE [権限](/glossary/権限/)を与える必要があると説明しています。

問題は見え方です。実装は検索経路を組み立てる段階で、名前を認識できない[スキーマ](/glossary/スキーマ/)と読み取り[権限](/glossary/権限/)が無い[スキーマ](/glossary/スキーマ/)を一覧から外します。注記によれば、検索経路の設定自体はすでに受理されているため、ここでは[エラー](/glossary/エラー/)にできないからです。

確認方法は2つあります。

```sql
SELECT has_schema_privilege(current_user, 'app', 'USAGE');
SELECT * FROM app.users;
```

下のように[スキーマ](/glossary/スキーマ/)名を付けて実行すると、[権限](/glossary/権限/)が原因なら文言が `permission denied for schema app` へ変わります。修飾したときだけ理由が表に出ます。

対処は[権限](/glossary/権限/)の付与です。

```sql
GRANT USAGE ON SCHEMA app TO app_user;
```

### 原因3：作成した綴りと参照した綴りが違う {#quoted-identifier-case}

二重引用符で囲んで作成した名前を、囲まずに参照している場合です。公式ドキュメントは、囲まない名前は常に小文字に畳まれると説明しています。`FOO`、`foo`、`"foo"` は同じものですが、`"Foo"` と `"FOO"` はそれらとも互いとも別です。

確認方法は、登録されている綴りを見ることです。

```sql
SELECT relname FROM pg_class WHERE relname ILIKE 'users';
```

`Users` のように大文字が含まれていれば確定です。

対処は、参照する側も囲むか、名前を小文字へ変えるかです。

```sql
SELECT * FROM "Users";
ALTER TABLE "Users" RENAME TO users;
```

後者を選ぶ場合は、その名前を使う[クライアント](/glossary/クライアント/)側もあわせて直します。

### 原因4：接続先が違う、または作られていない {#different-database-or-not-created}

`current_database()` の値が想定と違う場合です。接続文字列や[環境変数](/glossary/環境変数/)が別の[データベース](/glossary/データベース/)を指していると、[サーバー](/glossary/サーバー/)と[ポート](/glossary/ポート/)は合っているため接続だけ成功し、作成の手順はもう一方へ適用されています。

```sql
SELECT current_database();
```

接続先が合っているのに[行](/glossary/行/)が返らない場合は、まだ作られていません。作成の手順が失敗していないか[ログ](/glossary/ログ/)を確認してください。

## 近いエラーとの違い

`column "..." does not exist`（42703）は、対象そのものは見つかったうえで、その中の[カラム](/glossary/カラム/)名で失敗しています。

`permission denied for table ...`（42501）は、名前の解決が済んだあとの[権限](/glossary/権限/)検査で止まっています。[テーブル](/glossary/テーブル/)自体への[権限](/glossary/権限/)が足りないだけなら、この記事の文言にはなりません。[スキーマ](/glossary/スキーマ/)側の USAGE が足りない場合だけ、修飾の有無で文言が入れ替わります。

`database "..." does not exist`（3D000）は、接続の段階で失敗しています。

`relation "..." does not exist, skipping` は[エラー](/glossary/エラー/)ではなく[通知](/glossary/通知/)です。`IF EXISTS` を付けた[削除](/glossary/削除/)や変更で対象が無かったときに出ます。

同じ文言に `There is a WITH item named ...` という詳細が付く場合は別の状況です。`WITH` で定義した名前を、まだ参照できない位置から呼んでいます。`WITH RECURSIVE` を使うか並び順を変えるようにという助言が一緒に出ます。

## 参考資料

- [スキーマと検索パス（PostgreSQL 公式）](https://www.postgresql.org/docs/current/ddl-schemas.html)
- [識別子と大文字小文字の扱い（PostgreSQL 公式）](https://www.postgresql.org/docs/current/sql-syntax-lexical.html)
- [pg_class（PostgreSQL 公式）](https://www.postgresql.org/docs/current/catalog-pg-class.html)
- [エラーコード一覧（PostgreSQL 公式）](https://www.postgresql.org/docs/current/errcodes-appendix.html)
- [名前解決の実装（namespace.c）](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/catalog/namespace.c)
- [文言の生成箇所（parse_relation.c）](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/parser/parse_relation.c)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
