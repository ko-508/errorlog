---
title: "Vercel の 404 エラー：原因と解決策"
date: 2026-06-07
description: "指定したデプロイメントまたはリソースが見つからない"
tags: ["Vercel"]
errorCode: "404"
service: "Vercel"
error_type: "404"
components: []
related_services: ["CLI", "Dashboard", "vercel.json"]
trend_incident: true
---
## エラーの概要

Vercel の 404 [エラー](/glossary/エラー/)は、指定したデプロイメント（本番環境）またはリソースが[サーバー](/glossary/サーバー/)で見つからないことを示します。単なるページが存在しないというだけでなく、デプロイメント自体が削除されていたり、ルーティング設定の誤りで意図したファイルに到達できていない場合も含まれます。Vercel 環境では、[設定ファイル](/glossary/設定ファイル/)の記述ミスや古いデプロイメント URL へのアクセスが、この問題の主な原因となります。

## 実際のエラーメッセージ例

**ブラウザで表示される場合：**

```
404 - NOT_FOUND
This page could not be found

The resource might have been removed or you might have mistyped the url.
```

**[API](/glossary/api/) [レスポンス](/glossary/レスポンス/)の場合：**

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "The deployment could not be found",
    "status": 404
  }
}
```

**[CLI](/glossary/cli/) から削除済みデプロイメントにアクセスした場合：**

```bash
Error: Deployment not found. The deployment <deployment-id> does not exist or has been removed.
```

## よくある原因と解決手順

### 原因1：デプロイメント URL が古いか誤っている

Vercel でプロジェクトを更新・再[デプロイ](/glossary/デプロイ/)したり、本番環境のドメインを変更したりすると、以前のデプロイメント URL は自動的に無効化されます。ブラウザのブックマークやスクリプトに古い URL が残っていると、404 [エラー](/glossary/エラー/)が発生します。また、手動で URL を入力する際の誤字も考えられます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// デプロイメント後、古いURLにアクセスしている
const API_URL = "https://my-project-abc123.vercel.app/api/users";

fetch(API_URL)
  .then(response => response.json())
  .catch(error => console.error('エラー:', error));
```

**After（修正後）：**

```javascript
// Vercel Dashboard で確認した最新のデプロイメント URL を使用
const API_URL = "https://my-project-xyz789.vercel.app/api/users";

fetch(API_URL)
  .then(response => response.json())
  .catch(error => console.error('エラー:', error));
```

**確認方法：**

```bash
# CLI で最新のデプロイメントを確認
vercel ls

# 出力例：
# my-project    Production    https://my-project-xyz789.vercel.app  Ready
```

Vercel Dashboard の「Deployments」タブを開き、最新のデプロイメント URL を確認してください。Production 環境と Preview 環境で異なる URL が割り当てられていることに注意してください。

### 原因2：削除されたデプロイメントにアクセスしている

