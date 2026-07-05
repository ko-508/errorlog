---
draft: true
title: "Podman の 503 エラー：原因と解決策"
date: 2026-05-29
description: "Podmanサービスまたはレジストリが一時的に利用できない"
tags: ["Podman"]
errorCode: "503"
service: "Podman"
error_type: "503"
components: []
related_services: ["Docker Hub", "Quay.io", "Docker"]
lastmod: 2026-06-14
---

## エラーの概要

Podman の 503 [エラー](/glossary/エラー/)は「Service Unavailable（サービス利用不可）」を意味し、Podman [API](/glossary/api/) サービスやコンテナレジストリが一時的に利用できない状態で発生します。この[エラー](/glossary/エラー/)は `podman` [コマンド](/glossary/コマンド/)実行時や[コンテナ](/glossary/コンテナ/)起動時、イメージプル操作時に頻出し、原因がローカルサービスの停止か外部[レジストリ](/glossary/レジストリ/)の障害かを見極める必要があります。

## 実際のエラーメッセージ例

```json
{
  "error": "Error response from daemon: Get \"https://registry-1.docker.io/v2/\": net/http: request canceled (Client.Timeout exceeded while awaiting headers)",
  "statusCode": 503
}
```

```
Error: unable to connect to Podman socket: Get \"http://d/v4.0.0/libpod/_ping\": dial unix /run/podman/podman.sock: connection refused
```

## よくある原因と解決手順

### 原因1：Podman API ソケット（podman.socket）が起動していない

Podman をシステムサービスとして動作させる場合、`podman.socket` がリッスンしていないと、すべての Podman [コマンド](/glossary/コマンド/)が 503 [エラー](/glossary/エラー/)で失敗します。特にリモート接続や複数ユーザーでの Podman 利用時に発生しやすいです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Podman API サービスが停止している状態
systemctl status podman.socket
# 出力: Unit podman.socket could not be found.

podman ps
# 出力: Error: unable to connect to Podman socket
```

**After（修正後）：**

```bash
# podman.socket を有効化して起動
systemctl enable podman.socket
systemctl start podman.socket

# ユーザーレベルの場合（非rootユーザー）
systemctl --user enable podman.socket
systemctl --user start podman.socket

# 接続確認
podman info
```

### 原因2：コンテナレジストリ（Docker Hub・Quay.io等）のメンテナンスまたは障害

[Docker](/glossary/docker/) Hub や Quay.io などの外部[レジストリ](/glossary/レジストリ/)がメンテナンス中、負荷が高い状態、または[ネットワーク](/glossary/ネットワーク/)遅延により一時的に 503 を返しています。この場合、イメージプル操作が失敗します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# レジストリが利用できない状況
podman pull docker.io/library/nginx:latest
# 出力: Error response from daemon: Get "https://registry-1.docker.io/v2/": net/http: request canceled
```

**After（修正後）：**

```bash
# タイムアウト値を増やしてリトライ
podman pull --retry 3 docker.io/library/nginx:latest

# 別のレジストリから取得（レジストリが回復まで待つか、キャッシュを利用）
podman pull quay.io/nginx/nginx:latest

# レジストリの状態確認（curl で直接確認）
curl -I https://registry-1.docker.io/v2/
# HTTP 200 が返ればレジストリは利用可能
```

### 原因3：Podman デーモンがクラッシュまたはメモリ不足

Podman デーモンプロセス（`podman system service` で起動したプロセス）がクラッシュしたり、[メモリ](/glossary/メモリ/)不足でキルされたりすると、新しい[リクエスト](/glossary/リクエスト/)に対して 503 を返します。特に大量の[コンテナ](/glossary/コンテナ/)を同時実行している環境で顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# podman デーモンが停止している状態
ps aux | grep -i podman
# podman service プロセスが存在しない

podman run --rm alpine echo "test"
# 出力: Error response from daemon: Service Unavailable
```

**After（修正後）：**

```bash
# デーモンを再起動
podman system service --time 0 &

# または systemd service として再起動
systemctl restart podman

