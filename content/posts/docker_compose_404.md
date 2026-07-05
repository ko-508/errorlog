---
title: "Docker Compose の 404 エラー：原因と解決策"
date: 2026-05-31
description: "指定したイメージ・サービス・ボリュームが見つからない"
tags: ["Docker Compose"]
errorCode: "404"
service: "Docker Compose"
error_type: "404"
components: ["Compose", "Registry", "Desktop"]
related_services: ["Docker Hub"]
top_queries:
- 'error response from daemon: page not found'
---
## エラーの概要

[Docker](/glossary/docker/) Compose の 404 [エラー](/glossary/エラー/)は、`docker-compose.yml`（または `compose.yml`）で指定された[イメージ](/glossary/イメージ/)、サービス、ボリューム、または[ネットワーク](/glossary/ネットワーク/)がシステムに見つからないときに発生します。この[エラー](/glossary/エラー/)は、[イメージ](/glossary/イメージ/)のプル失敗、ビルドコンテキストの誤設定、または依存リソースの不足が原因となることがほとんどです。[Docker](/glossary/docker/) Compose がコンテナーの起動や構築を試みた際に、参照先が存在しないことを検出すると、この[エラー](/glossary/エラー/)を出力して処理を中断します。

## 実際のエラーメッセージ例

```
Error response from daemon: pull access denied for <your-image-name>, repository does not exist or may require 'docker login'
```

または、より明確な 404 表現として：

```json
{
  "message": "manifest not found",
  "status": 404
}
```

ローカルでのビルド失敗時：

```
ERROR: Service '<your-service-name>' failed to build : [Errno 2] No such file or directory: '<your-build-context-path>'
```

## よくある原因と解決手順

### 原因1：compose.yml 内で指定したイメージが存在しない、またはタグが間違っている

[Docker](/glossary/docker/) Compose が[レジストリ](/glossary/レジストリ/)（[Docker](/glossary/docker/) Hub やプライベートレジストリー）から[イメージ](/glossary/イメージ/)をプルしようとしても、その[イメージ](/glossary/イメージ/)が存在しない、あるいは[タグ](/glossary/タグ/)が誤っていると 404 [エラー](/glossary/エラー/)が発生します。たとえば、タイポや[バージョン](/glossary/バージョン/)番号の誤指定があると、プル対象が見つからなくなります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:lattest  # タイポ: lattest → latest
    ports:
      - "80:80"
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:latest  # 正しいタグ名に修正
    ports:
      - "80:80"
```

### 原因2：build コンテキストのパスが存在しない、または間違っている

`build` キーでコンテキストパスを指定する際、相対[パス](/glossary/パス/)が誤っていたり、ディレクトリが削除されていたりすると、[Docker](/glossary/docker/) Compose は[イメージ](/glossary/イメージ/)をビルドできず 404 [エラー](/glossary/エラー/)を出力します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    build:
      context: ./srcs  # このパスが実際には存在しない
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  app:
    build:
      context: ./src  # 実際に存在するパスに修正
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
```

### 原因3：依存するボリューム、ネットワーク、サービスがあらかじめ作成されていない

compose ファイルで外部ボリューム（`external: true`）または外部[ネットワーク](/glossary/ネットワーク/)を参照しているが、それらが [Docker](/glossary/docker/) ホスト上に先に作成されていない場合、サービス起動時に 404 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  db:
    image: postgres:13
    volumes:
      - shared_data:/var/lib/postgresql/data
volumes:
  shared_data:
    external: true  # 外部ボリュームを参照
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  db:
    image: postgres:13
    volumes:
      - shared_data:/var/lib/postgresql/data
volumes:
  shared_data:
    external: false  # ローカルで自動作成、またはあらかじめ作成済み
```

あるいは事前に以下の[コマンド](/glossary/コマンド/)でボリュームを作成します：

```bash
docker volume create shared_data
```

## ツール固有の注意点

[Docker](/glossary/docker/) Compose 環境では、[イメージ](/glossary/イメージ/)のプル時にレジストリー[認証](/glossary/認証/)が必要な場合があります。プライベートレジストリーから[イメージ](/glossary/イメージ/)をプルする際は、`docker login` でレジストリーに[認証](/glossary/認証/)してから `docker compose up` を実行してください。また、compose ファイルの `image` フィールドに完全修飾[イメージ](/glossary/イメージ/)名（FQDN 形式）を指定する必要があります。

さらに、`docker compose build` でローカルイメージをビルドする場合は、Dockerfile が `context` で指定されたディレクトリ内に存在することを確認してください。Dockerfile が見つからない場合、[Docker](/glossary/docker/) Compose は 404 相当の[エラー](/glossary/エラー/)を出力します。複数のサービスが存在する場合、各サービスの `build.context` [パス](/glossary/パス/)を個別にチェックすることも重要です。

[環境変数](/glossary/環境変数/)を `.env` ファイルで注入している場合、そのファイルが compose ファイルと同じディレクトリに存在し、[変数](/glossary/変数/)の評価が正しく行われているか確認することも忘れずに。

## それでも解決しない場合

以下の手順で詳細を確認してください。

**ローカルイメージの確認：**

```bash
docker images
```

この[コマンド](/glossary/コマンド/)で、使用しようとしている[イメージ](/glossary/イメージ/)がローカルに存在するかどうかをリスト表示します。存在しない場合は、[イメージ](/glossary/イメージ/)名または[タグ](/glossary/タグ/)を修正するか、`docker compose up --build` で再度ビルドしてください。

**ビルドコンテキストの[パス](/glossary/パス/)確認：**

```bash
ls -la <your-build-context-path>
```

compose.yml で指定した[パス](/glossary/パス/)が実際に存在し、Dockerfile が含まれているか確認します。

**詳細なビルドログの確認：**

```bash
docker compose up --build --verbose
```

`--verbose` フラグを付けることで、より詳細なビルドログが表示され、[エラー](/glossary/エラー/)の正確な位置を特定しやすくなります。

**レジストリー[認証](/glossary/認証/)の確認（プライベートレジストリーの場合）：**

```bash
docker login <your-registry-url>
docker compose pull
```

プライベートレジストリーを使用している場合は、事前に[ログイン](/glossary/ログイン/)してからプルを試みてください。

詳細は [Docker Compose 公式ドキュメント](https://docs.docker.com/compose/) および [Docker イメージガイド](https://docs.docker.com/engine/images/) を参照してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*