---
title: "Podman の 400 エラー：原因と解決策"
date: 2026-05-28
description: "Podman APIまたはレジストリへのリクエストの形式が正しくない。。podman runコマンドのオプション指定が誤っているなど、Podman 400 エラーの原因と解決策を解説。"
tags: ["Podman"]
errorCode: "400"
---

Podman実行時に「400 Bad Request」が出ています。このエラーはPodman [API](/glossary/api/)または[レジストリ](/glossary/レジストリ/)への[リクエスト](/glossary/リクエスト/)形式が正しくないことを示しており、コマンドオプションやイメージ指定の誤りが原因です。

## よくある原因

**podman runコマンドのオプション指定が誤っている**

`podman run` のオプション順序やフラグの書き方が間違っていると、Podmanは[リクエスト](/glossary/リクエスト/)を解析できず400エラーを返します。例えば、値が必要なオプション（`--name`、`--memory` など）に値を渡さない、または重複定義した場合に発生します。イメージ指定の前に全てのオプションを配置する必要があります。

**イメージ名またはタグの書き方が間違っている**

イメージ名やタグの形式が不正だと[リクエスト](/glossary/リクエスト/)が成立しません。[レジストリ](/glossary/レジストリ/)が指定されていない場合、Podmanはデフォルト[レジストリ](/glossary/レジストリ/)から検索しますが、タグ内に無効な文字が含まれていたり、参照形式が壊れていたりするとエラーになります。

**Podman [API](/glossary/api/)ソケットへの[リクエスト](/glossary/リクエスト/)の[JSON](/glossary/json/)形式が壊れている**

[REST](/glossary/rest/) [API](/glossary/api/)を直接呼び出す場合、[JSON](/glossary/json/)[ペイロード](/glossary/ペイロード/)の構文エラーや必須フィールドの不足があると400エラーが発生します。curlなどで[API](/glossary/api/)を叩く際にダブルクォートの閉じ忘れやカンマの欠落が原因になります。

## 解決手順

**ステップ1：コマンドオプションの正しい書き方を確認する**

```bash
# 使用しているサブコマンドのヘルプを表示
podman help run

# よく使うオプション例
podman run --name <コンテナ名> --memory 512m --cpus 1 <イメージ名>:<タグ>
```

`podman help run` でオプション一覧と説明を確認し、オプション順序やフラグの記述が正しいか検証します。イメージ指定は必ずオプション指定の後に配置してください。

**ステップ2：イメージ名とタグをpodman searchで検証する**

```bash
# イメージ検索でレジストリに存在するか確認
podman search alpine

# タグ付きで正確なイメージ名を指定
podman run alpine:3.18 /bin/sh

# レジストリを明示的に指定する場合
podman run docker.io/library/alpine:3.18 /bin/sh
```

`podman search` で目的のイメージが[レジストリ](/glossary/レジストリ/)に存在し、正確なタグ名を確認します。タグが存在しない、または大文字小文字が異なっている場合も400エラーになります。

**ステップ3：Podmanをバージョン確認し、必要に応じて更新する**

```bash
# 現在のPodmanバージョンを確認
podman --version

# 古い場合はシステムパッケージマネージャーで更新
# Red Hat系の場合
sudo dnf update podman

# Debian系の場合
sudo apt update && sudo apt upgrade podman
```

古いバージョンでは[API](/glossary/api/)仕様が異なり、新しいオプションが存在しないか動作が異なる可能性があります。

**ステップ4：[REST](/glossary/rest/) [API](/glossary/api/)で直接呼び出す場合は[JSON](/glossary/json/)形式をチェック**

```bash
# Podman APIソケット経由での不正なリクエスト例
curl -X POST --unix-socket /run/podman/podman.sock \
  http://localhost/v4.0.0/libpod/containers/create \
  -H "Content-Type: application/json" \
  -d '{"Image": "alpine", "Cmd": ["sh"]}'

# JSON形式の検証ツール（jq）で事前チェック
echo '{"Image": "alpine"}' | jq .
```

[JSON](/glossary/json/)形式を整形・検証してから送信してください。jq などのツールを使うとシンタックスエラーを事前に検出できます。

## それでも解決しない場合

Podmanのログを詳細に確認します。`--log-level=debug` フラグを使うか、systemdジャーナルで詳細なエラーメッセージを見ることで、[リクエスト](/glossary/リクエスト/)のどの部分が問題かが判明します。

```bash
# デバッグレベルでのログ出力
podman --log-level=debug run <イメージ名>

# systemdジャーナル確認
journalctl -u podman -n 50
```

また、[コンテナ](/glossary/コンテナ/)[レジストリ](/glossary/レジストリ/)の[認証](/glossary/認証/)情報が古いか無効な場合も400エラーになります。`podman logout` で[クレデンシャル](/glossary/クレデンシャル/)をクリアし、必要に応じて `podman login` で再度[認証](/glossary/認証/)してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サ[ポート](/glossary/ポート/)ページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*