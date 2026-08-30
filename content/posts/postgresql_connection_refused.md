---
title: "PostgreSQL の connection refused：原因と解決策"
date: 2026-08-07
description: "connection refused は PostgreSQL が出した文字列ではなく、接続先の OS が接続要求を拒んだことを libpq がそのまま転記した文字列なので、認証や権限ではなく待ち受けの有無とポートから確認します。"
tags: ["PostgreSQL"]
images: ["og/posts/postgresql_connection_refused.png"]
errorCode: "connection refused"
lastmod: 2026-08-07
service: "PostgreSQL"
error_type: "connection refused"
components: ["libpq", "postmaster"]
related_services: ["psql", "Docker"]
trend_incident: false
---

## 結論

`connection refused` は PostgreSQL が生成した文言ではありません。接続先の [OS](/glossary/os/) が接続要求を拒んだときの `ECONNREFUSED` を、libpq が `strerror()` の結果としてそのまま転記したものです。実装では、接続に失敗した箇所で `SOCK_STRERROR(errorno, ...)` の結果を先頭に置き、その後ろに助言の1行を足しています。

この由来から、確認すべき範囲がほぼ確定します。要求は指定した相手と[ポート](/glossary/ポート/)まで届いており、そこで待ち受けている相手がいなかったという意味です。したがって、[パスワード](/glossary/パスワード/)、`pg_hba.conf`、[ロール](/glossary/ロール/)、[データベース](/glossary/データベース/)名は一切関係ありません。これらの問題であれば、接続自体は成立したうえで PostgreSQL 側の `FATAL` が返ります。

見るべきは3つです。[サーバー](/glossary/サーバー/)が動いているか、待ち受けている住所に自分が届いているか、[ポート](/glossary/ポート/)番号が合っているかです。

## エラーが発生する処理段階

[クライアント](/glossary/クライアント/)が接続を確立するまでには段階があります。`connection refused` は最初の段階、つまり `connect()` の呼び出しで止まっています。

第一段階は接続先の決定です。libpq は `host` から名前を引き、`hostaddr` があればそちらを使います。第二段階が実際の接続で、ここで拒否されると `connection refused` になります。第三段階が起動時のやり取りで、[データベース](/glossary/データベース/)名と利用者名を送ります。第四段階が[認証](/glossary/認証/)で、`pg_hba.conf` の照合と[パスワード](/glossary/パスワード/)の確認が行われます。

第二段階で止まっているということは、PostgreSQL の[プロセス](/glossary/プロセス/)がこの要求を一度も見ていないということです。[サーバー](/glossary/サーバー/)の[ログ](/glossary/ログ/)にも何も残りません。[ログ](/glossary/ログ/)を探しても記録が無いのは異常ではなく、この段階で止まっている証拠です。

## 最初に確認すること

まず、どの相手のどの[ポート](/glossary/ポート/)に対して拒否されたのかを、[エラー](/glossary/エラー/)文からそのまま読み取ります。

```text
psql: error: connection to server at "localhost" (::1), port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
```

括弧の中は、名前を引いた結果の実際の住所です。ここが `::1` になっているのに待ち受けが IPv4 だけ、という食い違いはよく起きます。`localhost` は[環境](/glossary/環境/)によって IPv6 を先に返すためです。

次に、その[ポート](/glossary/ポート/)で待ち受けている相手がいるかを確認します。

```bash
ss -ltnp | grep 5432
```

行が1つも出なければ、[サーバー](/glossary/サーバー/)が動いていないか、別の[ポート](/glossary/ポート/)で待ち受けています。行が出た場合は、左側の住所欄を見てください。`127.0.0.1:5432` なら[ネットワーク](/glossary/ネットワーク/)越しの接続は拒否され、`0.0.0.0:5432` または `*:5432` なら受け付けます。

## 原因別の確認方法と解決策

### 原因1：サーバーが起動していない

最も多い形です。停止しているか、起動に失敗して落ちています。

確認方法は稼働状態の照会です。

```bash
sudo systemctl status postgresql
```

停止していれば `inactive` または `failed` と出ます。`failed` の場合は起動を試す前に、失敗の理由を先に読んでください。[設定ファイル](/glossary/設定ファイル/)の誤りで落ちている場合、起動をやり直しても同じ場所で止まります。

```bash
sudo journalctl -u postgresql --since "1 hour ago" | tail -40
```

理由が分かってから起動します。

```bash
sudo systemctl start postgresql
```

