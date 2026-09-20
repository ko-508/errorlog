---
title: "PostgreSQLの接続上限エラー対処法"
date: 2026-09-19
draft: false
description: "PostgreSQLのFATAL: sorry, too many clients alreadyは、利用できる接続枠を使い切ったときに発生します。pg_stat_activityによる調査、不要な接続の整理、接続プールとmax_connectionsの見直し方を説明します。"
tags: ["PostgreSQL"]
images: ["og/posts/postgresql_too_many_clients.png"]
errorCode: "FATAL: sorry, too many clients already"
urgency: "high"
service: "PostgreSQL"
error_type: "too_many_connections"
components: ["connection", "max_connections", "pg_stat_activity"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

PostgreSQLへの接続時に次の[エラー](/glossary/エラー/)が出る場合、利用できる接続枠がすべて使われています。

```text
FATAL:  sorry, too many clients already
```

まず、接続済みの管理用[セッション](/glossary/セッション/)があれば`pg_stat_activity`で内訳を確認します。不要な接続を安全に終了し、[アプリケーション](/glossary/アプリケーション/)が接続を閉じているか、複数の接続プールの上限が大きすぎないかを調べてください。

`max_connections`を上げるだけでは、接続の増え続ける原因は解消しません。この[設定](/glossary/設定/)の変更にはPostgreSQLの再起動が必要で、値を増やすと共有[メモリ](/glossary/メモリ/)を含む資源の割り当ても増えます。先に接続の使い方を直し、それでも必要な場合に限って上限を見直します。

## sorry, too many clients alreadyの意味

PostgreSQLは、同時に受け付ける接続数を`max_connections`で制限しています。利用可能な接続枠を使い切ると、新しい接続を受け付けられず、`sorry, too many clients already`を返します。

この[エラー](/glossary/エラー/)のSQLSTATEは`53300`、条件名は`too_many_connections`です。[アプリケーション](/glossary/アプリケーション/)で[エラー](/glossary/エラー/)を判定するときは、表示文ではなくSQLSTATEを使うと、言語設定や文言の違いに影響されにくくなります。[PostgreSQL公式のエラーコード一覧](https://www.postgresql.org/docs/current/errcodes-appendix.html)でも確認できます。

PostgreSQL本体では、接続処理に必要な領域を確保できなかったときに、この[エラー](/glossary/エラー/)を返します。処理は[PostgreSQL本体のproc.c](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/storage/lmgr/proc.c#L435-L458)で確認できます。

## 似た2つのエラーとの違い

接続枠が少なくなった段階では、別の文言が表示されることがあります。

```text
FATAL:  remaining connection slots are reserved for roles with the SUPERUSER attribute
```

この場合は接続枠が完全になくなったわけではなく、残りがスーパーユーザー用に確保されています。スーパーユーザーで管理用接続を確立し、接続状況を調査できる可能性があります。

[環境](/glossary/環境/)によっては、次の文言が表示されます。

```text
FATAL:  remaining connection slots are reserved for roles with privileges of the "pg_use_reserved_connections" role
```

これは、残りが`pg_use_reserved_connections`の[権限](/glossary/権限/)を持つ役割とスーパーユーザー向けに確保されている状態です。

一方、`sorry, too many clients already`まで進むと、接続処理に使える枠自体が残っていません。予約された[権限](/glossary/権限/)を持つ利用者でも、新しい接続に失敗する可能性があります。予約枠の判定と文言は[PostgreSQL本体のpostinit.c](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/utils/init/postinit.c#L927-L952)で確認できます。

## 接続数と設定値を確認する

まだ利用できる管理用接続や既存の管理画面がある場合は、最初に現在値を確認します。

```sql
SHOW max_connections;
SHOW superuser_reserved_connections;
```

`reserved_connections`に対応する[環境](/glossary/環境/)では、次の値も確認してください。未対応の版では設定項目が存在しないため、[エラー](/glossary/エラー/)になります。

```sql
SHOW reserved_connections;
```

現在の[クライアント](/glossary/クライアント/)接続数は、次の[SQL](/glossary/sql/)で確認できます。

```sql
SELECT count(*) AS client_connections
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

`pg_stat_activity`にはサーバープロセスごとの状態が表示されます。PostgreSQL公式文書にも、現在の状態や問い合わせを確認する統計ビューとして説明されています。[pg_stat_activityの公式資料](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)

## どの接続が枠を使っているか調べる

利用者、接続元、[アプリケーション](/glossary/アプリケーション/)名、状態ごとに集計すると、接続が偏っている場所を絞れます。

```sql
SELECT
  usename,
  application_name,
  client_addr,
  state,
  count(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY usename, application_name, client_addr, state
ORDER BY connections DESC;
```

特に確認したい状態は`idle in transaction`です。これは、[トランザクション](/glossary/トランザクション/)を開いたまま、次の問い合わせを待っている接続を示します。

```sql
SELECT
  pid,
  usename,
  application_name,
  client_addr,
  state,
  xact_start,
  state_change,
  query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
```

同じ[アプリケーション](/glossary/アプリケーション/)名や接続元から想定以上の接続が作られている場合は、[アプリケーション](/glossary/アプリケーション/)側の接続上限と切断処理を確認してください。複数の[アプリケーション](/glossary/アプリケーション/)を動かしているなら、それぞれの最大接続数の合計も確認します。

## 緊急時に不要な接続を終了する

接続枠を戻す必要がある場合は、既存の管理用接続から対象を確認します。いきなり一括終了せず、`pid`、利用者、状態、開始時刻、問い合わせを確認してください。

終了して問題ない接続を特定できた場合に限り、1件ずつ終了します。

```sql
SELECT pg_terminate_backend(12345);
```

`12345`は確認済みの`pid`へ置き換えます。処理中の接続を終了すると、その接続で進行中の[トランザクション](/glossary/トランザクション/)は取り消されます。自分自身の接続、複製、[バックアップ](/glossary/バックアップ/)、保守処理を誤って終了しないでください。

新しい管理用接続も作れない場合は、[アプリケーション](/glossary/アプリケーション/)からの新規接続をいったん止め、既存の管理経路や接続を取りまとめる仕組みから不要な接続を閉じます。それも使えない場合、再起動は最後の手段です。実行前に停止時間と処理中[トランザクション](/glossary/トランザクション/)への影響を確認してください。

## 接続を閉じない実装を修正する

接続を作るたびに新規接続を開き、処理後に返却または切断していないと、利用者が増えていなくても枠が埋まります。

[アプリケーション](/glossary/アプリケーション/)では、正常終了だけでなく例外発生時にも接続が返却される構造にします。接続プールを使う場合は、各[アプリケーション](/glossary/アプリケーション/)の最大接続数、待ち時間、接続の寿命を確認してください。

たとえば、4つの[アプリケーション](/glossary/アプリケーション/)がそれぞれ最大30接続を確保できる[設定](/glossary/設定/)なら、合計は120接続です。PostgreSQL側の一般利用者向けの枠がこれより少なければ、負荷が重なったときに接続できなくなります。各設定を個別に見るだけでなく、同じPostgreSQLへ接続するすべての上限を合計して判断します。

## idle in transactionを放置しない

[トランザクション](/glossary/トランザクション/)を開いたまま止まる接続が繰り返し発生する場合は、まず[アプリケーション](/glossary/アプリケーション/)の処理を[修正](/glossary/修正/)します。そのうえで、安全網として`idle_in_transaction_session_timeout`を[設定](/glossary/設定/)できます。

特定の[アプリケーション](/glossary/アプリケーション/)用の役割だけに[設定](/glossary/設定/)する例は次のとおりです。

```sql
ALTER ROLE app_user
SET idle_in_transaction_session_timeout = '5min';
```

この変更は、その後に作成される[セッション](/glossary/セッション/)へ適用されます。`app_user`と時間は、[アプリケーション](/glossary/アプリケーション/)の正常な処理時間に合わせて変更してください。

この[設定](/glossary/設定/)の既定値は`0`で、無効です。長時間開いた[トランザクション](/glossary/トランザクション/)はロックを保持する場合があり、不要になった行の掃除も妨げます。[PostgreSQL公式の接続既定値](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-IDLE-IN-TRANSACTION-SESSION-TIMEOUT)では、表の肥大につながる可能性も説明されています。

[トランザクション](/glossary/トランザクション/)外の待機接続を終了する`idle_session_timeout`もありますが、接続プールなどが予期しない切断へ対応できない場合があります。公式文書も、この[設定](/glossary/設定/)を中間[ソフトウェア](/glossary/ソフトウェア/)経由の接続へ適用する際は注意するよう案内しています。

## max_connectionsを上げる前に確認すること

`max_connections`は同時接続数の上限です。既定値は通常100ですが、`initdb`の判断により小さくなる場合があります。[PostgreSQL公式の接続設定](https://www.postgresql.org/docs/current/runtime-config-connection.html#GUC-MAX-CONNECTIONS)に仕様が記載されています。

値を増やせば受け付けられる接続数は増えますが、PostgreSQLはこの値に基づいて共有[メモリ](/glossary/メモリ/)を含む一部の資源を確保します。また、変更は[設定](/glossary/設定/)の再読み込みだけでは反映されず、[サーバー](/glossary/サーバー/)の再起動が必要です。

そのため、次の順序で判断します。まず不要な接続と接続漏れをなくし、各接続プールの合計上限を調整します。通常時と混雑時の接続数を測り、それでも正当な接続需要が上限を超える場合に、利用できる[メモリ](/glossary/メモリ/)と再起動手順を確認して`max_connections`を見直してください。

## 予約接続枠を理解する

`superuser_reserved_connections`は、一般の接続で枠が埋まりかけたときにも管理者が接続できるよう、スーパーユーザー向けに枠を残す[設定](/glossary/設定/)です。既定値は3です。

たとえば`max_connections`が100、`superuser_reserved_connections`が3なら、一般の役割は通常97接続まで利用でき、その後の枠はスーパーユーザー向けになります。

`reserved_connections`は、`pg_use_reserved_connections`の[権限](/glossary/権限/)を持つ役割向けに追加の予約枠を設ける[設定](/glossary/設定/)です。既定値は0です。どちらも[サーバー](/glossary/サーバー/)起動時に決まる[設定](/glossary/設定/)であり、変更には再起動が必要です。

予約枠を減らして一般接続を増やすと、障害時に管理用接続を作れなくなる可能性があります。単に利用可能数を増やす目的で使い切らず、緊急時の調査経路を残してください。

## 近い接続エラーとの違い

`could not connect to server: Connection refused`は、PostgreSQLの待ち受け先まで接続できていない状態です。[サーバー](/glossary/サーバー/)停止、[ポート](/glossary/ポート/)、待ち受けアドレス、通信経路などを確認します。

`password authentication failed for user`は、PostgreSQLへ到達した後の認証失敗です。接続数ではなく、利用者名、[パスワード](/glossary/パスワード/)、認証設定を確認してください。

`number of requested standby connections exceeds "max_wal_senders"`は、複製用の接続枠に関する[エラー](/glossary/エラー/)です。通常の[アプリケーション](/glossary/アプリケーション/)接続とは分けて調査します。

## 解決手順のまとめ

最初に`pg_stat_activity`を利用者、接続元、[アプリケーション](/glossary/アプリケーション/)名、状態ごとに集計します。不要な接続や`idle in transaction`が多ければ、対象を確認したうえで整理してください。

次に、[アプリケーション](/glossary/アプリケーション/)が例外時にも接続を返しているか、複数の接続プールの上限合計が大きすぎないかを確認します。長時間放置される[トランザクション](/glossary/トランザクション/)には、処理の[修正](/glossary/修正/)と`idle_in_transaction_session_timeout`を検討します。

`max_connections`の増加は最後に判断します。再起動と資源の増加を伴うため、接続数の原因を確認せずに変更しないでください。

免責事項：本記事の内容は一般的なPostgreSQL[環境](/glossary/環境/)を前提としています。[本番環境](/glossary/本番環境/)で接続の終了や[サーバー](/glossary/サーバー/)[設定](/glossary/設定/)の変更、再起動を行う前に、処理中の[トランザクション](/glossary/トランザクション/)、複製、[バックアップ](/glossary/バックアップ/)、停止時間への影響を確認してください。
