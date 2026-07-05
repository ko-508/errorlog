---
draft: true
title: "CircleCI の 400 エラー：原因と解決策"
date: 2026-06-19
description: "CircleCI APIへのリクエストの形式または内容に誤りがある"
tags: ["CircleCI"]
errorCode: "400"
service: "CircleCI"
error_type: "400"
components: ["API", "CLI", "Pipeline", "Config"]
related_services: ["GitHub", "curl"]
---

## エラーの概要

CircleCI の 400 [エラー](/glossary/エラー/)は、CircleCI [API](/glossary/api/) への[リクエスト](/glossary/リクエスト/)の形式または内容に誤りがある場合に発生します。[設定ファイル](/glossary/設定ファイル/)の構文[エラー](/glossary/エラー/)、[API](/glossary/api/)[リクエストボディ](/glossary/リクエストボディ/)の [JSON](/glossary/json/) 不正、パイプラインパラメータの型不一致などが主な原因です。この[エラー](/glossary/エラー/)が発生すると、パイプラインの実行や [API](/glossary/api/) 連携が失敗し、[CI/CD](/glossary/ci-cd/) ワークフローが停止します。

## 実際のエラーメッセージ例

**[API](/glossary/api/) [レスポンス](/glossary/レスポンス/)の例：**

```json
{
  "message": "Invalid request body",
  "errors": [
    {
      "message": "field 'parameters' must be an object"
    }
  ]
}
```

**[設定ファイル](/glossary/設定ファイル/)検証時の例：**

```bash
$ circleci config validate .circleci/config.yml
Error: Config file is invalid.
The following errors were found:
- 'jobs' is not defined
```

## よくある原因と解決手順

### 原因 1：config.yml の構文エラーまたは必須フィールドの欠落

CircleCI の[設定ファイル](/glossary/設定ファイル/)が [YAML](/glossary/yaml/) として不正な構文になっているか、`version` や `jobs` などの必須フィールドが定義されていない場合に 400 [エラー](/glossary/エラー/)が発生します。[YAML](/glossary/yaml/) のインデント不正や、必須キーの完全な欠落が典型的です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# version フィールドが欠落している
jobs:
  build:
    docker:
      - image: cimg/python:3.11
    steps:
      - checkout
      - run: echo "Building..."

workflows:
  main:
    jobs:
      - build
```

**After（修正後）：**

```yaml
version: 2.1

jobs:
  build:
    docker:
      - image: cimg/python:3.11
    steps:
      - checkout
      - run: echo "Building..."

workflows:
  main:
    jobs:
      - build
```

検証方法として、[リポジトリ](/glossary/リポジトリ/)の CircleCI [CLI](/glossary/cli/) をインストールして以下の[コマンド](/glossary/コマンド/)を実行します。

```bash
circleci config validate .circleci/config.yml
```

### 原因 2：API リクエストボディの JSON が不正な形式

CircleCI [API](/glossary/api/) に直接[リクエスト](/glossary/リクエスト/)を送信する場合、[リクエストボディ](/glossary/リクエストボディ/)の [JSON](/glossary/json/) 構造が仕様に合致していないと 400 [エラー](/glossary/エラー/)が返されます。[JSON](/glossary/json/) のフォーマット不正やシングルクォート使用、値の型不一致などが該当します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X POST https://circleci.com/api/v2/project/github/<your-org>/<your-repo>/pipeline \
  -H "Circle-Token: <your-api-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "deploy_env": "production",
      "version": 1.0
    }
  }'
```

上記の[リクエスト](/glossary/リクエスト/)で `parameters` の値が正しくない場合（またはネストの深さが不適切な場合）に 400 [エラー](/glossary/エラー/)が発生します。

**After（修正後）：**

```bash
curl -X POST https://circleci.com/api/v2/project/github/<your-org>/<your-repo>/pipeline \
  -H "Circle-Token: <your-api-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "deploy_env": "production",
      "version": "1.0"
    }
  }'
```

