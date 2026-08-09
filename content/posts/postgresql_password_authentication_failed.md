---
title: "PostgreSQL のパスワード認証失敗：原因と解決策"
date: 2026-08-07
description: "この文言は原因を意図的に伏せた総称で、利用者が存在しない場合も同じ文が返るため、本当の理由はサーバーログの DETAIL 行にしか出力されず、そこを読むかどうかで切り分けの速さが決まります。"
tags: ["PostgreSQL"]
images: ["og/posts/postgresql_password_authentication_failed.png"]
errorCode: "password authentication failed for user"
lastmod: 2026-08-07
service: "PostgreSQL"
error_type: "password authentication failed"
components: ["postmaster", "pg_hba.conf"]
related_services: ["psql", "libpq"]
trend_incident: false
---

## 結論

`password authentication failed for user "app"` は、原因を意図的に伏せた文言です。実装では、`pg_hba.conf` の照合方式が `password`・`md5`・`scram-sha-256` のいずれかであれば、失敗の中身にかかわらずこの1文が返ります。

伏せる理由は実装のコメントに書かれています。[パスワード](/glossary/パスワード/)の取得に失敗しても、利用者が存在しないことを[クライアント](/glossary/クライアント/)に悟らせないために、[認証](/glossary/認証/)の手順を最後まで進めるという作りです。したがって、存在しない[ロール](/glossary/ロール/)名で接続しても、[パスワード](/glossary/パスワード/)を間違えた場合とまったく同じ文言が返ります。

本当の理由は `errdetail_log()` で出力されており、これは[サーバー](/glossary/サーバー/)の[ログ](/glossary/ログ/)にだけ書かれます。[クライアント](/glossary/クライアント/)には届きません。しかも、この詳細には照合に使われた `pg_hba.conf` の経路と[行番号](/glossary/行番号/)、その行の原文まで含まれています。

つまり最初にすべきことは[パスワード](/glossary/パスワード/)の再入力ではなく、[サーバー](/glossary/サーバー/)の[ログ](/glossary/ログ/)を開くことです。

## エラーが発生する処理段階

この[エラー](/glossary/エラー/)は接続が成立したあとに出ます。手前の段階はすべて通っています。

まず TCP または Unix ドメインソケットの接続が確立します。ここで拒まれれば `connection refused` になり、この文言は出ません。次に起動時のやり取りで、[データベース](/glossary/データベース/)名と利用者名が[サーバー](/glossary/サーバー/)へ送られます。

続いて `pg_hba.conf` の照合です。上から順に、接続の種類・[データベース](/glossary/データベース/)・利用者・接続元を見て、最初に一致した行が採用されます。一致する行が1つも無ければ `no pg_hba.conf entry for host` になります。

一致した行の方式が[パスワード](/glossary/パスワード/)系であれば、ここで確認が行われます。失敗するとこの文言が返ります。[データベース](/glossary/データベース/)の存在確認や接続[権限](/glossary/権限/)の確認は、さらに後の段階です。

## 最初に確認すること

[クライアント](/glossary/クライアント/)側の表示には、状態[コード](/glossary/コード/)以上の情報はありません。

```text
psql: error: connection to server at "db.internal" (10.0.1.5), port 5432 failed:
FATAL:  password authentication failed for user "app"
```

[サーバー](/glossary/サーバー/)の[ログ](/glossary/ログ/)を開くと、同じ時刻に `DETAIL` が並んで出ています。

```bash
sudo tail -n 50 /var/log/postgresql/postgresql-16-main.log
```

出力はこの形になります。

```text
FATAL:  password authentication failed for user "app"
DETAIL:  Password does not match for user "app".
	Connection matched file "/etc/postgresql/16/main/pg_hba.conf" line 96: "host all all 10.0.1.0/24 scram-sha-256"
```

1行目の `DETAIL` が本当の理由です。実装で定義されている文言は6種類で、`Role "app" does not exist.`、`User "app" has no password assigned.`、`User "app" has an expired password.`、`User "app" has a password that cannot be used with MD5 authentication.`、`Password does not match for user "app".`、`Password of user "app" is in unrecognized format.` です。どれが出ているかで、次に見る場所が確定します。

2行目は照合に使われた行そのものです。`pg_hba.conf` を探して読む必要はありません。経路と[行番号](/glossary/行番号/)と原文が、そのまま書かれています。

## 原因別の確認方法と解決策

### 原因1：パスワードが一致していない

`DETAIL` が `Password does not match for user "app".` の場合です。値そのものが違います。

確認方法は、疑いのある値を対話入力で試すことです。[環境変数](/glossary/環境変数/)や接続文字列に埋め込んだ値には、末尾の改行や引用符が紛れ込むことがあります。

```bash
psql "host=db.internal port=5432 dbname=app user=app"
```

対話で通るなら、渡し方の側に問題があります。[設定ファイル](/glossary/設定ファイル/)や[環境変数](/glossary/環境変数/)の値を、見えない文字ごと確認してください。

```bash
printenv PGPASSWORD | od -c | head -3
```

