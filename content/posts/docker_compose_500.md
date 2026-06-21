---
title: "Docker Compose の 500 エラー：原因と解決策"
date: 2026-05-31
description: "Docker Composeサービスの内部エラーが発生した"
tags: ["Docker Compose"]
errorCode: "500"
service: "Docker Compose"
error_type: "500"
components: ["Compose"]
related_services: ["Docker", "PostgreSQL"]
---
## エラーの概要

[Docker](/glossary/docker/) Compose の 500 [エラー](/glossary/エラー/)は、[Docker](/glossary/docker/) Compose 自体またはそれが管理するコンテナー内で内部[エラー](/glossary/エラー/)が発生したことを示します。この[エラー](/glossary/エラー/)は通常、コンテナー起動時のアプリケーションクラッシュ、エントリポイント実行の失敗、または[ヘルスチェック](/glossary/ヘルスチェック/)機構の不具合によって引き起こされます。対象のサービスが正常に起動・稼働できない状態を意味しており、迅速な原因特定と対応が必要です。

## 実際のエラーメッセージ例

[Docker](/glossary/docker/) Compose でコンテナーが起動に失敗した際の典型的な[エラー](/glossary/エラー/)出力は以下の通りです。

```bash
ERROR: for <service-name>  Cannot start service <service-name>: 
OCI runtime create failed: container_linux.go:380: 
starting container process caused: exec: 
"<command>": executable file not found in $PATH: unknown
```

または、[ヘルスチェック](/glossary/ヘルスチェック/)失敗時は以下のように表示されます。

```bash
<service-name> | ERROR: Health check failed. Retrying...
<service-name> | (Exit status: 1)
```

アプリケーション実行時の[エラーログ](/glossary/エラーログ/)は以下のようなパターンです。

```bash
docker-compose logs <service-name>
<service-name> | Traceback (most recent call last):
<service-name> |   File "/app/main.py", line 15, in <module>
<service-name> |     raise Exception("Database connection failed")
<service-name> | Exception: Database connection failed
```

## よくある原因と解決手順

### 原因1：サービスのコンテナー内部でアプリケーションがクラッシュしている

コンテナー起動後、アプリケーションが異常終了またはランタイムエラーで落ちてしまう状況です。これは依存関係の欠落、[設定ファイル](/glossary/設定ファイル/)の不在、メモリ不足、または不正な初期化処理によって発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    image: python:3.9
    working_dir: /app
    command: python main.py
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
```

上記の場合、`main.py` が `DATABASE_URL` をパースしようとした際に例外が発生したり、必要なライブラリがインストールされていない場合にクラッシュします。

**After（修正後）：**

```yaml
version: '3.8'
services:
  app:
    build: .
    working_dir: /app
    command: python main.py
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
    depends_on:
      db:
        condition: service_healthy
    restart: on-failure
```

対応する `Dockerfile` では依存パッケージをすべてインストールし、[エラーハンドリング](/glossary/エラーハンドリング/)を強化します。

```dockerfile
FROM python:3.9
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

**診断[コマンド](/glossary/コマンド/)：**

```bash
docker compose logs <service-name>
```

この[コマンド](/glossary/コマンド/)でアプリケーション側のスタックトレースや例外メッセージが表示されます。メッセージから原因を特定し、コード修正またはパッケージインストールを行います。

### 原因2：コンテナーのエントリポイントやコマンドが失敗して終了した

`docker-compose.yml` の `command` または `entrypoint` に指定したスクリプト・実行ファイルが見つからない、または実行権限がない場合に発生します。これはパス指定の誤り、ファイルの忘れ、ビルド時のレイヤー構成ミスが原因となります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    entrypoint: /app/start.sh
    ports:
      - "80:80"
```

`start.sh` が[イメージ](/glossary/イメージ/)内に存在しないか、実行権限がない状態です。

**After（修正後）：**

```yaml
version: '3.8'
services:
  web:
    build: .
    entrypoint: ["/bin/sh", "-c"]
    command: "chmod +x /app/start.sh && /app/start.sh"
    ports:
      - "80:80"