### 原因2：待ち受けの住所に自分が含まれていない

[サーバー](/glossary/サーバー/)は動いているのに、[ネットワーク](/glossary/ネットワーク/)越しからだけ拒否される場合です。`listen_addresses` の既定値は `localhost` で、公式ドキュメントには、この値では[サーバー](/glossary/サーバー/)自身からの折り返し接続だけが許されると明記されています。

確認方法は現在値の照会です。手元から接続できるなら、こちらが確実です。

```sql
SHOW listen_addresses;
```

接続できない場合は[設定ファイル](/glossary/設定ファイル/)を直接読みます。

```bash
grep -n "^listen_addresses" /etc/postgresql/*/main/postgresql.conf
```

対処は、受け付けたい範囲だけを列挙することです。`*` はすべての[ネットワーク](/glossary/ネットワーク/)接続面で待ち受けるという意味なので、外部に露出する[サーバー](/glossary/サーバー/)では慎重に扱ってください。公式ドキュメントも、この値が誰を通すかではなく、どの接続面で接続要求を受け付けるかを決めるものであり、安全でない接続面での攻撃を防ぐ役割があると説明しています。開放する場合は、`pg_hba.conf` と[ファイアウォール](/glossary/ファイアウォール/)の制限を先に用意してください。

```conf
listen_addresses = '10.0.1.5, localhost'
```

この値は起動時にしか変更できません。反映には再起動が要ります。

### 原因3：ポート番号が合っていない

既定は 5432 です。公式ドキュメントにも、待ち受ける TCP [ポート](/glossary/ポート/)は既定で 5432 だと書かれています。複数の版を同居させている[環境](/glossary/環境/)では 5433 や 5434 が割り当てられていることがあり、接続側だけが既定のままになっている、という食い違いが起きます。

確認方法は両側の突き合わせです。

```bash
sudo -u postgres psql -c "SHOW port;"
echo "$PGPORT"
```

対処は接続側を合わせることです。[環境変数](/glossary/環境変数/)か接続文字列で指定します。

```bash
psql "host=10.0.1.5 port=5433 dbname=app user=app"
```

### 原因4：ファイアウォールが拒否を返している

ここは切り分けの分かれ目になります。[ファイアウォール](/glossary/ファイアウォール/)が拒否の応答を返す設定なら `connection refused` になり、応答せずに破棄する設定なら応答が返らないため待ち続けて時間切れになります。つまり `connection refused` が出ている時点で、破棄型の遮断は候補から外れます。

確認方法は、経路上の応答を見ることです。

```bash
nc -vz 10.0.1.5 5432
```

`Connection refused` と返れば相手まで届いています。応答が無いまま止まるなら、破棄型の遮断か経路の問題です。

対処は必要な範囲だけを開けることです。全体を開放せず、接続元を限定してください。

```bash
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="10.0.1.0/24" port port="5432" protocol="tcp" accept'
sudo firewall-cmd --reload
```

### 原因5：コンテナの中から自分自身を指している

[コンテナ](/glossary/コンテナ/)で動かしている場合、`localhost` はその[コンテナ](/glossary/コンテナ/)自身を指します。[データベース](/glossary/データベース/)が別の[コンテナ](/glossary/コンテナ/)にあるなら、そこには誰も待ち受けていません。

確認方法は、接続元の中から見た到達性です。

```bash
docker compose exec app getent hosts db
```

名前が引けなければ、同じ[ネットワーク](/glossary/ネットワーク/)に属していません。引ける場合は、その名前を接続先に使います。

```bash
docker compose exec app psql "host=db port=5432 dbname=app user=app"
```

なお、公開設定で `127.0.0.1:5432:5432` としている場合、外部からは拒否されます。[コンテナ](/glossary/コンテナ/)の外に出す必要があるかどうかを先に決めてください。

## 近いエラーとの境界

`could not connect to server: No such file or directory` は、TCP ではなく Unix ドメインソケットで接続しようとして、指定した経路にソケットが無い場合です。libpq は接続先がソケットのとき、助言の文言を「そのソケットで待ち受けているか」に切り替えます。助言の1行を読めば、TCP とソケットのどちらで試したかが分かります。

応答が返らないまま時間切れになる場合は、要求が相手に届いていません。経路の遮断か、住所そのものの誤りです。`connection refused` とは逆に、相手まで届いていないことを示します。

