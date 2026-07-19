---
title: "Docker の 403 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 403 エラーは、認証（ログイン）には成功したものの、対象のリソース（イメージ、レジストリ、ボリューム等）へのアクセス権限がないことを示します。"
tags: ["Docker"]
errorCode: "403"
lastmod: 2026-05-31
service: "Docker"
error_type: "403"
components: ["Registry", "Desktop"]
related_services: ["Docker Hub", "Kubernetes", "Azure Container Registry"]
trend_incident: true
top_queries:
- 'docker pull 403'
- 'docker hub 403 forbidden alternative registry php 8.2-apache mirror 2024'
- 'docker hub 403 forbidden alternative registry python 3.11-slim mirror 2024'
---
# エラーの概要

[Docker](/glossary/docker/) の 403 [エラー](/glossary/エラー/)は、[認証](/glossary/認証/)（[ログイン](/glossary/ログイン/)）には成功したものの、対象のリソース（[イメージ](/glossary/イメージ/)、[レジストリ](/glossary/レジストリ/)、ボリューム等）への[アクセス権限](/glossary/アクセス権限/)がないことを示します。これはプライベートリポジトリへのアクセス、組織内のアクセス制限、または不十分な[認証](/glossary/認証/)[トークン](/glossary/トークン/)の[権限](/glossary/権限/)が原因で発生することがほとんどです。[Docker](/glossary/docker/) [CLI](/glossary/cli/)、[Docker](/glossary/docker/) Desktop、または docker push/pull 時に頻繁に遭遇する[エラー](/glossary/エラー/)です。

## 実際のエラーメッセージ例

```
Error response from daemon: Head "https://registry-1.docker.io/v2/myuser/myimage/manifests/latest": 
unauthorized: authentication required
403 Forbidden
```

```json
{
  "errors": [
    {
      "code": "DENIED",
      "message": "permission denied",
      "detail": "requested access to the resource is denied"
    }
  ]
}
```

```
docker push myrepo/myimage:tag
denied: requested access to the resource is denied
```

## よくある原因と解決手順

### 原因1：Docker Hub のログイン認証が無効または権限不足

なぜ発生するか：[Docker](/glossary/docker/) [CLI](/glossary/cli/) が[ログイン](/glossary/ログイン/)していない状態、または無効な[トークン](/glossary/トークン/)で[リポジトリ](/glossary/リポジトリ/)にアクセスしようとすると、403 [エラー](/glossary/エラー/)が返されます。特にプライベートリポジトリの場合、[認証](/glossary/認証/)なしでのアクセスが拒否されます。

**Before（[エラー](/glossary/エラー/)が起きる[コマンド](/glossary/コマンド/)）**

```bash
# ログインせずにプライベートリポジトリをプルしようとする
docker pull myusername/private-image:latest

# または古い認証情報で実行
docker push myrepo/myimage:tag
```

**After（修正後の[コマンド](/glossary/コマンド/)）**

```bash
# Docker Hub にログイン
docker login

# プロンプトで以下を入力：
# Username: <your-username>
# Password: <your-password-or-access-token>

# その後にプルまたはプッシュを実行
docker pull myusername/private-image:latest
docker push myrepo/myimage:tag
```

認証情報が有効か確認する方法：

```bash
# ログイン状態を確認
cat ~/.docker/config.json | jq '.auths'

# 認証トークンをリフレッシュ
docker logout
docker login
```

### 原因2：リポジトリの所有者または権限設定が不一致

なぜ発生するか：[Docker](/glossary/docker/) Hub で[リポジトリ](/glossary/リポジトリ/)を作成した時点の所有者と異なる[アカウント](/glossary/アカウント/)、または組織に属さないユーザーがアクセスしようとすると、権限不足で 403 が返されます。

**Before（[エラー](/glossary/エラー/)が起きる状況）**

```bash
# ユーザーAが作成した org/repo にユーザーBがログインしてアクセス
docker login  # ユーザーB としてログイン
docker push org/repo:v1.0
# Error: denied: requested access to the resource is denied
```

**After（修正後の対応）**

[リポジトリ](/glossary/リポジトリ/)の所有者が [Docker](/glossary/docker/) Hub Web UI で[アクセス権限](/glossary/アクセス権限/)を明示的に付与する必要があります：

```
Docker Hub Web UI > Repository > Settings > Collaborators
→ ユーザーB を追加し、"Write" 権限を付与
```

その後、ユーザーB は以下を実行：

```bash
docker logout
docker login  # ユーザーB で再度ログイン
docker push org/repo:v1.0
```

