---
title: "Docker ComposeでSpring PetClinicマイクロサービスをEC2にデプロイする際のHTTPエラー解決ガイド"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "Docker Composeを使ってSpring PetClinicマイクロサービスをAWS EC2にデプロイする際に遭遇しがちなHTTPエラーの原因と解決策を、具体的なコード例を交えて解説します。特に、サービス間の依存関係と起動順序に起因する問題に焦点を当てます。"
tags: ["Dev.to - Docker"]
trend_incident: true
---

## エラーの概要

Docker Composeで複数のマイクロサービスを起動する際、サービス間の依存関係が正しく解決されないと、HTTPリクエストが失敗したり、アプリケーションが正常に起動しなかったりするエラーが発生します。特に、Spring PetClinicのようなマイクロサービスアーキテクチャでは、設定サーバーやサービスディスカバリが他のサービスより先に起動している必要があります。これらのサービスが利用可能になる前に依存サービスが起動しようとすると、接続エラーや設定取得失敗などのHTTPエラーが発生します。

## 実際のエラーメッセージ例

以下は、Config ServerやDiscovery Serverが未起動の状態で依存サービスが起動しようとした際に、コンテナログやアプリケーションのHTTPレスポンスとして現れる可能性のあるエラーメッセージの例です。

**コンテナログの例（Config Serverへの接続失敗）:**

```
2023-10-27 10:00:05.123 ERROR 1 --- [           main] o.s.boot.SpringApplication               : Application run failed

org.springframework.cloud.config.client.ConfigServicePropertySourceLocator : Could not locate PropertySource: I/O error on GET request for "http://config-server:8888/config-client/default": Connection refused (Connection refused); nested exception is java.net.ConnectException: Connection refused (Connection refused)
```

**コンテナログの例（Eureka Discovery Serverへの登録失敗）:**

```
2023-10-27 10:00:10.567 ERROR 1 --- [           main] c.n.eureka.DefaultEurekaClientConfig     : Cannot execute request on server at http://eureka-server:8761/eureka/apps/

com.netflix.discovery.shared.transport.TransportException: Cannot execute request on server at http://eureka-server:8761/eureka/apps/
	at com.netflix.discovery.shared.transport.jersey.Abstract </your-service-name> JerseyEurekaHttpClient.handleException(AbstractJerseyEurekaHttpClient.java:214)
	at com.netflix.discovery.shared.transport.jersey.AbstractJerseyEurekaHttpClient.getApplications(AbstractJerseyEurekaHttpClient.java:120)
	...
Caused by: java.net.ConnectException: Connection refused (Connection refused)
	at java.base/java.net.PlainSocketImpl.socketConnect(Native Method)
	at java.base/java.net.AbstractPlainSocketImpl.doConnect(AbstractPlainSocketImpl.java:412)
	...
```

## よくある原因と解決手順

### 原因1：サービス起動順序の誤り

マイクロサービスアーキテクチャでは、各サービスが特定の役割を担い、他のサービスに依存していることがよくあります。例えば、設定情報を一元管理するConfig Serverや、サービス間の発見を担うDiscovery Server（Eureka）は、他のビジネスロジックサービスが起動する前に利用可能になっている必要があります。Docker Composeの`depends_on`はコンテナの起動順序を制御しますが、アプリケーションが完全に初期化されるまで待機するわけではありません。

**Before（エラーが起きるコード）：**

```yaml
# docker-compose.ymlの一部
version: '3.8'
services:
  api-gateway:
    image: springcommunity/spring-petclinic-api-gateway
    ports:
      - "8080:8080"
    # depends_onが設定されていない、または順序が不適切
    # depends_on:
    #   - config-server
    #   - discovery-server

  config-server:
    image: springcommunity/spring-petclinic-config-server
    ports:
      - "8888:8888"

  discovery-server:
    image: springcommunity/spring-petclinic-discovery-server
    ports:
      - "8761:8761"
```

**After（修正後）：**

