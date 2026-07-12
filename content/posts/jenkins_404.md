---
draft: true
title: "Jenkins の 404 エラー：原因と解決策"
date: 2026-06-18
description: "指定したジョブまたはビルドが見つからない"
tags: ["Jenkins"]
errorCode: "404"
service: "Jenkins"
error_type: "404"
components: []
related_services: ["REST API", "Jenkinsfile"]
---

## エラーの概要

404[エラー](/glossary/エラー/)は、Jenkinsが指定したジョブまたはビルドを見つけられない状態を示します。この[エラー](/glossary/エラー/)はパイプライン実行時、[API](/glossary/api/)アクセス時、またはWebUIでのジョブ確認時に発生し、ジョブの削除・リネーム、[URL](/glossary/url/)構成の誤り、ビルド番号の不一致などが主な原因となります。

## 実際のエラーメッセージ例

**Webブラウザでアクセス時：**

```
404 Not Found

The requested URL /job/<job-name>/ was not found on this server.
```

**[REST](/glossary/rest/) [API](/glossary/api/)経由での[レスポンス](/glossary/レスポンス/)：**

```json
{
  "status": 404,
  "error": "Job '<job-name>' does not exist",
  "_class": "hudson.model.Item$ItemNotFoundException"
}
```

**Jenkinsコンソールログ：**

```
ERROR hudson.model.Items - Item 'build-test' not found in 'jobs' folder
```

## よくある原因と解決手順

### 原因1：ジョブ名の綴りや大文字小文字が異なる

