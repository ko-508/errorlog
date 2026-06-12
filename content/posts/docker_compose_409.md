---
title: "Docker Compose の 409 エラー：原因と解決策"
date: 2026-05-31
description: "サービスの状態がリクエストと競合している。Docker Compose 409 エラーの原因と解決策を解説します。"
tags: ["Docker Compose"]
errorCode: "409"
service: "Docker Compose"
error_type: "409"
components: ["Compose"]
related_services: ["Docker", "nginx"]
---
## エラーの概要

[Docker](/glossary/docker/) Compose の 409 [エラー](/glossary/エラー/)は、[リクエスト](/glossary/リクエスト/)されたコンテナーや[ネットワーク](/glossary/ネットワーク/)、ボリュームの状態が現在の環境状態と競合していることを示します。この[エラー](/glossary/エラー/)は通常、既に存在するリソースの作成を試みたり、使用中の[ポート](/glossary/ポート/)・[ネットワーク](/glossary/ネットワーク/)を重複させたりした場合に発生します。既存の状態を認識しないまま操作を進めようとすると、[Docker](/glossary/docker/) Compose がこの競合を検出して実行を中止します。

## 実際のエラーメッセージ例

**パターン1：コンテナー名の競合**

```json
Error response from daemon: Conflict. The container name "<container-name>" is already in use by container "<existing-container-id>". You have to remove (or rename) that container to be able to reuse that name.
```

**パターン2：[ポート](/glossary/ポート/)番号の競合**

```bash
ERROR: for <service-name>  Cannot start service <service-name>: driver failed programming external connectivity on endpoint <endpoint-name>: Bind for 0.0.0.0:<port> failed: port is already allocated
```

**パターン3：[ネットワーク](/glossary/ネットワーク/)またはボリュームの競合**

```json
Error response from daemon: network with name <network-name> already exists
```

## よくある原因と解決手順

### 原因1：同じ名前のコンテナーがすでに起動または停止状態で残っている

[Docker](/glossary/docker/) Compose は `docker-compose.yml` で定義したサービス名とプロジェクト名の組み合わせでコンテナー名を生成します。以前に作成したコンテナーが停止状態で残っていたり、同じ構成を再度実行しようとしたりすると、同じ名前のコンテナーが存在することになり、409 [エラー](/glossary/エラー/)が発生します。

**修正方法：**

```bash
# 既存のコンテナーと関連リソースを完全に削除
docker compose down -v

# その後、新たに起動
docker compose up -d
```

`-v` フラグでボリュームも削除されるため、データの永続化が必要な場合は事前にバックアップを取得してください。

### 原因2：同じポートを複数のサービスが使おうとしている

`docker-compose.yml` で複数のサービスが同じホストポートをバインドしようとしている場合、またはホストシステムの別のプロセスがすでにその[ポート](/glossary/ポート/)を使用している場合に 409 [エラー](/glossary/エラー/)が発生します。

**修正方法：**

```yaml
version: '3.8'
services:
  web1:
    image: nginx:latest
    ports:
      - "8080:80"
  
  web2:
    image: nginx:latest
    ports:
      - "8081:80"
```

各サービスに異なるホストポートを割り当てることで競合を解決します。既に[ポート](/glossary/ポート/)が使用されている場合は、以下の[コマンド](/glossary/コマンド/)でホストマシン上の使用中[ポート](/glossary/ポート/)を確認できます。

```bash
# Linux の場合
sudo netstat -tulpn | grep <port-number>

# macOS の場合
lsof -i :<port-number>

# Windows の場合
netstat -ano | findstr :<port-number>
```

### 原因3：同名のネットワークまたはボリュームがすでに存在する

`docker-compose.yml` で定義したカスタムネットワークやボリュームが、すでに [Docker](/glossary/docker/) 環境に存在する場合、409 [エラー](/glossary/エラー/)が発生します。特に複数のプロジェクトで同じ命名規則を使用している場合に起こりやすい[エラー](/glossary/エラー/)です。

**既存リソースの削除：**

```bash
# 既存のネットワークとボリュームを確認して削除
docker network ls
docker network rm <existing-network-name>

docker volume ls
docker volume rm <existing-volume-name>
```

**既存リソースを再利用する場合の設定：**

```yaml
version: '3.8'
services:
  app:
    image: python:3.11
    networks:
      - app-network
    volumes:
      - app-data:/app/data

networks:
  app-network:
    external: true

volumes:
  app-data:
    external: true
```

## ツール固有の注意点

### プロジェクト名による自動接頭辞

[Docker](/glossary/docker/) Compose は、リソース作成時にプロジェクト名を自動的に接頭辞として付与します。デフォルトではディレクトリ名がプロジェクト名として使用されるため、同じ `docker-compose.yml` を異なるディレクトリにコピーして実行すると、リソース名が異なるものになります。複数環境で同じプロジェクト名を使用する場合は、`-p` オプションで明示的に指定します。

```bash
# プロジェクト名を明示的に指定
docker compose -p <project-name> up -d
```

### down コマンドのオプション使い分け

`docker compose down` を実行する際、オプションの選択が重要です。

- `docker compose down`：コンテナーと[ネットワーク](/glossary/ネットワーク/)を削除（ボリュームは保持）
- `docker compose down -v`：コンテナー、[ネットワーク](/glossary/ネットワーク/)、ボリュームをすべて削除
- `docker compose down --remove-orphans`：定義されていないコンテナーも削除

### Docker Desktop での特殊な注意

Windows または macOS の [Docker](/glossary/docker/) Desktop 環境では、ホストマシンのリソースが仮想マシン上の Linux にマッピングされます。[ポート](/glossary/ポート/)競合の問題が解決しない場合、[Docker](/glossary/docker/) Desktop のリソース割り当てやポートフォワード設定を確認してください。

## それでも解決しない場合

### ログの確認

```bash
# 詳細なログを表示
docker compose logs

# 特定サービスのログを確認
docker compose logs <service-name>

# デバッグモードで実行
docker compose -v up -d
```

### 環境全体のリセット

強制的に環境をリセットする必要がある場合は以下の手順を実行します。

```bash
# 実行中のすべてのコンテナーを停止
docker compose kill

# すべてのコンテナー、ネットワーク、ボリュームを削除
docker compose down -v --remove-orphans

# Docker 全体をクリーニング（上級者向け）
docker system prune -a --volumes
```

### 公式ドキュメントの確認

[Docker](/glossary/docker/) Compose の公式ドキュメント（https://docs.docker.com/compose/）では、詳細な設定オプションと各エラーの詳説が提供されています。また、`docker compose config` [コマンド](/glossary/コマンド/)で現在の設定を検証できます。

```bash
# compose.yml の構文チェック
docker compose config
```

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*