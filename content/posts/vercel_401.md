---
draft: true
title: "Vercel の 401 エラー：原因と解決策"
date: 2026-06-06
description: "Vercelへの認証に失敗した"
tags: ["Vercel"]
errorCode: "401"
service: "Vercel"
error_type: "401"
components: []
related_services: ["GitHub Actions", "GitLab CI", "CircleCI", "GitHub", "curl"]
trend_incident: true
---
## Vercel 401 エラーの原因と解決方法

## エラーの概要

Vercel 401 [エラー](/glossary/エラー/)は、Vercel の[サーバー](/glossary/サーバー/)に対する[認証](/glossary/認証/)が失敗したことを示します。[API](/glossary/api/) [トークン](/glossary/トークン/)の無効化、[環境変数](/glossary/環境変数/)の設定漏れ、外部サービス連携の切断など、認証周辺の問題が原因となり、[デプロイ](/glossary/デプロイ/)や [CLI](/glossary/cli/) 操作が停止します。この[エラー](/glossary/エラー/)が発生するとプロジェクトのデプロイメント（自動構築・[デプロイ](/glossary/デプロイ/)）パイプラインが停止するため、素早い対応が必要です。

## 実際のエラーメッセージ例

**Vercel [CLI](/glossary/cli/) からの出力：**

```
Error: Authentication failed (401 Unauthorized)
The provided token is invalid or has expired.
```

**GitHub Actions 内での[レスポンス](/glossary/レスポンス/)：**

```json
{
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Authentication token is invalid or expired (401)",
    "status": 401
  }
}
```

**curl 経由での[レスポンス](/glossary/レスポンス/)：**

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

Vercel [ダッシュボード](/glossary/ダッシュボード/)で生成した [API](/glossary/api/) [トークン](/glossary/トークン/)は、[セキュリティ](/glossary/セキュリティ/)上の理由から有効期限が設定されることがあります。また、[トークン](/glossary/トークン/)を削除した後も[環境変数](/glossary/環境変数/)に古い値が残っていると、[認証](/glossary/認証/)に失敗します。

**修正方法：**

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

[CI/CD](/glossary/ci-cd/) パイプライン（GitHub Actions、GitLab CI、CircleCI など）で[デプロイ](/glossary/デプロイ/)を自動化する際、シークレット[変数](/glossary/変数/)として VERCEL_TOKEN を登録する必要があります。シークレット名の誤入力、ペーストミス、または設定漏れが発生しやすい箇所です。

**修正方法：**

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
```

GitHub Actions の場合、[リポジトリ](/glossary/リポジトリ/)の Settings → Secrets and variables → Actions に `VERCEL_TOKEN` という名前で新しいリポジトリシークレットを追加してください。

### 原因3：GitHub との OAuth 連携が切れている

Vercel はデフォルトでプッシュ自動[デプロイ](/glossary/デプロイ/)機能を提供していますが、GitHub 連携の[権限](/glossary/権限/)が失効したり、GitHub [アカウント](/glossary/アカウント/)側で当該[アプリケーション](/glossary/アプリケーション/)の[認可](/glossary/認可/)を取り消したりすると、デプロイトリガーが動作しなくなります。

**修正方法：**

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
```

接続直後は、Vercel [ダッシュボード](/glossary/ダッシュボード/)または GitHub [アプリケーション](/glossary/アプリケーション/)連携ページで「Authorize」をクリックして、最新の[権限](/glossary/権限/)で[トークン](/glossary/トークン/)を再生成してください。

## Vercel 固有の注意点

**[トークン](/glossary/トークン/)の[スコープ](/glossary/スコープ/)確認：** Vercel [API](/glossary/api/) [トークン](/glossary/トークン/)には複数のスコープレベルがあります（全プロジェクト対象、特定プロジェクトのみなど）。[スコープ](/glossary/スコープ/)が制限されている場合、対象外のプロジェクトへのアクセスで 401 が返ります。[ダッシュボード](/glossary/ダッシュボード/)の Tokens ページで各[トークン](/glossary/トークン/)の詳細を確認してください。

**複数組織の場合：** Vercel [アカウント](/glossary/アカウント/)が複数の Team（組織）に属している場合、[デプロイ](/glossary/デプロイ/)先チームを明示的に指定する必要があります。`vercel deploy --scope=<team-slug>` で[スコープ](/glossary/スコープ/)を指定し、そのチームに所属する[トークン](/glossary/トークン/)であることを確認してください。

**[環境変数](/glossary/環境変数/)の大文字小文字：** [CLI](/glossary/cli/) や GitHub Actions では `VERCEL_TOKEN` として大文字で定義します。テンプレートやドキュメント閲覧時に他の変数名（例：`vercel_token`）と混同しやすいため注意が必要です。

**vercel.json 設定：** プロジェクトルートの `vercel.json` に記述される設定は、[CI/CD](/glossary/ci-cd/) 環境では[環境変数](/glossary/環境変数/)より優先度が低いため、[環境変数](/glossary/環境変数/)の設定を確認してからファイル設定を疑ってください。

## それでも解決しない場合

**Vercel [ログ](/glossary/ログ/)の確認方法：**

```bash
# CLI で詳細ログを出力
VERCEL_DEBUG=1 vercel deploy
```

[ダッシュボード](/glossary/ダッシュボード/)のデプロイページでも詳細確認が可能です。https://vercel.com/dashboard/deployments/<project-name> で失敗した[デプロイ](/glossary/デプロイ/)をクリックし、Logs タブで完全な[エラーメッセージ](/glossary/エラーメッセージ/)を確認してください。

**GitHub Actions 内の[ログ](/glossary/ログ/)確認：**

GitHub [リポジトリ](/glossary/リポジトリ/)の Actions タブから最新のワークフロー実行結果を開き、失敗したステップの出力を確認してください。シークレット[変数](/glossary/変数/)の値そのものはマスクされますが、[エラーメッセージ](/glossary/エラーメッセージ/)には認証失敗の詳細が記録されます。

**[トークン](/glossary/トークン/)再生成のベストプラクティス：**

1. Vercel [ダッシュボード](/glossary/ダッシュボード/)の Account Settings → Tokens に移動
2. 現在の[トークン](/glossary/トークン/)を「Delete」で削除
3. 「Create Token」で新規作成（有効期限を 90 日程度に設定推奨）
4. 生成直後にコピー（二度と表示されません）
5. 各 [CI/CD](/glossary/ci-cd/) 環境のシークレット[変数](/glossary/変数/)を上書き
6. テストデプロイで認証確認を実施

**公式サポートへの問い合わせ：**

上記手順をすべて実施してもなお 401 が継続する場合は、Vercel 公式ドキュメント（https://vercel.com/docs/rest-api）の認証セクションを確認するか、Vercel サポート（https://vercel.com/support）に問い合わせてください。API 制限や[レート制限](/glossary/レート制限/)の影響を受けている可能性もあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*