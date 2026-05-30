---
title: "Docker Compose の 401 エラー：原因と解決策"
date: 2026-05-30
description: "コンテナレジストリへの認証に失敗した。Docker Compose 401 エラーの原因と解決策を解説します。"
tags: ["Docker Compose"]
errorCode: "401"
---
Docker Composeで401エラーが発生した場合、コンテナーレジストリーへの認証に失敗しています。このエラーはプライベートイメージをpullしようとする際に最も頻繁に起こります。

## よくある原因

**docker loginを実行していない**

docker composeを実行する前にdocker loginコマンドで認証を済ませていないと、プライベートレジストリーのイメージをpullできません。認証情報が保存されていないため、レジストリー側は401（認証が必要）で応答します。

**compose.yml内のimageフィールドでプライベートレジストリーを参照しているが認証されていない**

compose.ymlでプライベートレジストリーのイメージを指定している場合、そのレジストリーに対する認証が完了していないと401エラーになります。例えば `image: myregistry.azurecr.io/myapp:latest` のようなURLが含まれているのに認証がないパターンです。

**CI/CD環境で認証情報が渡されていない**

GitHub ActionsやJenkinsなどのCI/CD環境ではローカルのdocker loginが存在しません。認証情報を環境変数またはシークレット経由で明示的に渡す必要があります。これを忘れるとdocker compose pullが失敗します。

## 解決手順

**ステップ1：ローカル環境での認証を確認する**

まずdocker loginコマンドでレジストリーに認証します。Docker Hubの場合は以下を実行します。

```bash
docker login
```

プロンプトに従ってユーザー名とパスワードを入力します。プライベートレジストリー（Azure Container Registry、AWS ECR、GCP Artifact Registryなど）の場合はレジストリーURLを指定します。

```bash
docker login <レジストリーURL>
# 例：Azure Container Registryの場合
docker login myregistry.azurecr.io
```

**ステップ2：compose.ymlのimageフィールドを確認する**

compose.ymlでイメージパスが正確に指定されているか確認します。プライベートレジストリーを使用している場合、フルパスにレジストリーURLを含める必要があります。

```yaml
version: '3.8'
services:
  app:
    image: myregistry.azurecr.io/myapp:latest
    # または
    image: <レジストリーURL>/<リポジトリー>:<タグ>
```

**ステップ3：docker compose pullを実行する**

認証後、docker compose pullコマンドでイメージをpullしてから、docker compose upを実行します。

```bash
docker compose pull
docker compose up -d
```

**ステップ4：CI/CD環境での認証設定**

GitHub Actionsの場合、以下のようにシークレットを使用して認証情報を渡します。

```yaml
- name: Log in to Container Registry
  run: |
    echo "${{ secrets.REGISTRY_PASSWORD }}" | docker login \
      -u "${{ secrets.REGISTRY_USERNAME }}" \
      --password-stdin <レジストリーURL>

- name: Pull and run Docker Compose
  run: docker compose pull && docker compose up -d
```

GitLabの場合は、`.gitlab-ci.yml`内で環境変数を設定します。

```yaml
deploy:
  image: docker:latest
  services:
    - docker:dind
  before_script:
    - echo $REGISTRY_PASSWORD | docker login -u $REGISTRY_USERNAME --password-stdin $REGISTRY_URL
  script:
    - docker compose pull
    - docker compose up -d
```

**ステップ5：認証情報の確認**

docker configコマンドで、現在の認証情報が正しく保存されているか確認できます。

```bash
cat ~/.docker/config.json
```

このファイルにレジストリーのエントリが存在し、認証トークンが保存されていることを確認します。

## それでも解決しない場合

認証情報を一度クリアしてから再度ログインしてください。以前の間違った認証情報がキャッシュされている可能性があります。

```bash
docker logout <レジストリーURL>
docker login <レジストリーURL>
```

また、IAMロール（AWS ECRやGCP Artifact Registryの場合）やマネージド認証（Azure Container Registryの場合）を使用している環境では、ローカルのdocker loginではなくクラウドプロバイダーの認証メカニズムを活用する必要があります。各プロバイダーの公式ドキュメントで、Docker Composeとの統合方法を確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*