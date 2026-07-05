---
draft: true
title: "Vercel の 400 エラー：原因と解決策"
date: 2026-06-06
description: "Vercel APIへのリクエストの形式または内容に誤りがある"
tags: ["Vercel"]
errorCode: "400"
service: "Vercel"
error_type: "400"
components: []
related_services: ["Vercel CLI", "Vercel API"]
trend_incident: true
---
## エラーの概要

Vercel の 400 [エラー](/glossary/エラー/)は、Vercel [API](/glossary/api/) へ送信された[リクエスト](/glossary/リクエスト/)の形式または内容に不正がある場合に発生します。これはクライアント側の誤りを示す [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)で、[デプロイ](/glossary/デプロイ/)時や [API](/glossary/api/) 呼び出し時に発生することがあります。Vercel [CLI](/glossary/cli/) を使用した[デプロイ](/glossary/デプロイ/)、または直接 [API](/glossary/api/) を呼び出している場合に確認が必要です。

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

vercel.json は、Vercel の[デプロイ](/glossary/デプロイ/)設定を定義するファイルです。[JSON](/glossary/json/) の形式誤りや、キーの綴り間違い、不正な値の型が 400 [エラー](/glossary/エラー/)を引き起こします。例えば、[環境変数](/glossary/環境変数/)の設定項目のキー名を間違えたり、配列であるべき値を[オブジェクト](/glossary/オブジェクト/)として定義したりすると、[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)が拒否されます。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

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

**修正後：**

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

Vercel [API](/glossary/api/) を直接呼び出す場合、[認証](/glossary/認証/)[トークン](/glossary/トークン/)やプロジェクト [ID](/glossary/id/)、[デプロイ](/glossary/デプロイ/)対象のファイル情報など、必須パラメーターの不足が 400 [エラー](/glossary/エラー/)を引き起こします。特にカスタムスクリプトや [CI/CD](/glossary/ci-cd/) パイプライン（自動実行環境）から自動[デプロイ](/glossary/デプロイ/)する場合、[リクエストボディ](/glossary/リクエストボディ/)の構造を厳密に確認する必要があります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

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

**修正後：**

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

ビルドコマンドやインストールコマンドの指定が誤っていると、Vercel のデプロイパイプラインが 400 [エラー](/glossary/エラー/)を返します。複雑なコマンドチェーンや[シェル](/glossary/シェル/)特殊文字のエスケープ不足により、[API](/glossary/api/) が拒否することがあります。単一[コマンド](/glossary/コマンド/)の指定を心がけ、複数の処理が必要な場合は package.json の scripts セクションで定義してください。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "buildCommand": "npm run build && npm run test | grep coverage",
  "devCommand": "npm start > logs.txt 2>&1",
  "installCommand": "npm install; echo 'done'"
}
```

**修正後：**

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

Vercel は厳密な [JSON](/glossary/json/) [スキーマ](/glossary/スキーマ/)検証を行うため、vercel.json の構造に 1 つでも不正があると即座に 400 [エラー](/glossary/エラー/)になります。特に複数環境を設定する場合、環境ごとのキー名（`production`、`preview`、`development`）を正確に記述しないと拒否されます。

また、Vercel [CLI](/glossary/cli/) の[バージョン](/glossary/バージョン/)が古い場合、新しい [API](/glossary/api/) 仕様に対応できず、正しい[設定ファイル](/glossary/設定ファイル/)でも 400 [エラー](/glossary/エラー/)が発生することがあります。チームで複数のマシンから[デプロイ](/glossary/デプロイ/)する場合、全員が同じ[バージョン](/glossary/バージョン/)を使用していることを確認してください。

[環境変数](/glossary/環境変数/)の値の型も厳密です。数値は文字列で囲む必要があり、配列や[オブジェクト](/glossary/オブジェクト/)は正しくシリアライズされていなければなりません。特に [API](/glossary/api/) を直接呼び出す場合、ファイルコンテンツは Base64 エンコード（64進法のテキスト形式に変換）で送信する必要があり、バイナリのまま送信すると 400 [エラー](/glossary/エラー/)が発生します。

## それでも解決しない場合

まず、Vercel [CLI](/glossary/cli/) の `--debug` オプションでデプロイプロセスの詳細[ログ](/glossary/ログ/)を確認してください。

```bash
vercel deploy --debug
```

この[コマンド](/glossary/コマンド/)は [API](/glossary/api/) 呼び出しの詳細情報や、[サーバー](/glossary/サーバー/)からの詳しい[エラーメッセージ](/glossary/エラーメッセージ/)を表示します。

次に、vercel.json を [JSON](/glossary/json/) スキーマバリデーターで検証します。オンラインツール（例：[JSON Schema Validator](https://www.jsonschemavalidator.net/)）を使用するか、ローカルでバリデーションツールを実行してください。

```bash
npm install --global ajv-cli
ajv validate -s /path/to/schema.json -d vercel.json
```

さらに、Vercel [CLI](/glossary/cli/) を最新版に[アップデート](/glossary/アップデート/)してください。

```bash
npm install -g vercel@latest
vercel --version
```

それでも解決しない場合は、[Vercel 公式ドキュメント](https://vercel.com/docs/api)の [API](/glossary/api/) 仕様確認と、[Vercel Community Discord](https://vercel.com/support)でのサポート相談を検討してください。[ログファイル](/glossary/ログファイル/)は `~/.vercel` ディレクトリーに保存されており、詳細な情報取得に役立ちます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*