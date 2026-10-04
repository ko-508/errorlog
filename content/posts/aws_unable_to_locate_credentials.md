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

[AWS](/glossary/aws/) [CLI](/glossary/cli/)やboto3で次の[エラー](/glossary/エラー/)が出たら、その処理が参照できる場所に認証情報が見つかっていません。

```text
Unable to locate credentials. You can configure credentials by running "aws configure".
```

まず、[エラー](/glossary/エラー/)が出た[環境](/glossary/環境/)で`aws configure list`を実行します。プロファイルを指定しているなら、確認[コマンド](/glossary/コマンド/)にも同じ`--profile`を付けてください。手元の[ターミナル](/glossary/ターミナル/)では成功しても、[Docker](/glossary/docker/)やCI、別の実行ユーザーでは[設定ファイル](/glossary/設定ファイル/)も[環境変数](/glossary/環境変数/)も異なります。

[開発環境](/glossary/開発環境/)では使用するプロファイルと[ログイン](/glossary/ログイン/)状態、EC2ではインスタンスプロファイル、ECSではタスクロールを確認します。認証情報が見つからない段階なので、S3の[権限](/glossary/権限/)を増やしてもこの[エラー](/glossary/エラー/)は解消しません。

## Unable to locate credentialsの意味

Pythonでは次のように表示されます。

```text
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```

