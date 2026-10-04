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

[AWS](/glossary/aws/) [CLI](/glossary/cli/)や[SDK](/glossary/sdk/)の実行中に次の[エラー](/glossary/エラー/)が出た場合、使用中の一時的な認証情報が期限切れになっています。

```text
ExpiredToken: The security token included in the request is expired
```

最初に`aws configure list`と[環境変数](/glossary/環境変数/)を確認し、[AWS](/glossary/aws/) [CLI](/glossary/cli/)や[SDK](/glossary/sdk/)がどこから認証情報を取得しているかを特定します。`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_SESSION_TOKEN`を手動で[設定](/glossary/設定/)している場合は、3つをまとめて[削除](/glossary/削除/)し、新しい認証情報を取得してください。

一時的な認証情報を毎回環境変数へコピーする運用では、期限切れが再発します。[AWS](/glossary/aws/) [CLI](/glossary/cli/)では[ロール](/glossary/ロール/)を指定したプロファイル、EC2ではインスタンスプロファイル、ECSではタスクロールを使い、[CLI](/glossary/cli/)や[SDK](/glossary/sdk/)に取得と更新を任せる方法へ変更します。

## ExpiredTokenの意味

一時的な認証情報は、アクセスキー[ID](/glossary/id/)、シークレットアクセスキー、セッショントークンの3つで構成され、有効期限があります。[AWS IAMの公式文書](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html)によると、期限を過ぎた認証情報は再利用できません。

代表的な表示は次のとおりです。

```text
An error occurred (ExpiredToken) when calling the ListBuckets operation:
The provided token has expired.
```

```text
The security token included in the request is expired
```

