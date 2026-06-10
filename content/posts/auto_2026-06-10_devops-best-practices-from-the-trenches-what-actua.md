---
title: "DevOpsのベストプラクティス：CI/CDの遅延、IaCの欠如、監視不足が引き起こす問題と解決策"
date: 2026-06-10
lastmod: 2026-06-10
draft: false
description: "DevOpsのベストプラクティスは、単なるツールのチェックリストではありません。CI/CDの遅延、IaCの欠如、監視不足、データベース接続の管理不足、クラウドコストの軽視、環境の不整合、セキュリティの後回し、バックアップの未検証といった具体的な問題が、どのようにシステム全体のパフォーマンスと信頼性を低下させるかを解説し、それぞれの解決策を具体的なコード例とともに紹介します。"
tags: ["Dev.to - AWS"]
---

## エラーの概要

DevOpsのプラクティスにおける「エラー」とは、特定のHTTPステータスコードに直結するものではなく、開発・運用プロセス全体の非効率性や信頼性の欠如を指します。具体的には、CI/CDパイプラインの遅延、Infrastructure as Code（IaC）の欠如、監視体制の不備、データベース接続の管理不足、クラウドコストの肥大化、環境間の不整合、セキュリティの軽視、バックアップの未検証などが挙げられます。これらは最終的に、アプリケーションのパフォーマンス低下、デプロイ失敗、予期せぬダウンタイム、セキュリティ侵害、コスト超過といった形で顕在化します。

## 実際のエラーメッセージ例

DevOpsのプラクティス不足に起因する問題は、直接的なエラーメッセージとして現れることもあれば、間接的なログとして現れることもあります。

**CI/CDパイプラインのタイムアウト例:**

```
##[error]The job was canceled because it exceeded the maximum allowed time of 40 minutes.
```

**デプロイ後のヘルスチェック失敗例:**

```
Deploy failed health check, rolling back...
Error: Service 'api' in cluster 'production' did not reach a stable state.
```

**データベース接続過多によるエラー例:**

```
FATAL: remaining connection slots are reserved for non-replication superuser connections
```

## よくある原因と解決手順

### 原因1：CI/CDパイプラインのフィードバックループが遅すぎる

パイプラインの実行時間が長すぎると、開発者は結果を待たずにマージするようになり、CI/CDの信頼性が失われます。40分かかるパイプラインは、もはや誰も信用しません。

**Before（エラーが起きるコード）：**

```yaml
# .github/workflows/ci.yml
jobs:
  build-and-test:
    runs-on: ubuntu-latest
    timeout-minutes: 40 # 長すぎるタイムアウト
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm run lint && npm run typecheck && npm test && npm run test:integration
```

**After（修正後）：**

```yaml
# .github/workflows/ci.yml
jobs:
  lint-typecheck:
    runs-on: ubuntu-latest
    timeout-minutes: 2 # 短いタイムアウトで高速フィードバック
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm run lint && npm run typecheck
  unit-tests:
    runs-on: ubuntu-latest
    needs: lint-typecheck
    timeout-minutes: 5 # 並列実行で高速化
    strategy:
      matrix:
        shard: [1, 2, 3, 4] # テストをシャード化して並列実行
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm test -- --shard=${{ matrix.shard }}/4
  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    timeout-minutes: 10 # サービスを立ち上げて統合テスト
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_PASSWORD: test }
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm run test:integration
```
**解決手順:**
1. **パイプラインのステージング:** リント、型チェック、ユニットテスト、統合テストなど、フェーズを分割します。
2. **並列実行:** ユニットテストなどをシャード化し、複数のジョブで並列実行することで時間を短縮します。
3. **タイムアウト設定:** 各ジョブに適切なタイムアウトを設定し、無駄な待機時間を削減します。
4. **自動ロールバック:** デプロイ後にヘルスチェックが失敗した場合、自動的に以前のバージョンにロールバックする仕組みを導入します。これにより、問題のあるリリースが本番環境に長時間影響を与えることを防ぎます。

### 原因2：Infrastructure as Code（IaC）が導入されていない、または不完全

インフラストラクチャがコードとして管理されていない場合、何がデプロイされているか不明瞭になり、不要なリソースが残り続けたり、環境の再現性が失われたりします。これはコスト超過や障害発生時の復旧遅延につながります。

**Before（エラーが起きるコード）：**

