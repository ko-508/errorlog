---
title: "Podman の 503 エラー：原因と解決策"
date: 2026-05-29
description: "Podmanサービスまたはレジストリが一時的に利用できない。Podman APIサービスが起動していないなど、Podman 503 エラーの原因と解決策を解説。"
tags: ["Podman"]
errorCode: "503"
service: "Podman"
error_type: "503"
components: []
related_services: ["Docker Hub", "Quay.io", "Docker"]
---
Podman の 503 [エラー](/glossary/エラー/)が発生した場合、Podman [API](/glossary/api/) サービスやコンテナレジストリが一時的に利用できない状態です。以下の手順で原因を特定し、解決します。

## よくある原因

**Podman [API](/glossary/api/) サービスが起動していない**

Podman を使用する際、バックグラウンドで動作する Podman [API](/glossary/api/) サービス（podman.socket）が停止しています。このサービスが起動していないと、[コンテナ](/glossary/コンテナ/)の管理操作や[レジストリ](/glossary/レジストリ/)へのアクセスができなくなります。特に、Podman をシステムサービスとして起動する場合や、リモート接続を使用する場合に多く発生します。

**コンテナレジストリが一時的に停止またはメンテナンス中**

[Docker](/glossary/docker/) Hub や Quay.io などのコンテナレジストリが予期しないダウンタイムやメンテナンス作業中の場合、[イメージ](/glossary/イメージ/)のプル操作時に 503 [エラー](/glossary/エラー/)が返されます。これは[レジストリ](/glossary/レジストリ/)側の問題であるため、[レジストリ](/glossary/レジストリ/)の復旧を待つ必要があります。

**[ネットワーク](/glossary/ネットワーク/)接続に問題がある**

Podman が実行されているホストとコンテナレジストリ間の[ネットワーク](/glossary/ネットワーク/)接続が切断されている、またはファイアウォールルールが[レジストリ](/glossary/レジストリ/)へのアクセスをブロックしている場合、503 [エラー](/glossary/エラー/)が発生します。[DNS](/glossary/dns/) 解決の失敗も同様の症状を引き起こします。

## 解決手順

**ステップ 1: Podman [API](/glossary/api/) サービスの状態を確認する**

まず、Podman [API](/glossary/api/) サービスが正常に起動しているか確認します。以下の[コマンド](/glossary/コマンド/)を実行してください。

```bash
systemctl status podman.socket
```

出力例として `active (running)` と表示されていれば、サービスは起動しています。`inactive (dead)` や `failed` と表示されている場合は、次のステップでサービスを起動します。

**ステップ 2: Podman [API](/glossary/api/) サービスを起動する**

サービスが停止している場合、以下の[コマンド](/glossary/コマンド/)で起動します。

```bash
systemctl start podman.socket
```

システムブート時に自動的にサービスが起動するように設定する場合は、以下の[コマンド](/glossary/コマンド/)を実行してください。

```bash
systemctl enable podman.socket
```

**ステップ 3: [ネットワーク](/glossary/ネットワーク/)接続を確認する**

[レジストリ](/glossary/レジストリ/)への接続テストを行います。以下の[コマンド](/glossary/コマンド/)でインターネット接続を確認してください。

```bash
ping 8.8.8.8
```

接続が確認できない場合は、ネットワークインターフェースの設定を確認するか、[ファイアウォール](/glossary/ファイアウォール/)設定を見直します。[DNS](/glossary/dns/) 解決を確認する場合は以下を実行します。

```bash
nslookup docker.io
```

**ステップ 4: [レジストリ](/glossary/レジストリ/)のステータスを確認する**

使用しているコンテナレジストリの公式ステータスページを確認します。[Docker](/glossary/docker/) Hub であれば `https://www.docker.com/status` で、Quay.io であれば `https://status.quay.io` で確認できます。障害情報が掲示されている場合は、復旧を待つ必要があります。

**ステップ 5: Podman サービスをリスタートする**

上記の確認後も問題が解決しない場合は、以下の[コマンド](/glossary/コマンド/)で Podman サービス全体をリスタートします。

```bash
systemctl restart podman
systemctl restart podman.socket
```

## それでも解決しない場合

Podman の[ログ](/glossary/ログ/)を詳細に確認して、具体的なエラーメッセージを取得します。

```bash
journalctl -u podman -n 50
journalctl -u podman.socket -n 50
```

代替[レジストリ](/glossary/レジストリ/)の使用も検討してください。例えば、[Docker](/glossary/docker/) Hub の代わりに Quay.io や独自の[レジストリ](/glossary/レジストリ/)を使用する場合、Podman の[設定ファイル](/glossary/設定ファイル/) `/etc/containers/registries.conf` を編集して、[レジストリ](/glossary/レジストリ/)の優先順位やミラーサーバーを指定できます。

```yaml
[[registry]]
location = "docker.io"
mirror = [
  "https://mirror.example.com"
]
```

それでも解決しない場合は、Podman の再インストールやシステムの再起動を検討してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*