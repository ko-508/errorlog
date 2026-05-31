---
title: "Docker Compose の 503 エラー：原因と解決策"
date: 2026-05-31
description: "サービスが起動できないか利用できない状態にある。Docker Compose 503 エラーの原因と解決策を解説します。"
tags: ["Docker Compose"]
errorCode: "503"
---
## エラーの概要

503エラーは「Service Unavailable」を意味し、Docker Composeでは依存するサービスが正常に起動できていない、または起動完了前にアクセスされている状況を示します。マイクロサービスアーキテクチャではよく発生するエラーで、特に複数コンテナーの起動順序やヘルスチェック設定に起因することが多いです。

## 実際のエラーメッセージ例

Docker Composeで503エラーが発生した際のログ例を以下に示します。

```json
{
  "status": 503,
  "message": "Service Unavailable",
  "error": "connect ECONNREFUSED 172.20.0.3:5432"
}
```

```bash
docker compose logs app-service
2024-01-15T10:23:45.123Z ERROR Failed to connect to database: ECONNREFUSED
2024-01-15T10:23:46.456Z WARN Service startup failed, retrying...
2024-01-15T10:23:50.789Z ERROR Max retries exceeded
```

## よくある原因と解決手順

### 原因1：depends_onで依存関係を定義しているが、ヘルスチェック待機を設定していない

マイクロサービス構成では、アプリケーションコンテナーがデータベースコンテナーの**完全な起動完了**を待つ必要があります。`docker compose up`実行時、デフォルトでは依存するコンテナーが「起動した」ことだけを確認して先に進むため、データベースが受け入れ準備完了する前にアクセスされます。

**Before（エラーが起きるコード）：**

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
  
  app:
    image: myapp:latest
    depends_on:
      - postgres
    ports:
      - "8080:8080"
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
  
  app:
    image: myapp:latest
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8080:8080"
```

上記の修正では、`service_healthy`条件によってPostgresのヘルスチェック成功を待ってからアプリケーション起動が開始されます。

### 原因2：ヘルスチェックコマンドが不適切で常に失敗している

ヘルスチェックが定義されていても、そのコマンドが実装されていない、不正な形式、または環境に合わない場合、サービスは「unhealthy」と判定され続け、503エラーが解決されません。

**Before（エラーが起きるコード）：**

```yaml
version: '3.8'
services:
  redis:
    image: redis:7
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6379/health"]
      interval: 5s
      retries: 3
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  redis:
    image: redis:7
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 3
  
  app:
    image: myapp:latest
    depends_on:
      redis:
        condition: service_healthy
    environment:
      REDIS_HOST: redis
      REDIS_PORT: 6379
```

Redisの場合、`redis-cli ping`がヘルスチェック手段として有効です。対象サービスに応じて適切なコマンドを選択してください。

### 原因3：コンテナーが起動直後に停止している（エントリーポイントエラー）

アプリケーションコンテナーが起動スクリプトや依存パッケージの不足でクラッシュしている場合、Docker Composeがサービスを「起動した」と判定しても実際には停止状態になり、503エラーが返されます。

**Before（エラーが起きるコード）：**

```dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# アプリケーション起動時にエラーが発生する可能性
CMD ["python", "app.py"]
```

**After（修正後）：**

```dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# ヘルスチェックエンドポイントを公開
EXPOSE 8080
# エラーハンドリングと起動ログの追加
CMD ["sh", "-c", "echo 'Starting app...' && python app.py || (echo 'App startup failed'; exit 1)"]
```

同時にDocker Composeの設定でも確認メカニズムを追加します。

```yaml
version: '3.8'
services:
  app:
    build: .
    container_name: myapp
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    restart: on-failure
```

## ツール固有の注意点

Docker Composeで503エラーを防ぐために、以下のベストプラクティスに従うことが重要です。

**ヘルスチェックの`start_period`パラメーター**：アプリケーション初期化に時間がかかる場合は、`start_period`を設定して初期ヘルスチェック失敗を無視させます。これにより、起動直後の一時的な接続失敗で「unhealthy」と判定されるのを防げます。

**複数レイヤーの依存構成**：3層以上のマイクロサービス構成（例：Nginx → API → Database）では、各層すべてに`condition: service_healthy`を設定します。中間層のみ待機しても、その先のサービスがダウンしていれば結局503エラーが発生します。

**ネットワーク分離**：複数のCompose設定を運用する場合、`networks`セクションで明示的にネットワークを定義し、不要なサービス間通信を遮断することで、予期しない503エラーの原因を減らせます。

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    networks:
      - backend
  
  app:
    image: myapp:latest
    networks:
      - backend
    depends_on:
      postgres:
        condition: service_healthy

networks:
  backend:
    driver: bridge
```

## それでも解決しない場合

503エラーが継続する場合は、以下の手順で詳細な原因調査を行います。

**ログ確認コマンド**：

```bash
# 全サービスのログを時系列で表示
docker compose logs -f

# 特定サービスのみ確認
docker compose logs -f postgres

# 起動失敗の詳細メッセージを確認
docker compose logs app-service | grep -i error
```

**コンテナー状態の確認**：

```bash
# 全コンテナーの状態を表示
docker compose ps

# 特定コンテナーの詳細情報
docker inspect <container_id>

# ヘルスチェック状態の確認
docker compose exec postgres pg_isready -U postgres
```

**ネットワーク疎通確認**：

```bash
# 別コンテナーから対象サービスへの接続テスト
docker compose exec app curl -v http://postgres:5432

# ポートリッスン状態の確認
docker compose exec postgres netstat -tlnp
```

**設定ファイルの検証**：

```bash
# compose.ymlの構文エラーを確認
docker compose config --quiet

# 明示的なエラーメッセージ表示
docker compose config
```

Composeファイルに記述エラーがないか、公式ドキュメント（https://docs.docker.com/compose/compose-file/）で仕様を再確認し、特に`condition`値が`service_healthy`、`service_started`、`service_completed_successfully`のいずれかか確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*