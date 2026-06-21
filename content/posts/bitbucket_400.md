---
title: "Bitbucket の 400 エラー：原因と解決策"
date: 2026-06-14
description: "Bitbucket APIへのリクエストの形式または内容に誤りがある"
tags: ["Bitbucket"]
errorCode: "400"
service: "Bitbucket"
error_type: "400"
components: []
related_services: ["Bitbucket Pipelines", "Bitbucket REST API", "Bitbucket Cloud API"]
---
## エラーの概要

Bitbucket の 400 [エラー](/glossary/エラー/)は、[API](/glossary/api/) への[リクエスト](/glossary/リクエスト/)の形式または内容が不正であることを示します。[リクエストボディ](/glossary/リクエストボディ/)の [JSON](/glossary/json/) 破損、必須[パラメータ](/glossary/パラメータ/)の欠落、[YAML](/glossary/yaml/) 構文[エラー](/glossary/エラー/)、クエリパラメータの不正な値など、クライアント側の入力データに問題がある場合に返されます。この[エラー](/glossary/エラー/)はデプロイメント、リポジトリー操作、パイプライン設定で頻繁に遭遇します。

## 実際のエラーメッセージ例

**Bitbucket [API](/glossary/api/) [レスポンス](/glossary/レスポンス/)例：**

```json
{
  "type": "error",
  "error": {
    "message": "Invalid request",
    "detail": "Request body is not valid JSON"
  },
  "status": 400
}
```

**Bitbucket Pipelines 実行時の出力例：**

```bash
ERROR: Unexpected error: Repository not found or invalid configuration
Pipeline error: 'message' field is required in bitbucket-pipelines.yml
```

## よくある原因と解決手順

### 原因 1：bitbucket-pipelines.yml の YAML 構文エラー

Bitbucket Pipelines の[設定ファイル](/glossary/設定ファイル/)に [YAML](/glossary/yaml/) 形式の誤りがあると、パイプラインの起動時に 400 [エラー](/glossary/エラー/)が発生します。インデント不正、クォート漏れ、不正なキー名、シーケンス記法の誤りなどが該当します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
image: atlassian/default-image:latest

pipelines:
  default:
    - step:
      name: Build
      script:
        - echo "Building..."
        - npm install
      artifacts:
        - node_modules/**
```

**After（修正後）：**

```yaml
image: atlassian/default-image:latest

pipelines:
  default:
    - step:
        name: Build
        script:
          - echo "Building..."
          - npm install
        artifacts:
          - node_modules/**
```

上記の例では、`step:` の直下のキーが正しくインデントされていませんでした。各階層は 2 スペースまたは 4 スペースで統一する必要があります。

### 原因 2：API リクエストボディの JSON 形式が不正

Bitbucket [REST](/glossary/rest/) [API](/glossary/api/) を呼び出す際、[リクエストボディ](/glossary/リクエストボディ/)の [JSON](/glossary/json/) が壊れていたり、必須[パラメータ](/glossary/パラメータ/)が欠落していたりすると 400 [エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X POST https://api.bitbucket.org/2.0/repositories/<workspace>/<repo_slug>/issues \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Bug found
  }'
```

**After（修正後）：**

```bash
curl -X POST https://api.bitbucket.org/2.0/repositories/<workspace>/<repo_slug>/issues \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Bug found",
    "content": {
      "raw": "This is a test issue"
    }
  }'
```

[JSON](/glossary/json/) の末尾のダブルクォートが閉じられておらず、また `content` フィールド（必須）が欠落していました。[API](/glossary/api/) ドキュメントで必須フィールドを確認し、有効な [JSON](/glossary/json/) 形式で[リクエスト](/glossary/リクエスト/)を送信します。

### 原因 3：クエリパラメータの値が不正な形式

[API](/glossary/api/) 呼び出しのクエリパラメータに無効な値を指定すると、400 [エラー](/glossary/エラー/)が発生します。例えば、ページネーション、フィルター条件、ソート順序で無効な値を渡す場合などです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X GET "https://api.bitbucket.org/2.0/repositories/<workspace>?pagelen=invalid&page=abc" \
  -H "Authorization: Bearer <token>"
```

**After（修正後）：**

```bash
curl -X GET "https://api.bitbucket.org/2.0/repositories/<workspace>?pagelen=50&page=1" \
  -H "Authorization: Bearer <token>"
```

`pagelen` は整数値、`page` も整数で指定する必要があります。ソートパラメータも Bitbucket が認識する値（例：`name`, `-name`）を使用します。

## ツール固有の注意点

**Bitbucket Pipelines での注意：**
bitbucket-pipelines.yml をリポジトリーのルートに配置する際、ファイルのエンコーディングが UTF-8 であることを確認してください。また、Bitbucket の Web UI にある「Pipeline Validator」で [YAML](/glossary/yaml/) 構文を事前検証できます。リポジトリー設定内の「Pipelines」セクションから直接バリデーションツールにアクセス可能です。

**Bitbucket Cloud [API](/glossary/api/) での注意：**
[API](/glossary/api/) 呼び出し時に `Content-Type: application/json` [ヘッダー](/glossary/ヘッダー/)を明示的に指定することが重要です。また、[認証](/glossary/認証/)[トークン](/glossary/トークン/)の有効期限切れは 401 [エラー](/glossary/エラー/)になりますが、[トークン](/glossary/トークン/)が存在しても[スコープ](/glossary/スコープ/)（[API](/glossary/api/) の使用権限範囲）が不足していると 400 が返される場合があります。[API](/glossary/api/) [トークン](/glossary/トークン/)の生成時に、必要な[権限](/glossary/権限/)[スコープ](/glossary/スコープ/)（例：`repository:read`, `issue:write`）を確認します。

## それでも解決しない場合

まず Bitbucket UI 内のパイプライン実行[ログ](/glossary/ログ/)を確認してください。詳細な[エラーメッセージ](/glossary/エラーメッセージ/)は「Pipeline」→「Build」→「Logs」タブに表示されます。

[API](/glossary/api/) 呼び出しの場合、cURL に `-v` フラグを付けて詳細な[リクエスト](/glossary/リクエスト/)・[レスポンス](/glossary/レスポンス/)を確認します：

```bash
curl -v -X POST https://api.bitbucket.org/2.0/repositories/<workspace>/<repo>/issues \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"test"}'
```

レスポンスボディの `errors` または `message` フィールドに問題の詳細が記載されます。

オンラインの [YAML](/glossary/yaml/) バリデーターを使用して、bitbucket-pipelines.yml の構文を独立して検証することもできます（例：https://www.yamllint.com）。

最後に、[Bitbucket Cloud REST API ドキュメント](https://developer.atlassian.com/cloud/bitbucket/rest/)で対象の[エンドポイント](/glossary/エンドポイント/)の必須[パラメータ](/glossary/パラメータ/)と形式を確認し、[Bitbucket Pipelines YAML リファレンス](https://support.atlassian.com/bitbucket-cloud/docs/build-with-pipelines/)でパイプライン設定の仕様を参照してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*