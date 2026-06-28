---
title: "AWS S3 の NoSuchKey エラー：原因と解決策"
date: 2026-06-26
description: "AWS S3 の NoSuchKey は、指定したキーが存在しないことを示す 404 エラーです。"
tags: ["AWS S3"]
errorCode: "NoSuchKey"
urgency: "medium"
service: "AWS S3"
error_type: "NoSuchKey"
components: ["S3"]
related_services: ["boto3"]
---

## エラーの概要

AWS S3の **NoSuchKey** [エラー](/glossary/エラー/)は、指定したキー（オブジェクトパス）が[バケット](/glossary/バケット/)内に存在しないことを示す[HTTP](/glossary/http/) 404[エラー](/glossary/エラー/)です。この[エラー](/glossary/エラー/)が発生すると、GetObject、HeadObject、DeleteObject などの[オブジェクト](/glossary/オブジェクト/)操作は失敗し、「The specified key does not exist.」というメッセージが返されます。一見すると「[オブジェクト](/glossary/オブジェクト/)がないこと」を示していますが、実際には**キーの指定ミスやプレフィックスの誤り、大文字小文字の区別、削除済み[オブジェクト](/glossary/オブジェクト/)の参照**など、複数の原因が絡むことが多いため、正確な診断が重要です。

## 実際のエラーメッセージ例

```json
{
  "Error": {
    "Code": "NoSuchKey",
    "Message": "The specified key does not exist."
  },
  "ResponseMetadata": {
    "HTTPStatusCode": 404,
    "HTTPHeaders": {
      "content-type": "application/xml"
    }
  }
}
```

**[エラーメッセージ](/glossary/エラーメッセージ/)の読み方：**

- `"Code": "NoSuchKey"` → S3が返すエラーコード。指定したキーが[バケット](/glossary/バケット/)内に存在しないことを示す
- `"Message": "The specified key does not exist."` → 詳細な説明。[リクエスト](/glossary/リクエスト/)で指定された[オブジェクト](/glossary/オブジェクト/)が[バケット](/glossary/バケット/)に見つからなかったことを意味する
- `"HTTPStatusCode": 404` → [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)。リソースが見つからないことを示す標準的な応答
- `content-type: application/xml` → S3が[XML](/glossary/xml/)形式で[エラーレスポンス](/glossary/エラーレスポンス/)を返していることを示す

## よくある原因と解決手順

### 原因1：キー名のスペルミス、パス区切りの誤り

S3のキーは大文字小文字を区別し、ファイルパスの階層は **スラッシュ（`/`）** で区切られます。`my-file.txt` と `my_file.txt` は異なるキーであり、`folder/file.txt` と `folder\file.txt` も区別されます。これらのわずかなスペルミスや区切り文字の誤りが NoSuchKey [エラー](/glossary/エラー/)の最も一般的な原因です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import boto3

s3 = boto3.client('s3')
bucket_name = 'my-bucket'
key = 'documents/my-file.txt'  # キーが実際には 'documents/my_file.txt' で存在する

response = s3.get_object(Bucket=bucket_name, Key=key)
# NoSuchKey エラーが発生
```

**After（修正後）：**

```python
import boto3

s3 = boto3.client('s3')
bucket_name = 'my-bucket'
key = 'documents/my_file.txt'  # 正しいキー名に修正

response = s3.get_object(Bucket=bucket_name, Key=key)
data = response['Body'].read()
print(f"Successfully retrieved: {key}")
```

✅ 修正後の確認：

```bash
aws s3 ls s3://my-bucket/documents/
```

`my_file.txt` が一覧に表示されればキー名が正しいことが確認できます。

### 原因2：バケット内のオブジェクトの存在確認なしにアクセス

GetObject の前に HeadObject を使って、[オブジェクト](/glossary/オブジェクト/)が実際に存在するか確認していない場合、存在しないキーへのアクセスが直ちに NoSuchKey [エラー](/glossary/エラー/)を引き起こします。特に、ユーザー入力やダイナミックに構築されたキーを使う場合は、事前の存在確認が不可欠です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import boto3

s3 = boto3.client('s3')
bucket_name = 'my-bucket'
user_input_key = 'uploads/user123/profile.jpg'

# オブジェクトの存在を確認せずに直接 GetObject を実行
try:
    response = s3.get_object(Bucket=bucket_name, Key=user_input_key)
except Exception as e:
    print(f"Error: {e}")
    # NoSuchKey エラーが発生する可能性がある
```

