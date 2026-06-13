---
title: "Docker の 409 エラー：原因と解決策"
date: 2026-01-01
description: "Dockerの409エラーは、HTTP標準仕様で「Conflict（競合）」を示すステータスコードです。Docker Daemon がコンテナやイメージの操作を受け付けられない状態を表します。"
tags: ["Docker"]
errorCode: "409"
lastmod: 2026-06-13
service: "Docker"
error_type: "409"
components: ["Compose"]
related_services: []
trend_incident: true
---

## エラーの概要

Dockerの409エラーは、HTTP標準仕様で「Conflict」を示すステータスコードです。Docker Daemonがコンテナやイメージの操作を受け付けられない状態を表します。通常、リソースの重複、ポートの競合、不正なコンテナの状態遷移などが原因となります。このエラーが発生した場合、現在のシステム状態と実行しようとしている操作に矛盾があることを意味しており、Dockerコマンド実行時やAPI呼び出し時に頻繁に遭遇します。

## 実際のエラーメッセージ例

```json
{
  "message": "Error response from daemon: Conflict. The container name \"/web-app\" is already in use by container \"abc123def456\". You have to remove (or rename) that container to be able to reuse that name."
}
```

```bash
$ docker run --name myapp nginx
docker: Error response from daemon: Conflict. The container name "/myapp" is already in use by container "e7f8c9a2b1d4". You have to remove (or rename) that container to be able to reuse that name.
```

## よくある原因と解決手順

### 原因1：コンテナ名の重複

同じ名前のコンテナが既に存在する場合、新たに同じ名前でコンテナを作成しようとすると409エラーが発生します。停止中のコンテナであっても名前は保持されるため、`docker run --name` で既存の名前を指定するとエラーになります。

**Before（エラーが起きるコード）：**

```bash
docker run --name web-app -d nginx
# 後に同じ名前で再度実行
docker run --name web-app -d nginx:latest
# Error: Conflict. The container name "/web-app" is already in use
```

**After（修正後）：**

```bash
# 既存コンテナを確認して削除
docker ps -a | grep web-app
docker rm web-app

# その後、新しいコンテナを作成
docker run --name web-app -d nginx:latest
```

### 原因2：ポート番号の競合

複数のコンテナが同じポート番号にバインドしようとする場合、409エラーが発生します。特にホストマシンの同じポートを複数のコンテナが使用しようとする際に起こりやすい問題です。

**Before（エラーが起きるコード）：**

```bash
docker run -d -p 8080:80 --name web1 nginx
# 別のコンテナで同じホストポートを使用しようとする
docker run -d -p 8080:80 --name web2 apache
# Error: Conflict. driver failed programming external connectivity on endpoint web2
```

**After（修正後）：**

```bash
# ホストポートを別の番号に変更
docker run -d -p 8080:80 --name web1 nginx
docker run -d -p 8081:80 --name web2 apache

# または、別のネットワークを使用
docker network create frontend
docker run -d --network frontend -p 8080:80 --name web1 nginx
docker run -d --network frontend -p 8081:80 --name web2 apache
```

### 原因3：イメージのタグ重複

既存のイメージに対して同じタグで新しいイメージをビルドしようとする場合、特定の状況下で409エラーが発生することがあります。これは主にDockerレジストリへのプッシュ時に見られます。

**Before（エラーが起きるコード）：**

```bash
docker build -t myapp:1.0 .
# 同じタグで再度ビルド・プッシュ
docker tag myapp:1.0 myregistry.azurecr.io/myapp:1.0
docker push myregistry.azurecr.io/myapp:1.0
# Error: Conflict. Image with the same name already exists in the registry
```

**After（修正後）：**

```bash
# バージョンタグを更新してプッシュ
docker build -t myapp:1.1 .
docker tag myapp:1.1 myregistry.azurecr.io/myapp:1.1
docker push myregistry.azurecr.io/myapp:1.1

# または既存タグを強制上書き（レジストリが対応している場合）
docker push --force myregistry.azurecr.io/myapp:1.0
```

### 原因4：コンテナの不正な状態遷移

実行中のコンテナを削除しようとしたり、既に起動中のコンテナをもう一度起動しようとする場合、409エラーが発生します。コンテナのライフサイクル状態と実行しようとしている操作が矛盾していることが原因です。

**Before（エラーが起きるコード）：**

```bash
docker run -d --name app nginx
# 実行中のコンテナを停止せずに削除しようとする
docker rm app
# Error: You cannot remove a running container

# または実行中のコンテナを再度起動
docker start app
docker start app
# Error: Conflict. The container is already running
```

**After（修正後）：**

```bash
# 実行中のコンテナを停止してから削除
docker stop app
docker rm app

# または強制削除（データ消失に注意）
docker rm -f app

# 既に実行中のコンテナの再起動
docker restart app
```

## Docker固有の注意点

### Docker Composeでのコンテナ名競合

`docker-compose.yml`でサービス定義を複数保持しながら複数回実行すると、同じコンテナ名の重複が409エラーを引き起こします。プロジェクト名が異なる場合も考慮が必要です。

```bash
# プロジェクト名を明示することで名前空間を分離
docker-compose -p project1 up -d
docker-compose -p project2 up -d
```

### ネットワークとポート割り当ての相互作用

ブリッジネットワークとホストネットワークを混在させると、ポート割り当てで409エラーが発生することがあります。特にマルチコンテナ環境では、ネットワークドライバの選択とポート公開の設定を慎重に行う必要があります。

```yaml
# docker-compose.yml での正しい設定例
services:
  web:
    image: nginx
    ports:
      - "8080:80"
    networks:
      - frontend
  
  api:
    image: node:latest
    ports:
      - "3000:3000"
    networks:
      - frontend

networks:
  frontend:
    driver: bridge
```

### レジストリ認証とイメージプッシュの競合

プライベートレジストリへのプッシュ時に、同じイメージ名で異なるタグをプッシュしようとするか、認証情報が不足していると409エラーが発生することがあります。

```bash
# 認証情報の確認
docker login myregistry.azurecr.io

# タグ付けとプッシュ
docker tag myapp:latest myregistry.azurecr.io/myapp:v1.0.0
docker push myregistry.azurecr.io/myapp:v1.0.0
```

## それでも解決しない場合

### ログとデバッグコマンドの確認

Docker Daemonのログを確認することで、詳細なエラー原因を特定できます。

```bash
# Daemonログの確認（Linux/Mac）
docker logs --tail 50 <container-id>

# Daemonの詳細ログを有効化
sudo journalctl -u docker -f

# Windows環境での確認
Get-EventLog -LogName Application -Source Docker -Newest 20
```

### リソース競合の完全クリア

頑固な409エラーが続く場合、以下の手順で全リソースを確認・クリアしてください。

```bash
# 全コンテナをリスト表示（停止中も含む）
docker ps -a

# 不要なコンテナを削除
docker container prune

# ネットワーク状況を確認
docker network ls
docker network inspect <network-name>

# ボリュームの競合確認
docker volume ls
```

### 公式ドキュメント

Dockerの公式ドキュメント「[Container Conflicts](https://docs.docker.com/engine/reference/commandline/run/)」では、ポート割り当てとコンテナ名に関する詳細な説明があります。また、「[Error Handling](https://docs.docker.com/engine/api/sdk/)」ではAPI経由での409エラーの詳細が記載されています。

### コミュニティリソース

既知の409エラーについては、[Docker GitHub Issues](https://github.com/moby/moby/issues)で類似事例を検索することで解決策が見つかることが多くあります。特に「Conflict」というキーワードで検索すると、数千件の関連イシューが存在します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*