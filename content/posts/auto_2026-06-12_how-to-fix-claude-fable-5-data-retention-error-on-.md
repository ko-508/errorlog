---
title: "Amazon BedrockでClaude Fable 5利用時に発生する「400 data retention mode 'default' is not available for this model」エラーの解決策"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "Amazon BedrockでClaude Fable 5を利用しようとした際に発生する「400 data retention mode 'default' is not available for this model」エラーの原因と解決策を詳細に解説します。データ保持ポリシーの変更方法と、それに伴う注意点について説明します。"
tags: ["Dev.to - AWS", "AWS", "Amazon Bedrock", "Claude Fable 5", "データ保持", "エラー解決"]
trend_incident: true
---

## エラーの概要

このエラー「400 data retention mode 'default' is not available for this model」は、Amazon BedrockでAnthropic Claude Fable 5モデルを利用しようとした際に発生します。これは、アカウントのデータ保持ポリシーがClaude Fable 5の要件を満たしていないために、モデルが利用できないことを示すものです。クライアント側の設定では解決できない、アカウントレベルのポリシーが原因です。

## 実際のエラーメッセージ例

Amazon Bedrockを介してClaude Fable 5を呼び出す際に、以下のようなAPIエラーやコンソール出力が表示されます。

**APIレスポンス例:**

```json
{
  "__type": "ValidationException",
  "message": "data retention mode 'default' is not available for this model"
}
```

**モデルステータス確認時のレスポンス例:**

```json
{
  "id": "anthropic.claude-fable-5",
  "status": "unavailable",
  "status_reason": "This model is not available under data retention mode 'default'.",
  "data_retention": {
    "mode": "default",
    "source": "model_default",
    "allowed_modes": ["provider_data_share"]
  }
}
```

## よくある原因と解決手順

### 原因1：Claude Fable 5が特定のデータ保持モードを要求している

Claude Fable 5（およびClaude Mythos 5）は「Covered Models」に分類され、信頼性と安全性の目的でプロンプトと応答を最大30日間保持する必要があります。そのため、ゼロデータ保持（`none`）モードでは利用できません。Fable 5は、データがモデルプロバイダーと共有されることを意味する`provider_data_share`モードを必須としています。

**なぜ発生するか：**
新しいAmazon Bedrockアカウントのデータ保持モードはデフォルトで`inherit`に設定されており、これがFable 5に対しては`default`モードとして解決されます。しかし、Fable 5は`default`モードを許可しておらず、`provider_data_share`モードのみを許可しているため、この不一致によりエラーが発生します。

**Before（エラーが起きるコード）：**

```bash
# 現在のデータ保持モードを確認する（読み取り専用）
curl https://bedrock-mantle.us-east-1.api.aws/v1/models/anthropic.claude-fable-5 \
  -H "x-api-key: $BEDROCK_API_KEY"
# レスポンスの "data_retention.mode" が "default" または "inherit" の場合、エラーが発生します。
```

**After（修正後）：**

```bash
# Bedrockコントロールプレーンのデータ保持モードを更新
curl -X PUT https://bedrock.us-east-1.amazonaws.com/data-retention \
  -H "Authorization: Bearer $AWS_BEARER_TOKEN_BEDROCK" \
  -H "Content-Type: application/json" \
  -d '{ "mode": "provider_data_share" }'

# Bedrockモデル推論プレーンのデータ保持モードを更新
curl -X PUT https://bedrock-mantle.us-east-1.api.aws/v1/data_retention \
  -H "x-api-key: $BEDROCK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "mode": "provider_data_share" }'
```
**解説:**
Claude Fable 5を利用するには、アカウントのデータ保持モードを`provider_data_share`に設定する必要があります。これは、プロンプトと応答がモデルプロバイダーと共有され、信頼性と安全性の目的で最大30日間保持されることを意味します。この設定は、Bedrockのコントロールプレーンとモデル推論プレーンの両方で更新する必要があります。

### 原因2：データ保持ポリシーの変更が片方のエンドポイントにしか適用されていない

Amazon Bedrockのデータ保持設定は、内部的に2つの異なるプレーン（コントロールプレーンとモデル推論プレーン）で管理されています。片方のエンドポイントのみで設定を変更しても、もう片方が古い設定のままだと、モデルは引き続き利用不可の状態となります。

**なぜ発生するか：**
ユーザーがデータ保持ポリシーを変更する際に、BedrockのAPIエンドポイントが複数存在することを見落とし、一方のエンドポイントにのみ変更を適用してしまうことがあります。これにより、変更が完全に反映されず、エラーが解消されません。

**Before（エラーが起きるコード）：**

```bash
# Bedrockコントロールプレーンのみを更新した場合（不完全な修正）
curl -X PUT https://bedrock.us-east-1.amazonaws.com/data-retention \
  -H "Authorization: Bearer $AWS_BEARER_TOKEN_BEDROCK" \
  -H "Content-Type: application/json" \
  -d '{ "mode": "provider_data_share" }'

# この後、モデルステータスを確認しても "source": "model_default" のままになる可能性があります。
curl https://bedrock-mantle.us-east-1.api.aws/v1/models/anthropic.claude-fable-5 \
  -H "x-api-key: $BEDROCK_API_KEY"
```

**After（修正後）：**