**After（修正後）：**

```python
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
bucket_name = 'my-bucket'
user_input_key = 'uploads/user123/profile.jpg'

# HeadObject で存在確認
try:
    s3.head_object(Bucket=bucket_name, Key=user_input_key)
    # オブジェクトが存在する場合のみ GetObject を実行
    response = s3.get_object(Bucket=bucket_name, Key=user_input_key)
    data = response['Body'].read()
    print(f"Successfully retrieved: {user_input_key}")
except ClientError as e:
    if e.response['Error']['Code'] == '404':
        print(f"Object does not exist: {user_input_key}")
    else:
        print(f"Error: {e}")
```

✅ 修正後の確認：

```bash
aws s3api head-object --bucket my-bucket --key "uploads/user123/profile.jpg"
```

[メタデータ](/glossary/メタデータ/)が表示されれば、[オブジェクト](/glossary/オブジェクト/)が存在することが確認できます。[エラー](/glossary/エラー/)が出た場合は、キー名を見直してください。

### 原因3：バージョニング有効なバケットで旧バージョンのオブジェクトにアクセス

S3の **[バージョニング](/glossary/バージョニング/)** を有効化した[バケット](/glossary/バケット/)では、[オブジェクト](/glossary/オブジェクト/)が複数の[バージョン](/glossary/バージョン/)（VersionId）を持つことがあります。最新[バージョン](/glossary/バージョン/)が削除マーカーで標記されている場合、`VersionId` を明示せずにアクセスすると NoSuchKey [エラー](/glossary/エラー/)が発生します。また、古い[バージョン](/glossary/バージョン/)の VersionId を指定しているが、削除されている場合も同じ[エラー](/glossary/エラー/)が出ます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import boto3

s3 = boto3.client('s3')
bucket_name = 'versioned-bucket'
key = 'important-file.txt'
old_version_id = '<your-old-version-id>'

# 削除済みまたは無効な VersionId でアクセス
response = s3.get_object(Bucket=bucket_name, Key=key, VersionId=old_version_id)
# NoSuchKey エラーが発生する可能性がある
```

**After（修正後）：**

```python
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
bucket_name = 'versioned-bucket'
key = 'important-file.txt'

# 利用可能なバージョン一覧を取得
versions = s3.list_object_versions(Bucket=bucket_name, Prefix=key)

if 'Versions' in versions:
    # 最新かつ削除されていないバージョンを取得
    for version in versions['Versions']:
        if version['Key'] == key:
            valid_version_id = version['VersionId']
            response = s3.get_object(Bucket=bucket_name, Key=key, VersionId=valid_version_id)
            data = response['Body'].read()
            print(f"Successfully retrieved version: {valid_version_id}")
            break
