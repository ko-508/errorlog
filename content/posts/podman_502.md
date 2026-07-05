---
draft: true
title: "Podman の 502 エラー：原因と解決策"
date: 2026-06-28
description: "Podmanにおける502エラーは、通常、ゲートウェイまたはプロキシとして機能するサーバーがアップストリームサーバーから。"
tags: ["Podman"]
errorCode: "502"
urgency: "high"
service: "Podman"
error_type: "502"
components: ["Pod", "Image", "Registry", "Volume"]
related_services: ["Quay", "OpenShift", "Kubernetes", "Quadlet"]
---

## エラーの概要

Podman の 502 Bad Gateway [エラー](/glossary/エラー/)は、Podman ホストがゲートウェイまたは[プロキシ](/glossary/プロキシ/)として機能する際に、アップストリームサーバーから無効な応答を受け取ったことを示します。この[エラー](/glossary/エラー/)は特にコンテナレジストリとの通信時、リバースプロキシ設定時、またはランタイム変更後に発生します。Podman 内部の[コンテナ](/glossary/コンテナ/)間通信や[コンテナ](/glossary/コンテナ/)とホスト間の[通信](/glossary/通信/)が正常に機能していない状態を意味することが多いです。

## 実際のエラーメッセージ例

```
Error: parsing image configuration: Error fetching blob: invalid status code from registry 502 (Bad Gateway)
```

```
Error: Error writing blob: Error initiating layer upload to /v2/repo/image/blobs/uploads/ in <registry>: received unexpected HTTP status: 502 Bad Gateway
```

```
502 Bad Gateway
```

**[エラーメッセージ](/glossary/エラーメッセージ/)の読み方：**

- `502` → [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)：ゲートウェイまたは[プロキシ](/glossary/プロキシ/)が無効な応答を受け取った状態を示す
- `Bad Gateway` → 理由フレーズ：アップストリームサーバーとの通信障害が発生している
- `Error fetching blob` / `Error writing blob` → コンテナレジストリとの[イメージ](/glossary/イメージ/)転送処理で[エラー](/glossary/エラー/)が発生している
- `invalid status code from registry 502` → レジストリサーバーが 502 を返していることを示す

## よくある原因と解決手順

### 原因1：コンテナレジストリとの通信障害（Quay等）

Quay などのコンテナレジストリに[イメージ](/glossary/イメージ/)をプルまたはプッシュする際に、[SSL](/glossary/ssl/) 証明書[エラー](/glossary/エラー/)や誤ったバックエンドストレージのホスト名が原因で[通信](/glossary/通信/)が失敗します。レジストリサーバー自体がダウンしているか、[バックエンド](/glossary/バックエンド/) DB が応答しない状態にあることが多いです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
podman pull quay.io/<your-namespace>/<image-name>:latest
# Error: parsing image configuration: Error fetching blob: invalid status code from registry 502 (Bad Gateway)
```

**After（修正後）：**

```bash
# レジストリコンテナ（Quayが自ホストで動作している場合）を再起動
podman restart quay-container

# または OpenShift/Kubernetes 環境で動作している場合
oc delete pod quay-app
oc wait --for=condition=Ready pod -l app=quay --timeout=300s

# 再度イメージプルを試行
podman pull quay.io/<your-namespace>/<image-name>:latest
```

✅ 修正後の確認：

```bash
podman pull quay.io/<your-namespace>/<image-name>:latest
# イメージが正常にダウンロードされ、Resolved image ... と表示されれば成功です。
```

### 原因2：リバースプロキシ内のネットワーク設定不備

リバースプロキシ設定において、[コンテナ](/glossary/コンテナ/)内の `localhost` がホストの `localhost` と異なる、または同じ[ネットワーク](/glossary/ネットワーク/)上にないため、[コンテナ](/glossary/コンテナ/)が外部または他の[コンテナ](/glossary/コンテナ/)のサービスに接続できません。[コンテナ](/glossary/コンテナ/)の 127.0.0.1 は[コンテナ](/glossary/コンテナ/)内部のループバックアドレスであり、ホストのサービスにアクセスできません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# Quadlet ファイル (例: /etc/containers/systemd/app.container)
[Container]
Image=nginx:latest
PublishPort=8080:80
# リバースプロキシ設定がコンテナ内の localhost を指す
Environment="PROXY_BACKEND=http://localhost:8000"
# これはコンテナ内の localhost であり、ホストのサービスに到達しない
```

**After（修正後）：**

```yaml
# Quadlet ファイル (例: /etc/containers/systemd/app.container)
[Container]
Image=nginx:latest
PublishPort=8080:80
# host.containers.internal を使用してホストのサービスにアクセス
Environment="PROXY_BACKEND=http://host.containers.internal:8000"
# または直接 IP アドレスを指定
Environment="PROXY_BACKEND=http://192.168.0.17:8000"
```

