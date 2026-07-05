---
title: "AWS S3 の AccessDenied エラー：原因と解決策"
date: 2026-06-26
description: "AWS S3 の AccessDenied は、権限不足や拒否設定でアクセスが拒否されるエラーです。"
tags: ["AWS S3"]
errorCode: "AccessDenied"
urgency: "medium"
service: "AWS S3"
error_type: "AccessDenied"
components: ["IAM", "S3"]
related_services: []
---

## エラーの概要

AWS S3 の AccessDenied [エラー](/glossary/エラー/)は、[IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)の不足、バケットポリシーの明示的な拒否設定、または[オブジェクト](/glossary/オブジェクト/)の ACL 設定によって、リソースへのアクセスが拒否されたときに発生します。認証情報は正常に認識されているものの、[権限](/glossary/権限/)がない状態です。

## 実際のエラーメッセージ例

```json
{
  "Error": {
    "Code": "AccessDenied",
    "Message": "Access Denied"
  }
}
```

```
An error occurred (AccessDenied) when calling the GetObject operation: Access Denied
```

**[エラーメッセージ](/glossary/エラーメッセージ/)の読み方：**

- `AccessDenied` → [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/) 403 に相当。[認証](/glossary/認証/)は成功したが[権限](/glossary/権限/)がない
- `Access Denied` → リソースへのアクセスが拒否されていることを示すメッセージ
- [リクエスト](/glossary/リクエスト/)元の AWS [アカウント](/glossary/アカウント/)・[IAM](/glossary/iam/) ユーザー・[ロール](/glossary/ロール/)が、実行しようとしたアクション（s3:GetObject など）を許可されていない

## よくある原因と解決手順

### 原因1：IAM ポリシーで必要なアクションが許可されていない

S3 [バケット](/glossary/バケット/)にアクセスするユーザー・[ロール](/glossary/ロール/)・サービスに対して、`s3:GetObject`、`s3:PutObject` などの必要な[権限](/glossary/権限/)が付与されていない場合に発生します。特に新規に作成した [IAM](/glossary/iam/) ユーザーや、特定の[バケット](/glossary/バケット/)に限定したアクセスに構成した際に起きやすいです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::my-bucket"
    }
  ]
}
```

**After（修正後）：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::my-bucket"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::my-bucket/*"
    }
  ]
}
```

✅ 修正後の確認：

```bash
aws s3 cp s3://my-bucket/test.txt . --profile <your-profile>
```

修正が反映されると、指定したファイルが[ダウンロード](/glossary/ダウンロード/)され、[エラー](/glossary/エラー/)が出なくなります。

### 原因2：バケットポリシーで Deny が明示的に設定されている

バケットポリシーで `"Effect": "Deny"` が設定されている場合、[IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)で Allow されていても、より制限的な[ポリシー](/glossary/ポリシー/)が優先されて AccessDenied が発生します。IP アドレス制限やプリンシパル制限などの条件で無意識に Deny が適用されていることもあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::my-bucket",
        "arn:aws:s3:::my-bucket/*"
      ]
    }
  ]
}
```

**After（修正後）：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<your-account-id>:root"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-bucket/*"
    }
  ]
}
```

✅ 修正後の確認：

```bash
aws s3api get-bucket-policy --bucket my-bucket --profile <your-profile>
```

バケットポリシーが新しい設定に更新されていれば、制限が解除されます。

### 原因3：Block Public Access 設定が有効で、公開アクセスがブロックされている

[オブジェクト](/glossary/オブジェクト/)の ACL を Public に設定しても、S3 の Block Public Access 機能が有効な場合は公開アクセスが拒否されます。特に外部ユーザーや別[アカウント](/glossary/アカウント/)からのアクセスを想定している場合に発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Block Public Access が全て有効な状態
aws s3api get-public-access-block --bucket my-bucket --profile <your-profile>
# Output: {
#   "PublicAccessBlockConfiguration": {
#     "BlockPublicAcls": true,
#     "IgnorePublicAcls": true,
#     "BlockPublicPolicy": true,
#     "RestrictPublicBuckets": true
#   }
# }
```

**After（修正後）：**

```bash
aws s3api put-public-access-block \
  --bucket my-bucket \
  --public-access-block-configuration \
  "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false" \
  --profile <your-profile>
```

✅ 修正後の確認：

```bash
aws s3api get-public-access-block --bucket my-bucket --profile <your-profile>
```

`BlockPublicAcls`、`BlockPublicPolicy` などの値が `false` に変更されていれば、Block Public Access 設定が解除されています。

### 原因4：別のAWSアカウント・クロスアカウントアクセスが正しく設定されていない

別の AWS [アカウント](/glossary/アカウント/)のユーザーまたは[ロール](/glossary/ロール/)が[バケット](/glossary/バケット/)にアクセスする場合、バケットポリシーでそのプリンシパル（外部[アカウント](/glossary/アカウント/)の ARN）を明示的に許可し、同時に外部[アカウント](/glossary/アカウント/)側の [IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)も s3 アクションを許可する必要があります。どちらか一方が不足すると AccessDenied が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:root"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-bucket/*"
    }
  ]
}
```

外部[アカウント](/glossary/アカウント/)（123456789012）の [IAM](/glossary/iam/) ユーザーの[権限](/glossary/権限/)が不足している状態。

**After（修正後）：**