```bash
# Bedrockコントロールプレーンのデータ保持モードを更新
curl -X PUT https://bedrock.us-east-1.amazonaws.com/data-retention \
  -H "Authorization: Bearer $AWS_BEARER_TOKEN_BEDROCK" \
  -H "Content-Type: application/json" \
  -d '{ "mode": "provider_data_share" }'

# Bedrockモデル推論プレーンのデータ保持モードを更新
curl -X PUT https://bedrock-mantle.us-east-1.api.aws/v1/data_retention \
  -H "x-api-key: $BEDROCK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "mode": "provider_data_share" }'

# 両方のエンドポイントを更新後、モデルステータスを確認すると "source": "account" になります。
curl https://bedrock-mantle.us-east-1.api.aws/v1/models/anthropic.claude-fable-5 \
  -H "x-api-key: $BEDROCK_API_KEY"
```
**解説:**
データ保持ポリシーの変更は、Bedrockのコントロールプレーン（`bedrock.us-east-1.amazonaws.com`）とモデル推論プレーン（`bedrock-mantle.us-east-1.api.aws`）の両方に対して実行する必要があります。これにより、アカウントレベルでの設定が完全に反映され、モデルが利用可能になります。

### 原因3：IAMユーザー/ロールに必要な権限が付与されていない

データ保持ポリシーを変更するには、`bedrock:PutAccountDataRetention`アクションを実行する権限が必要です。使用しているIAMユーザーまたはロールにこの権限が付与されていない場合、API呼び出しが認証エラーで失敗します。

**なぜ発生するか：**
Bedrock APIキーやAWS認証情報を使用している場合でも、その認証情報に関連付けられたIAMポリシーに`bedrock:PutAccountDataRetention`アクションが許可されていないと、データ保持モードの変更APIは実行できません。

**Before（エラーが起きるコード）：**

```bash
# IAMポリシーに適切な権限がない状態でPUTリクエストを実行すると、認証エラーが発生します。
curl -X PUT https://bedrock.us-east-1.amazonaws.com/data-retention \
  -H "Authorization: Bearer $AWS_BEARER_TOKEN_BEDROCK" \
  -H "Content-Type: application/json" \
  -d '{ "mode": "provider_data_share" }'
# エラー例: "User: arn:aws:iam::<your-account-id>:user/<your-user-name> is not authorized to perform: bedrock:PutAccountDataRetention on resource: arn:aws:bedrock:<your-region>:<your-account-id>:account"
```

**After（修正後）：**

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:PutAccountDataRetention",
                "bedrock:GetAccountDataRetention",
                "bedrock:GetFoundationModel"
            ],
            "Resource": "*"
        }
    ]
}
```
**解説:**
データ保持ポリシーを変更するIAMユーザーまたはロールに、`bedrock:PutAccountDataRetention`アクションを許可するポリシーをアタッチします。必要に応じて、現在のデータ保持設定を確認するための`bedrock:GetAccountDataRetention`や、モデル情報を取得するための`bedrock:GetFoundationModel`などの権限も追加すると良いでしょう。

## ツール固有の注意点

*   **プライバシーに関するトレードオフ:** `provider_data_share`モードを設定すると、プロンプトと応答がモデルプロバイダー（Anthropic）と共有され、最大30日間保持されます。組織のコンプライアンス要件でゼロデータ保持が必須の場合、この設定は避けるべきです。その場合は、AWSアカウントマネージャーに相談し、ゼロデータ保持アクセスが可能なモデルについて検討してください。
*   **コスト:** Claude Fable 5は、Claude Opus 4.8と比較してトークンあたりの料金が約2倍です。Fable 5は、長時間にわたる自律的な作業や、非常に複雑な問題解決など、その高度な機能が本当に必要な場合にのみ利用を検討してください。日常的な対話や一般的なエージェント作業には、Opus 4.8やSonnet 4.6などのより安価なモデルが適しています。
*   **コンソールUIの不在:** 現時点では、Amazon BedrockのコンソールUIからデータ保持ポリシーを変更する機能は提供されていません。APIまたはSDKを介してのみ設定変更が可能です。
*   **ロールバック:** `provider_data_share`モードを無効にするには、両方のエンドポイントに対して`mode`を`none`または`inherit`に設定し直します。`none`はゼロデータ保持を保証し、`inherit`はモデルのデフォルト設定に戻します。

## それでも解決しない場合

1.  **ログの確認:**
    *   AWS CloudTrail: Bedrock API呼び出しの履歴を確認し、`PutAccountDataRetention`アクションが成功しているか、または認証エラーが発生していないかを確認します。
    *   アプリケーションログ: Bedrockへのリクエストがどのように構築され、どのようなレスポンスを受け取っているかを詳細に確認します。

2.  **デバッグコマンド:**
    *   現在のデータ保持モードの確認:
        ```bash
        curl https://bedrock-mantle.us-east-1.api.aws/v1/models/anthropic.claude-fable-5 \
          -H "x-api-key: $BEDROCK_API_KEY"
        ```
        このコマンドの出力で`"data_retention.mode"`が`"provider_data_share"`、`"data_retention.source"`が`"account"`になっていれば、設定は正しく反映されています。
    *   アカウント全体のデータ保持設定の確認:
        ```bash
        curl https://bedrock.us-east-1.amazonaws.com/data-retention \
          -H "Authorization: Bearer $AWS_BEARER_TOKEN_BEDROCK"
        ```
        このコマンドでコントロールプレーンの設定を確認できます。

3.  **公式ドキュメントへの参照:**
    *   [Amazon Bedrock: データ保持](https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html)
    *   [Anthropic: APIとデータ保持](https://docs.anthropic.com/claude/docs/data-retention)
    *   [Amazon Bedrock: 料金](https://aws.amazon.com/bedrock/pricing/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*