値そのものを変える場合は、平文が[ログ](/glossary/ログ/)や履歴に残らない方法を選びます。`psql` の対話[コマンド](/glossary/コマンド/)は入力を伏せます。

```sql
\password app
```

### 原因2：ロールが存在しない

`DETAIL` が `Role "app" does not exist.` の場合です。[クライアント](/glossary/クライアント/)側の文言は[パスワード](/glossary/パスワード/)の失敗と同じなので、[ログ](/glossary/ログ/)を見ない限り区別できません。

確認方法は一覧の照会です。名前の大文字小文字にも注意してください。引用符なしで作成した名前はすべて小文字になります。

```sql
SELECT rolname, rolcanlogin, rolvaliduntil FROM pg_roles ORDER BY rolname;
```

対処は作成か、接続側の名前の修正です。作成する場合、[権限](/glossary/権限/)は必要な範囲にとどめてください。

```sql
CREATE ROLE app LOGIN PASSWORD 'input-here';
```

### 原因3：パスワードが設定されていない、または期限が切れている

`DETAIL` が `User "app" has no password assigned.` または `User "app" has an expired password.` の場合です。前者は[ロール](/glossary/ロール/)は存在するが値が未設定、後者は `VALID UNTIL` を過ぎています。

確認方法は[属性](/glossary/属性/)の照会です。

```sql
SELECT rolname, rolpassword IS NOT NULL AS has_password, rolvaliduntil
FROM pg_authid WHERE rolname = 'app';
```

`rolvaliduntil` が過去の日時であれば期限切れです。対処は期限の更新です。無期限にする場合は `infinity` を指定できますが、期限を設けている運用であればその意図を確認してから変更してください。

```sql
ALTER ROLE app VALID UNTIL '2027-01-01';
```

### 原因4：保存されている形式と照合方式が合っていない

`DETAIL` が `User "app" has a password that cannot be used with MD5 authentication.` または `Password of user "app" is in unrecognized format.` の場合です。`pg_hba.conf` が要求する方式と、保存されている値の種類が噛み合っていません。

実装では、方式が `md5` の行に一致したとき、保存されている値が MD5 形式であれば MD5 で、そうでなければ SCRAM で確認します。方式が `scram-sha-256` の行であれば常に SCRAM で確認するため、MD5 形式で保存された値は必ず失敗します。

確認方法は、保存形式の先頭を見ることです。

```sql
SELECT rolname, left(rolpassword, 14) AS stored_format FROM pg_authid WHERE rolname = 'app';
```

`SCRAM-SHA-256$` で始まっていれば SCRAM 形式、`md5` で始まっていれば MD5 形式です。

対処は保存し直しです。`password_encryption` を目的の値にしてから、[パスワード](/glossary/パスワード/)を設定し直します。既存の値は再設定するまで古い形式のまま残るため、設定を変えるだけでは切り替わりません。

```sql
SET password_encryption = 'scram-sha-256';
\password app
```

古い[クライアント](/glossary/クライアント/)は SCRAM に対応していないことがあります。公式ドキュメントもこの点に触れているため、切り替え前に接続元の対応状況を確認してください。

### 原因5：想定と違う行に一致している

`DETAIL` の2行目が、自分が編集した行と違う場合です。`pg_hba.conf` は上から順に評価され、最初に一致した行だけが使われます。下のほうに正しい行を足しても、上に広い範囲の行があればそちらが採用されます。

確認方法は、`DETAIL` の2行目に出ている[行番号](/glossary/行番号/)と原文の突き合わせです。稼働中の内容は照会でも読めます。

```sql
SELECT line_number, type, database, user_name, address, auth_method
FROM pg_hba_file_rules ORDER BY line_number;
```

`error` 列に値が入っている行があれば、その行は読み込みに失敗しています。対処は順序の修正です。狭い条件の行を上に置いてください。編集後は再読み込みが要ります。

```sql
SELECT pg_reload_conf();
```

再読み込みは接続中の[セッション](/glossary/セッション/)を切りません。内容に誤りがあると読み込みが拒否されるため、実行後に `pg_hba_file_rules` を再度確認してください。

## 近いエラーとの境界

`no pg_hba.conf entry for host "10.0.1.9", user "app", database "app", no encryption` は、一致する行が1つも無い場合です。方式の選択にすら至っていません。状態[コード](/glossary/コード/)は 28000 で、[パスワード](/glossary/パスワード/)失敗の 28P01 とは別です。

`Peer authentication failed for user "app"` は、方式が `peer` の行に一致した場合です。Unix ドメインソケット経由でのみ使われ、[OS](/glossary/os/) の利用者名と接続先の[ロール](/glossary/ロール/)名が一致しているかを見ます。[パスワード](/glossary/パスワード/)は関係ありません。同じ理由で `Ident authentication failed for user` も別の方式です。

`connection refused` は接続そのものが成立していません。`FATAL` で始まる応答が返っている時点で、この候補は外れます。

