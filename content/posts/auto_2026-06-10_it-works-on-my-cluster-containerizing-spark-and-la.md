---
title: "データエンジニアのためのDocker活用術：Sparkとレイクハウス開発環境のコンテナ化"
date: 2026-06-10
lastmod: 2026-06-10
draft: false
description: "「ローカルでは動くのに本番では動かない」問題を解決する、Sparkとレイクハウス開発環境の完全コンテナ化手法を解説します。DockerとDocker Composeを使って、開発環境と本番環境の差異をなくし、信頼性の高いデータパイプラインを構築する方法を学びましょう。"
tags: ["Dev.to - DevOps"]
---

## エラーの概要

データパイプライン開発において、「ローカル環境では問題なく動作するのに、本番クラスターにデプロイするとエラーが発生する」という問題は頻繁に発生します。これは、開発環境と本番環境の間に存在する依存関係の不一致、SparkやDelta Lakeのバージョン差異、タイムゾーン設定の違いなどが原因で引き起こされます。ウェブ開発の世界ではDockerのようなコンテナ技術によってこの問題は解決されましたが、データエンジニアリングの分野では未だに多くのチームがこの課題に直面しています。

## 実際のエラーメッセージ例

データパイプラインが本番環境で失敗する際、以下のようなエラーメッセージが出力されることがあります。

**PySparkジョブの依存関係エラー:**

```
Py4JJavaError: An error occurred while calling o#.runCommand.
: org.apache.spark.sql.AnalysisException: Failed to find data source: io.delta.sql.DeltaSparkSessionExtension. Please ensure the data source package is installed.
```

**Delta Lakeプロトコルバージョン不一致エラー:**

```
Py4JJavaError: An error occurred while calling o#.runCommand.
: org.apache.delta.exceptions.DeltaUnsupportedOperationException: This table was written with a newer version of Delta Lake (protocol version 5, reader version 2) that is not supported by this version of Delta Lake. Please upgrade your Delta Lake library.
```

**Hadoop S3コネクタ関連のエラー:**

```
Py4JJavaError: An error occurred while calling o#.runCommand.
: java.lang.ClassNotFoundException: Class org.apache.hadoop.fs.s3a.S3AFileSystem not found
```

## よくある原因と解決手順

データパイプラインの環境差異は、主に以下の4つのレイヤーで発生します。

1.  **計算ランタイム:** Spark、Scala、JVM、Python、ネイティブライブラリ（Arrow、Parquet、libhdfs）のバージョン。
2.  **テーブルフォーマットレイヤー:** Delta Lake / Icebergのライブラリバージョンとプロトコルバージョン。
3.  **ストレージレイヤー:** S3/ADLSのセマンティクス（マルチパートアップロード、結果整合性、パススタイル vs バーチャルホストアクセス）。
4.  **オーケストレーションレイヤー:** スケジューラのPython環境。

これらのレイヤーをコードで固定し、バージョン管理することが「ローカルでは動くのに本番では動かない」問題を解決する鍵となります。

### 原因1：Sparkおよび関連ライブラリのバージョン不一致

開発環境と本番環境でSpark、Delta Lake、Hadoop AWSコネクタなどのバージョンが異なると、互換性の問題が発生します。特に、`spark-submit`時に`--packages`オプションでJARを解決すると、Maven Centralがランタイム依存となり、予期せぬバージョン変更でエラーが発生する可能性があります。

**Before（エラーが起きるコード）：**

```dockerfile
# Sparkのバージョンを固定せず、PySparkのみをインストール
FROM python:3.11-slim
RUN pip install pyspark==3.5.4 delta-spark==3.3.0
# --packagesでランタイムにJARを解決
# spark-submit --packages io.delta:delta-spark_2.12:3.3.0,org.apache.hadoop:hadoop-aws:3.3.6 your_job.py
```

