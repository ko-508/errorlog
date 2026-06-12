---
title: "GitHub組織のセキュリティを強化する：よくあるエラーと解決策"
date: 2026-06-10
lastmod: 2026-06-10
draft: false
description: "GitHub組織のセキュリティを強化するための実践的なガイド。一般的なエラーの原因と解決策をコード例を交えて解説します。"
tags: ["Dev.to - GitHub"]
trend_incident: true
---

## エラーの概要

GitHubは単なるソースコードプラットフォームではなく、アイデンティティシステム、ソフトウェアサプライチェーン、CI/CDプラットフォーム、シークレットストア、デプロイオーケストレーター、そして本番環境の変更管理システムとしての役割を担っています。そのため、GitHubのセキュリティ設定が不十分な場合、ソースコード、ワークフロー、シークレット、ビルドシステム、リリースプロセス、または本番環境が侵害されるリスクがあります。本記事では、GitHub組織のセキュリティを強化する際に遭遇しやすい設定ミスやポリシー違反による「エラー」に焦点を当て、その原因と解決策を解説します。

## 実際のエラーメッセージ例

GitHubのセキュリティ設定が不十分な場合、直接的なエラーメッセージとして表示されることは稀ですが、以下のような状況で問題が顕在化します。

**GitHub Actionsの実行失敗（権限不足）:**

```
Error: Resource not accessible by integration
```

**リポジトリへの不正なプッシュ（ブランチ保護ルール違反）:**

```
remote: error: GH006: Protected branch update failed for refs/heads/main.
remote: error: Required status check "build" is expected.
remote: error: Required approvals: 1
```

**シークレットの漏洩警告（GitHub Secret Scanning）:**

```json
{
  "alert_number": 123,
  "created_at": "2023-01-01T12:00:00Z",
  "state": "open",
  "secret_type": "aws_access_key",
  "resolution": null,
  "resolved_by": null,
  "resolved_at": null,
  "url": "https://github.com/<your-org>/<your-repo>/security/secret-scanning/123",
  "repository": {
    "id": 456,
    "node_id": "MDEwOlJlcG9zaXRvcnk0NTY=",
    "name": "<your-repo>",
    "full_name": "<your-org>/<your-repo>",
    "private": true,
    "owner": {
      "login": "<your-org>",
      "id": 789,
      "node_id": "MDEyOk9yZ2FuaXphdGlvbjc4OQ==",
      "avatar_url": "https://avatars.githubusercontent.com/u/789?v=4",
      "gravatar_id": "",
      "url": "https://api.github.com/users/<your-org>",
      "html_url": "https://github.com/<your-org>",
      "type": "Organization",
      "site_admin": false
    }
  },
  "push_protection_bypass_reason": null
}
```

## よくある原因と解決手順

### 原因1：組織のベース権限が過剰に設定されている

GitHub組織のベース権限が「Read」や「Write」に設定されている場合、組織内のすべてのメンバーがデフォルトでその権限を持つことになります。これにより、意図しないリポジトリへのアクセスや変更が可能になり、セキュリティリスクが高まります。

**Before（エラーが起きるコード）：**

```json
# GitHub組織設定 (APIレスポンスの抜粋を想定)
{
  "default_repository_permission": "read",
  "members_can_create_repositories": true,
  "members_can_create_private_repositories": true
}
```

**After（修正後）：**

```json
# GitHub組織設定 (APIレスポンスの抜粋を想定)
{
  "default_repository_permission": "none",
  "members_can_create_repositories": false,
  "members_can_create_private_repositories": false
}
```

**解決手順：**
1. GitHub組織の「Settings」に移動します。
2. 「Member privileges」セクションを開きます。
3. 「Base permissions」を「No permission」に設定します。
4. 「Repository creation」や「Repository visibility changes」などの項目も、必要に応じて制限します。
5. 各リポジトリへのアクセスは、チームとリポジトリの組み合わせで明示的に付与するようにします。

### 原因2：ブランチ保護ルールが不十分である

本番環境にデプロイされるコードを含むブランチ（例: `main`、`master`）に、十分なブランチ保護ルールが設定されていない場合、未承認の変更が直接プッシュされたり、必要なレビューやCI/CDチェックがスキップされたりする可能性があります。

**Before（エラーが起きるコード）：**

```json
# GitHubリポジトリのブランチ保護ルール (APIレスポンスの抜粋を想定)
{
  "required_pull_request_reviews": null,
  "required_status_checks": null,
  "enforce_admins": false
}
```

**After（修正後）：**

```json
# GitHubリポジトリのブランチ保護ルール (APIレスポンスの抜粋を想定)
{
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1
  },
  "required_status_checks": {
    "strict": true,
    "contexts": ["build", "test"]
  },
  "enforce_admins": true,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
```

**解決手順：**
1. GitHubリポジトリの「Settings」に移動します。
2. 「Branches」セクションを開き、保護したいブランチ（例: `main`）の「Add rule」または既存ルールの「Edit」をクリックします。
3. 以下の項目を有効化します。
    *   **Require a pull request before merging:** プルリクエストを必須にします。
    *   **Require approvals:** 承認レビュー数を設定します。
    *   **Require status checks to pass before merging:** CI/CDパイプラインの成功を必須にします。
    *   **Require signed commits:** コミット署名を必須にします。
    *   **Include administrators:** 管理者にもルールを適用します。
