---
title: "PostgreSQLの接続数超過エラーを解決！PgBouncerで高負荷時のパフォーマンスを劇的に改善する方法"
date: 2026-06-10
lastmod: 2026-06-10
draft: false
description: "PostgreSQLで「too many connections」エラーが発生する原因と、PgBouncerを使った効果的な解決策を解説します。データベースの接続管理を最適化し、高負荷時でも安定したサービス運用を実現しましょう。"
tags: ["Dev.to - AWS"]
---

## エラーの概要

PostgreSQLで「too many connections」エラーは、データベースへの同時接続数が設定された上限を超えた場合に発生します。これは、アプリケーションサーバーからの接続要求が多すぎたり、接続が適切にクローズされずに蓄積されたりすることで引き起こされます。特に、アクセスが急増するイベント時や、多数のアプリケーションインスタンスが稼働している環境で顕著になります。

## 実際のエラーメッセージ例

PostgreSQLのログには、以下のようなエラーメッセージが出力されます。

```
FATAL:  too many connections for role "<your-role-name>"
```

アプリケーション側では、データベース接続プールからの接続取得に失敗し、以下のようなエラーが発生することがあります（言語やフレームワークによって異なります）。

```json
{
  "error": "Failed to acquire connection from pool",
  "details": "database system is starting up" // または "too many connections"
}
```

## よくある原因と解決手順

### 原因1：アプリケーションからの直接接続数が多すぎる

多くのアプリケーションフレームワークは、デフォルトでデータベース接続プールを内蔵しています。しかし、アプリケーションサーバーのインスタンス数が増えると、各インスタンスが持つ接続プールの合計接続数がデータベースの上限を容易に超えてしまうことがあります。PostgreSQLは、アクティブな接続数が200を超えるとパフォーマンスが急激に低下し始め、最終的には接続を拒否するようになります。

**Before（エラーが起きるコード）：**

```javascript
// Node.jsアプリケーションの例
// 各アプリケーションインスタンスが独自の接続プールを持つ
const { Pool } = require('pg');
const pool = new Pool({
  user: 'your_user',
  host: 'your_db_host',
  database: 'your_database',
  password: 'your_password',
  port: 5432,
  max: 100 // 各アプリインスタンスが100接続を持つ
});

// 10インスタンスが稼働すると、合計1000接続がPostgreSQLに直接向かう
```

**After（修正後）：**

```javascript
// PgBouncerを介して接続するよう設定
const { Pool } = require('pg');
const pool = new Pool({
  user: 'your_user',
  host: 'your_pgbouncer_host', // PgBouncerのホストを指定
  database: 'your_database',
  password: 'your_password',
  port: 6432, // PgBouncerのポートを指定
  max: 100 // 各アプリインスタンスはPgBouncerに100接続する
});

// PgBouncerがPostgreSQLへの接続数を集約するため、PostgreSQLへの直接接続は大幅に減少する
```

### 原因2：データベース接続プールが適切に設定されていない

アプリケーションの接続プール設定が不適切である場合、例えば `max` 設定が高すぎたり、アイドル接続のタイムアウトが長すぎたりすると、不要な接続が長時間保持され、利用可能な接続数を圧迫することがあります。

**Before（エラーが起きるコード）：**

```javascript
// Node.jsアプリケーションの例 (pgモジュール)
const { Pool } = require('pg');
const pool = new Pool({
  // ...
  max: 200, // 高すぎる設定
  idleTimeoutMillis: 300000 // 5分間アイドル接続を保持
});
```

**After（修正後）：**

```javascript
// PgBouncerを使用し、アプリケーション側の接続プールはPgBouncerへの接続に集中させる
// PgBouncerがPostgreSQLへの接続数を厳密に管理するため、アプリケーション側の設定は緩和できる
const { Pool } = require('pg');
const pool = new Pool({
  // ...
  host: 'your_pgbouncer_host',
  port: 6432,
  max: 100, // PgBouncerへの接続数は適度な値に設定
  idleTimeoutMillis: 30000 // 30秒でアイドル接続を解放
});

// PgBouncer側の設定でPostgreSQLへの接続数を制限する
// pgbouncer.ini
[pgbouncer]
pool_mode = transaction
max_client_conn = 10000
default_pool_size = 150 # PostgreSQLへの実際の接続数を制限
```

