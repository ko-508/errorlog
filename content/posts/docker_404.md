---
title: "Docker の 404 エラー：原因と解決策"
date: 2026-01-01
description: "Docker で 404 エラーが発生するのは、指定したイメージまたはリポジトリがレジストリ（Docker Hub や ECR などのイメージ保管先）に存在しないことを意味します。"
tags: ["Docker"]
errorCode: "404"
lastmod: 2026-05-31
service: "Docker"
error_type: "404"
components: ["Registry", "Hub"]
related_services: ["Docker Compose", "AWS ECR", "Azure Container Registry"]
trend_incident: true
---
## エラーの概要

[Docker](/glossary/docker/)で404[エラー](/glossary/エラー/)が発生するのは、指定した[イメージ](/glossary/イメージ/)または[リポジトリ](/glossary/リポジトリ/)が[レジストリ](/glossary/レジストリ/)（[Docker](/glossary/docker/) Hubやエクリプスなどの[イメージ](/glossary/イメージ/)保管先）に存在しないことを意味します。この[エラー](/glossary/エラー/)は`docker pull`、`docker run`、`docker push`などの[コマンド](/glossary/コマンド/)実行時に表示され、[イメージ](/glossary/イメージ/)名の誤字、存在しないタグの指定、[アクセス権限](/glossary/アクセス権限/)の不足などが主な原因です。

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

[Docker](/glossary/docker/) Hubやエクリプスに存在する[イメージ](/glossary/イメージ/)名でも、1文字でも間違っていれば404[エラー](/glossary/エラー/)が発生します。大文字小文字の混在や、アンダースコア・ハイフンの混同が典型的です。

**Before（[エラー](/glossary/エラー/)が起きる例）：**

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

[イメージ](/glossary/イメージ/)名は正しくても、そのバージョン（タグ）が公開されていない場合があります。特に[プライベートレジストリ](/glossary/プライベートレジストリ/)やカスタムイメージで頻発します。

**Before（[エラー](/glossary/エラー/)が起きる例）：**

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

利用可能なタグを確認する[コマンド](/glossary/コマンド/)：

```bash
curl -s https://registry.hub.docker.com/v2/library/postgres/tags/list | jq .
```

### 原因3：フルネームの省略形を使用している

[Docker](/glossary/docker/) Hubの[イメージ](/glossary/イメージ/)を参照する際、[レジストリ](/glossary/レジストリ/)URLを省略した形式（`ubuntu`など）が使用できますが、[プライベートレジストリ](/glossary/プライベートレジストリ/)やアカウント配下の[リポジトリ](/glossary/リポジトリ/)では完全なURLを指定する必要があります。

**Before（[エラー](/glossary/エラー/)が起きる例）：**

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

[プライベートレジストリ](/glossary/プライベートレジストリ/)やプライベートリポジトリの場合、認証済みの状態でないと404[エラー](/glossary/エラー/)が発生することがあります。

**Before（[エラー](/glossary/エラー/)が起きる例）：**

```bash
docker pull myregistry.azurecr.io/myapp:latest
```

**After（修正後）：**

```bash
az acr login --name myregistry
docker pull myregistry.azurecr.io/myapp:latest
```

## ツール固有の注意点

### Docker Hubとの連携
[Docker](/glossary/docker/) Hubの無料アカウントで[イメージ](/glossary/イメージ/)をプッシュした場合、デフォルトではプライベートリポジトリになります。他のマシンから`docker pull`する場合は、明示的に[ログイン](/glossary/ログイン/)（`docker login`）が必要です。

```bash
docker login -u <your-username>
docker pull <your-username>/<your-repo>:<tag>
```

### AWS ECR（Amazon Elastic Container Registry）での注意
ECRではイメージリポジトリが明示的に存在する必要があります。[リポジトリ](/glossary/リポジトリ/)作成前にプッシュしようとすると404が発生します。

```bash
# Before：エラーが発生
aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.ap-northeast-1.amazonaws.com
docker push <account-id>.dkr.ecr.ap-northeast-1.amazonaws.com/myapp:latest

# After：リポジトリを先に作成
aws ecr create-repository --repository-name myapp --region ap-northeast-1
docker push <account-id>.dkr.ecr.ap-northeast-1.amazonaws.com/myapp:latest
```

### プライベートDocker Compose環境
`docker-compose.yml`でカスタムイメージを参照する場合、ビルドコンテキストが正しく指定されていないと404になります。

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
# 実際にpullできるかテスト（ドライラン）
docker pull --dry-run <image>:<tag>

# レジストリの接続状態確認
curl -I https://registry.hub.docker.com/v2/

# Dockerデーモンのデバッグログを確認
dockerd --debug 2>&1 | grep -i "404\|not found"

# ローカルにキャッシュされたイメージ一覧
docker images
```

### 公式リソース
- [Docker Registry HTTP API V2仕様](https://docs.docker.com/registry/spec/api/)
- [Docker Hubリポジトリ管理ガイド](https://docs.docker.com/docker-hub/repos/)
- [Dockerコマンドリファレンス](https://docs.docker.com/engine/reference/commandline/)

### コミュニティリソース
[Docker](/glossary/docker/)のGitHub Issues（https://github.com/moby/moby/issues）では同様の事例が多数報告されており、検索すれば解決策が見つかる可能性があります。プライベートレジストリの設定に関する問題は、該当するレジストリ（ECR、GCR、Azure Container Registryなど）の公式ドキュメントも合わせて確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*