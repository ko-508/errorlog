---
title: "Vercel の 401 エラー：原因と解決策"
date: 2026-06-06
description: "Vercelへの認証に失敗した。Vercel 401 エラーの原因と解決策を解説します。"
tags: ["Vercel"]
errorCode: "401"
---
## Vercel 401 エラーの原因と解決方法

## エラーの概要

Vercel 401 エラーは、Vercel のサーバーに対して実施した認証に失敗したことを示します。API トークンの無効化、環境変数の設定漏れ、外部サービス連携の切断など、認証周辺の問題が原因となり、デプロイや CLI 操作が停止します。このエラーが発生するとプロジェクトのデプロイメントパイプラインが停止するため、素早い対応が必要です。

## 実際のエラーメッセージ例

**Vercel CLI からの出力：**

```
Error: Authentication failed (401 Unauthorized)
The provided token is invalid or has expired.
```

**GitHub Actions 内でのレスポンス：**

```json
{
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Authentication token is invalid or expired (401)",
    "status": 401
  }
}
```

**curl 経由でのレスポンス：**

```bash
curl -H "Authorization: Bearer <invalid_token>" https://api.vercel.com/v1/projects
```

```
HTTP/1.1 401 Unauthorized
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid token"
  }
}
```

## よくある原因と解決手順

### 原因1：Vercel API トークンが無効または期限切れになっている

Vercel ダッシュボードで生成した API トークンは、セキュリティ上の理由から有効期限が設定されることがあります。また、トークンを削除した後も環境変数に古い値が残っていると、認証に失敗します。

**修正前（エラーが起きるコード）：**

```bash
# 古いトークンを使用し続けている
export VERCEL_TOKEN=abcd1234efgh5678ijkl9999...
vercel deploy
# Error: Authentication failed (401 Unauthorized)
```

**修正後：**

```bash
# Vercel ダッシュボードから新しいトークンを生成する手順
# 1. https://vercel.com/account/tokens にアクセス
# 2. 「Create Token」をクリック
# 3. トークン名と有効期限を設定
# 4. 生成されたトークンをコピーして以下のように設定

export VERCEL_TOKEN=<newly_generated_token>
vercel deploy
# Deployment successful
```

### 原因2：VERCEL_TOKEN 環境変数が正しく設定されていない

CI/CD パイプライン（GitHub Actions、GitLab CI、CircleCI など）でデプロイを自動化する際、シークレット変数として VERCEL_TOKEN を登録する必要があります。シークレット名の誤入力、ペーストミス、または設定漏れが発生しやすい箇所です。

**修正前（エラーが起きるコード）：**

```yaml
# GitHub Actions の例
name: Deploy to Vercel
on: [push]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy
        run: |
          npm install -g vercel
          # 環境変数が設定されていない、または名前が異なる
          vercel deploy --token $VERCEL_AUTH_TOKEN
        # Error: Authentication failed (401)
```

**修正後：**

```yaml
# GitHub Actions での正しい設定
name: Deploy to Vercel
on: [push]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy
        env:
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
        run: |
          npm install -g vercel
          vercel deploy --token $VERCEL_TOKEN
        # Deployment successful
```

GitHub Actions の場合、リポジトリの Settings → Secrets and variables → Actions に `VERCEL_TOKEN` という名前で新しいリポジトリシークレットを追加してください。

### 原因3：GitHub との OAuth 連携が切れている

Vercel はデフォルトでプッシュ自動デプロイ機能を提供していますが、GitHub 連携の権限が失効したり、GitHub アカウント側で当該アプリケーションの認可を取り消したりすると、デプロイトリガーが動作しなくなります。

**修正前（エラーが起きるコード）：**

```bash
# GitHub 連携が有効と思い込んでコミットをプッシュ
git add .
git commit -m "Update features"
git push origin main
# Vercel 側で 401 エラーが発生、デプロイされない
```

**修正後：**

```bash
# 1. Vercel ダッシュボード (https://vercel.com/dashboard) にログイン
# 2. Settings → Git Integrations をクリック
# 3. Connected Repositories にある GitHub を確認
# 4. 「Disconnect」で一度削除し、「Connect」で再接続
# 5. GitHub 認可画面で許可を与える
# 6. その後、通常通りコミットをプッシュ

git add .
git commit -m "Update features"
git push origin main
# Vercel Deployment successful
```

接続直後は、Vercel ダッシュボードまたは GitHub アプリケーション連携ページで「Authorize」をクリックして、最新の権限でトークンを再生成してください。

## Vercel 固有の注意点

**トークンのスコープ確認：** Vercel API トークンには複数のスコープレベルがあります（全プロジェクト対象、特定プロジェクトのみなど）。スコープが制限されている場合、対象外のプロジェクトへのアクセスで 401 が返ります。ダッシュボードの Tokens ページで各トークンの詳細を確認してください。

**複数組織の場合：** Vercel アカウントが複数の Team（組織）に属している場合、デプロイ先チームを明示的に指定する必要があります。`vercel deploy --scope=<team-slug>` でスコープを指定し、そのチームに所属するトークンであることを確認してください。

**環境変数の大文字小文字：** CLI や GitHub Actions では `VERCEL_TOKEN` として大文字で定義します。テンプレートやドキュメント閲覧時に他の変数名（例：`vercel_token`）と混同しやすいため注意が必要です。

**vercel.json 設定：** プロジェクトルートの `vercel.json` に記述される設定は、CI/CD 環境では環境変数より優先度が低いため、環境変数の設定を確認してからファイル設定を疑ってください。

## それでも解決しない場合

**Vercel ログの確認方法：**

```bash
# CLI で詳細ログを出力
VERCEL_DEBUG=1 vercel deploy

# ダッシュボードのデプロイページでも詳細確認可能
# https://vercel.com/dashboard/deployments/<project-name>
# 失敗したデプロイをクリック → Logs タブで完全なエラーメッセージを閲覧
```

**GitHub Actions 内のログ確認：**

GitHub リポジトリの Actions タブから最新のワークフロー実行結果を開き、失敗したステップの出力を確認してください。シークレット変数の値そのものはマスクされますが、エラーメッセージには認証失敗の詳細が記録されます。

**トークン再生成のベストプラクティス：**

1. Vercel ダッシュボードの Account Settings → Tokens に移動
2. 現在のトークンを「Delete」で削除
3. 「Create Token」で新規作成（有効期限を 90 日程度に設定推奨）
4. 生成直後にコピー（二度と表示されません）
5. 各 CI/CD 環境のシークレット変数を上書き
6. テストデプロイで認証確認を実施

**公式サポートへの問い合わせ：**

上記手順をすべて実施してもなお 401 が継続する場合は、Vercel 公式ドキュメント（https://vercel.com/docs/rest-api）の認証セクションを確認するか、Vercel サポート（https://vercel.com/support）に問い合わせてください。API 制限やレート制限の影響を受けている可能性もあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*