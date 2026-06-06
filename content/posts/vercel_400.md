---
title: "Vercel の 400 エラー：原因と解決策"
date: 2026-06-06
description: "Vercel APIへのリクエストの形式または内容に誤りがある。Vercel 400 エラーの原因と解決策を解説します。"
tags: ["Vercel"]
errorCode: "400"
---
## エラーの概要

Vercel の 400 エラーは、Vercel API へ送信されたリクエストの形式または内容に不正がある場合に発生します。これはクライアント側の誤りを示す HTTP ステータスコードで、デプロイ時や API 呼び出し時に頻繁に遭遇します。Vercel CLI を使用したデプロイ、または直接 API を呼び出している場合に特に注意が必要です。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": "BAD_REQUEST",
    "message": "Invalid request body"
  }
}
```

```bash
Error: Bad Request (400)
POST /v13/deployments
```

## よくある原因と解決手順

### 原因1：vercel.json の設定に誤りがある

vercel.json は、Vercel のデプロイ設定を定義する重要なファイルです。JSON の形式エラーや、キーの綴り間違い、不正な値の型が 400 エラーを引き起こします。例えば、環境変数の設定項目のキー名を間違えたり、配列であるべき値をオブジェクトとして定義したりすると、API リクエストが拒否されます。

**Before（エラーが起きるコード）：**

```json
{
  "buildCommand": "npm run build",
  "installCommand": "npm install",
  "outputDirectory": "dist",
  "env": {
    "DATABASE_URL": "postgresql://..."
  },
  "enviroments": {
    "production": {
      "DATABASE_URL": "postgresql://prod..."
    }
  }
}
```

**After（修正後）：**

```json
{
  "buildCommand": "npm run build",
  "installCommand": "npm install",
  "outputDirectory": "dist",
  "env": {
    "DATABASE_URL": "postgresql://..."
  },
  "envs": [
    {
      "key": "production",
      "value": {
        "DATABASE_URL": "postgresql://prod..."
      }
    }
  ]
}
```

### 原因2：API リクエストの必須パラメーターが欠けている

Vercel API を直接呼び出す場合、認証トークンやプロジェクト ID、デプロイ対象のファイル情報など、必須パラメーターの不足が 400 エラーを引き起こします。特にカスタムスクリプトや CI/CD パイプライン（継続的インテグレーション・デプロイメント）から自動デプロイする場合、リクエストボディの構造を厳密に確認する必要があります。

**Before（エラーが起きるコード）：**

```javascript
const deployProject = async () => {
  const response = await fetch('https://api.vercel.com/v13/deployments', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer <your-token>',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      name: 'my-project',
      files: [
        { file: 'index.js' }
      ]
    })
  });
  return response.json();
};
```

**After（修正後）：**

```javascript
const deployProject = async () => {
  const response = await fetch('https://api.vercel.com/v13/deployments', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer <your-token>',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      name: 'my-project',
      files: [
        {
          file: 'index.js',
          data: Buffer.from('// your code').toString('base64')
        }
      ],
      meta: {
        githubCommitSha: '<your-commit-sha>'
      }
    })
  });
  return response.json();
};
```

### 原因3：デプロイ設定でビルドコマンドの形式が正しくない

ビルドコマンドやインストールコマンドの指定が誤っていると、Vercel のデプロイパイプラインが 400 エラーを返します。複雑なコマンドチェーンやシェル特殊文字のエスケープ不足により、API が拒否することがあります。単一コマンドの指定を心がけ、複数の処理が必要な場合は package.json の scripts セクションで定義してください。

**Before（エラーが起きるコード）：**

```json
{
  "buildCommand": "npm run build && npm run test | grep coverage",
  "devCommand": "npm start > logs.txt 2>&1",
  "installCommand": "npm install; echo 'done'"
}
```

**After（修正後）：**

```json
{
  "buildCommand": "npm run build",
  "devCommand": "npm start",
  "installCommand": "npm install",
  "scripts": {
    "build": "npm run compile && npm run test",
    "test": "jest"
  }
}
```

## ツール固有の注意点

Vercel は厳密な JSON Schema 検証を行うため、vercel.json の構造に 1 つでも不正があると即座に 400 エラーになります。特に複数環境を設定する場合、環境ごとのキー名（`production`、`preview`、`development`）を正確に記述しないと拒否されます。

また、Vercel CLI のバージョンが古い場合、新しい API 仕様に対応できず、正しい設定ファイルでも 400 エラーが発生することがあります。チームで複数のマシンからデプロイする場合、全員が同じバージョンを使用していることを確認してください。

環境変数の値の型も厳密です。数値は文字列で囲む必要があり、配列やオブジェクトは正しくシリアライズされていなければなりません。特に API を直接呼び出す場合、ファイルコンテンツは Base64 エンコード（64 進法の文字列形式に変換）されたテキストとして送信する必要があり、バイナリのまま送信すると 400 エラーが発生します。

## それでも解決しない場合

まず、Vercel CLI の `--debug` オプションでデプロイプロセスの詳細ログを確認してください。

```bash
vercel deploy --debug
```

このコマンドは API 呼び出しの詳細情報や、サーバーからの詳しいエラーメッセージを表示します。

次に、vercel.json を JSON Schema バリデーター（JSON 形式の妥当性を検証するツール）で検証します。オンラインツール（例：[JSON Schema Validator](https://www.jsonschemavalidator.net/)）を使用するか、ローカルでバリデーションツールを実行してください。

```bash
npm install --global ajv-cli
ajv validate -s /path/to/schema.json -d vercel.json
```

さらに、Vercel CLI を最新版にアップデートしてください。

```bash
npm install -g vercel@latest
vercel --version
```

それでも解決しない場合は、[Vercel 公式ドキュメント](https://vercel.com/docs/api)の API 仕様確認と、[Vercel Community Discord](https://vercel.com/support)でのサポート相談を検討してください。ログファイルは `~/.vercel` ディレクトリーに保存されており、詳細な情報取得に役立ちます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*