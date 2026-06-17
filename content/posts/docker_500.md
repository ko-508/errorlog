---
title: "Docker の 500 エラー：原因と解決策"
date: 2026-01-01
description: "Docker環境で500エラーが発生する場合、Dockerデーモンが予期しない内部エラーに遭遇していることを示しています。"
tags: ["Docker"]
errorCode: "500"
lastmod: 2026-06-13
service: "Docker"
error_type: "500"
components: []
related_services: []
trend_incident: true
top_queries:
- "docker http 500: internal server error"
- "http 500: internal server error docker"
---

## エラーの概要

[Docker](/glossary/docker/)環境で500[エラー](/glossary/エラー/)が発生する場合、[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)が予期しない内部[エラー](/glossary/エラー/)に遭遇していることを示しています。この[エラー](/glossary/エラー/)は[Docker](/glossary/docker/) [CLI](/glossary/cli/)[コマンド](/glossary/コマンド/)実行時や[コンテナ](/glossary/コンテナ/)操作時に返される汎用的なサーバーエラーであり、原因は多岐にわたります。ディスク不足、メモリ枯渇、[デーモン](/glossary/デーモン/)のクラッシュ、権限問題など複数の要因が考えられるため、段階的な調査が必要です。[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)の状態確認と[ログ](/glossary/ログ/)分析を通じて、根本原因を特定することが解決への第一歩となります。

## 実際のエラーメッセージ例

```bash
$ docker run ubuntu:latest
Error response from daemon: Internal Server Error
```

```json
{
  "message": "Internal Server Error"
}
```

```bash
$ docker ps
Error response from daemon: Internal Server Error
```

```bash
$ docker build -t myapp .
Error response from daemon: Internal Server Error
```

## よくある原因と解決手順

### 原因1：Dockerデーモンの停止またはクラッシュ

[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)が応答していない、または不安定な状態にあると500[エラー](/glossary/エラー/)が返されます。デーモンプロセスが終了していたり、メモリ不足で強制終了された場合、すべての[Docker](/glossary/docker/)操作が失敗します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# デーモンが停止している状態で実行
docker ps
# Error response from daemon: Internal Server Error
```

**After（修正後）：**

```bash
# Dockerデーモンの状態確認
sudo systemctl status docker

# デーモンが停止している場合は再起動
sudo systemctl restart docker

# 再度実行
docker ps
```

### 原因2：ディスク容量不足

[Docker](/glossary/docker/)は[イメージ](/glossary/イメージ/)、[コンテナ](/glossary/コンテナ/)、ボリュームデータを `/var/lib/docker` に保存します。このディレクトリが属するパーティションのディスク容量が枯渇すると、新規操作が失敗して500[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ディスク満杯の状態で実行
docker pull ubuntu:latest
# Error response from daemon: Internal Server Error
```

**After（修正後）：**

```bash
# ディスク使用状況を確認
df -h /var/lib/docker

# 不要なイメージやコンテナを削除
docker system prune -a

# 具体的に削除対象を確認する場合
docker images
docker ps -a

# 特定のイメージを削除
docker rmi <image-id>

# 特定のコンテナを削除
docker rm <container-id>
```

### 原因3：Dockerデーモンのプロセス権限不足または設定エラー

[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)が適切な[権限](/glossary/権限/)で実行されていない、または[設定ファイル](/glossary/設定ファイル/)が破損していると500[エラー](/glossary/エラー/)が発生します。特に `/etc/docker/daemon.json` の設定[エラー](/glossary/エラー/)や、デーモンプロセスの所有権が不正な場合に起こります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
// /etc/docker/daemon.json（不正な設定）
{
  "storage-driver": "invalid-driver",
  "debug": true,
  "log-level": "debug"
}
```

**After（修正後）：**

```json
// /etc/docker/daemon.json（正しい設定）
{
  "storage-driver": "overlay2",
  "debug": true,
  "log-level": "debug",
  "live-restore": true
}
```

```bash
# デーモンを停止して設定を再確認
sudo systemctl stop docker

# 設定ファイルの構文をチェック
docker -D ps