4. 必要に応じて、「Restrict who can push to matching branches」や「Allow force pushes」などの設定も調整します。

### 原因3：GitHub Actionsのシークレット管理が不適切である

GitHub Actionsでクラウドプロバイダの認証情報やAPIキーなどのシークレットを使用する際、それらをGitHubのシークレットストアに長期的に保存していると、漏洩のリスクが高まります。特に、Classic Personal Access Token (PAT) の使用は推奨されません。

**Before（エラーが起きるコード）：**

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS
on:
  push:
    branches:
      - main
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Configure AWS Credentials
      uses: aws-actions/configure-aws-credentials@v1
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1
    - name: Deploy application
      run: aws s3 sync . s3://<your-bucket-name>
```

**After（修正後）：**

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS
on:
  push:
    branches:
      - main
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write # OIDCトークンを要求するために必要
      contents: read
    steps:
    - uses: actions/checkout@v3
    - name: Configure AWS Credentials
      uses: aws-actions/configure-aws-credentials@v1
      with:
        role-to-assume: arn:aws:iam::<your-aws-account-id>:role/<your-github-actions-role>
        aws-region: us-east-1
    - name: Deploy application
      run: aws s3 sync . s3://<your-bucket-name>
```

**解決手順：**
1. **OIDC (OpenID Connect) Federationの利用:**
   *   AWS、Azure、GCPなどの主要なクラウドプロバイダは、GitHub ActionsからのOIDCトークンを受け入れ、一時的な認証情報を発行する機能を提供しています。これにより、GitHubに長期的なシークレットを保存する必要がなくなります。
   *   クラウドプロバイダ側で、GitHub ActionsからのOIDCトークンを信頼するIAMロール（または同等の権限）を設定します。
   *   GitHub Actionsのワークフローで、`permissions: id-token: write` を設定し、`aws-actions/configure-aws-credentials` などのアクションで `role-to-assume` を指定します。
2. **Fine-grained Personal Access Token (PAT) の利用:**
   *   OIDCが利用できない場合、Classic PATの代わりにFine-grained PATを使用します。
   *   Fine-grained PATは、特定のリポジトリや権限に限定できるため、Classic PATよりも安全です。
   *   PATには必ず有効期限を設定し、最小限の権限のみを付与します。
3. **Secret ScanningとPush Protectionの有効化:**
   *   GitHub Advanced Security (GHAS) の機能であるSecret ScanningとPush Protectionを有効にすることで、コミットやプッシュ時に誤ってシークレットが漏洩するのを防ぎます。

## ツール固有の注意点

*   **GitHub Enterprise Cloud / Server:** GitHub Enterpriseを利用している場合、組織レベルまたはエンタープライズレベルでルールセットを適用できます。これにより、個々のリポジトリ設定に依存せず、一貫したセキュリティポリシーを強制できます。例えば、すべてのリポジトリで特定のブランチ保護ルールを必須にしたり、特定のユーザーグループのみがリポジトリを作成できるようにしたりできます。
*   **GitHub Advanced Security (GHAS):** GHASは、Secret Scanning、Code Scanning (CodeQL)、Dependency Review、Dependabotなどの高度なセキュリティ機能を提供します。これらの機能を活用することで、コードの脆弱性、依存関係のセキュリティ問題、シークレットの漏洩を早期に検出し、防止できます。特に、Push Protectionは、シークレットがリポジトリにプッシュされるのをリアルタイムでブロックするため、非常に効果的です。
*   **GitHub Apps / OAuth Apps:** 組織にインストールされているGitHub AppsやOAuth Appsは、リポジトリや組織のデータにアクセスする権限を持っています。これらのAppの権限を定期的にレビューし、不要なAppや過剰な権限を持つAppは削除または制限することが重要です。

## それでも解決しない場合

*   **GitHub Audit Logの確認:** 組織またはエンタープライズのAudit Logは、誰が、いつ、どのような操作を行ったかの詳細な記録を提供します。不審なアクティビティや設定変更の履歴を確認することで、問題の原因を特定できる場合があります。
    *   組織のAudit Log: `https://github.com/organizations/<your-org>/settings/audit-log`
    *   エンタープライズのAudit Log: `https://github.com/enterprises/<your-enterprise>/settings/audit-log`
*   **GitHub CLIでのデバッグ:** GitHub CLI (`gh`) を使用して、リポジトリや組織の設定をプログラム的に取得し、期待される設定と比較することで、設定ミスを発見できる場合があります。
    ```bash
    # リポジトリのブランチ保護ルールを取得
    gh api repos/<your-org>/<your-repo>/branches/main/protection

    # 組織のメンバー権限を取得
    gh api orgs/<your-org>
    ```
*   **公式ドキュメントの参照:** GitHubのセキュリティ設定は多岐にわたります。最新かつ詳細な情報は、GitHubの公式ドキュメントで確認してください。
    *   [Securing your organization](https://docs.github.com/en/organizations/managing-organization-settings/securing-your-organization)
    *   [About security hardening with GitHub Actions](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
    *   [About GitHub Advanced Security](https://docs.github.com/en/code-security/getting-started/about-github-advanced-security)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*