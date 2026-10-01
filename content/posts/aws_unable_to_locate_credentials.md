---
title: "AWS認証情報が見つからない時の対処法"
date: 2026-10-01
draft: false
description: "AWS CLIやboto3のUnable to locate credentialsは、要求の署名に必要な認証情報が見つからないエラーです。プロファイル、実行ユーザー、Docker・CIへの引き渡し、EC2・ECSのロールを順に確認します。"
tags: ["AWS"]
images: ["og/posts/aws_unable_to_locate_credentials.png"]
errorCode: "Unable to locate credentials"
urgency: "medium"
service: "AWS"
error_type: "NoCredentialsError"
components: ["AWS CLI", "boto3", "IAM"]
related_services: ["Amazon EC2", "Amazon ECS"]
trend_incident: false
---

## 冒頭まとめ

AWS CLIやboto3で次のエラーが出たら、その処理が参照できる場所に認証情報が見つかっていません。

```text
Unable to locate credentials. You can configure credentials by running "aws configure".
```

まず、エラーが出た環境で`aws configure list`を実行します。プロファイルを指定しているなら、確認コマンドにも同じ`--profile`を付けてください。手元のターミナルでは成功しても、DockerやCI、別の実行ユーザーでは設定ファイルも環境変数も異なります。

開発環境では使用するプロファイルとログイン状態、EC2ではインスタンスプロファイル、ECSではタスクロールを確認します。認証情報が見つからない段階なので、S3の権限を増やしてもこのエラーは解消しません。

## Unable to locate credentialsの意味

Pythonでは次のように表示されます。

```text
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```

