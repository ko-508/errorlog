---
title: "データエンジニアのためのDocker活用術：Sparkとレイクハウス開発をコンテナで再現可能にする方法"
date: 2026-06-10
lastmod: 2026-06-10
draft: false
description: "データパイプライン開発における「手元の環境では動くのに本番では動かない」問題を解決するため、Sparkとレイクハウス環境をDockerで完全にコンテナ化する方法を解説します。開発、CI、本番環境で一貫した動作を実現するための具体的な手順と注意点を紹介します。"
tags: ["Dev.to - Docker"]
---

## エラーの概要

データエンジニアリングにおいて、ローカル環境で正常に動作するPySparkジョブが、本番クラスターやCI環境で予期せぬエラーを起こすことは珍しくありません。これは、開発環境と本番環境の間で、Sparkのバージョン、依存ライブラリ、Delta Lakeのプロトコル、タイムゾーン設定、オブジェクトストレージの挙動など、複数のレイヤーで差異（環境ドリフト）が生じるために発生します。

この問題は、ウェブ開発の世界ではDockerなどのコンテナ技術によって「Works on my machine（私のマシンでは動く）」問題として解決されてきましたが、データエンジニアリングの分野では未だに多くのチームが直面しています。結果として、高価なクラウド環境でのデバッグや、本番環境での予期せぬ障害につながることがあります。

## 実際のエラーメッセージ例

データパイプラインの環境ドリフトによって発生するエラーは多岐にわたりますが、典型的なものとしては以下のようなメッセージが挙げられます。

**依存関係の不一致:**

```
Py4JJavaError: An error occurred while calling o*.load.
: java.lang.NoClassDefFoundError: org/apache/hadoop/fs/s3a/S3AFileSystem
    at io.delta.storage.HadoopFileSystemLogStore.resolvePath(HadoopFileSystemLogStore.scala:100)
    at io.delta.storage.HadoopFileSystemLogStore.<init>(HadoopFileSystemLogStore.scala:59)
    ...
```

**SparkバージョンやDelta Lakeプロトコルの不一致:**

```
Py4JJavaError: An error occurred while calling o*.load.
: org.apache.spark.sql.AnalysisException: Delta Lake table at s3a://<your-bucket>/<your-path> requires a newer version of Delta Lake.
    Please upgrade your Delta Lake library to at least version <required-version>.
    ...
```

**タイムゾーン関連のエラー:**

```
Py4JJavaError: An error occurred while calling o*.collectToPython.
: java.time.DateTimeException: Invalid value for DayOfMonth (valid values 1 - 28/31): 30
    at java.time.temporal.ValueRange.checkValidValue(ValueRange.java:320)
    at java.time.LocalDate.of(LocalDate.java:264)
    ...
```

## よくある原因と解決手順

データパイプラインの環境ドリフトは、主に以下の4つのレイヤーで発生します。

1.  **計算ランタイム:** Spark、Scala、JVM、Python、ネイティブライブラリ（Arrow, Parquet, libhdfs）のバージョン。
2.  **テーブルフォーマットレイヤー:** Delta Lake / Icebergのライブラリバージョンとプロトコルバージョン。
3.  **ストレージレイヤー:** S3/ADLSのセマンティクス（マルチパートアップロード、結果整合性、パススタイル vs バーチャルホストアクセス）。
4.  **オーケストレーションレイヤー:** スケジューラのPython環境。

これらのレイヤーをコンテナ化し、コードで固定することで、環境ドリフトを防止できます。

### 原因1：Sparkおよび関連ライブラリのバージョンが固定されていない

ローカル環境と本番環境でSparkのマイナーバージョンや、Delta Lake、Hadoop-AWSコネクタなどの依存ライブラリのバージョンが異なる場合、互換性の問題が発生します。特に、`spark-submit`時に`-packages`オプションでJARを動的に解決すると、Maven Centralの変更によって予期せぬバージョンがダウンロードされ、エラーにつながる可能性があります。

**解決手順:**
Dockerイメージのビルド時に、Spark本体、Delta Lake、Hadoop-AWSコネクタなどのすべての依存関係を明示的にバージョン指定し、イメージ内に含めます。これにより、実行時に外部リポジトリに依存することなく、常に同じ環境でSparkジョブが実行されます。

**Before（エラーが起きるコード）：**

