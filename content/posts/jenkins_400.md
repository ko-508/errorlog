---
draft: true
title: "Jenkins の 400 エラー：原因と解決策"
date: 2026-06-17
description: "JenkinsのREST APIへのリクエストの形式が正しくない"
tags: ["Jenkins"]
errorCode: "400"
service: "Jenkins"
error_type: "400"
components: []
related_services: ["REST API", "Jenkinsfile", "Groovy", "cURL"]
---

## エラーの概要

Jenkinsの400[エラー](/glossary/エラー/)は、[REST](/glossary/rest/) [API](/glossary/api/)への[リクエスト](/glossary/リクエスト/)の形式が正しくないことを示します。[JSON](/glossary/json/)[パラメータ](/glossary/パラメータ/)の不正な形式、必須[パラメータ](/glossary/パラメータ/)の欠落、型の不一致、またはJenkinsfileのGroovy構文[エラー](/glossary/エラー/)によって発生します。この[エラー](/glossary/エラー/)が返されると、ビルドトリガーやパイプライン実行、ジョブ設定の更新などが正常に動作しません。

## 実際のエラーメッセージ例

**Jenkins [REST](/glossary/rest/) [API](/glossary/api/)の[HTTP](/glossary/http/)[レスポンス](/glossary/レスポンス/)：**

```json
{
  "status": 400,
  "error": "Bad Request",
  "message": "Invalid request body",
  "detail": "JSON parse error: Unexpected character ('{' (code 123)): expected valid JSON"
}
```

**Jenkinsの[ログ](/glossary/ログ/)出力例：**

```bash
ERROR: Failed to parse JSON payload: 
com.google.gson.JsonSyntaxException: java.io.EOFException: End of input at line 1 column 10 character 10
```

## よくある原因と解決手順

### 原因1：APIリクエストのJSONパラメータが不正な形式

[REST](/glossary/rest/) [API](/glossary/api/)を経由してJenkinsジョブをトリガーする際、POST[リクエスト](/glossary/リクエスト/)のボディに含まれる[JSON](/glossary/json/)が正しくパースできない形式になっていることが原因です。ダブルクォートの漏れ、末尾のカンマ、エスケープ漏れなどが典型的な問題です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "parameter": [
      {"name": "BUILD_ENV", "value": "production"},
      {"name": "VERSION", "value": "1.2.3",}
    ]
  }' \
  http://jenkins.example.com/job/my-job/buildWithParameters
```

**After（修正後）：**

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "parameter": [
      {"name": "BUILD_ENV", "value": "production"},
      {"name": "VERSION", "value": "1.2.3"}
    ]
  }' \
  http://jenkins.example.com/job/my-job/buildWithParameters
```

### 原因2：必須パラメータが欠けているか型が間違っている

Jenkinsの特定の[エンドポイント](/glossary/エンドポイント/)では、[JSON](/glossary/json/)[リクエスト](/glossary/リクエスト/)に必須の項目が必ず含まれていなければなりません。また、数値や真偽値を文字列のまま送信するなど、期待される型と異なるデータ型で[パラメータ](/glossary/パラメータ/)を渡すと400[エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "jobs": [
      {
        "name": "job-name"
      }
    ]
  }' \
  http://jenkins.example.com/queue/item/12345/cancel
```

**After（修正後）：**

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "jobs": [
      {
        "name": "job-name",
        "description": "Sample job",
        "enabled": true
      }
    ]
  }' \
  http://jenkins.example.com/queue/item/12345/cancel
```

### 原因3：JenkinsfileのGroovy構文エラー

パイプラインジョブのJenkinsfileに構文[エラー](/glossary/エラー/)があると、Jenkins がファイルをパース時に400[エラー](/glossary/エラー/)を返すことがあります。括弧の不一致、不正なステージ定義、シェルコマンドの引用符エスケープ漏れなどが原因になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```groovy
pipeline {
  agent any
  
  stages {
    stage('Build') {
      steps {
        sh 'echo Building...'
      }
    // ← ステージが閉じられていない
    
    stage('Deploy') {
      steps {
        sh 'echo Deploying...'
      }
    }
  }
}
```

**After（修正後）：**

```groovy
pipeline {
  agent any
  
  stages {
    stage('Build') {
      steps {
        sh 'echo Building...'
      }
    }
    
    stage('Deploy') {
      steps {
        sh 'echo Deploying...'
      }
    }
  }
}
```

