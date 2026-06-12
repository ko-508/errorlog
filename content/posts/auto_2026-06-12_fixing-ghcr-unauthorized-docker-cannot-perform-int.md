---
title: "GitHub ActionsとSSHデプロイにおけるGHCRのUnauthorizedエラーとDockerのCannot perform interactive login from non-TTYエラーの解決策"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "GitHub Container Registry (GHCR) を利用する際に発生する認証エラーと、Dockerの非対話型ログインエラーの原因と解決策を、GitHub ActionsとSSHデプロイの文脈で詳しく解説します。"
tags: ["Dev.to - Docker", "GitHub Actions", "Docker", "GHCR", "認証エラー"]
trend_incident: true
---

## エラーの概要

この記事では、GitHub Container Registry (GHCR) を利用する際に発生する「Unauthorized」エラーと、Dockerコマンド実行時に発生する「Cannot perform interactive login from non-TTY」エラーについて解説します。これらのエラーは、主にGitHub ActionsやSSH経由でのデプロイ環境で、Dockerイメージのプッシュやプルを行う際に認証情報が正しく渡されていない場合に発生します。

## 実際のエラーメッセージ例

GitHub Actionsのログやコンソール出力では、以下のようなエラーメッセージが表示されます。

**GHCR Unauthorizedエラーの例:**

```
Error: denied: unauthorized: You don't have permission to access the requested resource.
```

**Docker Cannot perform interactive login from non-TTYエラーの例:**

```
Cannot perform an interactive login from a non TTY device
```

## よくある原因と解決手順

### 原因1：認証情報の不足または誤り

GHCRへのアクセスには認証が必要です。GitHub ActionsやSSHデプロイ環境で認証情報が提供されていない、または誤った情報が使用されている場合に「Unauthorized」エラーが発生します。

**Before（エラーが起きるコード）：**

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches:
      - main

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t ghcr.io/<your-github-username>/<your-repo-name>:<your-tag> .

      - name: Push Docker image
        run: docker push ghcr.io/<your-github-username>/<your-repo-name>:<your-tag>
        # ここで認証情報が不足しているためエラーが発生
```

**After（修正後）：**

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches:
      - main

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }} # GitHub Actionsの実行ユーザー
          password: ${{ secrets.GITHUB_TOKEN }} # GitHubが提供するトークン

      - name: Build Docker image
        run: docker build -t ghcr.io/<your-github-username>/<your-repo-name>:<your-tag> .

      - name: Push Docker image
        run: docker push ghcr.io/<your-github-username>/<your-repo-name>:<your-tag>
```

### 原因2：非対話型環境での`docker login`の誤用

GitHub ActionsやSSH経由のデプロイ環境は非対話型（non-TTY）です。このような環境で`docker login`コマンドを引数なしで実行すると、ユーザー名とパスワードの入力を求められ、それができないために「Cannot perform interactive login from non-TTY」エラーが発生します。

**Before（エラーが起きるコード）：**

```bash
# SSH経由で実行されるスクリプトやGitHub Actionsのrunステップ
docker login ghcr.io
# この後、ユーザー名とパスワードの入力を求められるが、非対話型環境では入力できない
```

**After（修正後）：**

```bash
# SSH経由で実行されるスクリプトやGitHub Actionsのrunステップ
echo <your-github-token> | docker login ghcr.io -u <your-github-username> --password-stdin
```
または、GitHub Actionsの場合は`docker/login-action`を使用します。

```yaml
# .github/workflows/deploy.yml
# ...
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
# ...
```

### 原因3：GitHub Personal Access Token (PAT) の権限不足

GHCRへのアクセスには、適切なスコープを持つGitHub Personal Access Token (PAT) が必要です。`GITHUB_TOKEN`は通常、リポジトリへの読み書き権限を持ちますが、GHCRへのプッシュには`write:packages`スコープが必要です。PATを使用する場合は、このスコープを付与する必要があります。

**Before（エラーが起きるコード）：**

PATを作成する際に、`repo`スコープのみを選択している。

**After（修正後）：**

PATを作成する際に、`repo`スコープに加えて`write:packages`スコープを選択する。

**GitHub ActionsでのPATの利用例:**

```yaml
# .github/workflows/deploy.yml
# ...
      - name: Log in to GHCR with PAT
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: <your-github-username>
          password: ${{ secrets.GHCR_PAT }} # リポジトリのSecretsにGHCR_PATとして保存
# ...
```

## ツール固有の注意点

*   **GitHub Actions:**
    *   `GITHUB_TOKEN`は、ワークフローが実行されているリポジトリのGHCRに対して自動的に認証されます。通常、`docker/login-action`と組み合わせることで、追加のPATなしでイメージのプッシュ・プルが可能です。
    *   ただし、他のリポジトリのGHCRにアクセスする場合や、`GITHUB_TOKEN`のデフォルト権限では不足する高度な操作を行う場合は、適切なスコープを持つPATをSecretsとして設定し、それを使用する必要があります。
    *   `docker/login-action`は、`~/.docker/config.json`に認証情報を自動的に書き込んでくれるため、その後の`docker push`や`docker pull`コマンドで認証情報を明示的に渡す必要がありません。

*   **SSHデプロイ:**
    *   SSH経由でデプロイする場合、GitHub Actionsのように`GITHUB_TOKEN`が自動的に利用できるわけではありません。
    *   `docker login`コマンドを使用する際は、必ず`--password-stdin`オプションと、適切な権限を持つPATをパイプで渡す形式を使用してください。
    *   PATは環境変数として渡すか、安全な方法でスクリプトに埋め込む必要があります。本番環境では、パスワードを直接スクリプトに記述せず、環境変数やシークレット管理ツールを利用することを強く推奨します。

## それでも解決しない場合

1.  **GitHub Actionsのログを確認する:**
    *   `docker/login-action`のステップが成功しているか確認します。
    *   `docker push`や`docker pull`コマンドの直前のログに、認証に関する警告やエラーがないか詳細に確認します。
    *   `GITHUB_TOKEN`の権限が不足している場合、GitHub Actionsのワークフロー実行ログに権限に関する警告が表示されることがあります。

2.  **PATのスコープを確認する:**
    *   使用しているPersonal Access Token (PAT) のスコープが、`write:packages`を含んでいるかGitHubのSettings > Developer settings > Personal access tokensで再確認します。

3.  **Docker設定ファイルを確認する:**
    *   デプロイ環境で`~/.docker/config.json`ファイルが存在する場合、その内容を確認し、GHCRの認証情報が正しく記述されているか確認します。
    *   特にSSHデプロイの場合、`docker login`が成功していればこのファイルに認証情報が保存されます。

4.  **公式ドキュメントを参照する:**
    *   GitHub Container Registryの公式ドキュメント: [https://docs.github.com/ja/packages/working-with-a-github-packages-registry/working-with-the-container-registry](https://docs.github.com/ja/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
    *   GitHub ActionsでのDocker Loginアクション: [https://github.com/docker/login-action](https://github.com/docker/login-action)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*