```dockerfile
# Sparkのバージョンは指定するが、Delta LakeやHadoop-AWSは実行時に動的に解決
FROM eclipse-temurin:17-jre-jammy
ARG SPARK_VERSION=3.5.4
RUN curl -fsSL https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz \
    | tar -xz -C /opt && mv /opt/spark-${SPARK_VERSION}-bin-hadoop3 /opt/spark
ENV SPARK_HOME=/opt/spark PATH=$PATH:/opt/spark/bin
# 実行時に spark-submit --packages io.delta:delta-spark_2.12:3.3.0,org.apache.hadoop:hadoop-aws:3.3.6 で解決
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
# Spark本体をピン留め
RUN curl -fsSL https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz \
    | tar -xz -C /opt && mv /opt/spark-${SPARK_VERSION}-bin-hadoop3 /opt/spark
ENV SPARK_HOME=/opt/spark PATH=$PATH:/opt/spark/bin PYTHONHASHSEED=0 TZ=UTC
# Delta + S3コネクタをビルド時に解決し、JARをイメージに含める
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

### 原因2：ローカル開発環境が本番クラスターの挙動を正確に再現できていない

多くのデータエンジニアは、ローカルでSparkの`local[*]`モードを使用したり、クラウドの共有ワークスペースで開発したりします。しかし、`local[*]`モードはJVM間のシリアライゼーションやシャッフルを隠蔽するため、本番クラスターで発生する可能性のあるバグ（例: UDFの直列化問題、メモリ不足）を早期に発見できません。また、クラウドワークスペースは環境ドリフトのリスクを抱えています。

**解決手順:**
Docker Composeを使用して、ローカル環境にSparkマスター/ワーカーペアと、MinIO（S3互換オブジェクトストレージ）を構築します。これにより、本番クラスターに近い分散環境と、S3互換のストレージレイヤーをローカルで再現できます。

**Before（エラーが起きるコード）：**

```python
# ローカルモードでSparkセッションを初期化
spark = (SparkSession.builder
    .master("local[*]") # local[*]モードは分散環境の挙動を隠蔽する
    .appName("LocalSparkApp")
    .getOrCreate())
# S3へのアクセスは、ローカル環境のAWS認証情報に依存
```

**After（修正後）：**

`compose.yaml`ファイルでSparkマスター、ワーカー、MinIOを設定します。

```yaml
# compose.yaml
services:
  spark-master:
    build: . # 上記のDockerfileでビルドしたイメージを使用
    command: /opt/spark/sbin/start-master.sh
    environment: [SPARK_NO_DAEMONIZE=true]
    ports: ["7077:7077", "8080:8080"]
  spark-worker:
    build: .
    command: /opt/spark/sbin/start-worker.sh spark://spark-master:7077
    environment:
      - SPARK_NO_DAEMONIZE=true
      - SPARK_WORKER_MEMORY=4g
      - SPARK_WORKER_CORES=2
    depends_on: [spark-master]
    deploy:
      replicas: 2          # 2つ以上のワーカーで実際のシャッフルとシリアライゼーションを再現
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

Sparkセッションの初期化では、MinIOをS3エンドポイントとして指定します。

```python
# SparkセッションをMinIOに接続
spark = (SparkSession.builder
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
    .config("spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    .getOrCreate())
# これにより、s3a://lakehouse/... のパスがMinIOを指すようになる
```

### 原因3：CI/CDパイプラインで本番環境に近いテストができていない

CI/CD環境でSparkジョブのテストを行う際、DataFrameをモックしたり、Sparkを完全にモックしたりすることがあります。しかし、これは実際のSparkの挙動やDelta Lakeのトランザクションログ、オブジェクトストレージとのインタラクションをテストしていることにはなりません。結果として、テストはパスするが本番で失敗するという問題が発生します。

**解決手順:**
Testcontainersライブラリを使用して、CI環境で実際のSparkとMinIOコンテナを起動し、その上で統合テストを実行します。これにより、開発環境と同じコンテナイメージと環境で、本番に近いテストが可能です。

**Before（エラーが起きるコード）：**

```python
# PySparkのDataFrameをモックしてテスト
from unittest.mock import MagicMock
def test_silver_dedup_keeps_latest_record_mocked():
    mock_spark = MagicMock()
    mock_df = MagicMock()
    mock_spark.read.format.return_value.load.return_value = mock_df
    # ... モックされたDataFrameに対するアサーション ...
```

**After（修正後）：**