```

対応する `Dockerfile`：

```dockerfile
FROM nginx:latest
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh
EXPOSE 80
```

**診断[コマンド](/glossary/コマンド/)：**

```bash
docker compose ps
```

コンテナーの状態が `Exit (1)` または類似のステータスになっていれば、エントリポイント実行時の失敗です。

```bash
docker compose logs <service-name>
```

で詳細な[エラーメッセージ](/glossary/エラーメッセージ/)を確認します。

### 原因3：ヘルスチェックが失敗しコンテナーが再起動ループに入っている

`healthcheck` で定義されたチェックが継続的に失敗し、[Docker](/glossary/docker/) がコンテナーを繰り返し再起動するため、サービスが安定しない状態です。これはアプリケーション起動時間が[タイムアウト](/glossary/タイムアウト/)値より長い、[ポート](/glossary/ポート/)待機が遅い、または接続情報が誤っている場合に発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  db:
    image: postgres:13
    environment:
      POSTGRES_PASSWORD: secret
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres"]
      interval: 5s
      timeout: 1s
      retries: 3
```

アプリケーション起動に 10 秒必要な場合、[タイムアウト](/glossary/タイムアウト/)値 1s と再試行回数 3 回では十分な時間がなく、何度も再起動が繰り返されます。

**After（修正後）：**

```yaml
version: '3.8'
services:
  db:
    image: postgres:13
    environment:
      POSTGRES_PASSWORD: secret
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
```

`start_period` を追加することで、コンテナー起動直後の[ヘルスチェック](/glossary/ヘルスチェック/)を遅延させ、アプリケーションが準備完了するまで待機します。

**診断[コマンド](/glossary/コマンド/)：**

```bash
docker compose logs <service-name> --tail=50
```

繰り返される[エラーメッセージ](/glossary/エラーメッセージ/)を確認し、[ヘルスチェック](/glossary/ヘルスチェック/)失敗の理由を特定します。

```bash
docker inspect <container-id> | grep -A 20 "Health"
```

現在の[ヘルスチェック](/glossary/ヘルスチェック/)状態を詳細に表示します。

## ツール固有の注意点

### サービス間の依存関係と起動順序

[Docker](/glossary/docker/) Compose の `depends_on` オプションはデフォルトではサービスの起動完了を待たず、コンテナー起動後すぐに次のサービスを起動します。[データベース](/glossary/データベース/)が完全に初期化される前にアプリケーションが接続を試みる場合、500 [エラー](/glossary/エラー/)が発生します。

```yaml
version: '3.8'
services:
  app:
    depends_on:
      db:
        condition: service_healthy
  db:
    healthcheck:
      test: ["CMD", "pg_isready"]
```

`condition: service_healthy` を使用することで、[ヘルスチェック](/glossary/ヘルスチェック/)成功までアプリケーション起動を遅延させます。

### マルチステージビルドでの依存関係漏れ

Dockerfile でマルチステージビルドを使用する場合、最終ステージに必要なランタイムやライブラリをコピーし忘れると、実行時に 500 [エラー](/glossary/エラー/)が発生します。

```dockerfile
FROM golang:1.19 as builder
WORKDIR /app
COPY . .
RUN go build -o myapp

FROM alpine:latest
COPY --from=builder /app/myapp /usr/local/bin/
# libc がないため実行時エラー
```

解決策として、必要なライブラリをインストールします。

```dockerfile
FROM alpine:latest
RUN apk add --no-cache libc6-compat
COPY --from=builder /app/myapp /usr/local/bin/
```

### 環境変数の未設定

アプリケーションが必須環境変数を参照しているが、`docker-compose.yml` で定義されていない場合、初期化時に例外が発生します。

```bash
docker compose config
```

で設定全体を確認し、[環境変数](/glossary/環境変数/)が適切に展開されているか検査します。

## それでも解決しない場合

### 詳細なログ確認

```bash
docker compose logs <service-name> -f --tail=100
```

`-f` フラグでリアルタイムログを監視し、`--tail=100` で直近 100 行を表示します。

個別サービスの起動[テスト](/glossary/テスト/)：

```bash
docker compose up --no-deps -d <service-name>
docker compose logs <service-name>
docker compose down
```

このコマンドセットでサービスを独立起動し、他のサービスの影響を除外して原因を特定できます。

### コンテナー内での直接実行

```bash
docker compose run --rm <service-name> /bin/bash
```

でコンテナー内の[シェル](/glossary/シェル/)を取得し、手動でアプリケーションを実行して[エラー](/glossary/エラー/)を確認します。

### イベントログの確認

```bash
docker events --filter type=container
```

でコンテナーのライフサイクルイベント（起動、停止、再起動）を監視します。

### 公式ドキュメント参照

- [Docker Compose Health checks](https://docs.docker.com/compose/compose-file/compose-file-v3/#healthcheck)
- [Docker Compose depends_on](https://docs.docker.com/compose/compose-file/compose-file-v3/#depends_on)
- [Docker Compose Troubleshooting](https://docs.docker.com/compose/troubleshooting/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*