```
# 手動でAWSコンソールからEC2インスタンス、RDS、ロードバランサーなどをプロビジョニング
# ドキュメントはWikiやスプレッドシートに散在
```

**After（修正後）：**

```terraform
# infra/modules/ecs-service/main.tf
resource "aws_ecs_service" "main" {
  name            = var.service_name
  cluster         = var.ecs_cluster_id
  task_definition = var.task_definition_arn
  desired_count   = var.desired_count
  # ... その他ECSサービス設定
}

# infra/envs/production/main.tf
module "api_service" {
  source          = "../../modules/ecs-service"
  service_name    = "api"
  ecs_cluster_id  = aws_ecs_cluster.main.id
  task_definition_arn = aws_ecs_ecs_task_definition.api.arn
  desired_count   = 3
  # ...
}
```
**解決手順:**
1. **IaCツールの導入:** Terraform、AWS CDK、CloudFormationなどのIaCツールを導入し、すべてのインフラリソースをコードで定義します。
2. **モジュール化:** 再利用可能なインフラコンポーネント（例：ECSサービス、RDSインスタンス、Lambda関数）をモジュールとして定義します。
3. **環境ごとの分離:** 開発、ステージング、本番など、環境ごとにIaCの設定ファイル（例：`tfvars`）を分離し、環境固有の値を管理します。
4. **リソースの棚卸しと最適化:** 既存のインフラリソースをIaCで定義し直し、不要なリソースを削除したり、CloudWatchメトリクスに基づいて適切なサイズに調整したりします。

### 原因3：監視（Observability）が不十分で、問題が顕在化するまで気づけない

アプリケーションが本番稼働してから監視を導入するのでは遅すぎます。問題が発生した後に原因を特定するのに時間がかかり、ダウンタイムが長引きます。

**Before（エラーが起きるコード）：**

```
# アプリケーションのログは標準出力のみ
# メトリクス収集は行われていない
# エラー発生時に手動でログを調査
```

**After（修正後）：**

```javascript
// Node.jsアプリケーションの例（OpenTelemetryなどを使用）
const { diag, DiagConsoleLogger, DiagLogLevel } = require('@opentelemetry/api');
diag.setLogger(new DiagConsoleLogger(), DiagLogLevel.INFO);

const { NodeTracerProvider } = require('@opentelemetry/sdk-trace-node');
const { ConsoleSpanExporter, SimpleSpanProcessor } = require('@opentelemetry/sdk-trace-base');
const { Resource } = require('@opentelemetry/resources');
const { SemanticResourceAttributes } = require('@opentelemetry/semantic-conventions');

const provider = new NodeTracerProvider({
  resource: new Resource({
    [SemanticResourceAttributes.SERVICE_NAME]: 'my-api-service',
  }),
});

provider.addSpanProcessor(new SimpleSpanProcessor(new ConsoleSpanExporter()));
provider.register();

// Express.jsのミドルウェアでリクエストのレイテンシとエラーを計測
app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    console.log(`[${req.method}] ${req.originalUrl} - ${res.statusCode} - ${duration}ms`);
    // Prometheusなどのメトリクスに送信
    // traceId, spanIdをログに含める
  });
  next();
});
```
**解決手順:**
1. **アプリケーション計装:** 開発の初期段階から、アプリケーションの主要なメトリクス（P50/P95/P99レスポンスタイム、エラーレート、Apdexスコア）を収集するよう計装します。
2. **インフラメトリクス:** データベース接続数、キャッシュヒット率、Lambdaエラーレートなど、インフラ層の重要なメトリクスを監視します。
3. **ビジネスメトリクス:** コンバージョンファネルのドロップオフ率など、ビジネスに直結するメトリクスも追跡し、アプリケーションの変更がビジネスに与える影響を可視化します。
4. **アラート設定:** 異常値を検知した場合に、適切な担当者に通知されるようアラートを設定します。
5. **分散トレーシングとログ集約:** OpenTelemetryなどのツールを導入し、リクエストのライフサイクル全体を追跡できるようにし、ログを中央集約型システムに送信します。

### 原因4：データベース接続の管理が不適切

高負荷時にアプリケーションが大量のデータベース接続を確立しようとすると、データベースが過負荷になり、パフォーマンスが著しく低下したり、接続エラーが発生したりします。特にPostgreSQLは200以上の接続で性能が急激に劣化する傾向があります。