[botocoreの例外定義](https://github.com/boto/botocore/blob/develop/botocore/exceptions.py)では、`NoCredentialsError`の本文を`Unable to locate credentials`としています。[要求に署名する処理](https://github.com/boto/botocore/blob/develop/botocore/auth.py)は、認証情報が`None`ならこの例外を送出します。

これはAWSサービスが返す`AccessDenied`とは異なります。署名付きの要求を送るための認証情報を、クライアント側で取得できていない状態です。boto3のクライアントを作成できても、実際にAPIを呼ぶときに初めてエラーが出ることがあります。

AWS CLIに表示される`aws configure`の案内は、設定方法の一例です。組織がIAM Identity Centerを使っている場合や、EC2・ECSのロールを利用する場合まで、アクセスキーを手入力する必要があるわけではありません。

## 最初に取得元とプロファイルを確認する

失敗したコマンドと同じユーザー、同じコンテナ、同じCIのステップで確認します。

```bash
aws configure list
```

`access_key`と`secret_key`が`<not set>`なら、その実行条件では取得できていません。値が表示される場合は、`Type`と`Location`で取得元を確認します。環境変数から取得していれば`env`、共有認証情報ファイルなら`shared-credentials-file`などが表示されます。取得処理自体に問題がある場合は、この確認コマンドもエラーになることがあります。

プロファイルを指定している場合は、次のように同じ指定で調べます。`dev`は実際のプロファイル名に置き換えてください。

```bash
aws configure list --profile dev
aws sts get-caller-identity --profile dev
```

後者が成功したら、返された`Account`と`Arn`が想定したアカウントとロールか確認します。成功しても、S3などの個別の操作が許可されているとは限りません。

CLIでは成功し、Pythonだけ失敗する場合は、Pythonが同じプロファイルを使っているか確認します。

```python
import boto3

session = boto3.Session(profile_name="dev")
identity = session.client("sts", region_name="ap-northeast-1").get_caller_identity()
print(identity["Account"], identity["Arn"])
```

この例はローカルの`dev`プロファイルを使う場合の確認です。EC2やECSのロールを使うプログラムでは、プロファイル名を固定せず`boto3.Session()`で既定の取得経路を使います。

## 認証情報の優先順位を確認する

boto3は複数の取得元を順に調べ、認証情報を取得できたところで探索を止めます。[公式の認証情報ガイド](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html)には、クライアントやSessionへの明示的な指定、環境変数、AssumeRole、Web Identity、IAM Identity Center、共有ファイル、コンテナ、EC2メタデータなどの順序が記載されています。取得元の種類はバージョンによって追加されるため、単に「環境変数かファイルのどちらか」と考えると、実際の取得元を見落とします。

通常の探索では、環境変数の認証情報が共有ファイルより先に使われます。ただし、取得できた値がAWS側で有効かを確認してから次へ進む仕組みではありません。間違ったアクセスキーが環境変数に残っていても、設定ファイルの正しいキーへ自動で切り替わるとは限りません。この場合は`Unable to locate credentials`ではなく、無効なトークンや署名に関する別のエラーになることがあります。

一方、CLIの`--profile dev`のようにプロファイルを明示すると、通常の環境変数プロバイダは探索から外れます。[botocoreの実装](https://github.com/boto/botocore/blob/develop/botocore/credentials.py)にこの分岐があります。ただし、ロールを引き受けるための取得元として環境変数を指定する構成は別です。

[AWS CLIのIssue #8270](https://github.com/aws/aws-cli/issues/8270)には、環境変数だけなら認証情報を取得できるのに、認証情報を持たないプロファイルを`--profile`で指定すると、このエラーになる報告があります。リージョンと出力形式を設定しただけでは、そのプロファイルで認証できるようにはなりません。

環境変数で認証するつもりなら不要な`--profile`を外し、プロファイルで認証するつもりなら、そのプロファイルの認証方法を設定します。

## 開発環境の設定を直す

組織がIAM Identity Centerを使っている場合は、[AWS CLIの公式手順](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)に従ってプロファイルを設定し、ログインします。

```bash
aws configure sso --profile dev
aws sso login --profile dev
aws sts get-caller-identity --profile dev
```

すでに設定済みなら、設定を作り直す前に`aws sso login --profile dev`でログインをやり直します。SSOの設定やキャッシュが壊れている場合は、トークン取得などの別のエラーになることもあるため、表示された説明文も確認してください。

組織からアクセスキーを渡され、その方式で利用する場合は、次のコマンドで設定します。

```bash
aws configure --profile dev
aws sts get-caller-identity --profile dev
```

通常のユーザーで使うなら、`sudo`を付けずに実行します。標準の保存場所はユーザーのホームにある`.aws/credentials`と`.aws/config`です。別のユーザーで設定すると、普段の実行ユーザーからは見えない場所へ保存されることがあります。Windowsでも、実行ユーザーが変われば参照するホームが変わります。

`AWS_SHARED_CREDENTIALS_FILE`や`AWS_CONFIG_FILE`で別のファイルを指定している場合は、そのパスも確認します。リージョンだけを設定しても、署名に使う認証情報は補われません。

## DockerとCIに認証情報を渡す

ホストのAWS CLIで成功しても、コンテナへ設定は自動で引き継がれません。ローカルの開発用コンテナで共有設定を使う場合は、実行ユーザーのホームに合わせてマウントします。

次はLinux・macOSで、コンテナがrootとして動く場合の例です。`myimage`は対象のイメージ名に置き換えてください。

```bash
docker run --rm \
  --mount type=bind,src="$HOME/.aws",dst=/root/.aws,readonly \
  myimage
```

root以外で動くイメージでは、マウント先をそのユーザーの`.aws`ディレクトリに変更します。SSOを使う場合はログイン済みのキャッシュも必要で、読み取り専用のマウントではコンテナ内からキャッシュを更新できないことがあります。認証情報をDockerfileにコピーしてイメージへ含める方法は使いません。

CIでは、認証処理がAWSコマンドより前に実行され、そのコマンドを動かすステップやコンテナまで設定が渡っているか確認します。GitHub Actionsでは、[AWS公式の認証情報設定アクション](https://github.com/aws-actions/configure-aws-credentials)を利用し、OIDCでIAMロールを引き受ける構成を選べます。OIDCでは、GitHub側のトークン発行権限とAWS側の信頼ポリシーも必要です。

環境変数で渡す構成なら、`AWS_ACCESS_KEY_ID`と`AWS_SECRET_ACCESS_KEY`、一時的な認証情報では`AWS_SESSION_TOKEN`も同じ発行結果から渡します。確認のために秘密鍵やトークンをログへ出力せず、`aws configure list`と`get-caller-identity`で取得元と実行主体を確認してください。

## EC2とECSのロールを確認する

EC2では、[IAMロールを含むインスタンスプロファイル](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)をインスタンスへ関連付けます。対応するCLIやSDKがメタデータサービスから認証情報を取得します。

すでにロールがある場合は、アプリケーションの実行環境からメタデータサービスを利用できるか、取得を無効にする設定がないか確認します。ロールにS3の権限がない場合は、認証情報を取得できた後の権限エラーになるため、今回とは切り分けて調べます。

ECSでは、タスク定義の`taskRoleArn`を確認します。[タスクロール](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)は、コンテナ内のアプリケーションがAWS APIを呼ぶためのロールです。

| 設定 | 用途 |
|---|---|
| `taskRoleArn` | コンテナ内のアプリケーションによるAWS API呼び出し |
| `executionRoleArn` | ECSによるイメージ取得やログ送信など |

実行ロールだけを設定しても、アプリケーションの認証情報にはなりません。タスクロールを設定した新しいタスクを起動し、コンテナ内の処理から確認します。

Lambdaでは、実行ロールから得た認証情報をランタイムが提供します。[公式文書](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html)では、アクセスキーやセッショントークンが予約済みの環境変数として記載されています。Lambda上でこのエラーが出る場合は、別プロセスへの環境変数の引き渡しなどを確認し、ECSのタスクロールと同じ仕組みとして扱わないでください。

## 解決手順のまとめ

最初に、失敗した処理と同じ環境で`aws configure list`を実行します。プロファイルを指定している場合は同じ`--profile`を付け、認証情報が取得できているか確認します。

取得できていなければ、開発環境ではプロファイルとログイン、Docker・CIでは設定の引き渡し、EC2・ECSでは認証情報を提供するロールを直します。修正後は`aws sts get-caller-identity`でアカウントとARNを確認し、元の操作を再実行してください。

### 似ている認証エラーとの違い

| エラー | 確認すること |
|---|---|
| `Unable to locate credentials` | 認証情報の取得元、プロファイル、実行環境 |
| `Partial credentials found` | 取得元に必要な項目がそろっているか |
| `Error when retrieving credentials` | 記載された取得元の設定や通信 |
| `ExpiredToken` | 一時的な認証情報の期限と更新方法 |
| `InvalidClientTokenId` | 渡したアクセスキーやトークンの有効性 |
| `AccessDenied` | 対象操作を許可するポリシー |

アクセスキーIDが設定されていてシークレットアクセスキーが欠けている場合などは、`PartialCredentialsError`になります。取得元への接続が失敗した場合は、その取得元の扱いによって結果が異なり、必ず`CredentialRetrievalError`になるとは限りません。

期限切れの場合は[ExpiredTokenの対処法](/posts/aws_expiredtoken/)、権限拒否の場合は[AWSの403エラー](/posts/aws_403/)も確認してください。

免責事項：本記事の内容は一般的なAWS CLIおよびboto3の構成を前提としています。設定を変更する前に、実行ユーザー、対象アカウント、プロファイルを確認してください。認証情報をソースコード、コンテナイメージ、公開ログへ含めず、組織で定められた認証方法を使用してください。