### 原因3：PgBouncerが導入されていない、または設定が不適切

高負荷環境において、PgBouncerのような接続プーラーを導入しないことは、PostgreSQLの接続数超過エラーの主要な原因となります。PgBouncerは、アプリケーションからの多数の接続を少数のPostgreSQLへの接続に多重化することで、データベースの負荷を軽減し、スループットを向上させます。

**Before（エラーが起きるコード）：**

```
# PgBouncerが導入されていない、または設定ファイルが存在しない
# アプリケーションが直接PostgreSQLに接続している状態
```

**After（修正後）：**

```ini
# pgbouncer.ini の設定例
[databases]
production = host=<your-rds-endpoint> port=5432 dbname=production

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
pool_mode = transaction         # トランザクションモードが推奨
max_client_conn = 10000         # PgBouncerが受け入れるクライアント接続の最大数
default_pool_size = 150         # PgBouncerがPostgreSQLに確立する接続の最大数
reserve_pool_size = 10          # 予備の接続プールサイズ
reserve_pool_timeout = 5        # 予備プールを待つタイムアウト
server_idle_timeout = 600       # アイドル状態のサーバー接続を閉じるまでの時間
log_connections = 0
log_disconnections = 0
```

## ツール固有の注意点

### PgBouncerの`pool_mode`

PgBouncerには、`session`、`transaction`、`statement`の3つのプールモードがあります。

*   **`session`モード**: クライアントが接続している間、PostgreSQLへの接続を占有します。最もシンプルですが、接続効率は低いです。
*   **`transaction`モード**: クライアントがトランザクションを実行している間だけPostgreSQLへの接続を占有し、トランザクション完了後に解放します。これにより、同じPostgreSQL接続を複数のクライアントで共有できるようになり、接続効率が大幅に向上します。ただし、`SET`文やアドバイザリロック、`LISTEN/NOTIFY`など、セッションレベルの状態に依存する機能は、トランザクションを跨いで利用できません。
*   **`statement`モード**: 各ステートメントの実行後に接続を解放します。最も効率的ですが、トランザクションが利用できなくなるため、ほとんどのアプリケーションでは非現実的です。

ほとんどのWebアプリケーションでは、`transaction`モードがパフォーマンスと機能性のバランスが取れており推奨されます。セッションレベルの状態管理が必要な場合は、アプリケーション側で対応するか、`session`モードを検討する必要がありますが、その場合は`default_pool_size`を慎重に設定する必要があります。

### AWS RDSでのPgBouncer

AWS RDS for PostgreSQLでは、Amazon RDS ProxyがPgBouncerと同様の機能を提供します。RDS Proxyはサーバーレスで高可用性があり、PgBouncerの運用管理の手間を省くことができます。既存のRDSインスタンスに簡単に設定でき、自動的に接続を多重化してくれます。

## それでも解決しない場合

1.  **PgBouncerのログを確認する**: PgBouncerのログ（通常は`/var/log/pgbouncer/pgbouncer.log`など）を確認し、接続拒否やエラーメッセージがないか調べます。
2.  **PostgreSQLのログを確認する**: PostgreSQLのログ（RDSであればCloudWatch Logs）で、`log_connections`や`log_disconnections`が有効になっているか確認し、接続の確立と切断のパターンを分析します。
3.  **`pg_stat_activity`で接続状況を監視する**: PostgreSQLに接続し、`SELECT * FROM pg_stat_activity;`を実行して、現在アクティブな接続、アイドル状態の接続、実行中のクエリなどを確認します。
4.  **`SHOW STATS;`でPgBouncerの統計情報を確認する**: PgBouncerの管理コンソールに接続し（`psql -p 6432 -U pgbouncer pgbouncer`）、`SHOW STATS;`コマンドで現在の接続数、トラフィック量、プール利用状況などを確認します。
5.  **公式ドキュメントを参照する**:
    *   [PgBouncer 公式ドキュメント](https://www.pgbouncer.org/usage.html)
    *   [Amazon RDS Proxy ユーザーガイド](https://docs.aws.amazon.com/ja_jp/AmazonRDS/latest/UserGuide/rds-proxy.html)
    *   [PostgreSQL ドキュメント - 接続設定](https://www.postgresql.org/docs/current/runtime-config-connection.html)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*