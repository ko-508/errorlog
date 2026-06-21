---
title: "Vercel の 403 エラー：原因と解決策"
date: 2026-06-06
description: "Vercelプロジェクトまたはリソースへのアクセス権限がない"
tags: ["Vercel"]
errorCode: "403"
service: "Vercel"
error_type: "403"
components: []
related_services: ["GitHub Actions", "Vercel CLI"]
trend_incident: true
---
## エラーの概要

Vercel の 403 [エラー](/glossary/エラー/)は、[デプロイ](/glossary/デプロイ/)や [API](/glossary/api/) 呼び出し時にプロジェクトやリソースへの[アクセス権限](/glossary/アクセス権限/)がないことを意味します。これは認証自体は成功しているものの、[認可](/glossary/認可/)（[アクセス権](/glossary/アクセス権/)の許可判定）レベルで拒否される状態です。Vercel では、個人[アカウント](/glossary/アカウント/)・チームアカウント・[API](/glossary/api/) [トークン](/glossary/トークン/)の[スコープ](/glossary/スコープ/)（適用範囲）によって[権限](/glossary/権限/)が厳密に管理されており、不適切な組み合わせで 403 [エラー](/glossary/エラー/)が発生することがあります。

## 実際のエラーメッセージ例

**Vercel [CLI](/glossary/cli/) [デプロイ](/glossary/デプロイ/)時：**

```
Error: Received 403 from https://api.vercel.com/v13/deployments
You do not have permission to access this resource
```

**[API](/glossary/api/) [レスポンス](/glossary/レスポンス/)：**

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "You do not have permission to access this project",
    "status": 403
  }
}
```

## よくある原因と解決手順

### 原因1：別のチームのプロジェクトに個人トークンでアクセスしている

個人[アカウント](/glossary/アカウント/)の [API](/glossary/api/) [トークン](/glossary/トークン/)を使用しながら、チームが所有するプロジェクトにアクセスしようとすると 403 [エラー](/glossary/エラー/)が発生します。Vercel では個人[スコープ](/glossary/スコープ/)の[トークン](/glossary/トークン/)ではチーム配下のリソースにアクセスできません。

**修正前：**

```bash
# 個人アカウントのトークンでチームプロジェクトにデプロイ
export VERCEL_TOKEN=<個人スコープのトークン>
export VERCEL_ORG_ID=team_xxx  # チームID
export VERCEL_PROJECT_ID=<プロジェクトID>
vercel deploy
```

**修正後：**

```bash
# チームスコープを持つ API トークンを使用
export VERCEL_TOKEN=<チームスコープのトークン>
export VERCEL_ORG_ID=team_xxx
export VERCEL_PROJECT_ID=<プロジェクトID>
vercel deploy
```

チームスコープの[トークン](/glossary/トークン/)を生成するには、Vercel [ダッシュボード](/glossary/ダッシュボード/)で Settings → Tokens → Create の順に進み、[スコープ](/glossary/スコープ/)のドロップダウンから「Team」を選択します。

### 原因2：VERCEL_ORG_ID と VERCEL_PROJECT_ID の組み合わせが不正

プロジェクトが複数存在する環境で、誤った[環境変数](/glossary/環境変数/)の組み合わせを指定すると[アクセス権限](/glossary/アクセス権限/)[エラー](/glossary/エラー/)が発生します。特にチームアカウント間の移行や複数環境での運用時に起こりやすいです。

**修正前：**

```bash
# 個人アカウントのプロジェクトID をチームの ORG_ID で参照
export VERCEL_ORG_ID=team_abc123
export VERCEL_PROJECT_ID=prj_personal456  # 別チームのプロジェクト
vercel deploy
```

**修正後：**

```bash
# Vercel ダッシュボードから正しい値を確認して設定
export VERCEL_ORG_ID=team_abc123
export VERCEL_PROJECT_ID=prj_team_abc789  # 対応するプロジェクトID
export VERCEL_TOKEN=<チームスコープのトークン>
vercel deploy
```

正しいプロジェクト[ID](/glossary/id/) とチーム[ID](/glossary/id/) は、Vercel [ダッシュボード](/glossary/ダッシュボード/)のプロジェクト設定ページの Settings → General から確認できます。

### 原因3：プロジェクトのアクセス制限が有効

Vercel [ダッシュボード](/glossary/ダッシュボード/)でプロジェクトにメンバー制限を設定している場合、対象の [API](/glossary/api/) [トークン](/glossary/トークン/)やユーザーが許可リストに入っていないと 403 が返されます。

**修正方法：**

Vercel [ダッシュボード](/glossary/ダッシュボード/) → Project Settings → Security のアクセス制限設定を確認し、使用する [API](/glossary/api/) [トークン](/glossary/トークン/)が許可リストに登録されているか確認してください。必要に応じて、使用する[トークン](/glossary/トークン/)を許可リストに追加するか、許可済みの[トークン](/glossary/トークン/)に変更します。

## Vercel 固有の注意点

Vercel ではプロジェクトの所有権と[アクセス権](/glossary/アクセス権/)が厳密に分離されています。同じメールアドレスで複数の[アカウント](/glossary/アカウント/)（個人・チーム）を保有している場合、ブラウザーのセッションと [CLI](/glossary/cli/) の認証状態がズレることがあります。

[CI/CD](/glossary/ci-cd/) パイプラインで[デプロイ](/glossary/デプロイ/)を行う場合は、**チームスコープの [API](/glossary/api/) [トークン](/glossary/トークン/)を使用**してください。GitHub Actions 等で VERCEL_TOKEN を設定する際は、リポジトリーの Settings → Secrets から、チームが所有するプロジェクト用の[トークン](/glossary/トークン/)を登録します。また VERCEL_ORG_[ID](/glossary/id/) を指定しない場合、デフォルトで個人[スコープ](/glossary/スコープ/)で動作するため注意が必要です。

プロジェクトを個人[アカウント](/glossary/アカウント/)からチームアカウントに移行した直後は、古い[環境変数](/glossary/環境変数/)が残っていないか全デプロイメント設定を確認してください。

## それでも解決しない場合

まず Vercel [ダッシュボード](/glossary/ダッシュボード/)の[アカウント](/glossary/アカウント/)設定で、現在[ログイン](/glossary/ログイン/)しているのが正しい[アカウント](/glossary/アカウント/)であることを確認します。Settings → Account で表示されるメールアドレスと所属チームを確認し、[CLI](/glossary/cli/) の認証状態と一致しているか確認してください。

```bash
# 現在の認証状態を確認
vercel whoami

# 必要に応じて再度ログイン
vercel logout
vercel login
```

[API](/glossary/api/) [トークン](/glossary/トークン/)の詳細情報を確認する場合、以下の[コマンド](/glossary/コマンド/)で[トークン](/glossary/トークン/)の[スコープ](/glossary/スコープ/)や有効期限を確認できます。

```bash
# トークンの詳細を確認（Bearer トークンを使用）
curl -H "Authorization: Bearer <your-vercel-token>" \
  https://api.vercel.com/v2/user
```

プロジェクト固有の設定確認は、Vercel [ダッシュボード](/glossary/ダッシュボード/) → Project Settings → [API](/glossary/api/) から確認してください。公式ドキュメントの Access Control セクションに、[権限](/glossary/権限/)の詳細説明があります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*