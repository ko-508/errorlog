---
draft: true
title: "Podman の 404 エラー：原因と解決策"
date: 2026-05-29
description: "指定したイメージまたはコンテナが見つからない"
tags: ["Podman"]
errorCode: "404"
service: "Podman"
error_type: "404"
components: []
related_services: ["Docker", "Docker Hub"]
lastmod: 2026-06-14
---

## エラーの概要

Podman で 404 [エラー](/glossary/エラー/)が発生した場合、指定した[イメージ](/glossary/イメージ/)またはコンテナーがシステム上に見つからないことを意味します。[コマンド](/glossary/コマンド/)実行時に[イメージ](/glossary/イメージ/)名やコンテナー名の指定に問題があるケースがほとんどです。この[エラー](/glossary/エラー/)は[イメージ](/glossary/イメージ/)の取得・実行・削除などの操作で頻繁に遭遇します。

## 実際のエラーメッセージ例

```
Error: image not found: ubuntu:latestt
```

```
Error: container not found: <container-id>
```

```json
{
  "error": "image not found: myregistry.azurecr.io/myimage:v1.0",
  "code": 404
}
```

## よくある原因と解決手順

### 原因1：イメージ名またはタグ名の綴りが間違っている

Podman [コマンド](/glossary/コマンド/)を実行する際、[イメージ](/glossary/イメージ/)名のスペルミスや[タグ](/glossary/タグ/)名の入力誤りがあると 404 [エラー](/glossary/エラー/)が発生します。例えば `podman run ubuntu:latestt` のように「latestt」と誤入力した場合、その[タグ](/glossary/タグ/)は存在しないため見つかりません。レジストリー名を含める場合も、プレフィックスの綴り間違いが原因となることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
podman run ubuntu:latestt
# Error: image not found: ubuntu:latestt
```

**After（修正後）：**

```bash
# 正しいタグ名を確認して実行
podman pull ubuntu:latest
podman run ubuntu:latest
```

### 原因2：ローカルにもリモートにもイメージが存在しない

[イメージ](/glossary/イメージ/)名が正しく入力されていても、Podman がローカルストレージ内にその[イメージ](/glossary/イメージ/)を持たず、かつリモートレジストリーからも取得できない場合に 404 [エラー](/glossary/エラー/)が発生します。特にプライベートレジストリーの[イメージ](/glossary/イメージ/)を使用する場合、レジストリーへの[認証](/glossary/認証/)がないと取得に失敗することがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
podman run myregistry.example.com/myapp:v1.0
# Error: image not found: myregistry.example.com/myapp:v1.0
```

**After（修正後）：**

```bash
# レジストリーに認証してからイメージを取得
podman login myregistry.example.com
podman pull myregistry.example.com/myapp:v1.0
podman run myregistry.example.com/myapp:v1.0
```

### 原因3：イメージをプルしていない

Dockerfile からビルドしたカスタムイメージや、別のシステムで作成された[イメージ](/glossary/イメージ/)を使用する際、ローカルに存在しない[イメージ](/glossary/イメージ/)を直接実行しようとすると 404 [エラー](/glossary/エラー/)が発生します。[イメージ](/glossary/イメージ/)の存在確認や事前プルが必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
podman run myapp:1.0
# Error: image not found: myapp:1.0
```

**After（修正後）：**

```bash
# 利用可能なイメージを確認
podman images

# イメージが存在しない場合はプルまたはビルド
podman pull docker.io/library/myapp:1.0
# または
podman build -t myapp:1.0 .
podman run myapp:1.0
```

### 原因4：コンテナー ID またはコンテナー名が誤っている

`podman stop`、`podman rm`、`podman inspect` などの操作でコンテナーを指定する際、存在しないコンテナー [ID](/glossary/id/) やコンテナー名を指定すると 404 [エラー](/glossary/エラー/)が発生します。特に長いコンテナー [ID](/glossary/id/) の一部を誤入力した場合に注意が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
podman stop abc12345
# Error: container not found: abc12345
```

**After（修正後）：**

```bash
# 実行中のコンテナーを確認
podman ps

# 正しいコンテナー ID またはコンテナー名を指定
podman stop abc123456789abcdef
# またはコンテナー名で指定
podman stop mycontainer
```

## Podman 固有の注意点

Podman はデーモンレスで動作するため、ユーザーコンテキストごとにイメージストレージが独立しています。root ユーザーで `podman pull` した[イメージ](/glossary/イメージ/)を通常ユーザーで実行しようとすると 404 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# root で実行
sudo podman pull ubuntu:latest

# 通常ユーザーで実行
podman run ubuntu:latest
# Error: image not found: ubuntu:latest
```

**After（修正後）：**

```bash
# ユーザーのコンテキストで一貫性を保つ
podman pull ubuntu:latest
podman run ubuntu:latest

# または root で統一
sudo podman pull ubuntu:latest
sudo podman run ubuntu:latest
```

また、Podman のレジストリー[設定ファイル](/glossary/設定ファイル/)（`$HOME/.config/containers/registries.conf`）が正しく設定されていないと、デフォルトレジストリーからの[イメージ](/glossary/イメージ/)取得に失敗する可能性があります。デフォルトでは[スコープ](/glossary/スコープ/)なしで[イメージ](/glossary/イメージ/)名を指定した場合、[設定ファイル](/glossary/設定ファイル/)に記載されたレジストリーから順に検索されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
podman run nginx
# Error: image not found: nginx
# registries.conf でレジストリーが未設定
```

**After（修正後）：**

```bash
# registries.conf を確認・編集
cat ~/.config/containers/registries.conf

# 必要に応じてレジストリーを完全修飾名で指定
podman pull docker.io/library/nginx
podman run docker.io/library/nginx
```

## それでも解決しない場合

ローカルに保存されている[イメージ](/glossary/イメージ/)を確認するには `podman images` [コマンド](/glossary/コマンド/)で一覧表示できます。この[コマンド](/glossary/コマンド/)の出力に目的の[イメージ](/glossary/イメージ/)が存在しない場合は、明示的に `podman pull` で[イメージ](/glossary/イメージ/)を取得する必要があります。

レジストリー接続の問題を切り分ける場合は、`podman pull` を単独で実行して[ネットワーク](/glossary/ネットワーク/)接続やレジストリー[認証](/glossary/認証/)に問題がないかを確認します。認証情報がある場合は `podman login` で事前[ログイン](/glossary/ログイン/)しておきます。

詳細な[デバッグ](/glossary/デバッグ/)情報を得るには、`podman --log-level=debug` オプションを付けて[コマンド](/glossary/コマンド/)を再実行することで、[イメージ](/glossary/イメージ/)検索の詳細なプロセスを確認できます。

Podman の公式ドキュメントにある「Podman Image Search」セクションでは、レジストリー設定や[イメージ](/glossary/イメージ/)取得の詳細が説明されています。また、GitHub の Podman [リポジトリ](/glossary/リポジトリ/)の Issues セクションで、類似の[エラー](/glossary/エラー/)報告と解決方法を検索することも有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*