[バケット](/glossary/バケット/)側の[ポリシー](/glossary/ポリシー/)はそのままにして、外部[アカウント](/glossary/アカウント/)側で以下の [IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)を適用：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-bucket",
        "arn:aws:s3:::my-bucket/*"
      ]
    }
  ]
}
```

✅ 修正後の確認：

```bash
aws s3 ls s3://my-bucket --profile <cross-account-profile>
```

外部[アカウント](/glossary/アカウント/)のプロファイルから[バケット](/glossary/バケット/)内の[オブジェクト](/glossary/オブジェクト/)が一覧表示されれば、クロスアカウントアクセスが正常です。

## 解決策の早見表

| 解決策 | 実装難易度 | 再起動要否 | 対応[OS](/glossary/os/) |
|--------|-----------|-----------|-------|
| [IAM](/glossary/iam/)[ポリシー](/glossary/ポリシー/)に[権限](/glossary/権限/)を追加 | 低 | 不要 | 全[OS](/glossary/os/) |
| バケットポリシーの Deny 条件を修正 | 中 | 不要 | 全[OS](/glossary/os/) |
| Block Public Access を無効化 | 低 | 不要 | 全[OS](/glossary/os/) |
| クロスアカウント[権限](/glossary/権限/)を設定 | 中 | 不要 | 全[OS](/glossary/os/) |

## ツール固有の注意点

**AWS マネジメントコンソールでの確認方法：**

S3 [コンソール](/glossary/コンソール/) → [バケット](/glossary/バケット/)名をクリック → 「[権限](/glossary/権限/)」タブで「バケットポリシー」「ACL」「Block Public Access」を確認します。[ポリシー](/glossary/ポリシー/)の [JSON](/glossary/json/) は視覚的には わかりにくいため、AWS [IAM](/glossary/iam/) Policy Simulator（`https://policysim.aws.amazon.com/`）を使用してアクション実行をシミュレーションすることで、どの[ポリシー](/glossary/ポリシー/)が拒否しているか特定できます。

**[IAM](/glossary/iam/) [ロール](/glossary/ロール/)経由でのアクセス：**

EC2 [インスタンス](/glossary/インスタンス/)や Lambda 関数から S3 にアクセスする場合、インスタンスプロファイルまたは実行[ロール](/glossary/ロール/)に s3 [権限](/glossary/権限/)が付与されていることを確認してください。`aws sts get-caller-identity` を実行し、実際に使用されている[ロール](/glossary/ロール/) ARN を確認したうえで、その[ロール](/glossary/ロール/)の[ポリシー](/glossary/ポリシー/)を検証します。

**[バージョン管理](/glossary/バージョン管理/)が有効な場合：**

[バージョン管理](/glossary/バージョン管理/)が有効な[バケット](/glossary/バケット/)では、`s3:GetObjectVersion` という追加アクションが必要になる場合があります。[オブジェクト](/glossary/オブジェクト/)の過去[バージョン](/glossary/バージョン/)にアクセスする際は、[IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)に明示的に含めてください。

## それでも解決しない場合

**AWS CloudTrail で[リクエスト](/glossary/リクエスト/)を確認：**

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceType,AttributeValue=AWS::S3::Object \
  --max-results 10 \
  --profile <your-profile>
```

CloudTrail [ログ](/glossary/ログ/)から失敗した[リクエスト](/glossary/リクエスト/)の詳細（どの [IAM](/glossary/iam/) ユーザー、どのプリンシパルが拒否されたか）が確認できます。拒否の理由が「implicitDeny」（明示的な Allow がない）なのか「explicitDeny」（Deny [ポリシー](/glossary/ポリシー/)が存在）なのか判定できます。

**AWS Access Analyzer の活用：**

AWS [IAM](/glossary/iam/) Access Analyzer を使用すると、バケットポリシーやロールポリシーの問題を自動検出できます。AWS [コンソール](/glossary/コンソール/) → [IAM](/glossary/iam/) → Access Analyzer → リソースの外部アクセス可否を調査 で、アクセス拒否の原因を指摘してもらえます。

**公式ドキュメント：**

[AWS S3 での AccessDenied トラブルシューティング](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-overview.html)

## 代替ツールの検討

AWS S3 の [IAM](/glossary/iam/)・[ポリシー](/glossary/ポリシー/)管理が複雑で、AccessDenied [エラー](/glossary/エラー/)の原因特定に時間がかかる場合は、以下のツールへの移行を検討できます。

- **Google Cloud Storage（GCS）**：[IAM](/glossary/iam/) [ロール](/glossary/ロール/)管理がシンプルで、事前定義[ロール](/glossary/ロール/)（Storage Object Admin など）を割り当てるだけで権限制御が可能です。[ポリシー](/glossary/ポリシー/)言語が単純化されているため、AccessDenied の原因特定も素早くできます。

- **Azure Blob Storage**：ロールベースアクセス制御（[RBAC](/glossary/rbac/)）が統一されており、Azure AD との連携も強固です。きめ細かいアクセス制御が必要な企業環境に適しています。

- **Cloudflare R2**：S3 互換 [API](/glossary/api/) を提供しながら、シンプルなアクセストークンベースの[認証](/glossary/認証/)を採用しており、複雑な[ポリシー](/glossary/ポリシー/)管理が不要です。軽量な運用を重視する場合に有効です。

## Editor's Note

AWS 公式ドキュメントでは [IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)と バケットポリシーの関係を別々に説明していることが多いため、新規ユーザーは「[IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)で Allow しているのに拒否される」という混乱に陥りやすいです。実際のサポートフォーラムでは、[AWS re:Post での AccessDenied 事例](https://repost.aws/)でもこの原因が頻出しており、バケットポリシーの Deny 条件や Block Public Access が見落とされるケースが圧倒的です。現場では、まず AWS [IAM](/glossary/iam/) Policy Simulator で[ポリシー](/glossary/ポリシー/)評価を実行し、複数の[ポリシー](/glossary/ポリシー/)がどの順序で評価されているか可視化してから、個別の[ポリシー](/glossary/ポリシー/)を修正するのが有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
