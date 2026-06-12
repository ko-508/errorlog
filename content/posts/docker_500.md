---
title: "Docker の 500 エラー：原因と解決策"
date: 2026-01-01
description: "Docker環境で500エラーが発生する場合、Dockerデーモンが予期しない内部エラーに遭遇していることを示しています。"
tags: ["Docker"]
errorCode: "500"
lastmod: 2026-05-31
service: "Docker"
error_type: "500"
components: []
related_services: []
trend_incident: true
---

## エラーの概要

[Docker](/glossary/docker/)環境で500[エラー](/glossary/エラー/)が発生する場合、[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)が予期しない内部[エラー](/glossary/エラー/)に遭遇していることを示しています。この[エラー](/glossary/エラー/)は[Docker](/glossary/docker/) [CLI](/glossary/cli/)[コマンド](/glossary/コマンド/)実行時や[コンテナ](/glossary/コンテナ/)操作時に返される汎用的なサーバーエラーであり、原因は多岐にわたります。ディスク不足、メモリ枯渇、[デーモン](/glossary/デーモン/)のクラッシュ、権限問題など、複数の要因が考えられるため、段階的な調査が必要です。

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
Error response from daemon: error during connect: This error may indicate the docker daemon is not running.
```

## よくある原因と解決手順

### 原因1：Dockerデーモンが起動していない、または異常状態

[Docker](/glossary/docker/)[コマンド](/glossary/コマンド/)を実行する際、[バックエンド](/glossary/バックエンド/)のdockerdプロセスが応答しない場合、500[エラー](/glossary/エラー/)が返されます。これはLinux環境で特に多く発生します。

**Before（[エラー](/glossary/エラー/)が発生する状態）:**
```bash
# dockerdが停止している状態
$ systemctl status docker
● docker.service - Docker Application Container Engine
   Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled)
   Active: inactive (dead)

$ docker ps
Error response from daemon: Internal Server Error
```

**After（解決後）:**
```bash
# Dockerデーモンを起動
$ sudo systemctl start docker

# 起動確認
$ sudo systemctl status docker
● docker.service - Docker Application Container Engine
   Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled)
   Active: active (running)

# 自動起動を有効化（再起動後も起動するように）
$ sudo systemctl enable docker

$ docker ps
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

### 原因2：ディスク容量が枯渇している

[Docker](/glossary/docker/)はイメージレイヤー、[コンテナ](/glossary/コンテナ/)、ボリュームをディスク上に保存します。ディスク容量がなくなると[デーモン](/glossary/デーモン/)がファイル操作を実行できず、500[エラー](/glossary/エラー/)を返します。

**Before（容量不足の状態）:**
```bash
$ df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G   99G  1.0G  99%  /

$ docker run ubuntu:latest
Error response from daemon: Internal Server Error
```

**After（容量を確保後）:**
```bash
# 不要なイメージやコンテナを削除
$ docker image prune -a --force
Deleted Images:
untagged old-image:latest

$ docker container prune --force
Deleted Containers:
abc123def456

# ボリュームの確認と削除
$ docker volume ls
DRIVER    VOLUME NAME
local     unused-volume

$ docker volume rm unused-volume
unused-volume

# 容量確認
$ df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G   60G   40G  60%  /

# 正常に動作
$ docker run ubuntu:latest
```

### 原因3：Dockerソケットの権限エラー

[Docker](/glossary/docker/)ソケット（`/var/run/docker.sock`）は通常root所有で、ユーザーがアクセスできない場合があります。この場合、[CLI](/glossary/cli/)[コマンド](/glossary/コマンド/)が内部的に500[エラー](/glossary/エラー/)を報告することがあります。

**Before（権限不足の状態）:**
```bash
# dockerグループに属していないユーザーで実行
$ docker ps
Error response from daemon: Internal Server Error

# ソケットの確認
$ ls -la /var/run/docker.sock
srw-rw---- 1 root docker 0 Jan 15 10:00 /var/run/docker.sock

# ユーザーがdockerグループに属していない
$ groups
user adm sudo
```