Vercel では、古いデプロイメントは一定期間後に自動削除されたり、ユーザーが手動で削除したりします。削除済みのデプロイメント [ID](/glossary/id/) を直接指定してアクセスすると、404 [エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 3ヶ月前にデプロイした、既に削除されたデプロイメントにアクセス
curl https://my-project-old-deploy-abc.vercel.app/api/data

# レスポンス：
# {"error":{"code":"NOT_FOUND","message":"Deployment not found"}}
```

**After（修正後）：**

```bash
# 現在の本番デプロイメント URL でアクセス
curl https://my-project.vercel.app/api/data

# または、環境変数で URL を管理する
export VERCEL_URL="my-project.vercel.app"
curl https://$VERCEL_URL/api/data
```

デプロイメント保持期間を確認するには、Vercel の[アカウント](/glossary/アカウント/)設定で「Retention」を参照してください。Production デプロイメントは最新のものが保持されますが、Preview デプロイメントはプロジェクト設定で期間を指定できます。

### 原因3：vercel.json のリライト・リダイレクト設定が間違っている

vercel.json でルーティング設定を誤ると、存在するファイルにもアクセスできなくなります。正規表現のパターンマッチングに失敗したり、宛先パスを誤指定したりすると、すべての[リクエスト](/glossary/リクエスト/)が 404 で返されることもあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "rewrites": [
    {
      "source": "/api/(.*)",
      "destination": "/api/handlers/$1.js"
    }
  ]
}
```

このとき、実際のファイル構造が異なる場合（例：`/api/handlers/` ディレクトリが存在しない、ファイル[拡張子](/glossary/拡張子/)が `.ts` など）、マッチした[リクエスト](/glossary/リクエスト/)が行き先ファイルを見つけられず、404 になります。

**After（修正後）：**

```json
{
  "rewrites": [
    {
      "source": "/api/(.*)",
      "destination": "/api/$1"
    },
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

ファイル構造をあらかじめ確認し、リライト・リダイレクトのパターンが実際のファイルパスと一致するか検証してください。Vercel では、`source` と `destination` の対応関係を厳密にチェックします。SPA（単一ページアプリケーション）の場合、すべてのルートを `index.html` にリライトする設定が必須です。

## ツール固有の注意点

**Production デプロイメント vs Preview デプロイメント：**

Vercel では、メインブランチへのプッシュで Production デプロイメントが生成され、プルリクエストごとに Preview デプロイメントが作成されます。Preview URL は PR が閉じられると削除されるため、古い PR の URL にアクセスすると 404 になります。本番環境には必ず Production URL を使用してください。

**[環境変数](/glossary/環境変数/)と動的 URL の扱い：**

Vercel の[環境変数](/glossary/環境変数/) `VERCEL_URL` を使用すれば、デプロイメント URL を動的に参照できます。これにより、コード内にハードコードされた URL を避けられます。

```javascript
const baseUrl = process.env.VERCEL_URL 
  ? `https://${process.env.VERCEL_URL}`
  : 'http://localhost:3000';

fetch(`${baseUrl}/api/users`)
  .then(response => response.json());
```

**カスタムドメイン設定時の注意：**

カスタムドメインを設定している場合、[DNS](/glossary/dns/)（ドメイン名と[サーバー](/glossary/サーバー/)を対応させるシステム）設定の反映に時間がかかることがあります。設定直後は 404 が返される可能性があるため、30 分～1 時間待機してから再アクセスしてください。Vercel Dashboard の「Domains」セクションで「Verified」ステータスが表示されるまで待つことをお勧めします。

## それでも解決しない場合

**デプロイメントログの確認：**

```bash
# ビルドログと実行ログを確認
vercel logs <deployment-url> --follow

# 出力例：
# > vercel deploy
# > Deployment complete. URL: https://my-project-xyz.vercel.app
```

**ローカル環境での動作確認：**

```bash
# Vercel CLI でローカル実行
vercel dev

# ブラウザで http://localhost:3000 にアクセスし、同じリクエストを試す
```

**vercel.json の検証：**

[JSON](/glossary/json/) の文法[エラー](/glossary/エラー/)がないか確認してください。Vercel では[デプロイ](/glossary/デプロイ/)時に [JSON](/glossary/json/) [バリデーション](/glossary/バリデーション/)を行い、[エラー](/glossary/エラー/)があるとビルドが失敗します。

**公式ドキュメントの確認：**

- [Vercel Routing Documentation](https://vercel.com/docs/concepts/projects/project-configuration)
- [Rewrites and Redirects](https://vercel.com/docs/concepts/next.js/rewrites)
- [Deployments API Reference](https://vercel.com/docs/rest-api/endpoints#list-deployments)

GitHub や Vercel のコミュニティフォーラムで同様の事例が報告されていないか検索することも有効です。問題が解決しない場合は、Vercel サポートチケットを作成し、デプロイメント [ID](/glossary/id/) と詳細な[エラーメッセージ](/glossary/エラーメッセージ/)を添付してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*