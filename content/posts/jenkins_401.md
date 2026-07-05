---
draft: true
title: "Jenkins の 401 エラー：原因と解決策"
date: 2026-06-18
description: "Jenkinsへの認証に失敗した"
tags: ["Jenkins"]
errorCode: "401"
service: "Jenkins"
error_type: "401"
components: []
related_services: ["REST API", "LDAP", "SSO", "cURL", "Python requests", "Declarative pipeline"]
---

## エラーの概要

Jenkins 401[エラー](/glossary/エラー/)は、Jenkins[サーバー](/glossary/サーバー/)へのアクセス時に[認証](/glossary/認証/)が失敗したことを示します。[API](/glossary/api/)[トークン](/glossary/トークン/)の有効期限切れ、ユーザー名や[パスワード](/glossary/パスワード/)の誤入力、セキュリティレルム設定の変更により、クライアントがJenkinsに正常に[認証](/glossary/認証/)できない状態です。特にパイプラインスクリプトからの自動アクセスや[REST](/glossary/rest/) [API](/glossary/api/)呼び出し時に頻出します。

## 実際のエラーメッセージ例

**[REST](/glossary/rest/) [API](/glossary/api/)呼び出し時：**

```json
{
  "url": "https://jenkins.example.com/api/json",
  "status": 401,
  "message": "Authentication required",
  "response": "HTTP 401 Unauthorized"
}
```

**cURL[コマンド](/glossary/コマンド/)実行時：**

```bash
$ curl -u myuser:mytoken https://jenkins.example.com/api/json
curl: (22) The requested URL returned error: 401 Unauthorized
```

**Jenkins[コンソール](/glossary/コンソール/)出力：**

```
ERROR: Could not authenticate with provided credentials
hudson.security.SecurityException: Authentication failed: Invalid username or API token
```

## よくある原因と解決手順

### 原因1：APIトークンの有効期限切れまたは削除

Jenkinsの[セキュリティ](/glossary/セキュリティ/)向上のため、[API](/glossary/api/)[トークン](/glossary/トークン/)には有効期限が設定されることがあります。[トークン](/glossary/トークン/)が自動削除されたり、セキュリティレルムの再設定時に既存[トークン](/glossary/トークン/)が無効化される場合があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 古いトークンで認証を試みる
curl -u jenkins_user:<your-old-api-token> \
  https://jenkins.example.com/api/json
# 結果：401 Unauthorized
```

**After（修正後）：**

```bash
# Jenkinsの管理画面から新しいトークンを生成した後、新しいトークンを使用
curl -u jenkins_user:<your-new-api-token> \
  https://jenkins.example.com/api/json
# 結果：200 OK
```

Jenkins[サーバー](/glossary/サーバー/)で以下の手順を実行してください：

1. Jenkins管理画面に[ログイン](/glossary/ログイン/)
2. 左メニューから「ユーザー」→ユーザー一覧から該当ユーザーを選択
3. 「設定」ページで「[API](/glossary/api/)[トークン](/glossary/トークン/)」セクションへスクロール
4. 既存[トークン](/glossary/トークン/)が無効な場合は削除し、「新しい[トークン](/glossary/トークン/)を生成」をクリック
5. 生成された[トークン](/glossary/トークン/)値をコピーして、スクリプトや[API](/glossary/api/)クライアントに設定

### 原因2：ユーザー名またはAPIトークンの入力ミス

基本認証時にJenkinsのユーザー名を誤って入力する場合が多いです。特にメールアドレスを使用したり、大文字小文字を混同したり、[トークン](/glossary/トークン/)部分に余分なスペースが含まれていることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests
from requests.auth import HTTPBasicAuth

# メールアドレスを使用（誤り）
response = requests.get(
    'https://jenkins.example.com/api/json',
    auth=HTTPBasicAuth('user@example.com', '<your-api-token>')
)
# 結果：401 Unauthorized
```

**After（修正後）：**

```python
import requests
from requests.auth import HTTPBasicAuth

# Jenkinsの管理画面に表示されるユーザー名を使用
response = requests.get(
    'https://jenkins.example.com/api/json',
    auth=HTTPBasicAuth('jenkins_user', '<your-api-token>')
)
# 結果：200 OK
```

認証情報を確認するチェックリスト：

- Jenkinsの「ユーザー」一覧表示画面で、実際のユーザー名を確認する
- [トークン](/glossary/トークン/)値をコピー＆ペーストする際、前後の余分なスペースが含まれていないか確認
- [パスワード](/glossary/パスワード/)[認証](/glossary/認証/)の場合、大文字小文字が正確か確認
- [API](/glossary/api/)[トークン](/glossary/トークン/)は`Base64`エンコーディングの対象になるため、特殊文字が含まれていても問題ない

### 原因3：セキュリティレルムの設定変更

Jenkinsのセキュリティレルム設定を変更すると（例：ローカルユーザーデータベースからLDAPへ、またはその逆）、既存の[API](/glossary/api/)[トークン](/glossary/トークン/)やユーザー認証情報が無効になることがあります。特にLDAPやSSO[認証](/glossary/認証/)への移行時に発生しやすいです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# セキュリティレルム変更前に生成されたトークン
curl -u admin:<your-old-local-token> \
  https://jenkins.example.com/api/json