Jenkinsはジョブ名を大文字と小文字を区別するため、[URL](/glossary/url/)や[API](/glossary/api/)呼び出しで正確な名前を指定する必要があります。例えば「MyBuildJob」というジョブに対して「mybuildjob」でアクセスすると[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ジョブ名を小文字で指定しているが、実際は大文字小文字混合
curl -X GET "http://localhost:8080/job/mybuildjob/api/json" \
  -u <your-jenkins-user>:<your-api-token>
```

**After（修正後）：**

```bash
# Jenkinsのジョブ管理画面で確認した正確なジョブ名を使用
curl -X GET "http://localhost:8080/job/MyBuildJob/api/json" \
  -u <your-jenkins-user>:<your-api-token>
```

確認方法としては、Jenkinsのホーム画面で該当ジョブを右クリック→「リンクアドレスをコピー」で正確な[URL](/glossary/url/)を取得するか、ジョブ設定ページから直接[URL](/glossary/url/)を確認することが確実です。

### 原因2：フォルダ内のジョブのURLパスが間違っている

Jenkinsで[フォルダ](/glossary/フォルダ/)を使用してジョブを整理している場合、[URL](/glossary/url/)[パス](/glossary/パス/)は `job/<フォルダ名>/job/<ジョブ名>` という形式になります。単純に `job/<ジョブ名>` でアクセスすると、トップレベルのジョブしか検索されずに404[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# フォルダ構造を無視してジョブ名のみでアクセス
curl -X POST "http://localhost:8080/job/deploy-test/build" \
  -u <your-jenkins-user>:<your-api-token>
```

**After（修正後）：**

```bash
# フォルダを含めた正確なURLパスを指定
# フォルダ構造：project-folder > deploy-test
curl -X POST "http://localhost:8080/job/project-folder/job/deploy-test/build" \
  -u <your-jenkins-user>:<your-api-token>
```

ネストされた[フォルダ](/glossary/フォルダ/)がある場合は、各階層を `job/` で連結します。例えば、構造が「parent-folder > child-folder > build-job」の場合、[URL](/glossary/url/)は `/job/parent-folder/job/child-folder/job/build-job` となります。

### 原因3：ビルド番号が存在しないか削除されている

Jenkinsのビルド履歴は保持[ポリシー](/glossary/ポリシー/)によって自動削除される場合があります。削除されたビルド番号にアクセスしようとすると404[エラー](/glossary/エラー/)が返されます。また、存在しないビルド番号（例：ビルド100が最新のときにビルド200にアクセス）を指定した場合も同様です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 削除済みまたは存在しないビルド番号を指定
curl -X GET "http://localhost:8080/job/MyBuildJob/999/api/json" \
  -u <your-jenkins-user>:<your-api-token>
```

**After（修正後）：**

```bash
# 最新ビルドまたは有効なビルド番号を指定
# 最新ビルド情報を取得
curl -X GET "http://localhost:8080/job/MyBuildJob/lastBuild/api/json" \
  -u <your-jenkins-user>:<your-api-token>

# または、ビルド履歴から有効な番号を確認して指定
curl -X GET "http://localhost:8080/job/MyBuildJob/42/api/json" \
  -u <your-jenkins-user>:<your-api-token>
```

ビルド履歴の保持[ポリシー](/glossary/ポリシー/)は、ジョブの設定画面の「ビルド履歴の保存」セクションで確認・変更できます。`lastBuild`、`lastStableBuild`、`lastSuccessfulBuild` といった特殊な参照もJenkinsで利用可能で、ビルド番号が不確定な場合に活用できます。

## ツール固有の注意点

**Jenkinsの宣言型パイプラインでのジョブ参照：**

Jenkinsfileを使用するパイプラインジョブでは、他のジョブをビルドパラメータで参照する場合があります。このとき、ジョブ名を動的に構成する際は、[フォルダ](/glossary/フォルダ/)構造を含めた完全な[パス](/glossary/パス/)を指定する必要があります。

```groovy
// Before: フォルダを省略してビルド失敗
build job: 'deploy-test'

// After: フォルダを含めた完全なパスを指定
build job: 'project-folder/deploy-test'
```

**[キャッシュ](/glossary/キャッシュ/)やショートカットによる古い[URL](/glossary/url/)：**

ブラウザの[キャッシュ](/glossary/キャッシュ/)やブックマーク、外部ツール連携設定に古い[URL](/glossary/url/)が保存されていないか確認してください。Jenkinsでジョブをリネームまたは移動した場合、統合ツール（GitLab、GitHub、監視システム等）に設定された[Webhook](/glossary/webhook/)や[API](/glossary/api/)呼び出し[URL](/glossary/url/)も更新が必要です。

**Jenkins UI上での確認方法：**

Jenkinsホーム画面で目的のジョブを開き、ブラウザのアドレスバーに表示された[URL](/glossary/url/)が正確な[パス](/glossary/パス/)です。この[URL](/glossary/url/)をコピーして、[API](/glossary/api/)呼び出しやスクリプトで使用することで、綴り間違いを防げます。

## それでも解決しない場合

**Jenkinsの[ログ](/glossary/ログ/)を確認する：**

Jenkins マスター上で以下の[ログファイル](/glossary/ログファイル/)を確認し、404[エラー](/glossary/エラー/)の詳細情報を取得します。

```bash
# Jenkinsのログファイル位置（デフォルト）
tail -f /var/log/jenkins/jenkins.log

# またはJenkinsのWebUI：
# 「Manage Jenkins」→「System Log」→「All Jenkins Logs」
```

**[REST](/glossary/rest/) [API](/glossary/api/)を使用した確認：**

```bash
# 利用可能なジョブ一覧を取得
curl -X GET "http://localhost:8080/api/json" \
  -u <your-jenkins-user>:<your-api-token> | grep '"name"'

# フォルダ内のジョブを確認
curl -X GET "http://localhost:8080/job/project-folder/api/json" \
  -u <your-jenkins-user>:<your-api-token>
```

**ジョブの存在確認[コマンド](/glossary/コマンド/)：**

```bash
# 特定のジョブが存在するか確認（HTTPステータスコードで判定）
curl -I "http://localhost:8080/job/MyBuildJob/api/json" \
  -u <your-jenkins-user>:<your-api-token>
# 200が返ればジョブは存在、404なら存在しない
```

**公式ドキュメント参照：**

- Jenkins [REST](/glossary/rest/) [API](/glossary/api/): https://www.jenkins.io/doc/book/using/remote-access-api/
- ジョブの構成と[フォルダ](/glossary/フォルダ/): https://www.jenkins.io/doc/book/managing/organizing-jobs/
- Jenkinsfileでのジョブ呼び出し: https://www.jenkins.io/doc/pipeline/steps/pipeline-build-step/

これらの手段で原因を特定できない場合は、Jenkinsの[バージョン](/glossary/バージョン/)が最新であるか確認し、プラグインの競合がないか確認することも有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*