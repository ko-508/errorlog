---
title: "Docker の 409 エラー：原因と解決策"
date: 2026-01-01
description: "Dockerの409エラーは、HTTP標準仕様で「Conflict（競合）」を示すステータスコードです。Docker Daemon がコンテナやイメージの操作を受け付けられない状態を表します。"
tags: ["Docker"]
errorCode: "409"
lastmod: 2026-05-31
---
## エラーの概要

[Docker](/glossary/docker/)の409エラーは、[HTTP](/glossary/http/)標準仕様で「Conflict」を示す[ステータスコード](/glossary/ステータスコード/)です。[Docker](/glossary/docker/) Daemon がコンテナやイメージの操作を受け付けられない状態を表します。通常、リソースの重複、ポートの競合、不正なコンテナの状態遷移などが原因となります。このエラーが発生した場合、現在のシステム状態と実行しようとしている操作に矛盾があることを意味しています。

## 実際のエラーメッセージ例

```json
{
  "message": "Error response from daemon: Conflict. The container name \"/web-app\" is already in use by container \"abc123def456\". You have to remove (or rename) that container to be able to reuse that name."
}
```

```bash
Error response from daemon: Conflict. You cannot remove a running container abc123def456. Stop the container before attempting removal, or force remove
```

## よくある原因と解決手順

### 原因1：同じ名前のコンテナが既に存在している

同じ名前のコンテナが実行中または停止状態で残っているため、新たにコンテナを作成・起動できない場合に発生します。

**Before（エラーが起きる状況）:**
```bash
docker run --name web-app -p 8080:80 nginx
# Error: Conflict. The container name "/web-app" is already in use
```

**After（修正後）:**
```bash
# 既存のコンテナを確認
docker ps -a | grep web-app

# 停止中のコンテナを削除
docker rm web-app

# 新しいコンテナを作成
docker run --name web-app -p 8080:80 nginx
```

### 原因2：複数のコンテナが同じポートを使用しようとしている

ホストマシンの同じポートを複数のコンテナがバインドしようとすると、ポート競合により409エラーが発生します。

**Before（エラーが起きる状況）:**
```bash
docker run -d --name app1 -p 8080:80 nginx
docker run -d --name app2 -p 8080:80 apache
# Error: Conflict. The port is already in use
```

**After（修正後）:**
```bash
# 実行中のコンテナを確認
docker ps

# ポート使用状況を確認
docker port app1

# 異なるポートを指定
docker run -d --name app2 -p 8081:80 apache
```

### 原因3：イメージビルド時のキャッシュ競合

同じイメージ名またはタグで複数回ビルドを試行する場合、既に存在するイメージとの競合が発生します。

**Before（エラーが起きる状況）:**
```bash
docker build -t myapp:1.0 .
# 同じタグで再度ビルド
docker build -t myapp:1.0 .
# Error: Conflict during image layer processing
```

**After（修正後）:**
```bash
# 既存イメージを削除
docker rmi myapp:1.0

# または異なるタグを使用
docker build -t myapp:1.0-new .

# または --no-cache オプションで強制ビルド
docker build --no-cache -t myapp:1.0 .
```

## Docker固有の注意点

### コンテナのライフサイクル管理

Dockerで409エラーが頻発する場合、コンテナ管理に関する細かい仕様が影響しています。停止中のコンテナも`docker ps -a`で確認できるリソースとして存在し、同じ名前で新規作成できません。本番環境ではコンテナの自動削除オプションを活用することが推奨されます。

```bash
# --rm オプションで終了時に自動削除
docker run --rm --name temp-app nginx

# または停止と同時に削除
docker container prune -f
```

### Docker Composeでの競合

Docker Composeを使用する場合、`docker-compose.yml`内で定義したサービス名が既にコンテナとして存在していると409エラーが発生します。

**Before:**
```yaml
version: '3'
services:
  web:
    image: nginx
    ports:
      - "8080:80"
```

```bash
docker-compose up -d
# 再度実行時に競合発生
docker-compose up -d
```

**After:**
```bash
# 既存コンテナを停止・削除
docker-compose down

# 改めて起動
docker-compose up -d

# または既存リソースを保持したまま更新
docker-compose up -d --no-recreate
```

### ボリュームとネットワークの競合

コンテナ削除時に関連リソースが残っていると、同じ名前で再作成できない場合があります。

```bash
# 未使用リソースをすべてクリーンアップ
docker system prune -a --volumes

# または特定のボリュームを削除
docker volume rm <volume-name>
```

## それでも解決しない場合

### ログの確認方法

Docker Daemonのログを確認することで、より詳細な原因を特定できます。

```bash
# 最近のDocker Daemonログを表示
journalctl -u docker -n 50 -f

# または DockerホストでSyslogを確認
tail -f /var/log/syslog | grep docker
```

### デバッグコマンド

```bash
# 全リソースの概要を表示
docker system df

# 具体的なコンテナ・イメージ情報を確認
docker inspect <container-or-image-id>

# ネットワーク情報の確認
docker network ls
docker network inspect <network-name>
```

### 公式リソース

- [Docker公式ドキュメント：Docker API リファレンス](https://docs.docker.com/engine/api/)
- [Docker公式ドキュメント：トラブルシューティング](https://docs.docker.com/config/daemon/troubleshoot/)
- [GitHub Issues：docker/cli](https://github.com/moby/moby/issues)

409エラーの原因が不明な場合は、`docker version`と`docker info`で環境情報を確認し、GitHub Issuesで同様のケースが報告されていないか検索することが有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*