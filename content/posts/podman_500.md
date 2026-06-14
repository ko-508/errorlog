---
title: "Podman の 500 エラー：原因と解決策"
date: 2026-05-29
description: "Podmanシステムで予期しない内部エラーが発生した。Podman 500 エラーの原因と解決策を解説。"
tags: ["Podman"]
errorCode: "500"
service: "Podman"
error_type: "500"
components: []
related_services: ["SELinux", "journalctl"]
lastmod: 2026-06-14
---

## エラーの概要

Podman 500 エラーは、Podman デーモンで予期しない内部エラーが発生したことを示します。ストレージ破損、ディスク容量不足、権限問題によって発生することが多く、コンテナの起動・管理・削除といった基本的な操作が失敗します。このエラーが発生した場合、Podman のストレージとシステムリソースの状態を段階的に確認する必要があります。

## 実際のエラーメッセージ例

```json
{
  "error": "internal error",
  "code": 500,
  "message": "Error while removing container: container storage corrupted"
}
```

```bash
$ podman run -it alpine /bin/sh
Error: error creating container storage: mkdir /var/lib/containers/storage/overlay2/<id>/merged: no space left on device
```

## よくある原因と解決手順

### 原因1：ディスク容量不足

Podman のストレージディレクトリ（通常 `/var/lib/containers/storage`）の容量がいっぱいになると、新しいレイヤーやコンテナメタデータの書き込みに失敗し、500 エラーが発生します。

**原因の確認：**

```bash
df -h /var/lib/containers
```

ファイルシステムの使用率が 100% に近い場合、これが原因です。

**Before（エラーが起きるコード）：**

```bash
$ podman ps
Error: error listing containers: FIXME: container.Driver.GetGraphDriver failed: <nil>
```

**After（修正後）：**

```bash
# 不要なイメージ・コンテナを削除
podman image prune -a -f
podman container prune -f

# または古いイメージを明示的に削除
podman rmi <image_id>

# その後、ストレージ情報を確認
podman system df
```

### 原因2：ストレージメタデータの破損

不正なシャットダウンや Podman デーモンの強制終了によって、`/var/lib/containers/storage` 配下の設定ファイルやメタデータが破損することがあります。特に `containers.json` や overlay2 の統計ファイルが影響を受けやすいです。

**Before（エラーが起きるコード）：**

```bash
$ podman ps
Error: error reading containers: json: cannot unmarshal string into Go value of type struct { ... }
```

**After（修正後）：**

```bash
# Podman デーモンを停止
systemctl stop podman
# または
systemctl stop podman.socket

# ストレージの整合性チェック
podman system reset --force

# デーモンを再起動
systemctl start podman
systemctl start podman.socket

# 動作確認
podman ps
```

### 原因3：オーバーレイファイルシステムの不一致

overlay2 ドライバを使用している場合、lower レイヤー・upper レイヤー・work ディレクトリ間の構造が不一致になることがあります。特にコンテナ削除時の処理が中断された場合、orphaned な overlay ディレクトリが残存し、メタデータ読み込み時に 500 エラーが発生します。

**Before（エラーが起きるコード）：**

```bash
$ podman rm <container_id>
Error: error removing container <id>: remove overlay mount: internal error
```

**After（修正後）：**

```bash
# まず Podman デーモンを停止
systemctl stop podman
systemctl stop podman.socket

# orphaned なディレクトリを確認（手動確認用）
ls /var/lib/containers/storage/overlay2/

# ストレージデータベースの修復
podman system reset --force

# または、より安全に incremental で修復
podman storage reset
podman system gc --all

# デーモン再起動
systemctl start podman
systemctl start podman.socket
```

### 原因4：SELinux または AppArmor のラベル付け問題

SELinux または AppArmor が有効な場合、ストレージディレクトリのセキュリティコンテキストが不正な状態にあるとアクセス拒否が発生し、500 エラーとなります。

**Before（エラーが起きるコード）：**

```bash
$ podman images
Error: error accessing store: error looking up storage metadata: permission denied
```

**After（修正後）：**

```bash
# SELinux の場合
sudo restorecon -Rv /var/lib/containers/

# ラベルの確認（SELinux 有効時）
ls -laZ /var/lib/containers/storage/

# Podman デーモン再起動
systemctl restart podman
```

## ツール固有の注意点

### Rootless vs Rootfull 環境での相違

**Rootfull（root で実行）：**
```bash
podman ps  # /var/lib/containers/ 使用
```

**Rootless（一般ユーザーで実行）：**
```bash
podman ps  # ~/.local/share/containers/ 使用
```

Rootless 環境でのストレージ破損の場合、該当ユーザーのホームディレクトリを確認してください。

```bash
du -sh ~/.local/share/containers/
```

### Podman v4.x 以降での自動修復機能

Podman v4.4 以降では、一部のストレージ不整合は自動的に検出・修復されます。それでも 500 エラーが続く場合は、以下を実行します。

```bash
podman system reset --force
```

このコマンドはすべてのコンテナ・イメージ・ストレージを削除するため、重要なデータは事前にバックアップしてください。

### systemd-logind との相互作用

Rootless 環理でシステムシャットダウン時に Podman デーモンが強制終了されると、セッション中のコンテナ管理状態が不整合になることがあります。その場合は user session を明示的にリセットします。

```bash
loginctl terminate-user <username>
systemctl --user reset-failed
```

## それでも解決しない場合

### ログを確認する

Podman デーモンのジャーナルログを確認します。

```bash
# Systemd 管理下の Podman
journalctl -u podman -n 100

# User-level Podman（Rootless）
journalctl --user -u podman --all -n 100
```

### デバッグモードで再実行

Podman のデバッグモードでより詳細な情報を取得できます。

```bash
podman --log-level debug run alpine echo test
```

### ストレージドライバの再構成

`/etc/containers/storage.conf` が破損している可能性があります。バックアップを取った上で、デフォルト設定にリセットしてください。

```bash
# バックアップ
cp /etc/containers/storage.conf /etc/containers/storage.conf.bak

# デフォルト設定をリセット
rm /etc/containers/storage.conf
podman system reset --force
```

### 公式ドキュメント・サポートリソース

- [Podman トラブルシューティング](https://docs.podman.io/en/latest/)
- [Podman ストレージドライバドキュメント](https://docs.podman.io/en/latest/markdown/podman.1.html)
- [GitHub Issues - Podman](https://github.com/containers/podman/issues)

デバッグログと `podman info --format json` の出力をまとめて報告すると、問題解決が加速します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*