## ツール固有の注意点

**Jenkinsfile Linterの活用：** Jenkinsの管理画面に「Declarative: Validate」という機能があります。パイプラインジョブの設定画面で「Validate」ボタンをクリックするか、以下のcURL[コマンド](/glossary/コマンド/)で構文チェックが可能です。このツールはGroovy構文[エラー](/glossary/エラー/)を事前に検出し、[デプロイ](/glossary/デプロイ/)前にJenkinsfileを検証するのに非常に効果的です。

```bash
curl -X POST \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "jenkinsfile=<your-jenkinsfile-content>" \
  http://jenkins.example.com/pipeline-model-converter/validate
```

**[REST](/glossary/rest/) [API](/glossary/api/)[認証](/glossary/認証/)[トークン](/glossary/トークン/)の確認：** Jenkinsfilesで外部[API](/glossary/api/)を呼び出す場合、認証情報が正しく設定されているかを確認してください。[認証](/glossary/認証/)[ヘッダー](/glossary/ヘッダー/)が漏れていたり、[トークン](/glossary/トークン/)が期限切れになっていたりすると、Jenkinsが外部サービスからの応答をパースできず400[エラー](/glossary/エラー/)が返されることがあります。

**Groovy[変数](/glossary/変数/)の型マッピング：** パイプラインで外部[JSON](/glossary/json/) [API](/glossary/api/)の[レスポンス](/glossary/レスポンス/)を処理する場合、Groovyの型推論が期待と異なる場合があります。明示的に型キャストを行うか、`readJSON`ステップを使用して[JSON](/glossary/json/) を確実にマップに変換することが重要です。

## それでも解決しない場合

**Jenkinsの[ログファイル](/glossary/ログファイル/)を確認する：** マスターノードの場合は`<JENKINS_HOME>/logs/jenkins.log`、またはJenkinsUI上の「[ログ](/glossary/ログ/)の参照」機能でより詳細な[エラー](/glossary/エラー/)情報を確認できます。400[エラー](/glossary/エラー/)が返される直前の[ログ](/glossary/ログ/)に、実際のパース失敗箇所が記録されています。

**cURLで段階的に[API](/glossary/api/)[テスト](/glossary/テスト/)を実行する：** 以下の[コマンド](/glossary/コマンド/)でJenkins [REST](/glossary/rest/) [API](/glossary/api/)の各[エンドポイント](/glossary/エンドポイント/)を直接[テスト](/glossary/テスト/)します。`-v`フラグで[リクエスト](/glossary/リクエスト/)・[レスポンス](/glossary/レスポンス/)の[ヘッダー](/glossary/ヘッダー/)を確認し、Jenkinsが何を期待しているかを明らかにできます。

```bash
curl -v -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic <your-base64-encoded-credentials>" \
  -d '{"parameter": [{"name": "TEST", "value": "true"}]}' \
  http://jenkins.example.com/job/<job-name>/buildWithParameters
```

**公式ドキュメントで[エンドポイント](/glossary/エンドポイント/)仕様を確認する：** Jenkins [REST](/glossary/rest/) [API](/glossary/api/)公式ドキュメント（`http://<jenkins-url>/api/`にアクセスして[JSON](/glossary/json/)形式の[API](/glossary/api/)仕様を参照）で、対象[エンドポイント](/glossary/エンドポイント/)の必須[パラメータ](/glossary/パラメータ/)と型定義を確認してください。[エンドポイント](/glossary/エンドポイント/)固有の[リクエスト](/glossary/リクエスト/)形式が記載されており、400[エラー](/glossary/エラー/)の原因特定に有効です。

**ユーザー[権限](/glossary/権限/)の確認：** [REST](/glossary/rest/) [API](/glossary/api/)[リクエスト](/glossary/リクエスト/)に使用している[認証](/glossary/認証/)[トークン](/glossary/トークン/)・[API](/glossary/api/)キーに対象ジョブの実行権限がない場合、[サーバー](/glossary/サーバー/)が400ではなく401・403[エラー](/glossary/エラー/)を返すことが多いですが、ツールの[バージョン](/glossary/バージョン/)や[セキュリティ](/glossary/セキュリティ/)設定によっては400が返されることもあります。Jenkins管理画面でユーザーロールと[権限](/glossary/権限/)を再度確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*