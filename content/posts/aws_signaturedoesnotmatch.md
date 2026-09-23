---
title: "AWS署名不一致の原因と対処法"
date: 2026-09-23
draft: false
description: "AWSのSignatureDoesNotMatchは、AWS側が再計算した署名と送信した署名が一致しない場合に発生します。資格情報、時刻、リージョン、正規化したリクエスト、S3の事前署名URLを順に確認します。"
tags: ["AWS"]
images: ["og/posts/aws_signaturedoesnotmatch.png"]
errorCode: "SignatureDoesNotMatch"
urgency: "high"
service: "AWS"
error_type: "SignatureDoesNotMatch"
components: ["Signature Version 4", "authentication", "canonical request"]
related_services: ["Amazon S3", "AWS CLI"]
trend_incident: false
---

## 冒頭まとめ

AWSへのリクエストで次のエラーが出る場合、送信した署名とAWS側が同じリクエストから再計算した署名が一致していません。

```text
SignatureDoesNotMatch
The request signature we calculated does not match the signature you provided. Check your key and signing method.
```

最初に、AWS SDKまたはAWS CLIでも同じ操作が失敗するか確認します。SDKやCLIでは成功するなら、資格情報そのものより、独自に実装した署名処理、リクエストの変更、事前署名URLの使い方に原因がある可能性が高くなります。

AWS CLIでも失敗する場合は、使用中のアクセスキー、プロファイル、リージョン、時刻を確認してください。S3の事前署名URLでは、URL、HTTPメソッド、`Content-Type`などの署名対象が発行時と使用時で一致している必要があります。

## SignatureDoesNotMatchの意味

AWS Signature Version 4は、HTTPメソッド、パス、クエリ文字列、見出し、本文の要約値などから署名を作る認証方式です。AWSは署名付きリクエストを受け取ると、受信した内容から署名を再計算して、送られた署名と比較します。

一致しなければ、HTTP 403と`SignatureDoesNotMatch`が返ります。[AWS公式のSigV4トラブルシューティング](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-troubleshooting.html)にも、署名値がAWS側の計算結果と一致しないエラーだと記載されています。

HTTP 403だけを見て、すべてIAM権限の問題と判断してはいけません。Amazon S3では、権限拒否の`AccessDenied`も403ですが、`SignatureDoesNotMatch`は署名不一致を示します。エラーの状態コードだけでなく、コードと本文を確認してください。

IAMポリシーを広げても、誤った署名は正しくなりません。まず署名と資格情報を直し、その後に`AccessDenied`が出た場合は必要な権限を調べます。

## SDKやCLIでも失敗する場合

AWS CLIがどのプロファイル、アクセスキー、リージョンを使っているか確認します。

```bash
aws configure list
```

このコマンドはアクセスキーとシークレットアクセスキーの一部を伏せ、値の取得元も表示します。環境変数、共有資格情報ファイル、指定したプロファイルのどれが使われているかを確認してください。

名前付きプロファイルを使う場合は、対象を明示します。

```bash
aws configure list --profile example
```

資格情報でAWS APIを呼べるかは、次のコマンドでも確認できます。

```bash
aws sts get-caller-identity --profile example
```

想定と違う利用者やロールが表示された場合は、環境変数、プロファイル、実行環境に割り当てたロールを見直します。アクセスキーIDとシークレットアクセスキーが別の組から混ざっていないかも確認してください。

