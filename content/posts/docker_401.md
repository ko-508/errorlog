---
title: "Docker の 401 エラー：原因と解決策"
date: 2026-01-01
description: "Docker で 401 エラーが発生するのは、レジストリ（Docker Hub や ECR、プライベートレジストリなど）への認証に失敗したときです。認証情報が提供されていない、または提供されていても無効・期限切れの場合に表示されます。"
tags: ["Docker"]
errorCode: "401"
lastmod: 2026-05-31
---
## エラーの概要

[Docker](/glossary/docker/)で 401 エラーが発生するのは、[レジストリ](/glossary/レジストリ/)（Docker Hub や ECR、[プライベートレジストリ](/glossary/プライベートレジストリ/)など）への認証に失敗したときです。認証情報が提供されていない、または提供されていても無効・期限切れの場合に表示されます。特に `docker pull`、`docker push`、`docker login` の実行時によく見られます。

## 実際のエラーメッセージ例

```
Error response from daemon: unauthorized: incorrect username or password
```

```json
{
  "errors": [
    {
      "code": "UNAUTHORIZED",
      "message": "authentication required",
      "detail": null
    }
  ]
}
```

```
Error response from daemon: Get "https://registry-1.docker.io/v2/": unauthorized: authentication required
```

## よくある原因と解決手順

### 原因1: docker login コマンドを実行していない

Docker Hub や[プライベートレジストリ](/glossary/プライベートレジストリ/)を利用する際に、事前に `docker login` で認証を済ませていないと 401 エラーが発生します。

**Before（エラーが起きる状態）**
```bash
docker pull my-private-repo.azurecr.io/myapp:latest
# Error response from daemon: unauthorized
```

**After（修正後）**
```bash
# Azure Container Registry の場合
docker login my-private-repo.azurecr.io -u <username> -p <password>

# Docker Hub の場合
docker login -u <your-docker-username> -p <your-token>

# その後、pull/push が成功する
docker pull my-private-repo.azurecr.io/myapp:latest
```

### 原因2: 認証トークンの有効期限切れまたは無効なトークン

アクセストークン（Personal Access Token）が期限切れになった、または削除されると 401 エラーが起きます。Docker Hub やクラウドレジストリで新しいトークンを生成する必要があります。

**Before（エラーが起きる状態）**
```bash
# 古いトークンまたは期限切れトークンで認証
docker login -u myuser -p dckr_pat_old_expired_token_abc123
docker push myrepo/myimage:latest
# Error response from daemon: unauthorized: authentication required
```

**After（修正後）**
```bash
# Docker Hub から新しい Personal Access Token を取得
# 1. hub.docker.com にログイン
# 2. Account Settings > Security > New Access Token を生成
# 3. Token scope で適切な権限を選択（Read, Write, Delete）

docker login -u myuser -p dckr_pat_new_valid_token_xyz789
docker push myrepo/myimage:latest
# Success
```

### 原因3: 認証情報の保存形式が誤っている

`~/.docker/config.json` が破損しているか、base64 エンコードの形式が不正な場合、認証が失敗します。

**Before（エラーが起きる状態）**
```bash
# config.json が破損している場合
cat ~/.docker/config.json
# {
#   "auths": {
#     "registry.example.com": {
#       "auth": "invalid_base64_string_=="
#     }
#   }
# }

docker pull registry.example.com/myapp:latest
# Error response from daemon: unauthorized
```

**After（修正後）**
```bash
# config.json をリセットして再度ログイン
rm ~/.docker/config.json
docker login registry.example.com -u <your-username> -p <your-password>

# 正しい形式で保存される
cat ~/.docker/config.json
# {
#   "auths": {
#     "registry.example.com": {
#       "auth": "dXNlcm5hbWU6cGFzc3dvcmQ="
#     }
#   }
# }

docker pull registry.example.com/myapp:latest
```

### 原因4: レジストリのホスト名が誤っている

[プライベートレジストリ](/glossary/プライベートレジストリ/)へアクセスする際、ホスト名やレジストリアドレスが誤っていると認証情報が使われず 401 エラーになります。

**Before（エラーが起きる状態）**
```bash
# 誤ったホスト名で push しようとする
docker login myregistry.azurecr.io
docker push myregistry.azurecr.io/myapp:latest

# 別のマシンで、設定したホスト名と異なるアドレスでアクセス
docker pull wrong-registry-name.azurecr.io/myapp:latest
# Error response from daemon: unauthorized
```

**After（修正後）**
```bash
# ホスト名を統一する
docker login myregistry.azurecr.io -u <username> -p <password>
docker tag myapp:latest myregistry.azurecr.io/myapp:latest
docker push myregistry.azurecr.io/myapp:latest
```

## Docker 固有の注意点

### Docker Hub の場合

Docker Hub で 401 が出るときは、Personal Access Token（PAT）を使う必要があります。パスワード直接認証は推奨されていません。

```bash
# 正しい方法：PAT を使用
docker login -u <your-username> -p <your-pat-token>

# エラーが出る方法：パスワード直接使用（廃止予定）
docker login -u <your-username> -p <your-password>
```

### Azure Container Registry (ACR) の場合

ACR では管理者アカウントか Service Principal による認証が必要です。

```bash
# 管理者アカウント有効化
az acr update -n <your-acr-name> --admin-enabled true

# 認証情報取得
az acr credential show -n <your-acr-name>

# ログイン
docker login <your-acr-name>.azurecr.io -u <username> -p <password>
```

### AWS Elastic Container Registry (ECR) の場合

ECR はトークンが短命（12 時間）なため、定期的に更新が必要です。

```bash
# トークンを取得してログイン
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

# または aws-cli v1 の場合
$(aws ecr get-login --no-include-email --region <region>)
```

## それでも解決しない場合

### デバッグコマンド

```bash
# Docker のデバッグモードで実行
DOCKER_CONTENT_TRUST=1 docker pull <image> 2>&1 | head -50

# 認証情報が正しく保存されているか確認
docker config view --pretty

# ログをより詳しく出力
docker pull --verbose <image>

# レジストリへの接続確認
curl -v https://<registry-host>/v2/ -u <username>:<password>
```

### 確認すべきポイント

- `~/.docker/config.json` の認証情報が正しく保存されているか
- `docker logout` してから再度 `docker login` する
- ファイアウォールやプロキシ設定でレジストリへのアクセスがブロックされていないか
- IP アドレス制限が[レジストリ](/glossary/レジストリ/)に設定されていないか
- レジストリサーバーが実際にオンラインか（ステータスページで確認）

### 公式ドキュメント・リソース

- [Docker 公式：Authenticate with Docker Hub](https://docs.docker.com/engine/reference/commandline/login/)
- [Docker 公式：Configure authentication for Docker Daemon](https://docs.docker.com/engine/security/authenticate/)
- [Azure Container Registry：Authenticate with ACR](https://learn.microsoft.com/ja-jp/azure/container-registry/container-registry-authentication)
- [AWS ECR：Private registry authentication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registries.html)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*