**After（修正後）：**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM eclipse-temurin:17-jre-jammy AS base
ARG SPARK_VERSION=3.5.4
ARG DELTA_VERSION=3.3.0
ARG HADOOP_AWS_VERSION=3.3.6

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.11 python3-pip tini && \
    rm -rf /var/lib/apt/lists/*

# Spark自体を固定し、/opt/sparkに配置
RUN curl -fsSL https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz \
    | tar -xz -C /opt && mv /opt/spark-${SPARK_VERSION}-bin-hadoop3 /opt/spark
ENV SPARK_HOME=/opt/spark PATH=$PATH:/opt/spark/bin PYTHONHASHSEED=0 TZ=UTC

# Delta + S3コネクタをビルド時に解決し、Sparkのjarsディレクトリにコピー
RUN /opt/spark/bin/spark-shell --packages \
      io.delta:delta-spark_2.12:${DELTA_VERSION},org.apache.hadoop:hadoop-aws:${HADOOP_AWS_VERSION} \
      -e "println(\"deps cached\")" && \
    cp /root/.ivy2/jars/*.jar /opt/spark/jars/

COPY requirements.lock /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.lock

RUN useradd -m -u 1001 spark
USER 1001
ENTRYPOINT ["/usr/bin/tini", "--"]
```

**解決手順:**

1.  **ベースイメージの固定:** `eclipse-temurin`のような特定のJREバージョンをベースイメージとして使用します。
2.  **Sparkのピンニング:** `ARG`でSparkのバージョンを定義し、ビルド時に特定のバージョンのSparkバイナリをダウンロードして`/opt/spark`に配置します。
3.  **コネクタのビルド時解決:** `spark-shell --packages`コマンドをDockerfileのビルドステップで実行し、必要なJARファイル（Delta Lake、Hadoop AWSコネクタなど）をダウンロードしてSparkの`jars`ディレクトリにコピーします。これにより、ランタイムでの依存解決をなくし、再現性を高めます。
4.  **環境変数の固定:** `PYTHONHASHSEED=0`と`TZ=UTC`を設定することで、非決定的なバグ（ハッシュ値の順序やタイムゾーンの違いによる挙動の差異）を防ぎます。
5.  **依存関係のロック:** `requirements.lock`ファイルを使用し、`pip install --no-cache-dir -r /tmp/requirements.lock`でPythonの依存関係を厳密に固定します。`pip-compile`や`uv pip compile`などのツールで生成すると良いでしょう。
6.  **非rootユーザーでの実行:** `useradd`で`spark`ユーザーを作成し、`USER 1001`で非rootユーザーとしてSparkを実行することで、セキュリティを向上させます。

### 原因2：ローカルモードとクラスターモードの挙動の違い

Sparkの`local[*]`モードは、すべての処理を単一のJVM内で実行するため、実際のクラスター環境で発生するシリアライゼーション、シャッフル、ネットワーク関連のバグを隠蔽してしまいます。

**Before（エラーが起きるコード）：**

```python
# ローカルモードでSparkSessionを初期化
spark = SparkSession.builder \
    .master("local[*]") \
    .appName("MyLocalApp") \
    .getOrCreate()
```

**After（修正後）：**

```yaml
# compose.yaml
services:
  spark-master:
    build: . # 上記のDockerfileでビルドされたイメージを使用
    command: /opt/spark/sbin/start-master.sh
    environment: [SPARK_NO_DAEMONIZE=true]
    ports: ["7077:7077", "8080:8080"]
  spark-worker:
    build: . # 上記のDockerfileでビルドされたイメージを使用
    command: /opt/spark/sbin/start-worker.sh spark://spark-master:7077
    environment:
      - SPARK_NO_DAEMONIZE=true
      - SPARK_WORKER_MEMORY=4g
      - SPARK_WORKER_CORES=2
    depends_on: [spark-master]
    deploy:
      replicas: 2          # 複数のワーカーで実際のシャッフルとシリアライゼーションを再現
  minio:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: localdev
      MINIO_ROOT_PASSWORD: localdev-secret
    ports: ["9000:9000", "9001:9001"]
    volumes: [lake-data:/data]
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
  mc-init:                  # MinIO起動時にバケットを作成
    image: minio/mc:latest
    depends_on: { minio: { condition: service_healthy } }
    entrypoint: >
      /bin/sh -c "mc alias set local http://minio:9000 localdev localdev-secret &&
      mc mb -p local/lakehouse/bronze local/lakehouse/silver local/lakehouse/gold"
volumes:
  lake-data:
```

**解決手順:**

1.  **Docker Composeによるクラスターの再現:** `docker-compose.yaml`ファイルを使用して、Sparkマスターと複数のワーカーノードをローカルで起動します。これにより、実際のクラスター環境に近いシリアライゼーションとシャッフル処理を再現できます。
2.  **オブジェクトストレージのエミュレーション:** MinIOをS3互換のオブジェクトストレージとしてDocker Composeで起動し、データレイクのストレージレイヤーをローカルで再現します。`mc-init`サービスを使って、必要なバケットを自動で作成します。
3.  **Spark設定の調整:** Sparkアプリケーション内でMinIOを指すように設定を調整します。

```python
# SparkSessionをMinIOとDelta Lakeに対応させる
spark = (SparkSession.builder
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
    .config("spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    .getOrCreate())
```

### 原因3：開発環境と本番環境のイメージ差異

開発時にはデバッグツールやテストライブラリが必要ですが、本番環境ではそれらは不要であり、イメージサイズを増やし、セキュリティリスクを高めます。開発用と本番用で異なるイメージをビルドすると、再び環境差異の問題が発生する可能性があります。

**Before（エラーが起きるコード）：**

```dockerfile
# 開発用と本番用で完全に異なるDockerfileを作成
# Dockerfile.dev
FROM base
RUN pip install jupyterlab pytest debugpy

# Dockerfile.prod
FROM base
COPY src/ /app/src/
```

**After（修正後）：**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM eclipse-temurin:17-jre-jammy AS base
ARG SPARK_VERSION=3.5.4
ARG DELTA_VERSION=3.3.0
ARG HADOOP_AWS_VERSION=3.3.6
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.11 python3-pip tini && \
    rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz \
    | tar -xz -C /opt && mv /opt/spark-${SPARK_VERSION}-bin-hadoop3 /opt/spark
ENV SPARK_HOME=/opt/spark PATH=$PATH:/opt/spark/bin PYTHONHASHSEED=0 TZ=UTC
RUN /opt/spark/bin/spark-shell --packages \
      io.delta:delta-spark_2.12:${DELTA_VERSION},org.apache.hadoop:hadoop-aws:${HADOOP_AWS_VERSION} \
      -e "println(\"deps cached\")" && \
    cp /root/.ivy2/jars/*.jar /opt/spark/jars/
COPY requirements.lock /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.lock
RUN useradd -m -u 1001 spark
USER 1001
ENTRYPOINT ["/usr/bin/tini", "--"]

# 開発ステージ
FROM base AS dev
USER root
RUN pip install --no-cache-dir jupyterlab pytest debugpy
USER 1001

# 本番ステージ
FROM base AS prod
COPY --chown=1001:1001 src/ /app/src/
COPY --chown=1001:1001 jobs/ /app/jobs/
# 本番環境では不要なツールは含めない
```

**解決手順:**

1.  **マルチステージビルドの活用:** 単一のDockerfile内で複数の`FROM`ステートメントを使用し、開発用と本番用のステージを定義します。
2.  **ベースイメージの共有:** `base`ステージでSparkランタイムとコアな依存関係を構築し、`dev`ステージと`prod`ステージの両方でこの`base`イメージを再利用します。
3.  **ステージごとの依存関係:** `dev`ステージにはJupyterLab、pytest、debugpyなどの開発ツールを追加し、`prod`ステージには本番稼働に必要なコードのみをコピーします。これにより、本番イメージを最小限に保ちつつ、開発環境の利便性を確保します。
4.  **CI/CDパイプラインでの活用:** CIで`prod`ステージのイメージをビルドし、テストを実行し、そのイメージを本番環境にデプロイします。これにより、「テストしたイメージがデプロイされるアーティファクトである」という原則を遵守できます。

## ツール固有の注意点

*   **MinIOはS3の完全なクローンではない:** MinIOはS3 API互換ですが、S3特有のリクエストスロットリングやリージョン間レイテンシなどの挙動は再現できません。本番環境へのデプロイ前に、実際のS3に対して小規模なスモークテストを実行することをお勧めします。
*   **Sparkワーカーの数:** ローカル環境で`local[*]`モードではなく、Docker Composeで2つ以上のSparkワーカーを起動することで、実際のクラスター環境で発生するシリアライゼーションやシャッフル関連のバグを早期に発見できます。
*   **Delta Lake/Icebergプロトコルバージョンのピンニング:** テーブルフォーマットライブラリのバージョンだけでなく、テーブルプロトコルバージョンも固定することが重要です。新しいライターが生成したテーブルを古いリーダーが開けないといった問題を避けるため、イメージのビルド引数にプロトコルバージョンを含め、サポートする最も古いリーダーで読み込みテストを行うべきです。
*   **ローカルSparkのリソース制限:** `SPARK_WORKER_MEMORY`などの環境変数でローカルSparkワーカーのリソースを制限することで、ラップトップのリソース枯渇を防ぎ、パーティショニング戦略を早期に検討するきっかけにもなります。
*   **オーケストレーターのイメージ化:** Airflowのようなオーケストレーターの環境も、ジョブの環境と同様にコンテナ化し、`requirements.lock`のような厳密な依存関係管理を適用することで、オーケストレーター起因の環境差異を防ぎます。

## それでも解決しない場合

*   **ログの確認:**
    *   **Spark UI:** ローカルで`docker compose up`後、`http://localhost:8080`でSpark UIにアクセスし、ジョブの実行状況、ステージ、タスク、エラーログを確認します。
    *   **Docker Composeログ:** `docker compose logs <service_name>`コマンドで、特定のサービスのコンテナログを詳細に確認します。
    *   **アプリケーションログ:** Sparkジョブ内で出力されるアプリケーション固有のログを、設定されたログ出力先に合わせて確認します。
*   **デバッグコマンド:**
    *   **コンテナ内へのアクセス:** `docker compose exec <service_name> bash`で実行中のコンテナに入り、環境変数、ファイルパス、インストールされているパッケージなどを直接確認します。
    *   **Sparkシェルでのテスト:** Sparkマスターコンテナ内で`spark-shell`や`pyspark`を起動し、問題のコードスニペットを対話的に実行して挙動を確認します。
*   **公式ドキュメントへの参照:**
    *   **Apache Spark:** [https://spark.apache.org/docs/](https://spark.apache.org/docs/)
    *   **Delta Lake:** [https://delta.io/docs/](https://delta.io/docs/)
    *   **MinIO:** [https://min.io/docs/minio/linux/index.html](https://min.io/docs/minio/linux/index.html)
    *   **Docker:** [https://docs.docker.com/](https://docs.docker.com/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*