---
title: "Docker の 401 エラー：原因と解決策"
date: 2026-01-01
description: "Docker で 401 エラーが発生するのは、レジストリ（Docker Hub や ECR、プライベートレジストリなど）への認証に失敗したときです。認証情報が提供されていない、または提供されていても無効・期限切れの場合に表示されます。"
tags: ["Docker"]
errorCode: "401"
lastmod: 2026-06-26
service: "Docker"
error_type: "401"
components: ["Registry"]
related_services: ["Docker Hub", "Azure Container Registry", "ECR"]
trend_incident: true
---

## エラーの概要

[Docker](/glossary/docker/)で401[エラー](/glossary/エラー/)が発生するのは、[レジストリ](/glossary/レジストリ/)（[Docker](/glossary/docker/) Hub、ECR、[プライベートレジストリ](/glossary/プライベートレジストリ/)など）への[認証](/glossary/認証/)に失敗したときです。認証情報が提供されていない、または提供されていても無効・期限切れの場合に表示されます。特に `docker pull`、`docker push`、`docker login` の実行時によく見られます。

なお、2020年11月以降、[Docker](/glossary/docker/) Hubの匿名（[ログイン](/glossary/ログイン/)なし）でのイメージダウンロード数に制限が導入されたため、以前は[ログイン](/glossary/ログイン/)なしで利用できていたパブリックイメージでも、現在は[認証](/glossary/認証/)が必須になるケースが増えています。

## 実際のエラーメッセージ例

```
Error response from daemon: unauthorized: incorrect username or password
```

```json
{
  "errors": [
    {
      "code": "UNAUTHORIZED",
      "message": "authentication required",
      "detail": null
    }
  ]
}
```

```
Error response from daemon: Get "https://registry-1.docker.io/v2/": unauthorized: authentication required, 401
```

## よくある原因と解決手順

### 原因1：Docker Hubへのログインが完了していない

[Docker](/glossary/docker/) Hubのパブリックイメージであっても、[ダウンロード](/glossary/ダウンロード/)数制限により[認証](/glossary/認証/)が必須になるケースがあります。また、プライベートイメージにアクセスする場合は必ず[認証](/glossary/認証/)が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ログインなしで直接pullを実行
docker pull <your-username>/<image-name>:latest
```

**After（修正後）：**

```bash
# 最初にDocker Hubにログイン
docker login

# プロンプトにユーザー名とパスワード（またはPersonal Access Token）を入力
# その後でpullを実行
docker pull <your-username>/<image-name>:latest
```

### 原因2：AWS ECRの認証トークンが期限切れ

ECRの[認証](/glossary/認証/)[トークン](/glossary/トークン/)は12時間の有効期限があります。[Docker](/glossary/docker/) daemonに保存された[トークン](/glossary/トークン/)が期限切れになると401[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 古いトークンで直接pullを試行
docker pull <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/<your-repository>:<your-tag>
```

**After（修正後）：**

```bash
# AWS CLIで認証トークンを再取得し、Docker daemonに設定
aws ecr get-login-password --region <your-region> | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.<your-region>.amazonaws.com

# その後でpullを実行
docker pull <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/<your-repository>:<your-tag>
```

### 原因3：設定ファイル（config.json）の認証情報が破損または形式が不正

`~/.docker/config.json` に保存された認証情報が破損しているか、[レジストリ](/glossary/レジストリ/)のホスト名が正確に記録されていない場合に発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "auths": {
    "docker.io": {
      "auth": "invalid_base64_or_corrupted_data"
    }
  }
}
```

**After（修正後）：**

```bash
# 既存の認証情報をクリア
rm ~/.docker/config.json

# 新規ログインで正しい認証情報を再設定
docker login
```

### 原因4：プライベートレジストリのための認証情報が不足

Nexus、Harbor、GitLab Container Registry など自社運用の[プライベートレジストリ](/glossary/プライベートレジストリ/)にアクセスする際、ホスト名と[ポート](/glossary/ポート/)番号を含めた完全な[レジストリ](/glossary/レジストリ/)[URL](/glossary/url/)で[認証](/glossary/認証/)を設定する必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# プライベートレジストリにログインせず、イメージをpull
docker pull registry.internal.example.com:5000/my-image:v1.0
```

**After（修正後）：**

```bash
# 完全なレジストリURLでログイン
docker login registry.internal.example.com:5000

# ユーザー名・パスワード・パスフレーズを入力
docker pull registry.internal.example.com:5000/my-image:v1.0
```

### 原因5：Personal Access Token（PAT）の権限不足またはスコープ制限

[Docker](/glossary/docker/) Hubで[パスワード](/glossary/パスワード/)代わりにPATを使用している場合、その[トークン](/glossary/トークン/)に必要な[権限](/glossary/権限/)（Read、Write など）が付与されていないと401[エラー](/glossary/エラー/)になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Read権限のみのPATで push を試行
docker login --username <your-username>
# パスワード入力欄に読み取り専用のPATを入力
docker push <your-username>/<your-image>:latest
```

**After（修正後）：**

```bash
# Docker Hub ウェブサイト > Account Settings > Security > Personal Access Tokens へアクセス
# 「Read & Write」の権限を持つ新しいPATを生成

docker logout
docker login --username <your-username>
# パスワード入力欄に新しいPATを入力
docker push <your-username>/<your-image>:latest
```

## ツール固有の注意点

### Docker Compose での認証設定

`docker-compose.yml` で複数の[レジストリ](/glossary/レジストリ/)から[イメージ](/glossary/イメージ/)をpullする場合、各[レジストリ](/glossary/レジストリ/)への事前[ログイン](/glossary/ログイン/)が必要です。Compose ファイル内に認証情報を直接記述することは[セキュリティ](/glossary/セキュリティ/)上推奨されません。

```bash
# docker-compose.yml 実行前に全レジストリにログイン
docker login docker.io
docker login <your-account-id>.dkr.ecr.<your-region>.amazonaws.com
docker login registry.internal.example.com:5000

# その後

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