✅ 修正後の確認：

```bash
podman logs app-container | grep -i "proxy\|connection"
# ログに接続成功を示すメッセージが表示されていれば成功です。
# あるいは curl で動作確認: podman exec app-container curl http://host.containers.internal:8000
```

### 原因3：コンテナ間通信のネットワーク設定不備

複数の[コンテナ](/glossary/コンテナ/)が[通信](/glossary/通信/)する必要がある場合、それらが同じ Podman [ネットワーク](/glossary/ネットワーク/)上に配置されていないと、[コンテナ](/glossary/コンテナ/)間の[通信](/glossary/通信/)が失敗します。特に Quadlet で複数サービスを定義する際に、[ネットワーク](/glossary/ネットワーク/)を明示的に定義していないと、各[コンテナ](/glossary/コンテナ/)がデフォルトネットワークに接続された状態では[通信](/glossary/通信/)が正常に機能しないことがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# /etc/containers/systemd/backend.container
[Container]
Image=myapp:backend
PublishPort=8000:8000
# ネットワークが明示的に指定されていない

# /etc/containers/systemd/frontend.container
[Container]
Image=myapp:frontend
PublishPort=8080:80
# ネットワークが明示的に指定されていない
# frontend が backend に http://backend:8000 でアクセスしようとしても失敗
```

**After（修正後）：**

```yaml
# /etc/containers/systemd/app.network
[Network]
NetworkName=app-network

# /etc/containers/systemd/backend.container
[Container]
Image=myapp:backend
PublishPort=8000:8000
Network=app-network

# /etc/containers/systemd/frontend.container
[Container]
Image=myapp:frontend
PublishPort=8080:80
Network=app-network
# frontend が backend に http://backend:8000 でアクセス可能になる
```

✅ 修正後の確認：

```bash
podman network ls
# app-network が表示されていることを確認
podman exec frontend-container curl http://backend:8000
# backend への接続が成功し、レスポンスが返されれば成功です。
```

### 原因4：ランタイム変更によるシステムコール非互換

Podman のランタイムを `krun` などに切り替えた際に、新しいランタイムが必要なシステムコール（例：`FIONREAD`、`SIOCINQ`）をサポートしていないため、I/O 操作がハングアップまたは失敗します。これにより、[コンテナ](/glossary/コンテナ/)内の[アプリケーション](/glossary/アプリケーション/)がネットワークリクエストに応答できなくなり、ホストからは 502 [エラー](/glossary/エラー/)に見えます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# /etc/containers/containers.conf
[engine]
runtime = "krun"
# krun がシステムコール SIOCINQ をサポートしていない場合、
# コンテナ内のネットワーク I/O がハングアップ
```

**After（修正後）：**

```bash
# /etc/containers/containers.conf
[engine]
# デフォルトランタイム (runc) に戻す
runtime = "runc"

# または、krun を使用する場合は、互換性が確認されたバージョンを使用
# $ podman run --runtime=krun --version
# krun のバージョンと Podman のバージョンの互換性を確認
```

✅ 修正後の確認：

```bash
podman info | grep -A 5 "runtimes:"
# デフォルトランタイムが runc になっていることを確認
systemctl restart podman
podman run --rm nginx curl localhost
# コンテナが正常に起動してリクエストに応答すれば成功です。
```

### 原因5：Podman 5.0 のネットワークスタック変更（slirp4netns → pasta）

Podman 5.0 では、ユーザーモード・ネットワークスタックが `slirp4netns` から `pasta` に変更されました。既存の[コンテナ](/glossary/コンテナ/)設定が `pasta` と[互換性](/glossary/互換性/)がない場合（例：特定のポートマッピング、UDP トラフィック）、[通信](/glossary/通信/)が失敗して 502 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Podman 4.x で動作していた設定
podman run -p 8000:8000 -p 8001:8001/udp myapp:latest
# Podman 5.0 で実行すると、pasta との互換性問題で UDP ポートが機能しない
```

**After（修正後）：**

```bash
# Podman 5.0 で pasta と互換性のある設定に変更
podman run -p 8000:8000 -p 8001:8001 --network=slirp4netns:enable_sandbox=false myapp:latest
# または、slirp4netns に明示的に切り替える
podman run -p 8000:8000 --network=slirp4netns myapp:latest

