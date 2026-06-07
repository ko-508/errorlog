---
title: "Docker Compose の 403 エラー：原因と解決策"
date: 2026-05-31
description: "レジストリまたはリソースへのアクセス権限がない。Docker Compose 403 エラーの原因と解決策を解説します。"
tags: ["Docker Compose"]
errorCode: "403"
---
## エラーの概要

[Docker](/glossary/docker/) Compose で 403 [エラー](/glossary/エラー/)が発生する場合、これは[レジストリ](/glossary/レジストリ/)（[Docker](/glossary/docker/) Hub、[プライベートレジストリ](/glossary/プライベートレジストリ/)など）またはホストマシンのリソースに対して、実行ユーザーが十分な[アクセス権限](/glossary/アクセス権限/)を持っていないことを示しています。プライベートイメージの pull、ボリュームマウント時のファイルアクセス、[Docker](/glossary/docker/) ソケットへのアクセスなど、複数の場面で発生する可能性があります。

## 実際のエラーメッセージ例

**[Docker](/glossary/docker/) Hub などの[レジストリ](/glossary/レジストリ/)からのプライベートイメージ pull 時：**

```json
{
  "message": "Error response from daemon: pull access denied for myregistry/myimage, repository does not exist or may require 'docker login'",
  "error": "403 Forbidden"
}
```

**ボリュームマウントのパーミッション不足時：**

```bash
ERROR: for <service-name>  Cannot start service <service-name>: 
error while creating mount source path '/data/app': permission denied
```

**[Docker](/glossary/docker/) ソケットへのアクセス権限不足時：**

```bash
ERROR: Got permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock
```

## よくある原因と解決手順

### 原因1：プライベートイメージレジストリへの認証不足

[Docker](/glossary/docker/) Compose でプライベートイメージを利用する場合、[レジストリ](/glossary/レジストリ/)に対する認証情報が必要です。[認証](/glossary/認証/)なしにプライベートイメージを pull しようとすると 403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    image: myregistry.azurecr.io/myimage:latest
    # 認証情報が設定されていない
```

実行時に以下の[コマンド](/glossary/コマンド/)を実行すると 403 [エラー](/glossary/エラー/)が発生します：

```bash
docker-compose up
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  app:
    image: myregistry.azurecr.io/myimage:latest
    
# docker-compose.yml と同じディレクトリに .env ファイルを作成
# または docker login で事前に認証を完了させる
```

事前に認証情報を設定する方法：

```bash
# Docker Hub の場合
docker login -u <username> -p <password>

# プライベートレジストリの場合（例：Azure Container Registry）
docker login myregistry.azurecr.io -u <username> -p <password>

# その後、docker-compose up を実行
docker-compose up -d
```

また、docker-compose.yml で認証情報を管理する場合、ホームディレクトリの `~/.docker/config.json` が参照されます：

```yaml
version: '3.8'
services:
  app:
    image: myregistry.azurecr.io/myimage:latest
```

### 原因2：ボリュームマウント先ディレクトリのパーミッション不足

[Docker](/glossary/docker/) [コンテナ](/glossary/コンテナ/)内から、ホストマシンのマウント先ディレクトリに書き込みを試みると、パーミッション不足で 403 [エラー](/glossary/エラー/)が発生します。特に root でないユーザーで[コンテナ](/glossary/コンテナ/)を実行する場合に顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    image: myapp:latest
    volumes:
      - /data/app:/app/data
    # コンテナ内のユーザー ID とホスト側のパーミッションが一致していない
```

```bash
# ホストマシンで権限不足のディレクトリが存在
ls -la /data/app
# drwxr-x--- root root /data/app
# この場合、他のユーザーに書き込み権限がない
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  app:
    image: myapp:latest
    volumes:
      - /data/app:/app/data
    user: "1000:1000"  # コンテナ内のユーザー ID を明示
```

