---
title: "AWS ExpiredTokenの直し方"
date: 2026-09-25
draft: false
description: "AWSのExpiredTokenは、一時的な認証情報の有効期限が切れたときに発生します。認証情報の取得元を確認し、環境変数の削除、再取得、自動更新へ切り替える手順を解説します。"
tags: ["AWS"]
images: ["og/posts/aws_expiredtoken.png"]
errorCode: "ExpiredToken"
urgency: "high"
service: "AWS"
error_type: "ExpiredToken"
components: ["AWS STS", "AWS CLI", "IAM"]
related_services: ["Amazon EC2", "Amazon ECS"]
trend_incident: false
---

## 冒頭まとめ

AWS CLIやSDKの実行中に次のエラーが出た場合、使用中の一時的な認証情報が期限切れになっています。

```text
ExpiredToken: The security token included in the request is expired
```

最初に`aws configure list`と環境変数を確認し、AWS CLIやSDKがどこから認証情報を取得しているかを特定します。`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_SESSION_TOKEN`を手動で設定している場合は、3つをまとめて削除し、新しい認証情報を取得してください。

一時的な認証情報を毎回環境変数へコピーする運用では、期限切れが再発します。AWS CLIではロールを指定したプロファイル、EC2ではインスタンスプロファイル、ECSではタスクロールを使い、CLIやSDKに取得と更新を任せる方法へ変更します。

## ExpiredTokenの意味

一時的な認証情報は、アクセスキーID、シークレットアクセスキー、セッショントークンの3つで構成され、有効期限があります。[AWS IAMの公式文書](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html)によると、期限を過ぎた認証情報は再利用できません。

代表的な表示は次のとおりです。

```text
An error occurred (ExpiredToken) when calling the ListBuckets operation:
The provided token has expired.
```

```text
The security token included in the request is expired
```