# /etc/containers/containers.conf で pasta のパラメータを調整
# [engine]
# network_backend = "pasta"
# [network]
# pasta_options = ["--mtu=1500"]
```

✅ 修正後の確認：

```bash
podman run --rm -p 8000:8000 myapp:latest &
sleep 2
curl http://localhost:8000
# コンテナがリクエストに正常に応答すれば成功です。
```

## 解決策の早見表

| 解決策 | 実装難易度 | 再起動要否 | 対応[OS](/glossary/os/) |
|--------|-----------|-----------|-------|
| レジストリコンテナの再起動 | 低 | 必要 | 全[OS](/glossary/os/) |
| リバースプロキシ設定の修正 | 中 | 必要 | 全[OS](/glossary/os/) |
| コンテナネットワークの明示的定義 | 中 | 必要 | 全[OS](/glossary/os/) |
| ランタイムの変更またはダウングレード | 中 | 必要 | 全[OS](/glossary/os/) |
| ネットワークスタックパラメータ調整 | 高 | 必要 | Linuxのみ |

## ツール固有の注意点

**Podman のネットワークモード差異**：Podman はデフォルトでユーザーモード・[ネットワーク](/glossary/ネットワーク/)（`slirp4netns` または `pasta`）を使用します。これは `localhost` が[コンテナ](/glossary/コンテナ/)内のみのループバックである点が [Docker](/glossary/docker/) と異なります。[Docker](/glossary/docker/) では `--network=host` でホストの[ネットワーク](/glossary/ネットワーク/)名前空間を直接共有できますが、Podman では `host.containers.internal` を使用してホストのサービスにアクセスします。

**Quadlet との組み合わせ**：Podman v4.4 以降、systemd ネイティブの Quadlet [ファイル形式](/glossary/ファイル形式/)で[コンテナ](/glossary/コンテナ/)を管理できます。この場合、`[Network]` セクションで明示的に[ネットワーク](/glossary/ネットワーク/)を定義し、複数の `[Container]` で同じ[ネットワーク](/glossary/ネットワーク/)名を参照することが重要です。`podman-compose` や [YAML](/glossary/yaml/) ファイルとは異なり、Quadlet は各ファイルが独立して systemd サービスに変換されるため、[ネットワーク](/glossary/ネットワーク/)定義を別ファイルで明示的に記述する必要があります。

**Quay [インスタンス](/glossary/インスタンス/)の[バックエンド](/glossary/バックエンド/)確認**：自ホスト上で Quay を実行している場合、バックエンドストレージ（PostgreSQL、Redis 等）が正常に動作しているか確認してください。`podman logs quay-container` で[バックエンド](/glossary/バックエンド/)接続[エラー](/glossary/エラー/)が表示されていないか確認し、必要に応じてバックエンドサービスも再起動してください。

## それでも解決しない場合

ポドマン・レジストリサーバーの[ログ](/glossary/ログ/)を詳しく確認してください：

```bash
# Podman デーモンのログを確認
journalctl -u podman -n 50 -e
# または
podman logs <problematic-container>

# ネットワーク接続をデバッグ
podman run --rm alpine curl -v http://<backend-url>
# 詳細なネットワークレイヤー情報が表示されます

# DNS 解決の確認
podman run --rm alpine nslookup <service-name>
```

公式ドキュメント：[Podman Networking](https://docs.podman.io/en/latest/markdown/podman.1.html#network) および [Red Hat Solutions 6987158](https://access.redhat.com/solutions/6987158) で詳細なトラブルシューティング手順が提供されています。

Podman v4.x から v5.0 へのアップグレード後にこの[エラー](/glossary/エラー/)が発生した場合は、`podman --version` で[バージョン](/glossary/バージョン/)を確認し、[ネットワーク](/glossary/ネットワーク/)設定を v5.0 に対応させたかどうかを検証してください。

## 代替ツールの検討

この[エラー](/glossary/エラー/)が頻発して運用に支障が出る場合は、以下のツールへの移行を検討できます：

- **[Docker](/glossary/docker/)**：[Docker](/glossary/docker/) Desktop および [Docker](/glossary/docker/) Engine は[ネットワーク](/glossary/ネットワーク/)層の実装が安定しており、`host.containers.internal` の対応も [Docker](/glossary/docker/) 18.03 以降で標準化されています。Podman のランタイム変更やネットワークスタック変更による互換性問題が少ないため、安定性を優先する環境では有効です。

- **Rancher Desktop**：Rancher Desktop は [Docker](/glossary/docker/) と [Kubernetes](/glossary/kubernetes/) を統合した開発環境です。[GUI](/glossary/gui/) で[コンテナ](/glossary/コンテナ/)と[ネットワーク](/glossary/ネットワーク/)設定を管理でき、Podman のプレインな[コマンドライン](/glossary/コマンドライン/)よりもセットアップが直感的です。特にローカル開発環境では Podman よりも[デバッグ](/glossary/デバッグ/)が容易です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*