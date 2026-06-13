---
title: "Docker の 401 エラー：原因と解決策"
date: 2026-01-01
description: "Docker で 401 エラーが発生するのは、レジストリ（Docker Hub や ECR、プライベートレジストリなど）への認証に失敗したときです。認証情報が提供されていない、または提供されていても無効・期限切れの場合に表示されます。"
tags: ["Docker"]
errorCode: "401"
lastmod: 2026-06-13
service: "Docker"
error_type: "401"
components: ["Registry"]
related_services: ["Docker Hub", "Azure Container Registry", "ECR"]
trend_incident: true
---

## エラーの概要

Dockerで401エラーが発生するのは、レジストリ（Docker Hub、ECR、プライベートレジストリなど）への認証に失敗したときです。認証情報が提供されていない、または提供されていても無効・期限切れの場合に表示されます。特に `docker pull`、`docker push`、`docker login` の実行時によく見られます。

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
Error response from daemon: Get "https://registry-1.docker.io/v2/": unauthorized: authentication required, 401
```

## よくある原因と解決手順

### 原因1：Docker Hubへのログインが完了していない

Docker Hubのパブリックイメージであっても、ダウンロード数制限により認証が必須になるケースがあります。また、プライベートイメージにアクセスする場合は必ず認証が必要です。

**Before（エラーが起きるコード）：**

```bash
# ログインなしで直接pullを実行
docker pull <username>/<image-name>:latest
```

**After（修正後）：**

```bash
# 最初にDocker Hubにログイン
docker login

# プロンプトにユーザー名とパスワード（またはPersonal Access Token）を入力
# その後でpullを実行
docker pull <username>/<image-name>:latest
```

### 原因2：AWS ECRの認証トークンが期限切れ

ECRの認証トークンは12時間の有効期限があります。Docker daemonに保存されたトークンが期限切れになると401エラーが発生します。

**Before（エラーが起きるコード）：**

```bash
# 古いトークンで直接pullを試行
docker pull <account-id>.dkr.ecr.<region>.amazonaws.com/<repository>:<tag>
```

**After（修正後）：**

```bash
# AWS CLIで認証トークンを再取得し、Docker daemonに設定
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

# その後でpullを実行
docker pull <account-id>.dkr.ecr.<region>.amazonaws.com/<repository>:<tag>
```

### 原因3：設定ファイル（config.json）の認証情報が破損または形式が不正

`~/.docker/config.json` に保存された認証情報が破損しているか、レジストリのホスト名が正確に記録されていない場合に発生します。

**Before（エラーが起きるコード）：**

```json
{
  "auths": {
    "docker.io": {
      "auth": "invalid_base64_or_corrupted_data"
    }
  }
}
```

**After（修正後）：**

```bash
# 既存の認証情報をクリア
rm ~/.docker/config.json

# 新規ログインで正しい認証情報を再設定
docker login
```

### 原因4：プライベートレジストリのための認証情報が不足

Nexus、Harbor、GitLab Container Registry など自社運用のプライベートレジストリにアクセスする際、ホスト名とポート番号を含めた完全なレジストリURLで認証を設定する必要があります。

**Before（エラーが起きるコード）：**

```bash
# プライベートレジストリにログインせず、イメージをpull
docker pull registry.internal.example.com:5000/my-image:v1.0
```

**After（修正後）：**

```bash
# 完全なレジストリURLでログイン
docker login registry.internal.example.com:5000

# ユーザー名・パスワード・パスフレーズを入力
docker pull registry.internal.example.com:5000/my-image:v1.0
```

### 原因5：Personal Access Token（PAT）の権限不足またはスコープ制限

Docker Hubでパスワード代わりにPATを使用している場合、そのトークンに必要な権限（Read、Write など）が付与されていないと401エラーになります。

**Before（エラーが起きるコード）：**

```bash
# Read権限のみのPATで push を試行
docker login --username <username>
# パスワード入力欄に読み取り専用のPATを入力
docker push <username>/<image>:latest
```

**After（修正後）：**

```bash
# Docker Hub > Account Settings > Security > Personal Access Tokens で
# 「Read, Write」の権限を持つ新しいPATを生成

docker login --username <username>
# パスワード入力欄に新しいPATを入力
docker push <username>/<image>:latest
```

## ツール固有の注意点

### Docker Compose での認証設定

`docker-compose.yml` で複数のレジストリからイメージをpullする場合、各レジストリへの事前ログインが必要です。Compose ファイル内に認証情報を直接記述することはセキュリティ上推奨されません。

```bash
# docker-compose.yml 実行前に全レジストリにログイン
docker login docker.io
docker login <account-id>.dkr.ecr.<region>.amazonaws.com
docker login registry.internal.example.com:5000

# その後で compose up を実行
docker-compose up
```

### Docker buildx でのマルチアーキテクチャビルド

`docker buildx` でリモートレジストリにpushする場合、`--push` フラグを使用する前に対象レジストリへのログインを完了させます。

```bash
# ECRの場合
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker buildx build --push -t <account-id>.dkr.ecr.<region>.amazonaws.com/<repo>:latest .
```

### Kubernetes での imagePullSecrets

Kubernetes上でプライベートレジストリのイメージを使用する場合、`imagePullSecrets` で認証情報を参照する必要があります。この設定がないと、Podの起動時に401エラーが発生します。

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  imagePullSecrets:
  - name: regcred
  containers:
  - name: my-container
    image: registry.internal.example.com:5000/my-image:v1.0
```

認証情報は事前に Secret リソースとして作成します。

```bash
kubectl create secret docker-registry regcred \
  --docker-server=registry.internal.example.com:5000 \
  --docker-username=<username> \
  --docker-password=<password> \
  --docker-email=<email>
```

## それでも解決しない場合

### デバッグ方法

Docker daemon のデバッグログを有効にして、認証リクエストの詳細を確認します。

```bash
# Docker daemon を デバッグモードで再起動（Linux/macOS）
dockerd --debug

# または Windows の場合は Docker Desktop 設定から Debug モードを有効化
```

認証情報の保存状況をホスト側で確認します。

```bash
# config.json の存在確認（値は出力しない）
test -f ~/.docker/config.json && echo "config.json exists" || echo "config.json not found"

# ファイルパーミッションの確認
ls -l ~/.docker/config.json
```

### 公式ドキュメント

- [Docker Documentation - Authentication](https://docs.docker.com/engine/reference/commandline/login/)
- [AWS ECR - Private registry authentication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html)
- [Docker Hub - Personal Access Tokens](https://docs.docker.com/docker-hub/access-tokens/)

### コミュニティリソース

- GitHub Issues: [moby/moby](https://github.com/moby/moby/issues) で「401」を検索
- Docker Community Forums: https://forums.docker.com/

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*