[エラー](/glossary/エラー/)名や[HTTP](/glossary/http/)状態[コード](/glossary/コード/)はサービスによって異なります。[STSの共通エラー文書](https://docs.aws.amazon.com/STS/latest/APIReference/CommonErrors.html)では`ExpiredTokenException`を403、[Amazon S3のエラー文書](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/ErrorResponses.html)では`ExpiredToken`を400としています。そのため、[HTTP](/glossary/http/)状態[コード](/glossary/コード/)だけで判断せず、`ExpiredToken`、`ExpiredTokenException`、説明文を確認してください。

[IAM](/glossary/iam/)ユーザーの長期アクセスキーには、ロールセッションのような有効期限はありません。ただし、無効化や[削除](/glossary/削除/)は可能です。`ExpiredToken`が出た場合は、セッショントークンを含む一時的な認証情報、または有効期限のある[ID](/glossary/id/)プロバイダーの[トークン](/glossary/トークン/)を使っていないか確認します。

## 認証情報の取得元を確認する

まず、[AWS](/glossary/aws/) [CLI](/glossary/cli/)が現在どこからアクセスキーなどを取得しているかを確認します。

```bash
aws configure list
```

この[コマンド](/glossary/コマンド/)は、プロファイル、アクセスキー、シークレットアクセスキー、リージョンの値と取得元を表示します。`Type`や`Location`が`env`や環境変数名になっていれば、[環境変数](/glossary/環境変数/)が使われています。セッショントークン自体はこの一覧に通常表示されないため、別に確認します。

[Linux](/glossary/linux/)とmacOSでは次の[コマンド](/glossary/コマンド/)を使います。

```bash
env | grep '^AWS_'
```

PowerShellでは次の[コマンド](/glossary/コマンド/)で確認できます。

```powershell
Get-ChildItem Env:AWS_*
```

`AWS_SESSION_TOKEN`があれば、[環境変数](/glossary/環境変数/)に一時的な認証情報が[設定](/glossary/設定/)されています。ただし、表示されない場合でも、プロファイル、EC2のインスタンスプロファイル、ECSのタスクロールなどから一時的な認証情報を取得している可能性があります。

有効な認証情報へ更新した後は、呼び出し元も確認します。

```bash
aws sts get-caller-identity
```

この[コマンド](/glossary/コマンド/)で返る[アカウント](/glossary/アカウント/)とARNが想定どおりかを確認してください。期限切れの状態ではこの[コマンド](/glossary/コマンド/)自体も失敗するため、更新後の確認に使います。

## 環境変数の期限切れを直す

`aws sts assume-role`の結果を[環境変数](/glossary/環境変数/)へ手動設定した場合、その値は期限が来ても自動更新されません。古い3要素をすべて[削除](/glossary/削除/)してから、新しい認証情報を取得します。

[Linux](/glossary/linux/)とmacOSでは次のように[削除](/glossary/削除/)します。

```bash
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN
```

PowerShellでは次のように[削除](/glossary/削除/)します。

```powershell
Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
```

削除後に、利用している認証方法に従ってサインインまたは`AssumeRole`をやり直します。アクセスキーだけ、またはセッショントークンだけを更新すると、異なる[セッション](/glossary/セッション/)の値が混在するため、必ず同時に発行された3つを1組として扱ってください。

[環境変数](/glossary/環境変数/)は共有プロファイルより優先されます。[AWS CLIの設定優先順位](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)でも、[環境変数](/glossary/環境変数/)がプロファイルより先に評価されることが示されています。新しいプロファイルを[設定](/glossary/設定/)しても直らない場合は、古い[環境変数](/glossary/環境変数/)が残っていないか確認します。

## プロファイルで自動更新する

[AWS](/glossary/aws/) [CLI](/glossary/cli/)で[IAM](/glossary/iam/)[ロール](/glossary/ロール/)を使う場合は、`AssumeRole`の出力を手動で[環境変数](/glossary/環境変数/)へコピーせず、`~/.aws/config`に[ロール](/glossary/ロール/)用プロファイルを[設定](/glossary/設定/)します。

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

[AWS CLIの公式文書](https://docs.aws.amazon.com/cli/latest/topic/config-vars.html)によると、[ロール](/glossary/ロール/)用プロファイルを使うと、[CLI](/glossary/cli/)が`AssumeRole`を実行して一時的な認証情報を[キャッシュ](/glossary/キャッシュ/)し、期限切れ時に更新します。`source_profile`に指定した元の認証情報が有効であることは必要です。

[IAM](/glossary/iam/) Identity Centerを利用している場合は、その[設定](/glossary/設定/)に従って`aws sso login --profile <プロファイル名>`を再実行します。組織が指定する認証方法を優先し、長期アクセスキーを新しく作ることを期限切れ対策にしないでください。

## EC2・ECSではロールを使う

EC2上の[アプリケーション](/glossary/アプリケーション/)では、[IAM](/glossary/iam/)[ロール](/glossary/ロール/)を含むインスタンスプロファイルをEC2へ関連付け、[AWS](/glossary/aws/) [CLI](/glossary/cli/)や[SDK](/glossary/sdk/)に認証情報の取得を任せます。[EC2の公式文書](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-metadata-security-credentials.html)では、[CLI](/glossary/cli/)と[SDK](/glossary/sdk/)がインスタンスメタデータから認証情報を自動取得すると説明されています。

ECSでは、[コンテナ](/glossary/コンテナ/)へアクセスキーを埋め込まず、[タスク](/glossary/タスク/)定義に[IAM](/glossary/iam/)タスクロールを[設定](/glossary/設定/)します。[対応](/glossary/対応/)する[SDK](/glossary/sdk/)は[コンテナ](/glossary/コンテナ/)用の認証情報取得元から一時的な認証情報を読み込みます。

ただし、[環境変数](/glossary/環境変数/)に古い認証情報が残っていると、インスタンスプロファイルやタスクロールより先に使われる場合があります。EC2やECSへ[ロール](/glossary/ロール/)を[設定](/glossary/設定/)した後も`ExpiredToken`が続く場合は、[コンテナ](/glossary/コンテナ/)定義、起動[スクリプト](/glossary/スクリプト/)、CIのシークレットに`AWS_ACCESS_KEY_ID`などが残っていないか確認してください。

[メタデータ](/glossary/メタデータ/)の値を`curl`で取得して[環境変数](/glossary/環境変数/)へ固定する方法は避けます。取得時点では有効でも、その値を使い続ければ期限切れになります。[SDK](/glossary/sdk/)が[対応](/glossary/対応/)している認証情報の取得経路を使うことで、更新後の値を再取得できます。

## セッション時間と時計を確認する

`AssumeRole`の`DurationSeconds`は、[ロール](/glossary/ロール/)に[設定](/glossary/設定/)された最大[セッション](/glossary/セッション/)時間の範囲で指定します。[AssumeRole APIの公式文書](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)では、最大43200秒、つまり12時間まで[設定](/glossary/設定/)できます。ただし、許可される上限は対象[ロール](/glossary/ロール/)の[設定](/glossary/設定/)によって変わります。

一時的な認証情報で別の[ロール](/glossary/ロール/)を引き受ける[ロール](/glossary/ロール/)連鎖では、[セッション](/glossary/セッション/)は最大1時間です。1時間を超える`DurationSeconds`を指定すると、期限が延びるのではなく`AssumeRole`自体が失敗します。長時間動く処理では、期限を長くするだけでなく、[CLI](/glossary/cli/)や[SDK](/glossary/sdk/)が再取得できる構成にしてください。

認証情報を更新してもすぐ期限切れと判定される場合は、実行環境の日時とタイムゾーンも確認します。[AWS](/glossary/aws/)の要求には署名時刻が含まれるため、大きな時刻ずれは[認証](/glossary/認証/)[エラー](/glossary/エラー/)の原因になります。ただし、時刻ずれでは`RequestExpired`や署名関連の別[エラー](/glossary/エラー/)になる場合もあります。先に認証情報の実際の有効期限と取得元を確認してください。

### 近い認証エラーとの違い

`ExpiredToken`は、認証情報の組み合わせが正しくても、[セッション](/glossary/セッション/)の有効期限を過ぎた場合に発生します。

`InvalidClientTokenId`や`UnrecognizedClientException`は、アクセスキーや[トークン](/glossary/トークン/)が無効、認識できない、または組み合わせが一致しない場合に出ます。値の入力ミス、削除済みのアクセスキー、異なる[セッション](/glossary/セッション/)の値を混ぜた可能性を確認してください。

`SignatureDoesNotMatch`は、[AWS](/glossary/aws/)側で計算した署名と要求に含まれる署名が一致しない[エラー](/glossary/エラー/)です。シークレットアクセスキー、署名対象、リージョン、サービス名などを調べます。

`AccessDenied`は、認証後の権限判定で拒否された状態です。認証情報を再取得するだけでは直らず、[IAM](/glossary/iam/)[ポリシー](/glossary/ポリシー/)、リソースポリシー、Organizationsの制御などを確認する必要があります。

## 解決手順のまとめ

最初に`aws configure list`を実行し、アクセスキーの取得元を確認します。続いて[環境変数](/glossary/環境変数/)を調べ、期限切れの`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_SESSION_TOKEN`が残っていれば3つとも[削除](/glossary/削除/)します。

新しい一時的な認証情報を取得したら、`aws sts get-caller-identity`で[アカウント](/glossary/アカウント/)とARNを確認します。直った後は、手動コピーを続けず、[ロール](/glossary/ロール/)用プロファイル、[IAM](/glossary/iam/) Identity Center、EC2のインスタンスプロファイル、ECSのタスクロールなど、自動で再取得できる方法へ変更してください。

[ロール](/glossary/ロール/)連鎖は最大1時間です。処理時間が長い場合は、`DurationSeconds`だけで解決しようとせず、処理中に認証情報を更新できる構成かを確認します。認証情報が有効なのに失敗する場合は、最後に実行環境の時計を確認してください。

免責事項：本記事の内容は一般的な[AWS](/glossary/aws/) [CLI](/glossary/cli/)および[AWS](/glossary/aws/) [SDK](/glossary/sdk/)の構成を前提としています。認証情報を[削除](/glossary/削除/)または変更する前に、実行中の処理と使用中のプロファイルを確認してください。アクセスキー、シークレットアクセスキー、セッショントークンを[ログ](/glossary/ログ/)や画面共有へ表示しないでください。[本番環境](/glossary/本番環境/)では、組織の認証方針と[IAM](/glossary/iam/)管理者の手順を優先してください。