エラー名やHTTP状態コードはサービスによって異なります。[STSの共通エラー文書](https://docs.aws.amazon.com/STS/latest/APIReference/CommonErrors.html)では`ExpiredTokenException`を403、[Amazon S3のエラー文書](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/ErrorResponses.html)では`ExpiredToken`を400としています。そのため、HTTP状態コードだけで判断せず、`ExpiredToken`、`ExpiredTokenException`、説明文を確認してください。

IAMユーザーの長期アクセスキーには、ロールセッションのような有効期限はありません。ただし、無効化や削除は可能です。`ExpiredToken`が出た場合は、セッショントークンを含む一時的な認証情報、または有効期限のあるIDプロバイダーのトークンを使っていないか確認します。

## 認証情報の取得元を確認する

まず、AWS CLIが現在どこからアクセスキーなどを取得しているかを確認します。

```bash
aws configure list
```

このコマンドは、プロファイル、アクセスキー、シークレットアクセスキー、リージョンの値と取得元を表示します。`Type`や`Location`が`env`や環境変数名になっていれば、環境変数が使われています。セッショントークン自体はこの一覧に通常表示されないため、別に確認します。

LinuxとmacOSでは次のコマンドを使います。

```bash
env | grep '^AWS_'
```

PowerShellでは次のコマンドで確認できます。

```powershell
Get-ChildItem Env:AWS_*
```

`AWS_SESSION_TOKEN`があれば、環境変数に一時的な認証情報が設定されています。ただし、表示されない場合でも、プロファイル、EC2のインスタンスプロファイル、ECSのタスクロールなどから一時的な認証情報を取得している可能性があります。

有効な認証情報へ更新した後は、呼び出し元も確認します。

```bash
aws sts get-caller-identity
```

このコマンドで返るアカウントとARNが想定どおりかを確認してください。期限切れの状態ではこのコマンド自体も失敗するため、更新後の確認に使います。

## 環境変数の期限切れを直す

`aws sts assume-role`の結果を環境変数へ手動設定した場合、その値は期限が来ても自動更新されません。古い3要素をすべて削除してから、新しい認証情報を取得します。

LinuxとmacOSでは次のように削除します。

```bash
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN
```

PowerShellでは次のように削除します。

```powershell
Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
```

削除後に、利用している認証方法に従ってサインインまたは`AssumeRole`をやり直します。アクセスキーだけ、またはセッショントークンだけを更新すると、異なるセッションの値が混在するため、必ず同時に発行された3つを1組として扱ってください。

環境変数は共有プロファイルより優先されます。[AWS CLIの設定優先順位](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)でも、環境変数がプロファイルより先に評価されることが示されています。新しいプロファイルを設定しても直らない場合は、古い環境変数が残っていないか確認します。

## プロファイルで自動更新する

AWS CLIでIAMロールを使う場合は、`AssumeRole`の出力を手動で環境変数へコピーせず、`~/.aws/config`にロール用プロファイルを設定します。

```ini
[profile project1]
role_arn = arn:aws:iam::123456789012:role/Prod-Role
source_profile = user1
region = ap-northeast-1
```

次のようにプロファイルを指定して実行します。

```bash
aws sts get-caller-identity --profile project1
```

[AWS CLIの公式文書](https://docs.aws.amazon.com/cli/latest/topic/config-vars.html)によると、ロール用プロファイルを使うと、CLIが`AssumeRole`を実行して一時的な認証情報をキャッシュし、期限切れ時に更新します。`source_profile`に指定した元の認証情報が有効であることは必要です。

IAM Identity Centerを利用している場合は、その設定に従って`aws sso login --profile <プロファイル名>`を再実行します。組織が指定する認証方法を優先し、長期アクセスキーを新しく作ることを期限切れ対策にしないでください。

## EC2・ECSではロールを使う

EC2上のアプリケーションでは、IAMロールを含むインスタンスプロファイルをEC2へ関連付け、AWS CLIやSDKに認証情報の取得を任せます。[EC2の公式文書](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-metadata-security-credentials.html)では、CLIとSDKがインスタンスメタデータから認証情報を自動取得すると説明されています。

ECSでは、コンテナへアクセスキーを埋め込まず、タスク定義にIAMタスクロールを設定します。対応するSDKはコンテナ用の認証情報取得元から一時的な認証情報を読み込みます。

ただし、環境変数に古い認証情報が残っていると、インスタンスプロファイルやタスクロールより先に使われる場合があります。EC2やECSへロールを設定した後も`ExpiredToken`が続く場合は、コンテナ定義、起動スクリプト、CIのシークレットに`AWS_ACCESS_KEY_ID`などが残っていないか確認してください。

メタデータの値を`curl`で取得して環境変数へ固定する方法は避けます。取得時点では有効でも、その値を使い続ければ期限切れになります。SDKが対応している認証情報の取得経路を使うことで、更新後の値を再取得できます。

## セッション時間と時計を確認する

`AssumeRole`の`DurationSeconds`は、ロールに設定された最大セッション時間の範囲で指定します。[AssumeRole APIの公式文書](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)では、最大43200秒、つまり12時間まで設定できます。ただし、許可される上限は対象ロールの設定によって変わります。

一時的な認証情報で別のロールを引き受けるロール連鎖では、セッションは最大1時間です。1時間を超える`DurationSeconds`を指定すると、期限が延びるのではなく`AssumeRole`自体が失敗します。長時間動く処理では、期限を長くするだけでなく、CLIやSDKが再取得できる構成にしてください。

認証情報を更新してもすぐ期限切れと判定される場合は、実行環境の日時とタイムゾーンも確認します。AWSの要求には署名時刻が含まれるため、大きな時刻ずれは認証エラーの原因になります。ただし、時刻ずれでは`RequestExpired`や署名関連の別エラーになる場合もあります。先に認証情報の実際の有効期限と取得元を確認してください。

### 近い認証エラーとの違い

`ExpiredToken`は、認証情報の組み合わせが正しくても、セッションの有効期限を過ぎた場合に発生します。

`InvalidClientTokenId`や`UnrecognizedClientException`は、アクセスキーやトークンが無効、認識できない、または組み合わせが一致しない場合に出ます。値の入力ミス、削除済みのアクセスキー、異なるセッションの値を混ぜた可能性を確認してください。

`SignatureDoesNotMatch`は、AWS側で計算した署名と要求に含まれる署名が一致しないエラーです。シークレットアクセスキー、署名対象、リージョン、サービス名などを調べます。

`AccessDenied`は、認証後の権限判定で拒否された状態です。認証情報を再取得するだけでは直らず、IAMポリシー、リソースポリシー、Organizationsの制御などを確認する必要があります。

## 解決手順のまとめ

最初に`aws configure list`を実行し、アクセスキーの取得元を確認します。続いて環境変数を調べ、期限切れの`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_SESSION_TOKEN`が残っていれば3つとも削除します。

新しい一時的な認証情報を取得したら、`aws sts get-caller-identity`でアカウントとARNを確認します。直った後は、手動コピーを続けず、ロール用プロファイル、IAM Identity Center、EC2のインスタンスプロファイル、ECSのタスクロールなど、自動で再取得できる方法へ変更してください。

ロール連鎖は最大1時間です。処理時間が長い場合は、`DurationSeconds`だけで解決しようとせず、処理中に認証情報を更新できる構成かを確認します。認証情報が有効なのに失敗する場合は、最後に実行環境の時計を確認してください。

免責事項：本記事の内容は一般的なAWS CLIおよびAWS SDKの構成を前提としています。認証情報を削除または変更する前に、実行中の処理と使用中のプロファイルを確認してください。アクセスキー、シークレットアクセスキー、セッショントークンをログや画面共有へ表示しないでください。本番環境では、組織の認証方針とIAM管理者の手順を優先してください。
