---
title: "Docker の 404 エラー：原因と解決策"
date: 2026-01-01
description: "Docker で 404 エラーが発生するのは、指定したイメージまたはリポジトリがレジストリ（Docker Hub や ECR などのイメージ保管先）に存在しないことを意味します。"
tags: ["Docker"]
errorCode: "404"
lastmod: 2026-05-29
---

## エラーの概要

[Docker](/glossary/docker/) で 404 エラーが発生するのは、指定したイメージまたは[リポジトリ](/glossary/リポジトリ/)が[レジストリ](/glossary/レジストリ/)（[Docker](/glossary/docker/) Hub や ECR などのイメージ保管先）に存在しないことを意味します。このエラーは `docker pull`、`docker run`、`docker push` などのコマンド実行時に表示され、イメージ名の誤字、存在しないタグの指定、アクセス権限の不足などが主な原因です。

## 実際のエラーメッセージ例

```bash
$ docker pull myapp:latest
Error response from daemon: manifest not found: myapp:latest
```

```json
{
  "errors": [
    {
      "code": "NAME_UNKNOWN",
      "message": "repository myapp not found",
      "detail": {}
    }
  ]
}
```

## よくある原因と解決手順

### 原因1：イメージ名またはタグの誤字

[Docker](/glossary/docker/) Hub や ECR に存在するイメージ名でも、1文字でも間違っていれば 404 エラーが発生します。大文字小文字の混在や、アンダースコア・ハイフンの混同が典型的です。

**Before（エラーが起きる例）：**

```bash
docker pull ubuntu:Latest
docker pull myapp:1.0.0_beta
docker run node:16-alphine node app.js
```

**After（修正後）：**

```bash
docker pull ubuntu:latest
docker pull myapp:1.0.0-beta
docker run node:16-alpine node app.js
```

### 原因2：指定したタグがレジストリに存在しない

イメージ名は正しくても、そのバージョン（タグ）が公開されていない場合があります。特に[プライベートレジストリ](/glossary/プライベートレジストリ/)やカスタムイメージで頻発します。

**Before（エラーが起きる例）：**

```bash
docker pull postgres:13.5
docker pull mycompany/api:feature-branch
```

**After（修正後）：**

```bash
# 利用可能なタグを確認してから実行
docker pull postgres:13
docker pull mycompany/api:v1.2.0
```

利用可能なタグを確認するコマンド：

```bash
curl -s https://registry.hub.docker.com/v2/library/postgres/tags/list | jq .
```

### 原因3：フルネームの省略形を使用している

[Docker](/glossary/docker/) Hub のイメージを参照する際、[レジストリ](/glossary/レジストリ/) URL を省略した形式（`ubuntu` など）が使用できますが、[プライベートレジストリ](/glossary/プライベートレジストリ/)やアカウント配下の[リポジトリ](/glossary/リポジトリ/)では完全な URL を指定する必要があります。

**Before（エラーが起きる例）：**

```bash
docker pull myapp
docker run mycompany/backend:latest
```

**After（修正後）：**

```bash
docker pull docker.io/library/myapp:latest
docker pull <your-registry-url>/mycompany/backend:latest
```

### 原因4：レジストリにログインしていない

[プライベートレジストリ](/glossary/プライベートレジストリ/)やプライベートリポジトリの場合、認証済みの状態でないと 404 エラーが発生することがあります。

**Before（エラーが起きる例）：**

```bash
docker pull myregistry.azurecr.io/myapp:latest
```

**After（修正後）：**

```bash
az acr login --name myregistry
docker pull myregistry.azurecr.io/myapp:latest
```

## ツール固有の注意点

### Docker Hub との連携
[Docker](/glossary/docker/) Hub の無料アカウントでイメージをプッシュした場合、デフォルトではプライベートリポジトリになります。他のマシンから `docker pull` する場合は、明示的にログイン（`docker login`）が必要です。

```bash
docker login -u <your-username>
docker pull <your-username>/<your-repo>:<tag>
```

### AWS ECR（Amazon Elastic Container Registry）での注意
ECR ではイメージリポジトリが明示的に存在する必要があります。[リポジトリ](/glossary/リポジトリ/)作成前にプッシュしようとすると 404 が発生します。

```bash
# Before：エラーが発生
aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.ap-northeast-1.amazonaws.com
docker push <account-id>.dkr.ecr.ap-northeast-1.amazonaws.com/myapp:latest

# After：リポジトリを先に作成
aws ecr create-repository --repository-name myapp --region ap-northeast-1
docker push <account-id>.dkr.ecr.ap-northeast-1.amazonaws.com/myapp:latest
```

### プライベート Docker Compose 環境
`docker-compose.yml` でカスタムイメージを参照する場合、ビルドコンテキストが正しく指定されていないと 404 になります。

```yaml
# Before：存在しないイメージを参照
services:
  web:
    image: myapp:latest

# After：ローカルでビルドするか、正しいレジストリを指定
services:
  web:
    build: ./web
    image: myregistry.io/myapp:latest
```

## それでも解決しない場合

### デバッグに役立つコマンド
```bash
# 実際に pull できるかテスト（ドライラン）
docker pull --dry-run <image>:<tag>

# レジストリの接続状態確認
curl -I https://registry.hub.docker.com/v2/

# Docker デーモンのデバッグログを確認
dockerd --debug 2>&1 | grep -i "404\|not found"

# ローカルにキャッシュされたイメージ一覧
docker images
```

### 公式リソース
- [Docker Registry HTTP API V2 仕様](https://docs.docker.com/registry/spec/api/)
- [Docker Hub リポジトリ管理ガイド](https://docs.docker.com/docker-hub/repos/)
- [Docker コマンドリファレンス](https://docs.docker.com/engine/reference/commandline/)

### コミュニティリソース
[Docker](/glossary/docker/) の GitHub Issues（https://github.com/moby/moby/issues）では同様の事例が多数報告されており、検索すれば解決策が見つかる可能性があります。プライベートレジストリの設定に関する問題は、該当するレジストリ（ECR、GCR、Azure Container Registry など）の公式ドキュメントも合わせて確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*