```bash
# ホストマシンでパーミッションを確認・修正
ls -la /data/
# drwxr-xr-x root root data

# 必要に応じてディレクトリの所有者を変更
sudo chown 1000:1000 /data/app
sudo chmod 755 /data/app

# またはマウント先のパーミッションを緩和
sudo chmod 777 /data/app

# その後、docker-compose up を実行
docker-compose up -d
```

あるいは、Dockerfile で[コンテナ](/glossary/コンテナ/)内のユーザーを指定する方法：

```dockerfile
FROM ubuntu:20.04
RUN useradd -m -u 1000 appuser
USER appuser
```

### 原因3：Docker ソケットへのアクセス権限不足

現在のユーザーが docker グループに属していない場合、[Docker](/glossary/docker/) ソケット（`/var/run/docker.sock`）へのアクセスが拒否され 403 [エラー](/glossary/エラー/)が発生します。sudo なしで docker-compose を実行しようとすると発生しやすい問題です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 一般ユーザーで docker-compose を実行
docker-compose up
# Got permission denied while trying to connect to the Docker daemon socket
```

```bash
# 現在のユーザーのグループ確認
groups
# 出力に docker グループが含まれていない
```

**After（修正後）：**

```bash
# 一般ユーザーを docker グループに追加
sudo usermod -aG docker $USER

# グループ変更を有効にするため、ログインし直すか以下を実行
newgrp docker

# その後、sudo なしで docker-compose を実行可能
docker-compose up -d
```

または sudo で実行する場合：

```bash
sudo docker-compose up -d
```

ユーザーが docker グループに追加されたか確認：

```bash
id -nG
# docker が含まれていることを確認
```

## ツール固有の注意点

[Docker](/glossary/docker/) Compose で 403 [エラー](/glossary/エラー/)が発生する際、以下のシナリオ別の対応が必要です。

**マルチステージビルドでプライベートイメージを使用する場合：**

```yaml
version: '3.8'
services:
  builder:
    image: myregistry.azurecr.io/builder:latest
    # ビルドステージでプライベートイメージを使用する場合も
    # 同様に事前の docker login が必須
```

**[Docker](/glossary/docker/) Compose v2 を使用している場合：**

```bash
# v2 ではコマンド形式が異なる
docker compose up -d
# 権限がない場合は同じく docker グループへの追加が必要
```

**Windows または macOS で [Docker](/glossary/docker/) Desktop を使用している場合：**

[Docker](/glossary/docker/) Desktop のファイル共有設定で、マウント対象ディレクトリが許可リストに含まれている必要があります。設定→ Resources→ File Sharing で確認し、マウント先のパスが含まれていることを確認してください。

**Swarm モード使用時：**

```bash
# Swarm モードでサービスをデプロイする場合
docker stack deploy -c docker-compose.yml <stack-name>
# この場合も認証情報は事前に docker login で設定されている必要があります
```

## それでも解決しない場合

[Docker](/glossary/docker/) Compose の詳細な[エラー](/glossary/エラー/)出力を確認します。

```bash
# デバッグモードで実行（詳細ログを表示）
docker-compose -v up
```

[Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)の[ログ](/glossary/ログ/)を確認：

```bash
# Linux の場合
sudo journalctl -u docker -n 100

# macOS の場合（Docker Desktop）
~/Library/Logs/Docker/com.docker.docker.log
```

[Docker](/glossary/docker/) の設定を確認：

```bash
# 認証設定を確認
cat ~/.docker/config.json

# パーミッション情報を確認
ls -la /var/run/docker.sock
stat /data/app  # マウント対象のパーミッション詳細表示
```

公式ドキュメントの参照：

- [Docker Compose 認証ドキュメント](https://docs.docker.com/compose/compose-file/compose-file-v3/)
- [Docker Hub レジストリ認証](https://docs.docker.com/engine/reference/commandline/login/)
- [ボリュームマウント トラブルシューティング](https://docs.docker.com/storage/volumes/)

上記の対応でも解決しない場合、以下を確認してください：

```bash
# Docker デーモンの状態確認
sudo systemctl status docker

# ディスク容量不足の確認
df -h /var/lib/docker

# SELinux が有効になっていないか確認（CentOS/RHEL）
getenforce
```

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*