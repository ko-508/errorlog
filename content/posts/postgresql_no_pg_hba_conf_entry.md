---
title: "pg_hba.conf接続拒否の原因と対処法"
date: 2026-09-20
draft: false
description: "PostgreSQLのFATAL: no pg_hba.conf entry for hostは、接続種別、接続元、データベース、利用者に一致する許可規則がないと発生します。設定ファイルの場所、規則の確認、SSL条件、再読み込みの方法を説明します。"
tags: ["PostgreSQL"]
images: ["og/posts/postgresql_no_pg_hba_conf_entry.png"]
errorCode: "FATAL: no pg_hba.conf entry for host"
urgency: "high"
service: "PostgreSQL"
error_type: "invalid_authorization_specification"
components: ["pg_hba.conf", "client authentication", "SSL"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

PostgreSQLへの接続時に次のエラーが出る場合、`pg_hba.conf`に接続条件と一致する規則がありません。

```text
FATAL:  no pg_hba.conf entry for host "192.168.1.10", user "app", database "mydb", no encryption
```

エラーに表示された接続元IP、利用者名、データベース名、暗号化状態を確認し、この4つに合う規則を探してください。規則を追加する場合は、接続元を必要な範囲に絞り、`scram-sha-256`など適切な認証方式を指定します。

Linuxなどでは、ファイルの保存後に設定の再読み込みが必要です。Microsoft Windowsでは、変更内容がその後の新しい接続へ直ちに適用されます。

## no pg_hba.conf entry for hostの意味

`pg_hba.conf`は、PostgreSQLへ接続できる利用者、データベース、接続元、認証方式を定めるファイルです。HBAはhost-based authenticationの略で、接続元に基づく認証設定を指します。

PostgreSQLは、接続種別、接続元アドレス、要求されたデータベース、利用者名の4つを上から順に照合します。一致する規則が1つもなければ、接続を拒否して`no pg_hba.conf entry for host`を返します。

このエラーのSQLSTATEは`28000`、条件名は`invalid_authorization_specification`です。パスワードが違う場合の`28P01`とは別のエラーです。[PostgreSQL公式のエラーコード一覧](https://www.postgresql.org/docs/current/errcodes-appendix.html)で確認できます。

## エラー文の4項目を確認する

エラー文には、原因を絞るための情報が含まれています。

```text
host "192.168.1.10"
user "app"
database "mydb"
no encryption
```

`host`の値は、PostgreSQLから見た接続元IPです。利用者が想定していたIPではなく、エラーに表示された値を基準にしてください。

`user`と`database`は、接続時に指定されたPostgreSQLの利用者名とデータベース名です。似た名前の別環境へ接続していないかも確認します。

末尾の`no encryption`は暗号化されていない接続です。環境によっては`SSL encryption`または`GSS encryption`と表示されます。これは単なる補足ではなく、`hostssl`などの接続種別と照合する条件です。

## pg_hba.confの場所を確認する

編集すべきファイルの場所は、接続済みの管理用セッションから確認できます。

```sql
SHOW hba_file;
```

PostgreSQLは認証設定ファイルを別の場所へ移せるため、想像した場所のファイルを編集すると反映されないことがあります。必ず実際に使用されているパスを確認してください。

接続できる管理用セッションがない場合は、サーバーの設定管理、コンテナのマウント設定、クラウドサービスの管理画面などで使用中の認証設定を確認します。管理サービスでは`pg_hba.conf`を直接編集できない場合があります。

## 読み込める規則と書式エラーを調べる

`pg_hba_file_rules`を使うと、`pg_hba.conf`の規則と書式エラーを確認できます。既定ではスーパーユーザーだけが参照できます。

```sql
SELECT
  rule_number,
  file_name,
  line_number,
  type,
  database,
  user_name,
  address,
  auth_method,
  error
FROM pg_hba_file_rules
ORDER BY file_name, line_number;
```

`error`が`NULL`ではない行には、読み取れない理由が入ります。誤った行では、`line_number`と`error`以外が空になることがあります。

このビューは現在のファイル内容を表示するもので、サーバーが最後に読み込んだ内容を表示するものではありません。修正内容の事前確認や書式エラーの調査には使えますが、再読み込みが完了した証明にはなりません。[pg_hba_file_rulesの公式資料](https://www.postgresql.org/docs/current/view-pg-hba-file-rules.html)にもこの注意点があります。

## 接続元IPの範囲を合わせる

接続元IPが規則の範囲外なら、その接続に一致する行は見つかりません。たとえば、次の規則は`192.168.1.0`から`192.168.1.255`までのIPv4アドレスを対象にします。

```text
host    mydb    app    192.168.1.0/24    scram-sha-256
```

1台だけを許可するなら、IPv4では`/32`を使います。

```text
host    mydb    app    192.168.1.10/32    scram-sha-256
```

IPv4形式の規則はIPv4接続だけに一致し、IPv6形式の規則はIPv6接続だけに一致します。`127.0.0.1/32`と`::1/128`は別の規則です。公式文書でも、IPv4とIPv6の規則は互いの接続に一致しないと説明されています。

接続を許可する範囲は、実際に必要なIPまたはネットワークへ絞ってください。原因確認のために`0.0.0.0/0`へ広げたまま運用すると、すべてのIPv4アドレスが対象になります。

## hostとhostsslを使い分ける

`pg_hba.conf`の先頭列は接続種別です。

`host`はTCP/IP接続に一致し、SSLの有無を問いません。`hostssl`はSSLで暗号化されたTCP/IP接続だけに一致します。`hostnossl`はSSLを使わないTCP/IP接続だけが対象です。

たとえば、設定が次の行だけなら、末尾が`no encryption`の接続には一致しません。

```text
hostssl    mydb    app    192.168.1.0/24    scram-sha-256
```

通信の暗号化が必要な環境では、この行を`host`へ変えるのではなく、クライアント側でSSLを有効にします。接続方法に応じて、接続文字列の`sslmode=require`などを指定してください。

```text
postgresql://app@example.com/mydb?sslmode=require
```

暗号化なしの接続も意図的に許可する場合は、接続元を狭く限定したうえで`host`または`hostnossl`を使います。ただし、`scram-sha-256`はパスワード認証の方式であり、通信全体を暗号化する設定ではありません。

接続種別の仕様は[PostgreSQL公式のpg_hba.conf文書](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html)に記載されています。

## データベース名と利用者名を合わせる

次の規則は、`mydb`へ`app`として接続するときだけ一致します。

```text
host    mydb    app    192.168.1.0/24    scram-sha-256
```

接続先が別のデータベース名だったり、利用者名が異なったりすれば対象外です。複数の値を広く許可する前に、アプリケーションの接続文字列を確認してください。

データベース列や利用者列の`all`は、その列のすべてに一致する指定です。ただし、接続種別や接続元まで無条件に許可する意味ではありません。4つの条件すべてに一致する必要があります。

## 規則の順序を確認する

`pg_hba.conf`は上から順に評価され、最初に一致した規則だけが使われます。その規則で認証に失敗しても、下にある別の規則は試されません。

```text
host    mydb    app    192.168.1.10/32    reject
host    mydb    app    192.168.1.0/24     scram-sha-256
```

この例では、`192.168.1.10`からの接続は1行目で明示的に拒否されます。2行目の範囲にも含まれますが、後続の規則へ進みません。

明示的な`reject`に一致した場合は、次のように文言が変わります。

```text
FATAL:  pg_hba.conf rejects connection for host "192.168.1.10", user "app", database "mydb", no encryption
```

`no pg_hba.conf entry`は一致する規則がなかった状態で、`pg_hba.conf rejects connection`は`reject`規則に一致した状態です。

## 設定を再読み込みする

Linuxなどでは、`pg_hba.conf`を保存しただけでは実行中のPostgreSQLへ反映されません。接続済みの管理用セッションがあれば、次を実行します。

```sql
SELECT pg_reload_conf();
```

サーバー上のシェルから再読み込みする場合は、使用中のデータディレクトリを指定します。

```bash
pg_ctl reload -D /var/lib/postgresql/data
```

実際のデータディレクトリやサービスの管理方法は環境によって異なります。コンテナやクラウドサービスでは、提供されている再読み込み方法を使ってください。

Microsoft Windowsでは例外として、ファイル変更後の新しい接続へ直ちに適用されます。この違いは[PostgreSQL公式文書](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html)に明記されています。

## trustや全アドレス許可を避ける

次のような設定は、原因確認のためでも追加しないでください。

```text
host    all    all    0.0.0.0/0    trust
```

`0.0.0.0/0`はすべてのIPv4アドレスに一致します。さらに`trust`は、接続できる相手をパスワードなどで認証せず、指定されたPostgreSQL利用者としてログインさせます。

接続を許可する場合は、データベース、利用者、接続元を必要な範囲に限定し、`scram-sha-256`などの認証方式を使ってください。外部ネットワークを通る場合は、`hostssl`で暗号化も要求します。

## 近い接続エラーとの違い

`could not connect to server: Connection refused`は、PostgreSQLの待ち受け先まで接続できていない状態です。サーバー停止、ポート、`listen_addresses`、通信経路などを調べます。

`no pg_hba.conf entry for host`は、PostgreSQLまで到達したうえで、接続を許可する規則が見つからなかった状態です。

`password authentication failed for user`は、一致する規則が見つかり、その規則が指定した認証に失敗した状態です。利用者名、パスワード、保存されている認証情報を確認してください。

## 解決手順のまとめ

最初にエラー文のIP、利用者名、データベース名、暗号化状態を確認します。次に`SHOW hba_file;`で実際の設定ファイルを特定し、`pg_hba_file_rules`で規則と書式エラーを調べてください。

接続種別、接続元、データベース、利用者の4つに一致する規則を、必要な範囲だけ許可する形で追加または修正します。規則の順序とSSL条件も確認してください。

Linuxなどでは最後に設定を再読み込みします。広すぎる接続元や`trust`を一時的な回避策として使わず、必要な接続だけを許可することが重要です。

免責事項：本記事の内容は一般的なPostgreSQL環境を前提としています。本番環境で`pg_hba.conf`を変更する前に、現在の設定を保存し、管理用接続を維持した状態で書式、適用範囲、暗号化、認証方式を確認してください。