### 原因3：プライベートレジストリの認証情報が Kubernetes に未登録

なぜ発生するか：[Docker](/glossary/docker/) [コンテナ](/glossary/コンテナ/)を [Kubernetes](/glossary/kubernetes/) クラスタで実行する際、[プライベートレジストリ](/glossary/プライベートレジストリ/)の認証情報が ImagePullSecret として登録されていないため、kubelet が[イメージ](/glossary/イメージ/)取得時に 403 [エラー](/glossary/エラー/)を受け取ります。

**Before（[エラー](/glossary/エラー/)が起きる設定）**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-app
spec:
  containers:
  - name: app
    image: myregistry.azurecr.io/myimage:latest
  # imagePullSecrets が指定されていない → 403 エラー
```

**After（修正後の設定）**

```bash
# まずシークレットを作成
kubectl create secret docker-registry myregistrysecret \
  --docker-server=myregistry.azurecr.io \
  --docker-username=<your-username> \
  --docker-password=<your-password> \
  --docker-email=<your-email>
```

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-app
spec:
  containers:
  - name: app
    image: myregistry.azurecr.io/myimage:latest
  imagePullSecrets:
  - name: myregistrysecret  # ← シークレット参照を追加
```

## Docker 固有の注意点

### Docker Desktop での認証の永続化

[Docker](/glossary/docker/) Desktop（Mac/Windows）では、`~/.docker/config.json` に認証情報が保存されますが、Credential Helper を使用している場合、[トークン](/glossary/トークン/)の有効期限切れが原因で 403 が発生することがあります。その場合は以下を実行：

```bash
# Credential Helper を経由してキャッシュを削除
docker logout
docker login --username <your-username>
```

### Docker Compose と認証

[Docker](/glossary/docker/) Compose でプライベートイメージを使用する場合、以下のように .env [ファイル](/glossary/ファイル/)または docker-compose.yml で[認証](/glossary/認証/)を明示的に指定できます：

```yaml
version: '3.9'
services:
  myapp:
    image: myregistry.example.com/myimage:latest
    # Compose は docker login の認証情報を自動的に使用するため、
    # 別途設定は不要だが、CI/CD環境では明示的に login が必要
```

### Docker Registry API での 403

自身が構築したプライベート [Docker](/glossary/docker/) Registry（[Docker](/glossary/docker/) Distribution）にアクセスする場合、Basic [認証](/glossary/認証/)または[トークン](/glossary/トークン/)[認証](/glossary/認証/)が有効か確認：

```bash
# Basic 認証でテスト
curl -u username:password https://your-registry.com/v2/

# 401 が返されたら、認証情報が間違っている
# 403 が返されたら、ユーザーに対象リポジトリへのアクセス権限がない
```

## それでも解決しない場合

### 確認すべきログと情報

[Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)の[ログ](/glossary/ログ/)を確認して詳細な[エラー](/glossary/エラー/)を特定します：

```bash
# Docker Desktop (Mac)
cat ~/Library/Containers/com.docker.docker/Data/log/vm/docker.log

# Docker Desktop (Windows)
type "%APPDATA%\Docker\log.txt"

# Docker Engine (Linux)
journalctl -u docker --no-pager | tail -50
```

[レジストリ](/glossary/レジストリ/)へのアクセステストを以下で実施：

```bash
# 認証情報の確認
docker info | grep "Registries"

# 特定のリポジトリへの権限テスト
curl -H "Authorization: Bearer $(cat ~/.docker/config.json | jq -r '.auths["registry-1.docker.io"].auth')" \
  https://registry-1.docker.io/v2/<your-repo>/manifests/latest
```

### 公式ドキュメント参照

- [Docker Hub Authentication](https://docs.docker.com/docker-hub/access-tokens/)：アクセストークンの生成と管理
- [Docker Registry HTTP API](https://docs.docker.com/registry/spec/api/)：[レジストリ](/glossary/レジストリ/) [API](/glossary/api/) 仕様
- [Kubernetes Image Pull Secrets](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/)：[Kubernetes](/glossary/kubernetes/) での認証設定

### コミュニティリソース

GitHub の [Docker](/glossary/docker/) Issues や [Docker](/glossary/docker/) Community Forums で、同じ組織・レジストリサービス（AWS ECR、Azure Container Registry、Google Artifact Registry 等）固有の問題報告を検索し、同様のケースの解決策を確認することが有効です。特に [CI/CD](/glossary/ci-cd/) パイプライン内での 403 [エラー](/glossary/エラー/)は、service account の権限設定に関連することが多いため、該当サービスの公式ドキュメントも併せて確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*