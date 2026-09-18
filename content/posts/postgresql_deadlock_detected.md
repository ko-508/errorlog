---
title: "PostgreSQLデッドロックの原因と対処法"
date: 2026-09-18
draft: false
description: "PostgreSQLのERROR: deadlock detectedは、複数のトランザクションが互いのロック解放を待つと発生します。サーバーログの確認方法、更新順序の統一、40P01を使った再試行、deadlock_timeoutとの違いを説明します。"
tags: ["PostgreSQL"]
images: ["og/posts/postgresql_deadlock_detected.png"]
errorCode: "ERROR: deadlock detected"
urgency: "high"
service: "PostgreSQL"
error_type: "deadlock_detected"
components: ["transaction", "row lock", "deadlock"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

PostgreSQLで次のエラーが出た場合、複数のトランザクションが互いのロック解放を待っています。

```text
ERROR:  deadlock detected
DETAIL:  Process 1234 waits for ShareLock on transaction 5678; blocked by process 4321.
Process 4321 waits for ShareLock on transaction 5679; blocked by process 1234.
HINT:  See server log for query details.
```

最も重要な対策は、複数の行や表を更新する順序をすべての処理で統一することです。そのうえで、SQLSTATE `40P01`を検出したらトランザクション全体を再試行します。

`deadlock_timeout`を長くしたり短くしたりしても、デッドロックの原因そのものはなくなりません。まずサーバーログで衝突した問い合わせを特定し、ロックを取る順序を直してください。

## deadlock detectedとは

デッドロックは、2つ以上のトランザクションが互いに必要なロックを持ち、どちらも先へ進めなくなった状態です。

たとえば、トランザクションAが行1を更新してから行2を待ち、トランザクションBが行2を更新してから行1を待つと、待ち合わせの輪ができます。PostgreSQLはこの状態を自動で検出し、関係するトランザクションの1つを中断して処理を進めます。

どのトランザクションが中断されるかは予測しにくく、アプリケーション側で決めつけてはいけません。明示的に`LOCK TABLE`を使っていなくても、通常の`UPDATE`が取得する行ロックだけで発生します。これらの動作は[PostgreSQL公式文書のDeadlocks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS)で説明されています。

このエラーのSQLSTATEは`40P01`、条件名は`deadlock_detected`です。アプリケーションでは文章ではなくSQLSTATEで判定すると、表示言語や文言の変化に影響されにくくなります。[PostgreSQLのエラーコード一覧](https://www.postgresql.org/docs/current/errcodes-appendix.html)でも`40P01`を確認できます。

## 最初にサーバーログを確認する

手元のエラーに表示される`DETAIL`には、待っているプロセス番号、ロックの種類、トランザクション番号などが並びます。ただし、衝突した問い合わせ文がクライアント側の出力に含まれない場合があります。

`HINT: See server log for query details.`と表示されたら、PostgreSQLのサーバーログを確認してください。PostgreSQL本体は、クライアント向けの詳細とログ向けの詳細を分けて組み立て、ログ側には各プロセスの問い合わせ文を追加します。この処理は[PostgreSQL本体のdeadlock.c](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/storage/lmgr/deadlock.c#L1075-L1140)で確認できます。

ログには次のような情報が記録されます。

```text
Process 1234: UPDATE accounts SET balance = balance - 100 WHERE acctnum = 22222;
Process 4321: UPDATE accounts SET balance = balance + 100 WHERE acctnum = 11111;
```

プロセス番号だけを見て原因を決めず、各問い合わせがどの順序で行や表を操作しているかを比べます。

## 実行中のロック待ちを確認する

問題が発生している最中なら、`pg_stat_activity`でロック待ちの処理を確認できます。

```sql
SELECT
  pid,
  xact_start,
  wait_event_type,
  wait_event,
  state,
  query
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY xact_start;
```

`pid`はプロセス番号、`xact_start`はトランザクションの開始時刻、`query`は実行中または直前の問い合わせです。長時間開いているトランザクションや、同じ対象を異なる順序で更新する処理を探します。

`pg_stat_activity`の列とロック待ちの確認例は[PostgreSQL公式の監視統計](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)に記載されています。閲覧権限によっては、他の利用者が実行した問い合わせ文をすべて確認できません。

`DETAIL`に`relation 16384 of database ...`のような番号が表示された場合は、対象のデータベースへ接続して次のSQLを実行すると、リレーション名へ変換できます。

```sql
SELECT 16384::regclass;
```

番号は環境ごとに異なるため、エラーに表示された値へ置き換えてください。

## 原因1：更新する順序が処理ごとに違う

よくある原因は、同じ複数行を異なる順序で更新していることです。次の2つの処理が同時に走ると、互いに相手のロック解放を待つ可能性があります。

```sql
-- トランザクションA
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE acctnum = 11111;
UPDATE accounts SET balance = balance + 100 WHERE acctnum = 22222;
COMMIT;
```

```sql
-- トランザクションB：Aとは逆順
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE acctnum = 22222;
UPDATE accounts SET balance = balance + 100 WHERE acctnum = 11111;
COMMIT;
```

両方の処理で口座番号の小さい行から更新するなど、順序を統一します。

```sql
-- どの処理でも11111、22222の順に更新する
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE acctnum = 11111;
UPDATE accounts SET balance = balance + 100 WHERE acctnum = 22222;
COMMIT;
```

対象が動的に決まる場合も、主キーなどで並べてから同じ順序で更新します。PostgreSQL公式文書も、複数の対象に対して一貫した順序でロックを取得することを基本的な防止策としています。

## 原因2：明示的なロックの順序が違う

`SELECT ... FOR UPDATE`や`LOCK TABLE`を使う処理でも、取得順序が異なれば同じ問題が起こります。

たとえば、一方が`orders`をロックしてから`payments`をロックし、もう一方が逆の順番でロックすると、表同士の待ち合わせが発生します。すべての処理で`orders`、`payments`の順にするなど、規則を1つに揃えてください。

同じ対象に複数のロック方式が必要な場合は、そのトランザクションで最終的に必要となる最も強い方式を最初に取得することも公式文書で勧められています。

## 原因3：トランザクションを長時間開いている

トランザクション中に利用者の入力や外部APIの応答を待つと、取得済みのロックも長く保持されます。待ち時間が長いだけの状態はデッドロックとは限りませんが、処理が重なる時間が増えるため問題を起こしやすくなります。

トランザクション内ではデータベース処理だけを行い、利用者入力や外部通信は可能な範囲でトランザクションの外へ移してください。公式文書も、利用者入力を待ちながらトランザクションを長時間開く設計を避けるよう説明しています。

## 40P01を検出してトランザクションを再試行する

順序を揃えても、すべての組み合わせを事前に防げない場合があります。その場合はSQLSTATE `40P01`を検出し、中断されたトランザクション全体を最初から実行し直します。

再試行は無制限に行わず、回数の上限を設けて待ち時間を少しずつ延ばしてください。エラーになったSQLだけを単独で再実行すると、トランザクションの前半で行った処理との整合が崩れるおそれがあります。

PostgreSQL公式文書も、事前に防ぐことが難しい場合は、デッドロックで中断されたトランザクションを再試行する方法を示しています。ただし、再試行は原因調査の代わりではありません。同じ処理で繰り返し発生するなら、ロック順序とトランザクション範囲を直す必要があります。

## log_lock_waitsで長いロック待ちを記録する

デッドロックになる前の長いロック待ちも調べたい場合は、`log_lock_waits`を有効にします。

```sql
ALTER SYSTEM SET log_lock_waits = on;
SELECT pg_reload_conf();
```

`log_lock_waits`は、セッションが`deadlock_timeout`を超えてロックを待ったときに記録を残す設定です。既定値は`off`で、変更にはスーパーユーザーまたは適切な`SET`権限が必要です。仕様は[PostgreSQL公式のログ設定](https://www.postgresql.org/docs/current/runtime-config-logging.html#GUC-LOG-LOCK-WAITS)で確認できます。

調査後にシステム全体の設定を元へ戻す場合は、次を実行します。

```sql
ALTER SYSTEM RESET log_lock_waits;
SELECT pg_reload_conf();
```

運用環境では、既存の設定管理方法とログ量への影響を確認してから変更してください。

## deadlock_timeoutを変えれば直るのか

`deadlock_timeout`は、ロック待ちが始まってからデッドロックの検査を行うまでの時間です。既定値は1秒です。値を上げると不要な検査は減りますが、実際のデッドロックを報告するまでの時間も長くなります。

```sql
SHOW deadlock_timeout;
```

この値はデッドロックを解消する制限時間ではありません。更新順序が逆のままなら、値を変えても待ち合わせの輪は残ります。調査目的で変更する場合も、まず現在値を確認し、恒久的な解決はSQLや処理設計の修正で行ってください。詳しい仕様は[PostgreSQL公式のロック管理設定](https://www.postgresql.org/docs/current/runtime-config-locks.html#GUC-DEADLOCK-TIMEOUT)にあります。

## 似たエラーとの違い

`could not serialize access due to concurrent update`のSQLSTATEは`40001`です。再試行が必要になる点は似ていますが、直列化できないと判断されたエラーであり、互いにロックを待つ輪を検出した`40P01`とは異なります。

`canceling statement due to lock timeout`は、設定した`lock_timeout`を超えてロックを取得できなかった場合の中断です。デッドロックが成立していなくても発生します。

`duplicate key value violates unique constraint`はSQLSTATE `23505`で、一意でなければならない値が重複したエラーです。同時実行中に起きることはありますが、ロックの待ち合わせを示すものではありません。

## 解決手順のまとめ

最初にサーバーログを開き、エラーに関係したプロセスの問い合わせ文を確認します。次に、同じ行や表を異なる順序で操作していないかを調べ、すべての処理で順序を統一してください。

トランザクション内の利用者入力や外部通信を減らし、保持時間も短くします。それでも避けられない`40P01`には、回数制限付きでトランザクション全体を再試行します。

`deadlock_timeout`の変更は原因の修正ではありません。設定値を調整する前に、問い合わせとロック取得順序を直すことが基本です。

免責事項：本記事の内容は一般的なPostgreSQL環境を前提としています。本番環境でSQLやサーバー設定を変更する前に、バックアップ、権限、監視方法、利用中のPostgreSQL版を確認してください。