`depends_on`を使って、Config Server、Discovery Server、API Gatewayの順に起動するように明示的に依存関係を定義します。これにより、Docker Composeは依存関係のあるサービスが起動してから次のサービスを起動します。

```yaml
# docker-compose.ymlの一部
version: '3.8'
services:
  config-server:
    image: springcommunity/spring-petclinic-config-server
    ports:
      - "8888:8888"

  discovery-server:
    image: springcommunity/spring-petclinic-discovery-server
    ports:
      - "8761:8761"
    depends_on:
      - config-server # Config Serverが起動してからDiscovery Serverを起動

  api-gateway:
    image: springcommunity/spring-petclinic-api-gateway
    ports:
      - "8080:8080"
    depends_on:
      - config-server   # Config Serverが起動してからAPI Gatewayを起動
      - discovery-server # Discovery Serverが起動してからAPI Gatewayを起動

  # 他のサービスも同様にdepends_onを設定
  customers-service:
    image: springcommunity/spring-petclinic-customers-service
    depends_on:
      - config-server
      - discovery-server
    environment:
      - SPRING_PROFILES_ACTIVE=docker
```

### 原因2：アプリケーションの初期化遅延

`depends_on`はコンテナが起動したことを保証しますが、コンテナ内のアプリケーションが完全に初期化され、リクエストを受け付けられる状態になるまで待機するわけではありません。特にSpring Bootアプリケーションは起動に時間がかかることがあり、その間に依存サービスが接続を試みると「Connection refused」などのエラーが発生します。

**Before（エラーが起きるコード）：**

`docker-compose.yml`に`depends_on`は設定されているものの、アプリケーションの準備完了を待つ仕組みがない場合。

```yaml
# docker-compose.ymlの一部
version: '3.8'
services:
  discovery-server:
    image: springcommunity/spring-petclinic-discovery-server
    ports:
      - "8761:8761"
    depends_on:
      - config-server # コンテナ起動は待つが、アプリの準備完了は待たない

  customers-service:
    image: springcommunity/spring-petclinic-customers-service
    depends_on:
      - discovery-server # コンテナ起動は待つが、アプリの準備完了は待たない
    environment:
      - SPRING_PROFILES_ACTIVE=docker
```

**After（修正後）：**

`healthcheck`や`start_period`、`retries`などの設定を組み合わせることで、アプリケーションがHTTPリクエストに応答可能になるまで待機するように設定できます。これにより、依存サービスは確実に準備ができたサービスに接続できます。

```yaml
# docker-compose.ymlの一部
version: '3.8'
services:
  config-server:
    image: springcommunity/spring-petclinic-config-server
    ports:
      - "8888:8888"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8888/actuator/health"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 30s # 起動後30秒間はヘルスチェックの失敗を許容

  discovery-server:
    image: springcommunity/spring-petclinic-discovery-server
    ports:
      - "8761:8761"
    depends_on:
      config-server:
        condition: service_healthy # config-serverがhealthyになるまで待機
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8761/actuator/health"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 30s

  api-gateway:
    image: springcommunity/spring-petclinic-api-gateway
    ports:
      - "8080:8080"
    depends_on:
      config-server:
        condition: service_healthy
      discovery-server:
        condition: service_healthy # discovery-serverがhealthyになるまで待機
    environment:
      - SPRING_PROFILES_ACTIVE=docker
```

### 原因3：ネットワーク設定の不備またはポートの競合

Docker Composeでサービスを起動する場合、デフォルトでブリッジネットワークが作成され、サービス名で相互に通信できます。しかし、外部からのアクセスが必要なポートがEC2のセキュリティグループで開かれていない、またはホストマシン上で同じポートがすでに使用されている場合、HTTPアクセスが拒否されます。

**Before（エラーが起きるコード）：**

EC2のセキュリティグループで必要なポート（例: 8080, 8761, 9090, 9091, 3030, 9411）が開かれていない、または`docker-compose.yml`でポートマッピングが正しくない場合。