**Before（エラーが起きるコード）：**

```
# アプリケーションが直接PostgreSQLに接続
# 接続プールはアプリケーション側で設定されているが、
# データベース側の最大接続数を超過する可能性を考慮していない
```

**After（修正後）：**

```ini
# pgbouncer.ini — PgBouncerの設定例
[pgbouncer]
pool_mode = transaction  # トランザクションモードで接続をプール
max_client_conn = 10000  # PgBouncerが受け入れる最大クライアント接続数
default_pool_size = 150  # 各データベースへのデフォルトプールサイズ
reserve_pool_size = 5    # 予備の接続プールサイズ
```
**解決手順:**
1. **接続プーラーの導入:** PgBouncerなどのデータベース接続プーラーを導入し、アプリケーションとデータベースの間に配置します。これにより、アプリケーションからの多数の接続要求を、データベースへの少数の永続的な接続に集約できます。
2. **トランザクションモードの利用:** PgBouncerでは`pool_mode = transaction`を設定し、トランザクション単位で接続をプールすることで、効率的なリソース利用を実現します。
3. **IaCでの管理:** データベース接続プーラーの設定は、RDSリソースなどと同様にTerraformモジュール内で管理し、インフラ構築時に自動的にプロビジョニングされるようにします。

## ツール固有の注意点

- **GitHub Actions:** `timeout-minutes`はジョブ全体に適用されます。ステップごとに細かいタイムアウトを設定したい場合は、`run`コマンド内で`timeout`コマンドを使用するか、スクリプト内でタイムアウトロジックを実装する必要があります。
- **AWS ECS:** デプロイ時の自動ロールバックは、ECSサービスのデプロイ設定（`minimumHealthyPercent`, `maximumPercent`）と、ロードバランサーのヘルスチェック、そしてカスタムスクリプトを組み合わせることで実現します。`aws ecs wait services-stable`コマンドは、サービスが安定状態になるまで待機しますが、ヘルスチェック失敗時のロールバックは別途ロジックが必要です。
- **Terraform:** `terraform apply`は冪等性を持つため、何度実行しても同じ状態になります。しかし、手動で変更されたリソースは`terraform plan`で差分として検出されるため、定期的な`terraform plan`実行と、手動変更の禁止を徹底することが重要です。
- **PostgreSQL:** `max_connections`はデータベースの性能に直結する重要な設定です。アプリケーションの接続要件とサーバーリソースを考慮して適切に設定し、PgBouncerなどの接続プーラーと組み合わせて利用することを強く推奨します。

## それでも解決しない場合

- **詳細なログの確認:**
  - **CI/CDツール:** GitHub Actionsの実行ログ、AWS CodeBuildのビルドログ、Jenkinsのコンソール出力などを詳細に確認します。特に、タイムアウトやエラーが発生したステップの直前のログに注目します。
  - **アプリケーションログ:** CloudWatch Logs、Datadog、Splunkなどのログ集約サービスで、アプリケーションが出力するエラーログやスタックトレースを確認します。
  - **インフラログ:** EC2のシステムログ、RDSのログ（PostgreSQLログなど）、ロードバランサーのアクセスログなどを確認し、インフラ層での問題がないか調査します。
- **デバッグコマンドの活用:**
  - **AWS CLI:** `aws ecs describe-services --cluster <cluster-name> --services <service-name>`でECSサービスの状態を確認したり、`aws logs get-log-events`でCloudWatch Logsから特定のログストリームを取得したりします。
  - **Terraform:** `terraform plan`で現在のインフラとコードの差分を確認し、`terraform state show <resource-address>`で特定のリソースの状態を確認します。
  - **データベース:** `psql`コマンドでデータベースに接続し、`SHOW max_connections;`や`SELECT * FROM pg_stat_activity;`などで接続状況を確認します。
- **公式ドキュメントの参照:**
  - 各ツールの公式ドキュメントは、最新の情報と詳細なトラブルシューティングガイドを提供しています。
    - [GitHub Actions Documentation](https://docs.github.com/en/actions)
    - [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
    - [Terraform Documentation](https://www.terraform.io/docs/)
    - [PostgreSQL Documentation](https://www.postgresql.org/docs/)
    - [PgBouncer Documentation](https://www.pgbouncer.org/config.html)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*