# メモリ不足の場合はシステムメモリを確認
free -h

# 不要なコンテナやイメージを削除
podman container prune -f
podman image prune -f

# デーモンの状態確認
podman system df
```

### 原因4：ファイアウォール・プロキシ設定によるレジストリアクセス制限

組織内の[ファイアウォール](/glossary/ファイアウォール/)や[プロキシ](/glossary/プロキシ/)が [HTTPS](/glossary/https/) コネクションをブロックするか、[レジストリ](/glossary/レジストリ/)へのアクセスを制限しており、[デーモン](/glossary/デーモン/)が 503 と解釈する接続[エラー](/glossary/エラー/)を発生させています。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# プロキシを経由せずにイメージをプルしようとする
podman pull docker.io/library/alpine:latest
# 出力: Get "https://registry-1.docker.io/v2/": dial tcp: i/o timeout
```

**After（修正後）：**

```bash
# Podman にプロキシ設定を追加（$HOME/.config/containers/registries.conf）
cat > ~/.config/containers/registries.conf << 'EOF'
[[registries]]
location = "docker.io"
[[registries.insecure]]
insecure = false

[registries.custom]
# プロキシ設定が必要な場合、環境変数で指定
EOF

# または環境変数でプロキシを指定
export HTTP_PROXY=http://<proxy-host>:<port>
export HTTPS_PROXY=https://<proxy-host>:<port>
export NO_PROXY=localhost,127.0.0.1

podman pull docker.io/library/alpine:latest
```

## Podman 固有の注意点

### Podman ソケットのアクセス権限問題

非root ユーザーで Podman を実行する場合、`/run/user/<uid>/podman/podman.sock` への[アクセス権限](/glossary/アクセス権限/)が不足していると 503 [エラー](/glossary/エラー/)が発生します。`podman.socket` ユーザーモード版が起動していることを確認してください。

```bash
# 現在のユーザーID を確認
id -u

# ユーザーモードの podman.socket を有効化
systemctl --user enable podman.socket
systemctl --user start podman.socket

# ソケットファイルの権限確認
ls -la /run/user/$(id -u)/podman/podman.sock
```

### リモート Podman 接続での接続タイムアウト

Podman を SSH 経由でリモート接続する場合、SSH キーが設定されていないか、リモート側の Podman [API](/glossary/api/) サービスが起動していないと 503 が発生します。

```bash
# リモート接続先の接続情報確認
podman system connection list

# リモート接続を追加・更新
podman system connection add <connection-name> ssh://<user>@<host>/run/podman/podman.sock

# リモート接続をテスト
podman -c <connection-name> info
```

### Podman Compose の 503 エラー

`podman-compose` 使用時に 503 が発生する場合、Podman [デーモン](/glossary/デーモン/)（`podman.socket`）が起動していない、またはイメージレジストリが利用不可です。

```bash
# podman.socket が起動していることを確認
systemctl status podman.socket

# 詳細なログを出力してリトライ
podman-compose -f docker-compose.yml pull --verbose
```

## それでも解決しない場合

### ログ確認とデバッグ

```bash
# Podman デーモンログを確認（systemd 経由で起動した場合）
journalctl -u podman.socket -u podman.service -n 50 -f

# ユーザーモードの場合
journalctl --user -u podman.socket -u podman.service -n 50 -f

# Podman システム情報の詳細確認
podman system info --debug

# ネットワーク接続確認（レジストリへの疎通確認）
curl -v https://registry-1.docker.io/v2/
```

### リソースと参照先

- 公式ドキュメント：[Podman System Service](https://docs.podman.io/en/latest/markdown/podman-system-service.1.html)
- 公式ドキュメント：[Podman Remote Connection](https://docs.podman.io/en/latest/markdown/podman-system-connection.1.html)
- GitHub Issues：[Podman Issues](https://github.com/containers/podman/issues)
- [Docker](/glossary/docker/) Hub Status：[status.docker.com](https://status.docker.com/)
- [レジストリ](/glossary/レジストリ/)の公式ステータスページで障害情報を確認

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*