# セキュリティレルム変更後：401 Unauthorized
```

**After（修正後）：**

```bash
# セキュリティレルム変更後、新しく生成したトークン
curl -u admin:<your-new-realm-token> \
  https://jenkins.example.com/api/json
# 結果：200 OK
```

対応手順：

1. Jenkins管理画面の「[セキュリティ](/glossary/セキュリティ/)」設定ページを確認
2. セキュリティレルムが最近変更されていないか履歴を確認
3. セキュリティレルム変更後は、すべてのユーザーが自分のユーザーページで[API](/glossary/api/)[トークン](/glossary/トークン/)を再生成する必要があります
4. LDAP連携やSSO[認証](/glossary/認証/)に移行した場合、LDAPユーザー名がJenkinsのローカルユーザー名と異なる可能性があるため、正確なユーザー名を確認してください

## ツール固有の注意点

**Declarativeパイプラインでの認証設定：**

Jenkinsパイプラインから[プライベートレジストリ](/glossary/プライベートレジストリ/)やリモートサーバーにアクセスする際、認証情報が正しく設定されていない場合は401[エラー](/glossary/エラー/)が発生します。

```groovy
pipeline {
    agent any
    options {
        // credentialsIdを使用することで安全に認証情報を管理
        timestamps()
    }
    stages {
        stage('API Call') {
            steps {
                script {
                    withCredentials([usernamePassword(
                        credentialsId: 'jenkins-api-credentials',
                        usernameVariable: 'JENKINS_USER',
                        passwordVariable: 'JENKINS_TOKEN'
                    )]) {
                        sh '''
                            curl -u ${JENKINS_USER}:${JENKINS_TOKEN} \
                              https://jenkins.example.com/api/json
                        '''
                    }
                }
            }
        }
    }
}
```

認証情報を「シークレットテキスト」ではなく「ユーザー名と[パスワード](/glossary/パスワード/)」タイプのCredentialsとして登録し、パイプラインから参照することで、[トークン](/glossary/トークン/)が[コンソール](/glossary/コンソール/)出力に表示される問題を防げます。

**jenkins.xml設定確認：**

Jenkinsが[Docker](/glossary/docker/)[コンテナ](/glossary/コンテナ/)またはWindowsサービスとして実行されている場合、`jenkins.xml`の認証設定を確認してください。

```xml
<!-- ローカルユーザーデータベースを使用する場合の最小構成 -->
<hudson>
  <securityRealm class="hudson.security.LocalSecurityRealm">
    <disableSignup>true</disableSignup>
  </securityRealm>
  <authorizationStrategy class="hudson.security.AuthorizationStrategy$Unsecured"/>
</hudson>
```

セキュリティレルムクラスが空の場合やコメントアウトされている場合は、ユーザー[認証](/glossary/認証/)が無効になっているため、設定を確認して修正する必要があります。

## それでも解決しない場合

**[ログ](/glossary/ログ/)の確認：**

Jenkinsの[ログファイル](/glossary/ログファイル/)で詳細な[認証](/glossary/認証/)[エラー](/glossary/エラー/)を確認できます。

```bash
# Docker環境でのログ確認
docker logs <jenkins-container-id> | grep -i "authentication failed"

# 通常のJenkinsサーバーの場合
tail -f /var/log/jenkins/jenkins.log | grep -i "authentication"

# Windowsの場合
Get-Content "C:\Program Files\Jenkins\jenkins.log" -Tail 100 | Select-String "Authentication"
```

**[デバッグ](/glossary/デバッグ/)用[API](/glossary/api/)[テスト](/glossary/テスト/)：**

簡単な[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)で[トークン](/glossary/トークン/)の有効性を直接確認します。

```bash
# ユーザー情報を取得するAPI（トークン有効性テスト）
curl -v -u jenkins_user:<your-api-token> \
  https://jenkins.example.com/user/jenkins_user/api/json

# verbose出力(-v)でHTTPヘッダーを確認し、認証ヘッダーの形式を検証できます
```

**Jenkins[バージョン](/glossary/バージョン/)確認：**

古いJenkins[バージョン](/glossary/バージョン/)では[API](/glossary/api/)[トークン](/glossary/トークン/)機能が異なる場合があります。

```bash
# Jenkinsバージョン確認
curl -s https://jenkins.example.com/api/json | grep version
```

Jenkins 2.176以降を使用している場合、[API](/glossary/api/)[トークン](/glossary/トークン/)の有効期限設定が利用可能です。[バージョン](/glossary/バージョン/)が古い場合はアップグレードを検討してください。

**公式ドキュメント参照：**

- [Jenkins API Token設定ガイド](https://www.jenkins.io/doc/book/system-administration/authenticating-scripted-clients/)
- [Jenkins認証とセキュリティレルム](https://www.jenkins.io/doc/book/system-administration/security/)

上記の手順を順に実行することで、ほとんどの401[エラー](/glossary/エラー/)は解決されます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*