```

✅ 修正後の確認：

```bash
aws s3api list-object-versions --bucket versioned-bucket --prefix "important-file.txt"
```

出力された `VersionId` が有効であることが確認でき、`IsLatest: true` で最新[バージョン](/glossary/バージョン/)を識別できます。

## 解決策の早見表

| 解決策 | 実装難易度 | 再起動要否 | 対応[OS](/glossary/os/) |
|--------|-----------|-----------|-------|
| キー名のスペルミス・パス区切りを修正 | 低 | 不要 | 全[OS](/glossary/os/) |
| HeadObject で事前存在確認を追加 | 低 | 不要 | 全[OS](/glossary/os/) |
| [バージョニング](/glossary/バージョニング/)有効時に VersionId を指定 | 中 | 不要 | 全[OS](/glossary/os/) |

## ツール固有の注意点

### AWS CLIコマンドラインでの確認方法

S3の操作を AWS [CLI](/glossary/cli/) で行う場合、`aws s3 ls` でプレフィックスを指定して存在する[オブジェクト](/glossary/オブジェクト/)一覧を確認することが最初のトラブルシューティングステップになります。

```bash
aws s3 ls s3://my-bucket/documents/
```

この[コマンド](/glossary/コマンド/)で期待するキーが表示されない場合、キー名の指定が誤っている、または[オブジェクト](/glossary/オブジェクト/)が実際に削除済みである可能性が高いです。特に **大文字小文字の区別** は[コマンドライン](/glossary/コマンドライン/)では顕著に影響するため、出力結果と照合する際は詳細に比較してください。

### IAMアクセス権限による隠蔽

[IAM](/glossary/iam/)[権限](/glossary/権限/)が不足している場合、通常は 403 Forbidden が返ります。ただし、[オブジェクト](/glossary/オブジェクト/)が存在せず、かつ s3:ListBucket [権限](/glossary/権限/)もない場合は NoSuchKey ではなく 403 が返るため、「存在しないはずのキーで 403 が出る」という逆の混同が生じることがあります。権限関連が疑われる場合は、[IAM](/glossary/iam/) [ポリシー](/glossary/ポリシー/)のレビューを並行して行ってください。

### CloudFormation・IaC環境での再デプロイ

Infrastructure as Code（CloudFormation、Terraform等）でS3リソースを管理している場合、[デプロイ](/glossary/デプロイ/)時にキー名の指定が[環境変数](/glossary/環境変数/)や出力値と不一致になることがあります。テンプレート内のキー参照がハードコードされていないか、変数展開が正しく実行されているか確認してください。

## それでも解決しない場合

### ログ確認とデバッグ

AWS CloudTrail で S3 [API](/glossary/api/) 呼び出しの詳細[ログ](/glossary/ログ/)を確認できます。CloudTrail [コンソール](/glossary/コンソール/)から **Data events** を有効化し、GetObject、HeadObject の呼び出し履歴を確認することで、実際に送信されたキーと受信した[レスポンス](/glossary/レスポンス/)を追跡できます。

```bash
aws cloudtrail lookup-events --lookup-attributes AttributeKey=ResourceName,AttributeValue=my-bucket
```

### バケットポリシー・ACLの確認

```bash
aws s3api get-bucket-policy --bucket my-bucket
aws s3api get-object-acl --bucket my-bucket --key "path/to/object"
```

バケットポリシーによって特定のプリンシパルに GetObject が明示的に拒否されていないか確認してください。

### S3 リージョンの確認

```bash
aws s3api get-bucket-location --bucket my-bucket
```

[リクエスト](/glossary/リクエスト/)を送信しているリージョンと[バケット](/glossary/バケット/)の実際のリージョンが異なっていないか確認します。

## 代替ツールの検討

NoSuchKey [エラー](/glossary/エラー/)が頻発して運用に支障が出る場合は、以下のツールへの移行を検討できます。

- **Google Cloud Storage（GCS）** ：S3と互換性が高く、[オブジェクト](/glossary/オブジェクト/)存在確認の[API](/glossary/api/)仕様もシンプルです。特にマルチクラウド戦略がある場合、統一的な[SDK](/glossary/sdk/)で複数[クラウド](/glossary/クラウド/)を管理できます。

- **Azure Blob Storage** ：マイクロソフトエコシステムとの連携が必要な場合に有効です。[エラーハンドリング](/glossary/エラーハンドリング/)が詳細で、ブロブの存在確認と取得を単一の[API](/glossary/api/)呼び出しで実行できます。

- **Cloudflare R2** ：S3互換の[API](/glossary/api/)を提供しながら、デフォルトで出力（egress）料金が無料という特性があり、小〜中規模の[アプリケーション](/glossary/アプリケーション/)で NoSuchKey による頻繁な再試行を許容しやすい運用環境を構築できます。

## Editor's Note

[Stack Overflow での報告](https://stackoverflow.com/questions/44778448/s3-giving-me-nosuchkey-error-even-when-the-key-exists)では、「キーは確実に存在しているのに NoSuchKey が出る」というケースが頻繁に報告されており、その多くはキー末尾の改行文字（%0A）や先頭スラッシュなどの特殊文字の混入が原因でした。LocalStack の [GitHub Issue #8174](https://github.com/localstack/localstack/issues/8174) でも、特殊文字（a@a など）を含むフォルダ名で PutObject が NoSuchKey を返す問題が確認されており、特殊文字のエスケープ漏れは見落としやすい点として注意が必要です。現場では、HeadObject での事前確認と S3 サーバーアクセスログ（AWS 公式が直接推奨）の確認から着手するのが有効です。CloudTrail も参照可能ですが、S3 アクセスの直接的な調査には S3 サーバーアクセスログが適しています。

> **調査について**　この記事の解決策は、Stack Overflow・GitHub Issues への公開報告を Gemini + Google Search で検索・精査し、実効性の高いものを整理したものです。参照元の URL は Editor's Note に記載しています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
