---
title: "Podman の 401 エラー：原因と解決策"
date: 2026-05-28
lastmod: 2026-05-31
description: "Podmanでコンテナイメージをpullやpushしようとすると、401認証エラーが発生することがあります。このエラーはレジストリへの認証に失敗したときに出現し、適切な認証情報がないか有効期限切れの状態を示しています。"
tags: ["Podman"]
errorCode: "401"
service: "Podman"
error_type: "401"
components: []
related_services: ["Docker Hub", "GCR"]
---

Podmanでコンテナイメージをpullやpushしようとすると、401[認証](/glossary/認証/)[エラー](/glossary/エラー/)が発生することがあります。この[エラー](/glossary/エラー/)は[レジストリ](/glossary/レジストリ/)への[認証](/glossary/認証/)に失敗したときに出現し、適切な認証情報がないか有効期限切れの状態を示しています。

## よくある原因

### podman loginを実行していない
Podmanで[レジストリ](/glossary/レジストリ/)から[イメージ](/glossary/イメージ/)を取得するには、事前に[認証](/glossary/認証/)を完了する必要があります。[ログイン](/glossary/ログイン/)処理を行わずにpull[コマンド](/glossary/コマンド/)を実行すると、認証情報がないため401[エラー](/glossary/エラー/)が発生します。特に新しい環境構築時や、別の[レジストリ](/glossary/レジストリ/)を利用する場合に見落とされやすいです。

### 認証トークンの有効期限が切れている
[レジストリ](/glossary/レジストリ/)が発行した[認証](/glossary/認証/)[トークン](/glossary/トークン/)には有効期限が設定されていることが多いです。数週間から数ヶ月経過すると、以前[ログイン](/glossary/ログイン/)した認証情報が無効化されてしまい、401[エラー](/glossary/エラー/)が返されます。

### ~/.config/containers/auth.jsonの認証情報が古い
Podmanは[ログイン](/glossary/ログイン/)時の認証情報を `~/.config/containers/auth.json` に保存します。このファイルの内容が古い、破損している、または複数の[レジストリ](/glossary/レジストリ/)情報が混在していると、401[エラー](/glossary/エラー/)が発生することがあります。

## 解決手順

### ステップ1：現在のログイン状態を確認する
まず、どの[レジストリ](/glossary/レジストリ/)に対して認証情報が保存されているか確認します。

```bash
# auth.jsonの内容を確認
cat ~/.config/containers/auth.json
```

ファイルが存在しない場合や、対象の[レジストリ](/glossary/レジストリ/)URLが記載されていなければ、[ログイン](/glossary/ログイン/)が必要です。

### ステップ2：対象のレジストリに再ログインする
次の[コマンド](/glossary/コマンド/)で[レジストリ](/glossary/レジストリ/)に対してpodman loginを実行します。[レジストリ](/glossary/レジストリ/)URLは正確に指定してください。

```bash
# Docker Hubの場合
podman login docker.io

# プライベートレジストリの場合（例：プライベートGCR）
podman login gcr.io

# ユーザー名とパスワードを聞かれるので入力する
# Username: <your-username>
# Password: <your-password>
```

[ログイン](/glossary/ログイン/)が成功すると、認証情報が `~/.config/containers/auth.json` に保存されます。

### ステップ3：auth.jsonを削除して再ログインする
上記ステップで解決しない場合、auth.jsonを完全に削除した上で再度[ログイン](/glossary/ログイン/)してください。この方法で古い認証情報をクリアできます。

```bash
# auth.jsonを削除
rm ~/.config/containers/auth.json

# 再度ログイン処理を実行
podman login <レジストリURL>
```

削除後、新しい認証情報が`~/.config/containers/auth.json`に保存されます。

### ステップ4：レジストリURLが正しく指定されているか確認する
pullやpush[コマンド](/glossary/コマンド/)を実行する際、指定している[レジストリ](/glossary/レジストリ/)URLが正確か確認します。[レジストリ](/glossary/レジストリ/)URLが異なると、別の[レジストリ](/glossary/レジストリ/)として認識され、[認証](/glossary/認証/)[エラー](/glossary/エラー/)が発生します。

```bash
# 正しいレジストリURLでpullを実行
podman pull docker.io/library/ubuntu:latest

# pullが成功することを確認
podman images
```

[ログイン](/glossary/ログイン/)後にpull[コマンド](/glossary/コマンド/)を再度実行して、401[エラー](/glossary/エラー/)が解消されたか確認します。

## それでも解決しない場合

[ファイアウォール](/glossary/ファイアウォール/)や[プロキシ](/glossary/プロキシ/)が認証通信をブロックしていないか確認してください。企業[ネットワーク](/glossary/ネットワーク/)では[HTTP](/glossary/http/)[プロキシ](/glossary/プロキシ/)経由で[レジストリ](/glossary/レジストリ/)にアクセスする必要があるケースがあります。Podmanの場合、[プロキシ](/glossary/プロキシ/)設定は `~/.config/containers/registries.conf` で行います。

また、[レジストリ](/glossary/レジストリ/)が要求する[スコープ](/glossary/スコープ/)（scope）が限定されている場合、[認証](/glossary/認証/)[トークン](/glossary/トークン/)の生成時に[スコープ](/glossary/スコープ/)を指定しなければならないことがあります。詳細は[レジストリ](/glossary/レジストリ/)の公式ドキュメントを確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*