一時的な資格情報を使う場合は、アクセスキーとシークレットアクセスキーに加えてセッショントークンが必要です。[AWS公式の署名手順](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html#reference_sigv-create-signed-request-temp-credentials)では、`X-Amz-Security-Token`を見出しまたはクエリ文字列へ含めるよう説明されています。

計算機の時刻も確認します。

```bash
date -u
```

Windows PowerShellでは次を実行できます。

```powershell
Get-Date -AsUTC
```

時刻がずれている場合は、OSの自動時刻設定や時刻同期を有効にします。仮想マシンや休止状態から復帰した環境では、ホストとの時刻同期も確認してください。

## 手動署名ではCanonical Requestを比較する

SDKやCLIを使わずに署名を組み立てている場合は、Canonical RequestとString to Signを確認します。Canonical Requestは、リクエストを署名計算用の決められた形へ並べ直した文字列です。

SigV4のCanonical Requestは、次の要素を改行で連結します。

```text
<HTTPMethod>
<CanonicalURI>
<CanonicalQueryString>
<CanonicalHeaders>
<SignedHeaders>
<HashedPayload>
```

HTTPメソッドの違い、パスの符号化、クエリ文字列の順序、見出し名の小文字化、空白の処理、本文の要約値のどれか1文字でも違えば、最終的な署名は一致しません。

[AWS公式の署名作成手順](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html)では、空白を`+`ではなく`%20`にすること、パーセント符号化した16進数では大文字を使うことなどが示されています。一般的なURL符号化関数がAWSの規則と一致するとは限らない点にも注意が必要です。

エラー応答にAWS側のCanonical RequestやString to Signが含まれている場合は、自分の実装が署名前に出力した文字列と比較します。見やすく整形し直すと差が消える可能性があるため、改行、空白、符号化後の文字列をそのまま保存して比べてください。

AWS公式文書は、署名処理が複雑になり得るため、可能な限りAWS SDKまたはAWS CLIを使うよう推奨しています。独自実装が必須でなければ、対応するSDKへ置き換えるほうが安全です。

## 日付・リージョン・サービス名を確認する

SigV4のCredential Scopeは、通常次の形です。

```text
YYYYMMDD/region/service/aws4_request
```

日付、リージョン、サービス名、末尾の`aws4_request`が実際のリクエストと一致している必要があります。たとえば、S3へのリクエストで別リージョンや別サービス名を使って署名すると検証に失敗します。

AWSは、食い違った場所を特定できる場合に専用の文を返します。

```text
Date in Credential scope does not match YYYYMMDD from ISO-8601 version of date from HTTP
Credential should be scoped to a valid Region, not <region-code>
Credential should be scoped to correct service: '<service>'
Credential should be scoped with a valid terminator: 'aws4_request'
```

時刻が未来なら`Signature not yet current`、期限を過ぎていれば`Signature expired`と表示される場合があります。これらが出ているときは、一般的な`SignatureDoesNotMatch`より原因を絞りやすいため、示された日付や範囲を先に修正してください。

なお、SigV4aではリージョンがCredential Scopeに含まれません。SigV4とSigV4aを同じ構成として扱わないようにします。

途中のプロキシや独自のHTTP処理にも注意が必要です。署名後に`Host`などの見出し、パス、クエリ文字列、本文が変更されると、AWSが再計算する材料と一致しなくなります。可能であればプロキシを通さない経路で試し、差があるか確認してください。

## S3の事前署名URLを確認する

S3の事前署名URLで`SignatureDoesNotMatch`が出る場合は、発行時と使用時のリクエストを一致させます。[Amazon S3公式文書](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html#presigned-url-upload-object-troubleshooting)は、次の項目を確認するよう案内しています。

URLは生成された形のまま使います。クエリ文字列の追加、削除、再符号化、短縮URLへの変換を避けてください。`&`などの特殊文字をシェルが解釈しないよう、curlではURLを引用符で囲みます。

HTTPメソッドを一致させます。`GET`用に作ったURLを`PUT`で使うことはできません。アップロード時に`Content-Type`を署名へ含めた場合は、利用時も同じ値を送ります。

```bash
curl -X PUT -T "example.txt" \
  -H "Content-Type: text/plain" \
  "<presigned-url>"
```

バケットのリージョン、URLの有効期限、発行元と利用側の時刻も確認します。発行時に使った一時的な資格情報が先に期限切れになると、URLに設定した期限が残っていても利用できません。この場合は`ExpiredToken`など別のエラーになることがあります。

事前署名URLは認証情報に相当する値を含みます。調査のためでも、URL全体を公開ログ、課題管理、チャットへ貼り付けないでください。

### 署名後にリクエストが変わっていないか確認する

署名を作った後からAWSへ届くまでに内容が変わると、計算結果は一致しません。代理サーバー、API管理基盤、HTTPライブラリ、独自の再試行処理などが、見出しやURLを書き換えていないか確認します。

特に、署名対象として列挙した`SignedHeaders`と、実際に送信された見出しを比較してください。署名に含めた見出しの値が送信時に変わると失敗します。

```text
SignedHeaders=content-type;host;x-amz-date
```

この例では、`content-type`、`host`、`x-amz-date`が署名時と送信時で一致する必要があります。HTTPライブラリが`Content-Type`を自動追加または変更する構成では、署名を作る時点の値と実送信値を確認してください。

AWS公式文書では、`IncompleteSignatureException`の調査として、送信前の`Authorization`見出しをSHA-256で要約し、Base64へ変換した値をエラー文と比較する方法も示されています。これは途中で`Authorization`見出しが変更されたかを調べる手順であり、秘密鍵や見出しそのものをログへ出さずに比較できます。

ただし、通常の`SignatureDoesNotMatch`で比較用の値が返されない場合には使えません。その場合は、送信前後のCanonical Requestを安全な検証環境で記録し、秘密情報を除いて差分を確認します。

## 近いエラーとの違い

`AccessDenied`は、認証された利用者やロールに操作権限がない場合、バケットポリシーなどで明示的に拒否された場合に出ます。S3では`SignatureDoesNotMatch`と同じ403でも、調べる対象はIAMポリシーやバケットポリシーです。

`InvalidAccessKeyId`は、指定したアクセスキーIDがAWS側に存在しない状態です。`SignatureDoesNotMatch`では、アクセスキーと組になるシークレットアクセスキーが違う、または署名計算が違う可能性を調べます。

`ExpiredToken`は、一時的な資格情報が期限切れになった状態です。事前署名URLは、設定したURLの期限より先に元の資格情報が失効すると利用できなくなります。

`RequestTimeTooSkewed`は、S3がリクエスト時刻とサーバー時刻の差が大きすぎると判断した状態です。[S3公式のエラー一覧](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ErrorCodeBilling.html)では403として掲載されています。

`MissingAuthenticationToken`または`Missing Authentication Token`は、必要な署名が付いていない場合に返るエラーです。署名はあるが値が一致しない`SignatureDoesNotMatch`とは異なります。

## 解決手順のまとめ

最初に`aws configure list`で使用中のプロファイル、アクセスキーの取得元、リージョンを確認します。`aws sts get-caller-identity`や対象サービスのAWS CLIコマンドで同じ資格情報を試し、CLIでも失敗するかを切り分けてください。

CLIは成功し、独自実装だけが失敗する場合は、Canonical RequestとString to Signを出力し、AWSのエラー応答に比較対象があれば改行や符号化を含めて照合します。Credential Scopeの日付、リージョン、サービス名、`aws4_request`も確認してください。

S3の事前署名URLでは、URL、HTTPメソッド、署名対象の見出し、`Content-Type`、リージョン、有効期限を発行時と一致させます。URLを途中で変更する代理サーバーや処理を外して再現するかも調べます。

IAM権限を広げる前に、エラーコードが`SignatureDoesNotMatch`なのか`AccessDenied`なのかを確認することが重要です。署名処理を自作する必要がなければ、AWS SDKまたはAWS CLIへ置き換えることで計算や正規化の誤りを避けられます。

免責事項：本記事の内容はAWS Signature Version 4とAmazon S3の一般的な構成を前提としています。本番環境で資格情報や署名処理を変更する前に、現在の設定を保存し、検証環境で確認してください。アクセスキー、シークレットアクセスキー、セッショントークン、事前署名URLをログやリポジトリへ記録しないでください。