`no pg_hba.conf entry for host` は接続が成立したあとの[認証](/glossary/認証/)段階です。要求は PostgreSQL に届いており、照合の規則に合う行が無かったという意味になります。

`password authentication failed for user` も[認証](/glossary/認証/)段階です。行の照合までは通り、[パスワード](/glossary/パスワード/)の確認で落ちています。

`FATAL:  database "app" does not exist` や `FATAL:  role "app" does not exist` は、さらに後の段階です。いずれも接続は成立しています。

判断の目安は単純です。`FATAL` で始まる文言が返っていれば PostgreSQL が応答しており、`connection refused` なら応答していません。

## 内部動作または公式仕様

libpq の[エラー](/glossary/エラー/)文は2つの部品を連結して作られます。前半は接続先を特定する部分で、TCP なら `connection to server at "%s" (%s), port %s failed: ` の書式です。名前と、引いた結果の住所が異なる場合だけ括弧の中に住所が入ります。Unix ドメインソケットの場合は `connection to server on socket "%s" failed: ` になります。

後半は失敗の理由で、`connectFailureMessage()` が [OS](/glossary/os/) の `strerror()` の結果をそのまま置きます。`Connection refused` はここに入る文字列です。実装のコメントには、この[関数](/glossary/関数/)が「向こうに[サーバー](/glossary/サーバー/)がいないことを示す場合」に使うものだと明記されています。

助言の1行も、接続先の種類で切り替わります。TCP なら `Is the server running on that host and accepting TCP/IP connections?`、ソケットなら `Is the server running locally and accepting connections on that socket?` です。

`listen_addresses` については、公式ドキュメントが役割の違いを明示しています。誰が接続してよいかを決めるのは `pg_hba.conf` の側で、`listen_addresses` はどの接続面が接続要求を受け付けるかを決めます。前者が通す設定でも、後者に含まれていなければ要求は届きません。

## バージョン差・注意点

[エラー](/glossary/エラー/)文の書式は PostgreSQL 14 で変わりました。13 以前は `could not connect to server: Connection refused` で始まり、助言の中に対象の[サーバー](/glossary/サーバー/)名と[ポート](/glossary/ポート/)が埋め込まれる形でした。14 以降は接続先が先頭に来て、理由が後ろに続きます。実装を版ごとに比べると、13 系までは旧書式、14 系から新書式になっています。検索した記事の書式が手元と違う場合は、この境目を疑ってください。

助言の文言に住所が含まれるかどうかも変わっています。旧書式は助言の中に住所と[ポート](/glossary/ポート/)を入れていましたが、新書式では先頭に移りました。古い手順書をそのまま使うと、読む場所を間違えます。

対処の面では、`listen_addresses` を `*` にする案が広く出回っていますが、これは全接続面での待ち受けを意味します。到達できる範囲が広がるため、`pg_hba.conf` の内容と[ファイアウォール](/glossary/ファイアウォール/)の設定を確認してから行ってください。設定を緩めるより先に、経路と[ポート](/glossary/ポート/)の食い違いを潰すほうが安全です。

## Editor's Note

PostgreSQL 14 における接続失敗メッセージの書式変更は、この[エラー](/glossary/エラー/)の調査手順に直接影響します。14 の[リリース](/glossary/リリース/)は2021年9月30日で、この版から `connection to server at "host" (address), port N failed:` の書式になりました。13 以前は `could not connect to server:` で始まります。

当時の状態としては、旧書式が長く使われていたため、日本語で書かれた解説の多くが旧書式を前提にしています。助言の中に住所と[ポート](/glossary/ポート/)が入る前提で「2行目を読め」と書かれた手順は、14 以降では成立しません。

現在も適用できるかという点では、書式の違いはそのまま残っています。実装を確認すると、13 系のソースには旧書式が、14 系以降には新書式が入っています。手元の版は `psql --version` で確認できます。読み替えの規則は単純で、旧書式では2行目に住所と[ポート](/glossary/ポート/)、新書式では1行目に入っている、という対応です。

## 参考資料

- [Connections and Authentication（listen_addresses、port）](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [libpq - Database Connection Control Functions](https://www.postgresql.org/docs/current/libpq-connect.html)
- [The pg_hba.conf File](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html)
- [PostgreSQL 14 Release Notes](https://www.postgresql.org/docs/current/release-14.html)
- [libpq の実装（fe-connect.c）](https://github.com/postgres/postgres/blob/master/src/interfaces/libpq/fe-connect.c)
---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