# デーモンを再起動
sudo systemctl restart docker
```

### 原因4：コンテナランタイムエラー

containerdなどのコンテナランタイムが正常に機能していない、またはsocketsファイルが破損している場合、[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)が500[エラー](/glossary/エラー/)を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ランタイムソケットが無い/アクセス不可
ls -la /var/run/docker.sock
# ファイルが存在しないか、権限が不正
```

**After（修正後）：**

```bash
# ランタイムソケットの状態を確認
sudo systemctl restart containerd
sudo systemctl restart docker

# ソケットファイルの権限を確認
ls -la /var/run/docker.sock

# 必要に応じてファイルを再作成
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### 原因5：メモリ不足

[Docker](/glossary/docker/)デーモンプロセス自体がメモリ枯渇で強制終了されると、500[エラー](/glossary/エラー/)が発生します。特に大量の[コンテナ](/glossary/コンテナ/)を実行している環境では要注意です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# メモリ枯渇状態で実行
docker run -d --memory=500m myapp
# Error response from daemon: Internal Server Error
```

**After（修正後）：**

```bash
# 現在のメモリ使用状況を確認
free -h

# 実行中のコンテナとそのメモリ使用量を確認
docker stats

# 不要なコンテナを停止・削除
docker stop <container-id>
docker rm <container-id>

# メモリ制限を設定してコンテナ再起動
docker run -d --memory=1g --memory-swap=1g myapp
```

## ツール固有の注意点

### Docker Composeの場合

[Docker](/glossary/docker/) Compose環境で500[エラー](/glossary/エラー/)が発生する場合、イメージビルドの途中でのディスク不足が原因の可能性が高いです。マルチステージビルドや[キャッシュ](/glossary/キャッシュ/)の問題も関わります。

**確認方法：**

```bash
# Composeで詳細ログを出力
docker-compose -f docker-compose.yml up --verbose

# ビルドキャッシュをクリアして再ビルド
docker-compose build --no-cache

# 不要な中間イメージやボリュームを削除
docker-compose down -v
```

### Swarmモードの場合

[Docker](/glossary/docker/) Swarmクラスタ内のノードでリソース枯渇や[ネットワーク](/glossary/ネットワーク/)分断が起きると、500[エラー](/glossary/エラー/)が発生します。特にマネージャーノードのディスク不足に注意が必要です。

```bash
# Swarmのノード状態を確認
docker node ls

# マネージャーノードのリソース状況
docker node inspect <node-id>

# ノードを再起動する必要がある場合
sudo systemctl restart docker
```

### ログドライバー設定エラー

不正なログドライバー設定（例：外部ログサービスへの接続失敗）により、[デーモン](/glossary/デーモン/)が500[エラー](/glossary/エラー/)を返すことがあります。

```bash
# ログドライバーの設定を確認
docker info | grep -i "Logging Driver"

# daemon.jsonで設定を修正
# "log-driver": "json-file" に設定直後、デーモン再起動
sudo systemctl restart docker
```

## それでも解決しない場合

### ログの確認方法

```bash
# Dockerデーモンのシステムログを確認（Linux）
sudo journalctl -u docker -n 100 --no-pager

# より詳細なデバッグモード
sudo journalctl -u docker -f

# Dockerデーモンを直接実行してエラーを確認
sudo dockerd --debug
```

### Windows/Macの場合

[Docker](/glossary/docker/) Desktopを使用している場合は、以下の手順で診断情報を収集します。

```bash
# Docker Desktopの診断を取得
docker run --rm -it -v /var/run/docker.sock:/var/run/docker.sock docker:latest docker info
```

### 公式ドキュメント参照

- [Docker Troubleshooting](https://docs.docker.com/config/containers/logging/) - ロギング設定の公式ガイド
- [Daemon logs and troubleshooting](https://docs.docker.com/config/daemon/#check-the-daemon) - [デーモン](/glossary/デーモン/)診断の公式ドキュメント
- [Docker Engine release notes](https://docs.docker.com/engine/release-notes/) - 既知の問題と修正内容

### コミュニティリソース

- GitHub Issues：`moby/moby` [リポジトリ](/glossary/リポジトリ/)で「Internal Server Error」で検索
- [Docker](/glossary/docker/) Community Forums：https://forums.docker.com/ で同様の事例を検索
- Stack Overflow：`docker` タグで過去の解決事例を参照

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*