`FATAL:  database "app" does not exist` は[認証](/glossary/認証/)を通過したあとです。`FATAL:  permission denied for database "app"` も同様で、こちらは `CONNECT` [権限](/glossary/権限/)の不足を示します。

## 内部動作または公式仕様

`auth_failed()` は、一致した行の方式ごとに返す文言を選びます。`password`・`md5`・`scram-sha-256` の3つは同じ分岐に入り、いずれも `password authentication failed for user "%s"` になります。状態[コード](/glossary/コード/)だけは他と分けられており、この3つのときは 28P01、それ以外は 28000 です。

詳細は `errdetail_log()` で付けられます。この[関数](/glossary/関数/)はサーバーログにだけ出力し、[クライアント](/glossary/クライアント/)には送りません。実装のコメントは、失敗の理由を「利用者の情報を渡してしまわないよう」[クライアント](/glossary/クライアント/)へ送るべきでないと明記しています。

詳細の内容は、[パスワード](/glossary/パスワード/)の取得を行う `get_role_password()` と、照合を行う関数群が組み立てます。取得の段階で不在・未設定・期限切れが判明した場合でも、実装はそこで打ち切らず[認証](/glossary/認証/)の手順を続けます。コメントには、利用者が存在しないことを[クライアント](/glossary/クライアント/)に明かさないためだと書かれています。このとき、どの方式で問い合わせるかは `password_encryption` の現在値から決められます。多くの利用者がその形式の値を持っているはずなので、そう振る舞えば紛れ込みやすい、という理由です。

さらに `auth_failed()` は、方式にかかわらず `Connection matched file "%s" line %d: "%s"` を詳細へ連結します。照合に使われた[ファイル](/glossary/ファイル/)の経路、[行番号](/glossary/行番号/)、その行の原文が入ります。

## バージョン差・注意点

`password_encryption` の既定値は、現在の版では `scram-sha-256` です。この既定は PostgreSQL 14 で `md5` から切り替わりました。14 より前に作られた[ロール](/glossary/ロール/)の値は MD5 形式のまま残るため、版を上げただけでは切り替わりません。`pg_hba.conf` を `scram-sha-256` に変えると、再設定していない[ロール](/glossary/ロール/)だけが失敗します。原因4の形です。

MD5 形式は非推奨になりました。公式ドキュメントには、MD5 で[暗号化](/glossary/暗号化/)された[パスワード](/glossary/パスワード/)の対応は非推奨であり、将来の版で削除されると明記されています。新しく作る[ロール](/glossary/ロール/)は SCRAM 形式にしてください。

[ログ](/glossary/ログ/)の設定にも版による差があります。`log_connections` は 18 で真偽値から選択肢の一覧へ拡張されました。リリースノートには、従来の真偽値も引き続き使えると書かれています。既定値は空文字で、接続に関する記録は無効です。ただし `FATAL` の行と `DETAIL` は `log_connections` とは無関係に出力されるため、この[エラー](/glossary/エラー/)の調査には有効化は要りません。

なお `DETAIL` を読むには `log_min_messages` が既定のままである必要があります。既定より厳しい値に変更している[環境](/glossary/環境/)では出力されないことがあります。

## Editor's Note

`password_encryption` の既定値変更は、この[エラー](/glossary/エラー/)の典型的な発生源になりました。PostgreSQL 14 の[リリース](/glossary/リリース/)は2021年9月30日で、この版から既定が `scram-sha-256` になっています。

当時の状態としては、13 以前で作られた[ロール](/glossary/ロール/)の値が MD5 形式で保存されており、`pg_hba.conf` も `md5` のまま運用されている[環境](/glossary/環境/)が多くありました。この組み合わせでは、実装が保存形式を見て MD5 を選ぶため、そのまま動きます。問題は、版を上げたあとに `pg_hba.conf` だけを `scram-sha-256` へ変更した場合です。方式が `scram-sha-256` の行に一致すると常に SCRAM で確認されるため、MD5 形式のまま残った[ロール](/glossary/ロール/)だけが失敗します。しかも[クライアント](/glossary/クライアント/)側の文言は[パスワード](/glossary/パスワード/)の誤りと同一です。

現在も適用できるかという点では、そのまま当てはまります。実装の分岐は今も同じで、MD5 形式は非推奨として残っています。移行の手順も変わりません。`password_encryption` を切り替えたうえで、対象の[ロール](/glossary/ロール/)ごとに[パスワード](/glossary/パスワード/)を設定し直します。設定を変えるだけでは既存の値は書き換わらない、という点が要点です。

## 参考資料

- [Password Authentication](https://www.postgresql.org/docs/current/auth-password.html)
- [The pg_hba.conf File](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html)
- [Connections and Authentication（password_encryption）](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [PostgreSQL Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html)
- [pg_hba_file_rules](https://www.postgresql.org/docs/current/view-pg-hba-file-rules.html)
- [認証処理の実装（auth.c）](https://github.com/postgres/postgres/blob/master/src/backend/libpq/auth.c)
- [パスワード照合の実装（crypt.c）](https://github.com/postgres/postgres/blob/master/src/backend/libpq/crypt.c)
---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