```yaml
# docker-compose.ymlの一部
version: '3.8'
services:
  api-gateway:
    image: springcommunity/spring-petclinic-api-gateway
    # ポートマッピングが抜けている、または間違っている
    # ports:
    #   - "8080:8080"
```

**After（修正後）：**

1.  **EC2セキュリティグループの確認:**
    AWSコンソールでEC2インスタンスにアタッチされているセキュリティグループを確認し、必要なインバウンドポート（例: 8080, 8761, 9090, 9091, 3030, 9411）が「どこからでも (0.0.0.0/0)」または特定のIPアドレス範囲からのアクセスを許可していることを確認します。

2.  **`docker-compose.yml`のポートマッピング:**
    各サービスが外部からアクセスされるべきポートを`ports`セクションで正しくマッピングします。

```yaml
# docker-compose.ymlの一部
version: '3.8'
services:
  api-gateway:
    image: springcommunity/spring-petclinic-api-gateway
    ports:
      - "8080:8080" # ホストの8080ポートをコンテナの8080ポートにマッピング

  discovery-server:
    image: springcommunity/spring-petclinic-discovery-server
    ports:
      - "8761:8761" # ホストの8761ポートをコンテナの8761ポートにマッピング

  # Prometheus, Grafana, Zipkinなども同様にポートマッピング
  prometheus:
    image: prom/prometheus
    ports:
      - "9091:9090" # ホストの9091ポートをコンテナの9090ポートにマッピング
  grafana:
    image: grafana/grafana
    ports:
      - "3030:3000" # ホストの3030ポートをコンテナの3000ポートにマッピング
  zipkin:
    image: openzipkin/zipkin
    ports:
      - "9411:9411" # ホストの9411ポートをコンテナの9411ポートにマッピング
```

## ツール固有の注意点

*   **Docker Composeのバージョン:** `docker-compose`コマンドと`docker compose`コマンドは、それぞれDocker Compose V1とV2に対応しています。V2を使用していることを確認し、コマンドを統一してください（例: `docker compose up -d`）。
*   **EC2インスタンスのスペック:** Spring PetClinicのマイクロサービス版は、複数のサービスと監視スタック（Prometheus, Grafana, Zipkin）を含むため、メモリを多く消費します。`t2.medium`以上のインスタンスタイプを使用することを強く推奨します。メモリ不足は、サービスの起動失敗や予期せぬクラッシュにつながります。
*   **`newgrp docker`コマンド:** `sudo usermod -aG docker ubuntu`でユーザーをdockerグループに追加した後、`newgrp docker`を実行することで、ログアウトせずにグループ変更を適用できます。これにより、すぐに`sudo`なしで`docker`コマンドを実行できるようになります。

## それでも解決しない場合

1.  **コンテナログの確認:**
    `docker compose logs <service_name>`コマンドで、問題が発生している可能性のあるサービスのログを詳細に確認します。特に、起動時のエラーメッセージやスタックトレースに注目してください。

2.  **ヘルスチェックの状態確認:**
    `docker compose ps`コマンドで、各コンテナのステータス（`Up (healthy)`や`Up (unhealthy)`）を確認します。`unhealthy`なコンテナがあれば、そのサービスのログを深掘りします。

3.  **ネットワーク接続のテスト:**
    問題のあるコンテナ内でシェルに入り、`curl`や`ping`コマンドを使って、依存するサービスへのネットワーク接続をテストします。
    ```bash
    docker compose exec <your-service-name> sh
    # コンテナ内で
    curl http://config-server:8888/actuator/health
    ```

4.  **公式ドキュメントの参照:**
    Spring PetClinicの公式GitHubリポジトリや、Spring Cloudの公式ドキュメントを参照し、最新のデプロイガイドや既知の問題を確認してください。

    *   Spring PetClinic Microservices: [https://github.com/spring-petclinic/spring-petclinic-microservices](https://github.com/spring-petclinic/spring-petclinic-microservices)
    *   Docker Compose ドキュメント: [https://docs.docker.com/compose/](https://docs.docker.com/compose/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*