```python
# TestcontainersとPytestを使用して実際のSparkとMinIOでテスト
import pytest
from testcontainers.minio import MinioContainer
from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def lake(request):
    # MinioContainerを起動し、テストセッション全体で利用
    with MinioContainer("minio/minio:RELEASE.2025-09-07T16-13-09Z") as minio:
        yield minio

@pytest.fixture(scope="session")
def spark(lake):
    # Minioに接続するSparkSessionを初期化
    spark_session = (SparkSession.builder
        .master("local[*]") # テスト用にlocal[*]を使用することも可能だが、より厳密にはDocker ComposeでSparkクラスタをTestcontainersで起動する
        .config("spark.hadoop.fs.s3a.endpoint", lake.get_endpoint())
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .getOrCreate())
    yield spark_session
    spark_session.stop()

def test_silver_dedup_keeps_latest_record(lake, spark):
    # 実際のMinIOとSparkを使用してテストデータを書き込み、パイプラインを実行
    bronze_path = f"s3a://test/bronze/customers"
    write_fixture_events(spark, bronze_path, duplicates=True)
    run_silver_dedup(spark, bronze_path, "s3a://test/silver/customers")
    result = spark.read.format("delta").load("s3a://test/silver/customers")
    assert result.count() == EXPECTED_UNIQUE
    assert latest_record_wins(result)
```

## ツール固有の注意点

*   **`PYTHONHASHSEED=0`と`TZ=UTC`**: Dockerイメージのビルド時にこれらの環境変数を設定することで、Pythonのハッシュ値の非決定性やタイムゾーンのデフォルト設定に起因する「本番環境でのみ発生する非決定性バグ」を防ぐことができます。
*   **`requirements.lock`の使用**: `pip-compile`や`uv pip compile`などのツールで生成されたロックファイルを使用し、推移的な依存関係（特に`pandas`/`pyarrow`など）のバージョンがドリフトしないようにします。
*   **ローカルSparkワーカーは2つ以上**: `local[*]`モードではなく、Docker Composeで2つ以上のSparkワーカーを起動することで、JVM間のシリアライゼーションやシャッフルに関連するバグを早期に発見できます。
*   **Delta Lakeプロトコルバージョンのピン留め**: Delta LakeやIcebergはテーブルプロトコルバージョンを進化させています。新しいライターが生成したテーブルを古いリーダーが開けない可能性があるため、イメージビルド引数にプロトコルバージョンをエンコードし、サポートする最も古いリーダーでの読み取りテストを実施します。
*   **MinIOはS3の完全なクローンではない**: MinIOはS3 API互換ですが、S3のリクエストスロットリングやリージョン間のレイテンシなどは再現できません。小規模なスモークテストスイートを夜間に実際のオブジェクトストレージに対して実行し、それ以外の開発はローカルで行うのが良いでしょう。
*   **ローカルSparkのリソース制限**: `SPARK_WORKER_MEMORY`などの環境変数でローカルSparkのリソースを制限することで、ラップトップのメモリを使い果たすことを防ぎ、パーティショニング戦略について早期に検討するきっかけになります。
*   **オーケストレーターのイメージもコンテナ化**: AirflowなどのスケジューラのDAG解析環境もドリフトする可能性があります。ジョブと同様に、スケジューラのコンテナイメージもロックファイルなどの規律に従ってコンテナ化し、バージョン管理します。
*   **マルチステージビルド**: 開発用（Jupyter、デバッガーを含む）と本番用（最小限のランタイム、非rootユーザー）で異なるステージを持つマルチステージDockerfileを使用し、CIでビルドしたイメージをそのまま本番にデプロイします。

## それでも解決しない場合

上記の手順を試しても問題が解決しない場合は、以下の点を確認してください。

*   **ログの確認**:
    *   Dockerコンテナのログ: `docker logs <container_name>` でSparkマスター、ワーカー、MinIOなどのコンテナログを確認し、エラーメッセージやスタックトレースを探します。
    *   Spark UI: ローカルでSparkマスターを起動している場合、`http://localhost:8080`でSpark UIにアクセスし、ジョブの実行状況、ステージ、タスクのログを確認します。
*   **デバッグコマンド**:
    *   コンテナ内でのシェルアクセス: `docker exec -it <container_name> /bin/bash` でコンテナ内に入り、ファイルシステム、環境変数、インストールされているライブラリなどを直接確認します。
    *   PySparkの対話型シェル: 開発用イメージでJupyterやPySparkシェルを起動し、問題のコードスニペットをステップバイステップで実行してデバッグします。
*   **公式ドキュメント**:
    *   Apache Spark公式ドキュメント: 使用しているSparkのバージョンに応じた設定やトラブルシューティングガイドを確認します。
    *   Delta Lake公式ドキュメント: Delta Lakeのバージョン互換性やプロトコルに関する情報を確認します。
    *   MinIO公式ドキュメント: MinIOの設定やS3互換性に関する情報を確認します。
    *   Docker公式ドキュメント: Dockerfileの構文やDocker Composeの設定に関する詳細を確認します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*