**After（[権限](/glossary/権限/)を修正後）:**
```bash
# 現在のユーザーをdockerグループに追加
$ sudo usermod -aG docker $USER

# グループ変更を反映（ログアウト/ログインまたは以下を実行）
$ newgrp docker

# 権限確認
$ groups
user adm sudo docker

# 正常に動作
$ docker ps
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

### 原因4：メモリ不足によるデーモンクラッシュ

システムメモリが枯渇している場合、[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)はメモリ割り当てに失敗し、500[エラー](/glossary/エラー/)を返すか完全にクラッシュします。

**Before（メモリ枯渇の状態）:**
```bash
$ free -h
              total        used        free
Mem:          7.8Gi       7.6Gi       200Mi
Swap:         2.0Gi       1.8Gi       200Mi

$ docker run large-image
Error response from daemon: Internal Server Error
```

**After（メモリを解放後）:**
```bash
# 不要なコンテナを停止・削除
$ docker ps -a
CONTAINER ID   IMAGE     STATUS
abc123def456   ubuntu    Exited

$ docker rm abc123def456

# Dockerデーモンのメモリ制限を確認・調整
$ docker info | grep -i memory
 Memory Limit: true
 Swap Limit: true

# メモリ状態の確認
$ free -h
              total        used        free
Mem:          7.8Gi       4.2Gi       3.6Gi

$ docker run large-image
# 正常に動作
```

## Docker固有の注意点

### Docker Desktop（macOS/Windows）での500エラー

[Docker](/glossary/docker/) Desktopを使用している場合、ホストOS側のリソース不足が原因となることが多いです。[Docker](/glossary/docker/) Desktopの設定でCPU・メモリ割り当てを確認し、必要に応じて増やします。

```bash
# Docker Desktopの状態確認（macOS）
$ docker run --rm -it docker info | grep -E "Memory|CPUs"
 CPUs: 4
 Memory: 2GiB

# 設定ファイルで割り当てを変更: ~/.docker/daemon.json
{
  "cpus": 8,
  "memory": 4000000000
}
```

### Docker Composeでの500エラー

[Docker](/glossary/docker/) Composeで複数のサービスを起動する際、1つのサービスでメモリリークが発生すると、[デーモン](/glossary/デーモン/)全体が500[エラー](/glossary/エラー/)を返すことがあります。

```yaml
# Before: リソース制限がない
version: '3'
services:
  app:
    image: myapp:latest
    ports:
      - "8080:8080"
```

```yaml
# After: リソース制限を追加
version: '3'
services:
  app:
    image: myapp:latest
    ports:
      - "8080:8080"
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

### ログの確認方法

[デーモン](/glossary/デーモン/)自体の[ログ](/glossary/ログ/)を確認することで、500[エラー](/glossary/エラー/)の根本原因を特定できます。

```bash
# systemdを使用している環境
$ sudo journalctl -u docker -n 50 --no-pager

# Docker Desktopの場合
# メニュー > Troubleshoot > View logs

# Linux でのデーモンログ
$ sudo cat /var/log/docker.log
```

## それでも解決しない場合

[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)を完全にリセットする前に、以下の診断[コマンド](/glossary/コマンド/)を実行してください。

```bash
# デーモンの詳細情報取得
$ sudo docker info

# 全イメージ・コンテナ情報の出力（デバッグ用）
$ docker images --no-trunc
$ docker ps --all --no-trunc

# デーモンの再起動（最終手段）
$ sudo systemctl restart docker

# 強制的にデーモンをリセット（注意：全コンテナ・イメージが削除される可能性）
$ sudo dockerd --debug
```

[Docker](/glossary/docker/)公式ドキュメントの「Troubleshoot the [Docker](/glossary/docker/) daemon」ページに詳細なトラブルシューティングガイドが記載されています。また、GitHub上の[Docker](/glossary/docker/) Engine [リポジトリ](/glossary/リポジトリ/)で同様のIssueが報告されていないか確認することで、既知の問題や解決策を見つけられます。システムが複雑な場合（[Kubernetes](/glossary/kubernetes/)統合やカスタムネットワーク設定）は、[Docker](/glossary/docker/) Desktopのリセット機能（Settings > Reset [Docker](/glossary/docker/) Desktop）を試す前に、必ず重要な[イメージ](/glossary/イメージ/)とボリュームをバックアップしてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*