### 原因 3：パイプラインパラメータの型が宣言と一致していない

config.yml でパイプラインパラメータを `boolean` や `integer` で宣言した場合、[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)や手動トリガーで文字列や異なる型の値を渡すと 400 [エラー](/glossary/エラー/)が発生します。型の厳密な一致が要求されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
version: 2.1

parameters:
  enable_feature:
    type: boolean
    default: false
  build_number:
    type: integer
    default: 1

jobs:
  build:
    steps:
      - run: echo "Feature enabled: << pipeline.parameters.enable_feature >>"
```

この設定で、[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)で `enable_feature` を文字列 `"true"` で渡すと 400 [エラー](/glossary/エラー/)になります。

```bash
curl -X POST https://circleci.com/api/v2/project/github/<your-org>/<your-repo>/pipeline \
  -H "Circle-Token: <your-api-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "enable_feature": "true",
      "build_number": "1"
    }
  }'
```

**After（修正後）：**

```bash
curl -X POST https://circleci.com/api/v2/project/github/<your-org>/<your-repo>/pipeline \
  -H "Circle-Token: <your-api-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "enable_feature": true,
      "build_number": 1
    }
  }'
```

boolean は [JSON](/glossary/json/) のネイティブ値 `true`/`false`（クォートなし）、integer は `1`（文字列でない数値）で渡す必要があります。

## ツール固有の注意点

CircleCI では、[エラーレスポンス](/glossary/エラーレスポンス/)の `message` フィールドと `errors` 配列に問題の詳細が記載されます。[API](/glossary/api/) 呼び出し時は、必ず[レスポンス](/glossary/レスポンス/)をフルで確認してください。

```json
{
  "message": "Invalid request body",
  "errors": [
    {
      "message": "field 'parameters.version' must be a string, not a number"
    }
  ]
}
```

また、CircleCI の config.yml は v2.1 以上を使用する場合、Orb の参照やパイプラインパラメータの定義が可能になります。古い v2 形式を使用している場合は、これらの機能がサポートされないため、[バージョン](/glossary/バージョン/)を明示的に `version: 2.1` に更新してください。

Web UI からパイプラインを手動トリガーする場合でも、[パラメータ](/glossary/パラメータ/)の入力欄に型に合致しない値を入力すると 400 [エラー](/glossary/エラー/)で送信が拒否されます。

## それでも解決しない場合

以下の手順で詳細を確認してください。

**1. [設定ファイル](/glossary/設定ファイル/)の詳細な検証：**

```bash
circleci config validate .circleci/config.yml --strict
```

`--strict` オプションで、より詳細な検証ルールが適用されます。

**2. [API](/glossary/api/) [レスポンス](/glossary/レスポンス/)の完全な内容を確認：**

```bash
curl -v -X POST https://circleci.com/api/v2/project/github/<your-org>/<your-repo>/pipeline \
  -H "Circle-Token: <your-api-token>" \
  -H "Content-Type: application/json" \
  -d '{"parameters": {...}}'
```

`-v` フラグで詳細な[リクエスト](/glossary/リクエスト/)・レスポンスヘッダーとボディを表示します。

**3. CircleCI [API](/glossary/api/) ドキュメントで仕様確認：**

[CircleCI API v2 Reference](https://circleci.com/docs/api/v2/) で対象[エンドポイント](/glossary/エンドポイント/)の必須[パラメータ](/glossary/パラメータ/)と型を再確認してください。特に Trigger Pipeline [エンドポイント](/glossary/エンドポイント/)（POST /project/{project-slug}/pipeline）の仕様は頻繁に更新されるため、常に最新のドキュメントを参照してください。

**4. CircleCI サポートへの問い合わせ：**

上記の手順で解決しない場合は、CircleCI の Support Portal から問い合わせる際に、[エラーレスポンス](/glossary/エラーレスポンス/)の [JSON](/glossary/json/) 全体、config.yml の内容（機密情報を除く）、[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)の形式を記載してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*