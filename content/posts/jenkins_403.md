---
title: "Jenkins の 403 エラー：原因と解決策"
date: 2026-06-18
description: "JenkinsリソースへのアクセスがCSRFまたは権限チェックで拒否された。Jenkins 403 エラーの原因と解決策を解説します。"
tags: ["Jenkins"]
errorCode: "403"
service: "Jenkins"
error_type: "403"
components: []
related_services: ["CSRF", "Matrix-based security", "Role-based Access Control", "API Token"]
---

## エラーの概要

Jenkins の 403 Forbidden [エラー](/glossary/エラー/)は、ユーザーが[認可](/glossary/認可/)(Authorization)チェックに失敗したことを意味します。CSRF(クロスサイトリクエストフォージェリ)保護による拒否、または Jenkins の権限設定で必要な[権限](/glossary/権限/)がないために発生します。特に [CI/CD](/glossary/ci-cd/) パイプラインでジョブを自動実行したり、外部ツールから Jenkins [API](/glossary/api/) を呼び出したりする際に頻出する[エラー](/glossary/エラー/)です。

## 実際のエラーメッセージ例

**ブラウザから直接アクセスした場合：**

```
HTTP/1.1 403 Forbidden

403

Manage and Assign Roles
You are not authorized to view this page.
```

**[API](/glossary/api/)呼び出し時の[レスポンス](/glossary/レスポンス/)（[JSON](/glossary/json/)）：**

```json
{
  "error": "403 Forbidden",
  "message": "No valid crumb was included in the request"
}
```

**Jenkinsの[ログ](/glossary/ログ/)出力例：**

```
Jenkins.instance.checkPermission(hudson.model.Item.Build) denies hudson.model.User
Authentication required
```

## よくある原因と解決手順

### 原因1：CSRF保護が有効なのにCrumbヘッダーを付けずにAPIを呼び出している

Jenkins の CSRF 保護が有効になっていると、POST [リクエスト](/glossary/リクエスト/)（ジョブの実行、設定変更など）には Crumb [トークン](/glossary/トークン/)が必須です。この[トークン](/glossary/トークン/)を付けずに[リクエスト](/glossary/リクエスト/)すると 403 [エラー](/glossary/エラー/)が返されます。特に外部スクリプトから Jenkins [API](/glossary/api/) を呼ぶ場合、この原因が最も多いです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Crumbトークンを付けずにジョブをビルド
curl -X POST "http://localhost:8080/job/my-job/build" \
  -u "jenkins-user:<your-api-token>"
```

**After（修正後）：**

```bash
# 1. Crumbを取得
CRUMB=$(curl -s "http://localhost:8080/crumbIssuer/api/json" \
  -u "jenkins-user:<your-api-token>" | grep -o '"crumb":"[^"]*"' | cut -d'"' -f4)

# 2. Crumbをヘッダーに付けてリクエストを送信
curl -X POST "http://localhost:8080/job/my-job/build" \
  -u "jenkins-user:<your-api-token>" \
  -H "Jenkins-Crumb: $CRUMB"
```

Crumb の取得に失敗した場合は、Jenkins が CSRF 保護を有効にしているか確認し、[API](/glossary/api/) [トークン](/glossary/トークン/)が正しいことを検証してください。

### 原因2：Matrix-based security でジョブへの Build/Configure 権限がない

Jenkins の権限設定で Matrix-based security または Role-based Access Control を使用している場合、ユーザーがジョブをビルドしたり設定を変更したりする[権限](/glossary/権限/)がないと 403 [エラー](/glossary/エラー/)が発生します。[権限](/glossary/権限/)マトリックスでユーザー行とジョブ権限列の交差点がチェックされていないと拒否されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ci-user には my-job の Build 権限がない
curl -X POST "http://localhost:8080/job/my-job/build" \
  -u "ci-user:<your-api-token>" \
  -H "Jenkins-Crumb: $CRUMB"

# → 403 Forbidden が返される
```

**After（修正後）：**

```bash
# Jenkins 管理画面で ci-user に権限を付与した後
# （Manage Jenkins → Configure Global Security → 権限マトリックスで
#   ci-user 行の Job/Build、Job/Discover をチェック）

curl -X POST "http://localhost:8080/job/my-job/build" \
  -u "ci-user:<your-api-token>" \
  -H "Jenkins-Crumb: $CRUMB"

# → 201 Created (成功)
```

[権限](/glossary/権限/)の付与は Jenkins の Web UI で実施します。**Manage Jenkins** → **Configure Global Security** → **Authorization** セクションで Matrix-based security を選択し、該当ユーザー行と必要な権限列（Job/Build など）をチェックしてください。