[botocoreの例外定義](https://github.com/boto/botocore/blob/develop/botocore/exceptions.py)では、`NoCredentialsError`の本文を`Unable to locate credentials`としています。[要求に署名する処理](https://github.com/boto/botocore/blob/develop/botocore/auth.py)は、認証情報が`None`ならこの例外を送出します。

これは[AWS](/glossary/aws/)サービスが返す`AccessDenied`とは異なります。署名付きの要求を送るための認証情報を、[クライアント](/glossary/クライアント/)側で取得できていない状態です。boto3の[クライアント](/glossary/クライアント/)を作成できても、実際に[API](/glossary/api/)を呼ぶときに初めて[エラー](/glossary/エラー/)が出ることがあります。

[AWS](/glossary/aws/) [CLI](/glossary/cli/)に表示される`aws configure`の案内は、設定方法の一例です。組織が[IAM](/glossary/iam/) Identity Centerを使っている場合や、EC2・ECSの[ロール](/glossary/ロール/)を利用する場合まで、アクセスキーを手入力する必要があるわけではありません。

## 最初に取得元とプロファイルを確認する

失敗した[コマンド](/glossary/コマンド/)と同じユーザー、同じ[コンテナ](/glossary/コンテナ/)、同じCIのステップで確認します。

```bash
aws configure list
```

`access_key`と`secret_key`が`<not set>`なら、その実行条件では取得できていません。値が表示される場合は、`Type`と`Location`で取得元を確認します。[環境変数](/glossary/環境変数/)から取得していれば`env`、共有認証情報[ファイル](/glossary/ファイル/)なら`shared-credentials-file`などが表示されます。取得処理自体に問題がある場合は、この確認[コマンド](/glossary/コマンド/)も[エラー](/glossary/エラー/)になることがあります。

プロファイルを指定している場合は、次のように同じ指定で調べます。`dev`は実際のプロファイル名に置き換えてください。

```bash
aws configure list --profile dev
aws sts get-caller-identity --profile dev
```

後者が成功したら、返された`Account`と`Arn`が想定した[アカウント](/glossary/アカウント/)と[ロール](/glossary/ロール/)か確認します。成功しても、S3などの個別の操作が許可されているとは限りません。

[CLI](/glossary/cli/)では成功し、Pythonだけ失敗する場合は、Pythonが同じプロファイルを使っているか確認します。

```python
import boto3

session = boto3.Session(profile_name="dev")
identity = session.client("sts", region_name="ap-northeast-1").get_caller_identity()
print(identity["Account"], identity["Arn"])
```

この例はローカルの`dev`プロファイルを使う場合の確認です。EC2やECSの[ロール](/glossary/ロール/)を使う[プログラム](/glossary/プログラム/)では、プロファイル名を固定せず`boto3.Session()`で既定の取得経路を使います。

## 認証情報の優先順位を確認する

boto3は複数の取得元を順に調べ、認証情報を取得できたところで探索を止めます。[公式の認証情報ガイド](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html)には、[クライアント](/glossary/クライアント/)やSessionへの明示的な指定、[環境変数](/glossary/環境変数/)、AssumeRole、Web Identity、[IAM](/glossary/iam/) Identity Center、共有[ファイル](/glossary/ファイル/)、[コンテナ](/glossary/コンテナ/)、EC2[メタデータ](/glossary/メタデータ/)などの順序が記載されています。取得元の種類は[バージョン](/glossary/バージョン/)によって追加されるため、単に「[環境変数](/glossary/環境変数/)か[ファイル](/glossary/ファイル/)のどちらか」と考えると、実際の取得元を見落とします。

通常の探索では、[環境変数](/glossary/環境変数/)の認証情報が共有[ファイル](/glossary/ファイル/)より先に使われます。ただし、取得できた値が[AWS](/glossary/aws/)側で有効かを確認してから次へ進む仕組みではありません。間違ったアクセスキーが[環境変数](/glossary/環境変数/)に残っていても、[設定ファイル](/glossary/設定ファイル/)の正しい[キー](/glossary/キー/)へ自動で切り替わるとは限りません。この場合は`Unable to locate credentials`ではなく、無効な[トークン](/glossary/トークン/)や署名に関する別の[エラー](/glossary/エラー/)になることがあります。

一方、[CLI](/glossary/cli/)の`--profile dev`のようにプロファイルを明示すると、通常の[環境変数](/glossary/環境変数/)[プロバイダ](/glossary/プロバイダ/)は探索から外れます。[botocoreの実装](https://github.com/boto/botocore/blob/develop/botocore/credentials.py)にこの分岐があります。ただし、[ロール](/glossary/ロール/)を引き受けるための取得元として[環境変数](/glossary/環境変数/)を指定する構成は別です。

[AWS CLIのIssue #8270](https://github.com/aws/aws-cli/issues/8270)には、[環境変数](/glossary/環境変数/)だけなら認証情報を取得できるのに、認証情報を持たないプロファイルを`--profile`で指定すると、この[エラー](/glossary/エラー/)になる報告があります。リージョンと出力形式を[設定](/glossary/設定/)しただけでは、そのプロファイルで[認証](/glossary/認証/)できるようにはなりません。

[環境変数](/glossary/環境変数/)で[認証](/glossary/認証/)するつもりなら不要な`--profile`を外し、プロファイルで[認証](/glossary/認証/)するつもりなら、そのプロファイルの認証方法を[設定](/glossary/設定/)します。

## 開発環境の設定を直す

組織が[IAM](/glossary/iam/) Identity Centerを使っている場合は、[AWS CLIの公式手順](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)に従ってプロファイルを[設定](/glossary/設定/)し、[ログイン](/glossary/ログイン/)します。

```bash
aws configure sso --profile dev
aws sso login --profile dev
aws sts get-caller-identity --profile dev
```

すでに設定済みなら、[設定](/glossary/設定/)を作り直す前に`aws sso login --profile dev`で[ログイン](/glossary/ログイン/)をやり直します。SSOの[設定](/glossary/設定/)や[キャッシュ](/glossary/キャッシュ/)が壊れている場合は、[トークン](/glossary/トークン/)取得などの別の[エラー](/glossary/エラー/)になることもあるため、表示された説明文も確認してください。

組織からアクセスキーを渡され、その方式で利用する場合は、次の[コマンド](/glossary/コマンド/)で[設定](/glossary/設定/)します。

```bash
aws configure --profile dev
aws sts get-caller-identity --profile dev
```

通常のユーザーで使うなら、`sudo`を付けずに実行します。[標準](/glossary/標準/)の保存場所はユーザーのホームにある`.aws/credentials`と`.aws/config`です。別のユーザーで[設定](/glossary/設定/)すると、普段の実行ユーザーからは見えない場所へ[保存](/glossary/保存/)されることがあります。Windowsでも、実行ユーザーが変われば参照するホームが変わります。

`AWS_SHARED_CREDENTIALS_FILE`や`AWS_CONFIG_FILE`で別の[ファイル](/glossary/ファイル/)を指定している場合は、その[パス](/glossary/パス/)も確認します。リージョンだけを[設定](/glossary/設定/)しても、署名に使う認証情報は補われません。

## DockerとCIに認証情報を渡す

ホストの[AWS](/glossary/aws/) [CLI](/glossary/cli/)で成功しても、[コンテナ](/glossary/コンテナ/)へ[設定](/glossary/設定/)は自動で引き継がれません。ローカルの開発用[コンテナ](/glossary/コンテナ/)で共有設定を使う場合は、実行ユーザーのホームに合わせてマウントします。

次は[Linux](/glossary/linux/)・macOSで、[コンテナ](/glossary/コンテナ/)がrootとして動く場合の例です。`myimage`は対象の[イメージ](/glossary/イメージ/)名に置き換えてください。

```bash
docker run --rm \
  --mount type=bind,src="$HOME/.aws",dst=/root/.aws,readonly \
  myimage
```

root以外で動く[イメージ](/glossary/イメージ/)では、マウント先をそのユーザーの`.aws`[ディレクトリ](/glossary/ディレクトリ/)に変更します。SSOを使う場合は[ログイン](/glossary/ログイン/)済みの[キャッシュ](/glossary/キャッシュ/)も必要で、読み取り専用のマウントでは[コンテナ](/glossary/コンテナ/)内から[キャッシュ](/glossary/キャッシュ/)を更新できないことがあります。認証情報をDockerfileにコピーして[イメージ](/glossary/イメージ/)へ含める方法は使いません。

CIでは、認証処理が[AWS](/glossary/aws/)[コマンド](/glossary/コマンド/)より前に実行され、その[コマンド](/glossary/コマンド/)を動かすステップや[コンテナ](/glossary/コンテナ/)まで[設定](/glossary/設定/)が渡っているか確認します。[GitHub](/glossary/github/) Actionsでは、[AWS公式の認証情報設定アクション](https://github.com/aws-actions/configure-aws-credentials)を利用し、OIDCで[IAM](/glossary/iam/)[ロール](/glossary/ロール/)を引き受ける構成を選べます。OIDCでは、[GitHub](/glossary/github/)側の[トークン](/glossary/トークン/)発行権限と[AWS](/glossary/aws/)側の信頼[ポリシー](/glossary/ポリシー/)も必要です。

[環境変数](/glossary/環境変数/)で渡す構成なら、`AWS_ACCESS_KEY_ID`と`AWS_SECRET_ACCESS_KEY`、一時的な認証情報では`AWS_SESSION_TOKEN`も同じ発行結果から渡します。確認のために[秘密鍵](/glossary/秘密鍵/)や[トークン](/glossary/トークン/)を[ログ](/glossary/ログ/)へ出力せず、`aws configure list`と`get-caller-identity`で取得元と実行主体を確認してください。

## EC2とECSのロールを確認する

EC2では、[IAMロールを含むインスタンスプロファイル](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)を[インスタンス](/glossary/インスタンス/)へ関連付けます。[対応](/glossary/対応/)する[CLI](/glossary/cli/)や[SDK](/glossary/sdk/)がメタデータサービスから認証情報を取得します。

すでに[ロール](/glossary/ロール/)がある場合は、[アプリケーション](/glossary/アプリケーション/)の実行環境からメタデータサービスを利用できるか、取得を無効にする[設定](/glossary/設定/)がないか確認します。[ロール](/glossary/ロール/)にS3の[権限](/glossary/権限/)がない場合は、認証情報を取得できた後の[権限](/glossary/権限/)[エラー](/glossary/エラー/)になるため、今回とは切り分けて調べます。

ECSでは、[タスク](/glossary/タスク/)定義の`taskRoleArn`を確認します。[タスクロール](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)は、[コンテナ](/glossary/コンテナ/)内の[アプリケーション](/glossary/アプリケーション/)が[AWS](/glossary/aws/) [API](/glossary/api/)を呼ぶための[ロール](/glossary/ロール/)です。

| [設定](/glossary/設定/) | 用途 |
|---|---|
| `taskRoleArn` | [コンテナ](/glossary/コンテナ/)内の[アプリケーション](/glossary/アプリケーション/)による[AWS](/glossary/aws/) [API](/glossary/api/)呼び出し |
| `executionRoleArn` | ECSによる[イメージ](/glossary/イメージ/)取得や[ログ](/glossary/ログ/)[送信](/glossary/送信/)など |

実行[ロール](/glossary/ロール/)だけを[設定](/glossary/設定/)しても、[アプリケーション](/glossary/アプリケーション/)の認証情報にはなりません。タスクロールを[設定](/glossary/設定/)した新しい[タスク](/glossary/タスク/)を起動し、[コンテナ](/glossary/コンテナ/)内の処理から確認します。

Lambdaでは、実行[ロール](/glossary/ロール/)から得た認証情報をランタイムが提供します。[公式文書](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html)では、アクセスキーやセッショントークンが予約済みの[環境変数](/glossary/環境変数/)として記載されています。Lambda上でこの[エラー](/glossary/エラー/)が出る場合は、別[プロセス](/glossary/プロセス/)への[環境変数](/glossary/環境変数/)の引き渡しなどを確認し、ECSのタスクロールと同じ仕組みとして扱わないでください。

## 解決手順のまとめ

最初に、失敗した処理と同じ[環境](/glossary/環境/)で`aws configure list`を実行します。プロファイルを指定している場合は同じ`--profile`を付け、認証情報が取得できているか確認します。

取得できていなければ、[開発環境](/glossary/開発環境/)ではプロファイルと[ログイン](/glossary/ログイン/)、[Docker](/glossary/docker/)・CIでは[設定](/glossary/設定/)の引き渡し、EC2・ECSでは認証情報を提供する[ロール](/glossary/ロール/)を直します。修正後は`aws sts get-caller-identity`で[アカウント](/glossary/アカウント/)とARNを確認し、元の操作を再実行してください。

### 似ている認証エラーとの違い

| [エラー](/glossary/エラー/) | 確認すること |
|---|---|
| `Unable to locate credentials` | 認証情報の取得元、プロファイル、実行環境 |
| `Partial credentials found` | 取得元に必要な項目がそろっているか |
| `Error when retrieving credentials` | 記載された取得元の[設定](/glossary/設定/)や[通信](/glossary/通信/) |
| `ExpiredToken` | 一時的な認証情報の期限と更新方法 |
| `InvalidClientTokenId` | 渡したアクセスキーや[トークン](/glossary/トークン/)の有効性 |
| `AccessDenied` | 対象操作を許可する[ポリシー](/glossary/ポリシー/) |

アクセスキー[ID](/glossary/id/)が[設定](/glossary/設定/)されていてシークレットアクセスキーが欠けている場合などは、`PartialCredentialsError`になります。取得元への接続が失敗した場合は、その取得元の扱いによって結果が異なり、必ず`CredentialRetrievalError`になるとは限りません。

期限切れの場合は[ExpiredTokenの対処法](/posts/aws_expiredtoken/)、権限拒否の場合は[AWSの403エラー](/posts/aws_403/)も確認してください。

免責事項：本記事の内容は一般的な[AWS](/glossary/aws/) [CLI](/glossary/cli/)およびboto3の構成を前提としています。[設定](/glossary/設定/)を変更する前に、実行ユーザー、対象[アカウント](/glossary/アカウント/)、プロファイルを確認してください。認証情報をソースコード、[コンテナイメージ](/glossary/コンテナイメージ/)、公開[ログ](/glossary/ログ/)へ含めず、組織で定められた認証方法を使用してください。
