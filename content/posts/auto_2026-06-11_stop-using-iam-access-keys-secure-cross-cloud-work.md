---
title: "AWS IAMアクセスキーの代わりにOIDCフェデレーションで安全なクロス環境認証を実現する方法"
date: 2026-06-11
lastmod: 2026-06-11
draft: false
description: "AWS IAMアクセスキーの利用はセキュリティリスクが高いです。OpenID Connect (OIDC) フェデレーションを利用して、GitHub ActionsやAzure ADなどの外部サービスからAWSリソースへ安全にアクセスする方法を解説します。"
tags: ["Dev.to - AWS"]
trend_incident: true
---

## エラーの概要

このエラーは、厳密にはHTTPエラーコードとして直接発生するものではありません。代わりに、AWS IAMアクセスキーを外部サービスで使用する際に発生する**セキュリティ上の脆弱性**と、その結果として生じる**認証失敗や情報漏洩のリスク**を指します。AWSのベストプラクティスでは、長期的なIAMアクセスキーの使用は非推奨とされており、OpenID Connect (OIDC) フェデレーションを用いた一時的な認証情報の利用が推奨されています。

## 実際のエラーメッセージ例

IAMアクセスキーの誤用自体が直接エラーメッセージを生成するわけではありませんが、キーの漏洩や期限切れ、権限不足などによって、以下のような認証失敗のエラーが発生する可能性があります。

**AWS CLIでの認証失敗例:**

```
An error occurred (SignatureDoesNotMatch) when calling the GetCallerIdentity operation: The request signature we calculated does not match the signature you provided. Check your AWS Secret Access Key and signing method.
```

**GitHub Actionsでの認証失敗例:**

```yaml
Run aws s3 ls
Error: Failed to authenticate with AWS. Please check your AWS credentials.
Error: The process '/usr/bin/aws' failed with exit code 255
```

## よくある原因と解決手順

### 原因1：長期的なIAMアクセスキーの使用

多くの開発者や運用エンジニアは、外部サービス（GitHub Actions、Azure Functionsなど）からAWSリソースにアクセスする際に、IAMユーザーを作成し、そのアクセスキー（`AWS_ACCESS_KEY_ID`と`AWS_SECRET_ACCESS_KEY`）を外部サービスのシークレットとして設定しがちです。しかし、これらの長期的なアクセスキーは漏洩リスクが高く、一度漏洩するとAWS環境全体が危険に晒される可能性があります。

**Before（エラーが起きるコード）：**

```yaml
# .github/workflows/deploy.yml (GitHub Actionsの例)
name: Deploy to AWS
on: [push]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }} # 非推奨！
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }} # 非推奨！
          aws-region: us-east-1
      - name: Deploy to S3
        run: aws s3 sync . s3://your-bucket-name
```

**After（修正後）：**

```yaml
# .github/workflows/deploy.yml (GitHub Actionsの例)
name: Deploy to AWS
on: [push]
permissions:
  id-token: write # OIDCフェデレーションに必須
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<AWS_ACCOUNT_ID>:role/YourGitHubOidcRole # OIDCで引き受けるIAMロール
          aws-region: us-east-1
      - name: Deploy to S3
        run: aws s3 sync . s3://your-bucket-name
```

### 原因2：IAMロールの信頼ポリシーが不適切

OIDCフェデレーションを導入しても、IAMロールの信頼ポリシーが適切に設定されていないと、意図しないエンティティがロールを引き受けてしまうリスクがあります。特に、`aud` (audience) クレームだけでなく、`sub` (subject) クレームも厳密に指定することで、特定のアプリケーションやリポジトリのみがロールを引き受けられるように制限する必要があります。

**Before（エラーが起きるコード）：**

```json
# IAMロールの信頼ポリシー (GitHub Actionsの例 - 制限が緩い)
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
```

**After（修正後）：**

```json
# IAMロールの信頼ポリシー (GitHub Actionsの例 - 適切な制限)
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:repo": "<your-github-org>/<your-repo-name>:*" # 特定のリポジトリに制限
        }
      }
    }
  ]
}
```

### 原因3：OIDCプロバイダーの登録ミス

AWS IAMでOIDCプロバイダーを登録する際に、プロバイダーURLやオーディエンス（Audience）を誤って設定すると、AWSが外部からのJWTトークンを検証できず、認証が失敗します。特に、Azure ADの場合、テナントIDやアプリケーション（クライアント）IDの指定が重要です。

**Before（エラーが起きるコード）：**

```text
# AWS IAMコンソールでのOIDCプロバイダー登録 (Azure ADの例 - URLまたはAudienceが誤っている)
プロバイダーURL: https://login.microsoftonline.com/<間違った_AZURE_TENANT_ID>/v2.0
Audience: <間違った_AZURE_APP_CLIENT_ID>
```

**After（修正後）：**

```text
# AWS IAMコンソールでのOIDCプロバイダー登録 (Azure ADの例 - 正しい設定)
プロバイダーURL: https://login.microsoftonline.com/<YOUR_AZURE_TENANT_ID>/v2.0
Audience: <YOUR_AZURE_APP_CLIENT_ID>
```

## ツール固有の注意点

### GitHub Actionsの場合

GitHub ActionsでOIDCフェデレーションを使用するには、ワークフローファイルに`id-token: write`パーミッションを付与することが必須です。これにより、GitHub ActionsがOIDC JWTトークンをリクエストできるようになります。この設定がないと、`aws-actions/configure-aws-credentials`アクションがAWSロールを引き受けることができません。

### Azure AD (Entra ID) の場合

Azure ADをOIDCプロバイダーとして利用する場合、AWS IAMの信頼ポリシーで`sub`クレームにAzure ADのサービスプリンシパルオブジェクトIDを指定することで、特定のアプリケーションのみがロールを引き受けられるように厳密に制御できます。また、Azure ADのアプリケーション登録は、特別な要件がない限り「シングルテナント」に設定することが、セキュリティ上のベストプラクティスです。

### Infrastructure-as-Code (IaC) での注意点

TerraformやCloudFormationなどのIaCツールでOIDCプロバイダーを自動設定する場合、AWSはプロバイダーのサーバー証明書サムプリント（Thumbprint）を要求します。GitHubやMicrosoftがSSL証明書を更新する可能性を考慮し、このサムプリントを動的に取得するか、定期的に更新する仕組みを導入することが重要です。

## それでも解決しない場合

1.  **AWS CloudTrailの確認:** AWS CloudTrailは、AWSアカウント内で行われたすべてのアクションを記録します。`sts:AssumeRoleWithWebIdentity`アクションの失敗エントリを探し、エラーメッセージや拒否された理由を確認してください。
2.  **外部IDプロバイダーのログ:** GitHub Actionsであればワークフローの実行ログ、Azure ADであればサインインログや監査ログを確認し、JWTトークンの発行や検証に関するエラーがないか調べます。
3.  **JWTトークンのデコード:** 外部サービスからAWSに送信されるJWTトークンを一時的に取得し、[jwt.io](https://jwt.io/)などのツールでデコードして、`aud`、`sub`、`iss`などのクレームが期待通りに設定されているか確認します。
4.  **公式ドキュメントの参照:**
    *   AWS IAM OIDCプロバイダーの作成: [https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)
    *   GitHub ActionsでのOIDCの使用: [https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
    *   Azure ADとAWSの統合: [https://docs.microsoft.com/en-us/azure/active-directory/saas-apps/amazon-web-services-tutorial](https://docs.microsoft.com/en-us/azure/active-directory/saas-apps/amazon-web-services-tutorial)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*