### 原因3：匿名ユーザーのアクセスが制限されているのに認証なしで API を呼んでいる

Jenkins で匿名アクセスを禁止しているのに、認証情報を付けずに [API](/glossary/api/) を呼び出すと 403 [エラー](/glossary/エラー/)が返されます。外部の CD/CD ツールや監視スクリプトから Jenkins にアクセスする際、[API](/glossary/api/) [トークン](/glossary/トークン/)の生成や指定を忘れると発生しやすい[エラー](/glossary/エラー/)です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 認証情報を付けずに Jenkins API を呼び出す
curl "http://localhost:8080/api/json"

# → 403 Forbidden
```

**After（修正後）：**

```bash
# Jenkins ユーザーとそのAPIトークンを指定
curl "http://localhost:8080/api/json" \
  -u "jenkins-user:<your-api-token>"

# → 200 OK でJSON応答が返される
```

[API](/glossary/api/) [トークン](/glossary/トークン/)の取得方法：**Jenkins 管理画面** → **ユーザー一覧** → 対象ユーザーをクリック → **設定** → **[API](/glossary/api/) Token** セクションで新しい[トークン](/glossary/トークン/)を生成してください。

## ツール固有の注意点

**CSRF保護の設定確認方法：**

Jenkins 管理画面で **Manage Jenkins** → **Configure Global Security** を開き、**CSRF Protection** セクションを確認します。「Prevent Cross Site Request Forgery exploits」がチェックされていれば CSRF 保護が有効です。逆に無効にしたい場合（[セキュリティ](/glossary/セキュリティ/)上は推奨されませんが）はここでチェックを外します。

**[API](/glossary/api/) [トークン](/glossary/トークン/)と基本認証の違い：**

Jenkins では `/user/<username>/generateApiToken` [エンドポイント](/glossary/エンドポイント/)経由で生成した[トークン](/glossary/トークン/)を使い、[HTTP](/glossary/http/) 基本認証で `username:api-token` の形式で[認証](/glossary/認証/)します。[パスワード](/glossary/パスワード/)ではなく [API](/glossary/api/) [トークン](/glossary/トークン/)を使うことで、複雑な[パスワード](/glossary/パスワード/)管理を避けられます。

**複数ジョブへのアクセス制御：**

Role-based Access Control([RBAC](/glossary/rbac/))プラグインを導入している場合、[ロール](/glossary/ロール/)定義で「Job/Build」「Job/Configure」などの粒度の細かい[権限](/glossary/権限/)を設定できます。個別ユーザーではなく[ロール](/glossary/ロール/)単位で権限管理すると運用が楽になります。

**Jenkins Pipeline での CSRF 対策：**

Groovy スクリプト内で Jenkins [API](/glossary/api/) を呼ぶ場合、スクリプトの実行ユーザーの[権限](/glossary/権限/)が適用されます。Pipeline ステップ内で `sh` で curl を実行する場合でも、該当ユーザーに[権限](/glossary/権限/)がなければ 403 [エラー](/glossary/エラー/)が発生します。

## それでも解決しない場合

**Jenkins[ログ](/glossary/ログ/)の確認：**

`<Jenkins ホーム>/logs/jenkins.log` または Jenkins 管理画面の **System Log** を確認します。「Permission denied」や「Insufficient permission」というメッセージが記録されているはずです。

**デバッグコマンド：**

```bash
# 現在のユーザーに付与されている権限を確認
curl "http://localhost:8080/api/json" \
  -u "jenkins-user:<your-api-token>" | jq '.'

# 特定ジョブの詳細情報を確認
curl "http://localhost:8080/job/my-job/api/json" \
  -u "jenkins-user:<your-api-token>"

# ジョブのビルド実行（詳細レスポンス）
curl -v -X POST "http://localhost:8080/job/my-job/build" \
  -u "jenkins-user:<your-api-token>" \
  -H "Jenkins-Crumb: $CRUMB"
```

`-v` フラグでレスポンスヘッダーを確認すると、Crumb の有無や権限周りの詳細がわかります。

**公式ドキュメント参照：**

Jenkins 公式の [Remote API](https://www.jenkins.io/doc/book/using-jenkins/remote-access-api/) ドキュメントに [API](/glossary/api/) 呼び出しの詳細仕様が記載されています。また **Manage Jenkins** → **Script Console** で Groovy スクリプトを直接実行して[テスト](/glossary/テスト/)することもできます。権限設定を確認したい場合は [Role-Based Access Control](https://plugins.jenkins.io/role-based-auth/) プラグインのドキュメントも参照してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*