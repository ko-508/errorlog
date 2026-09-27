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

[AWS](/glossary/aws/)への[リクエスト](/glossary/リクエスト/)で次の[エラー](/glossary/エラー/)が出る場合、[送信](/glossary/送信/)した署名と[AWS](/glossary/aws/)側が同じ[リクエスト](/glossary/リクエスト/)から再計算した署名が一致していません。

```text
SignatureDoesNotMatch
The request signature we calculated does not match the signature you provided. Check your key and signing method.
```

最初に、[AWS](/glossary/aws/) [SDK](/glossary/sdk/)または[AWS](/glossary/aws/) [CLI](/glossary/cli/)でも同じ操作が失敗するか確認します。[SDK](/glossary/sdk/)や[CLI](/glossary/cli/)では成功するなら、資格情報そのものより、独自に実装した署名処理、[リクエスト](/glossary/リクエスト/)の変更、事前署名[URL](/glossary/url/)の使い方に原因がある可能性が高くなります。

[AWS](/glossary/aws/) [CLI](/glossary/cli/)でも失敗する場合は、使用中のアクセスキー、プロファイル、リージョン、時刻を確認してください。S3の事前署名[URL](/glossary/url/)では、[URL](/glossary/url/)、[HTTP](/glossary/http/)[メソッド](/glossary/メソッド/)、`Content-Type`などの署名対象が発行時と使用時で一致している必要があります。

## SignatureDoesNotMatchの意味

[AWS](/glossary/aws/) Signature Version 4は、[HTTP](/glossary/http/)[メソッド](/glossary/メソッド/)、[パス](/glossary/パス/)、[クエリ](/glossary/クエリ/)文字列、見出し、本文の要約値などから署名を作る認証方式です。[AWS](/glossary/aws/)は署名付き[リクエスト](/glossary/リクエスト/)を受け取ると、[受信](/glossary/受信/)した内容から署名を再計算して、送られた署名と比較します。

一致しなければ、[HTTP](/glossary/http/) 403と`SignatureDoesNotMatch`が返ります。[AWS公式のSigV4トラブルシューティング](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-troubleshooting.html)にも、署名値が[AWS](/glossary/aws/)側の計算結果と一致しない[エラー](/glossary/エラー/)だと記載されています。

[HTTP](/glossary/http/) 403だけを見て、すべて[IAM](/glossary/iam/)[権限](/glossary/権限/)の問題と判断してはいけません。Amazon S3では、権限拒否の`AccessDenied`も403ですが、`SignatureDoesNotMatch`は署名不一致を示します。[エラー](/glossary/エラー/)の状態[コード](/glossary/コード/)だけでなく、[コード](/glossary/コード/)と本文を確認してください。

[IAM](/glossary/iam/)[ポリシー](/glossary/ポリシー/)を広げても、誤った署名は正しくなりません。まず署名と資格情報を直し、その後に`AccessDenied`が出た場合は必要な[権限](/glossary/権限/)を調べます。

## SDKやCLIでも失敗する場合

[AWS](/glossary/aws/) [CLI](/glossary/cli/)がどのプロファイル、アクセスキー、リージョンを使っているか確認します。

```bash
aws configure list
```

この[コマンド](/glossary/コマンド/)はアクセスキーとシークレットアクセスキーの一部を伏せ、値の取得元も表示します。[環境変数](/glossary/環境変数/)、共有資格情報[ファイル](/glossary/ファイル/)、指定したプロファイルのどれが使われているかを確認してください。

名前付きプロファイルを使う場合は、対象を明示します。

```bash
aws configure list --profile example
```

資格情報で[AWS](/glossary/aws/) [API](/glossary/api/)を呼べるかは、次の[コマンド](/glossary/コマンド/)でも確認できます。

```bash
aws sts get-caller-identity --profile example
```

想定と違う利用者や[ロール](/glossary/ロール/)が表示された場合は、[環境変数](/glossary/環境変数/)、プロファイル、実行環境に割り当てた[ロール](/glossary/ロール/)を見直します。アクセスキー[ID](/glossary/id/)とシークレットアクセスキーが別の組から混ざっていないかも確認してください。

一時的な資格情報を使う場合は、アクセスキーとシークレットアクセスキーに加えてセッショントークンが必要です。[AWS公式の署名手順](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html#reference_sigv-create-signed-request-temp-credentials)では、`X-Amz-Security-Token`を見出しまたは[クエリ](/glossary/クエリ/)文字列へ含めるよう説明されています。

計算機の時刻も確認します。

```bash
date -u
```

Windows PowerShellでは次を実行できます。

```powershell
Get-Date -AsUTC
```

時刻がずれている場合は、[OS](/glossary/os/)の自動時刻設定や時刻同期を有効にします。仮想マシンや休止状態から復帰した[環境](/glossary/環境/)では、ホストとの時刻同期も確認してください。

## 手動署名ではCanonical Requestを比較する

[SDK](/glossary/sdk/)や[CLI](/glossary/cli/)を使わずに署名を組み立てている場合は、Canonical RequestとString to Signを確認します。Canonical Requestは、[リクエスト](/glossary/リクエスト/)を署名計算用の決められた形へ並べ直した文字列です。

SigV4のCanonical Requestは、次の要素を[改行](/glossary/改行/)で連結します。

```text
<HTTPMethod>
<CanonicalURI>
<CanonicalQueryString>
<CanonicalHeaders>
<SignedHeaders>
<HashedPayload>
```

[HTTP](/glossary/http/)[メソッド](/glossary/メソッド/)の違い、[パス](/glossary/パス/)の符号化、[クエリ](/glossary/クエリ/)文字列の順序、見出し名の小文字化、空白の処理、本文の要約値のどれか1文字でも違えば、最終的な署名は一致しません。

[AWS公式の署名作成手順](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html)では、空白を`+`ではなく`%20`にすること、パーセント符号化した16進数では大文字を使うことなどが示されています。一般的な[URL](/glossary/url/)符号化関数が[AWS](/glossary/aws/)の規則と一致するとは限らない点にも注意が必要です。

[エラー](/glossary/エラー/)応答に[AWS](/glossary/aws/)側のCanonical RequestやString to Signが含まれている場合は、自分の実装が署名前に出力した文字列と比較します。見やすく整形し直すと差が消える可能性があるため、[改行](/glossary/改行/)、空白、符号化後の文字列をそのまま[保存](/glossary/保存/)して比べてください。

[AWS](/glossary/aws/)公式文書は、署名処理が複雑になり得るため、可能な限り[AWS](/glossary/aws/) [SDK](/glossary/sdk/)または[AWS](/glossary/aws/) [CLI](/glossary/cli/)を使うよう推奨しています。独自実装が必須でなければ、対応する[SDK](/glossary/sdk/)へ置き換えるほうが安全です。

## 日付・リージョン・サービス名を確認する

SigV4のCredential Scopeは、通常次の形です。

```text
YYYYMMDD/region/service/aws4_request
```

日付、リージョン、サービス名、末尾の`aws4_request`が実際の[リクエスト](/glossary/リクエスト/)と一致している必要があります。たとえば、S3への[リクエスト](/glossary/リクエスト/)で別リージョンや別サービス名を使って署名すると検証に失敗します。

[AWS](/glossary/aws/)は、食い違った場所を特定できる場合に専用の文を返します。

```text
Date in Credential scope does not match YYYYMMDD from ISO-8601 version of date from HTTP
Credential should be scoped to a valid Region, not <region-code>
Credential should be scoped to correct service: '<service>'
Credential should be scoped with a valid terminator: 'aws4_request'
```

時刻が未来なら`Signature not yet current`、期限を過ぎていれば`Signature expired`と表示される場合があります。これらが出ているときは、一般的な`SignatureDoesNotMatch`より原因を絞りやすいため、示された日付や範囲を先に[修正](/glossary/修正/)してください。

なお、SigV4aではリージョンがCredential Scopeに含まれません。SigV4とSigV4aを同じ構成として扱わないようにします。

途中の[プロキシ](/glossary/プロキシ/)や独自の[HTTP](/glossary/http/)処理にも注意が必要です。署名後に`Host`などの見出し、[パス](/glossary/パス/)、[クエリ](/glossary/クエリ/)文字列、本文が変更されると、[AWS](/glossary/aws/)が再計算する材料と一致しなくなります。可能であれば[プロキシ](/glossary/プロキシ/)を通さない経路で試し、差があるか確認してください。

## S3の事前署名URLを確認する

S3の事前署名[URL](/glossary/url/)で`SignatureDoesNotMatch`が出る場合は、発行時と使用時の[リクエスト](/glossary/リクエスト/)を一致させます。[Amazon S3公式文書](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html#presigned-url-upload-object-troubleshooting)は、次の項目を確認するよう案内しています。

[URL](/glossary/url/)は生成された形のまま使います。[クエリ](/glossary/クエリ/)文字列の追加、[削除](/glossary/削除/)、再符号化、短縮[URL](/glossary/url/)への変換を避けてください。`&`などの特殊文字を[シェル](/glossary/シェル/)が解釈しないよう、curlでは[URL](/glossary/url/)を引用符で囲みます。

[HTTP](/glossary/http/)[メソッド](/glossary/メソッド/)を一致させます。`GET`用に作った[URL](/glossary/url/)を`PUT`で使うことはできません。[アップロード](/glossary/アップロード/)時に`Content-Type`を署名へ含めた場合は、利用時も同じ値を送ります。

```bash
curl -X PUT -T "example.txt" \
  -H "Content-Type: text/plain" \
  "<presigned-url>"
```

[バケット](/glossary/バケット/)のリージョン、[URL](/glossary/url/)の有効期限、発行元と利用側の時刻も確認します。発行時に使った一時的な資格情報が先に期限切れになると、[URL](/glossary/url/)に[設定](/glossary/設定/)した期限が残っていても利用できません。この場合は`ExpiredToken`など別の[エラー](/glossary/エラー/)になることがあります。

事前署名[URL](/glossary/url/)は認証情報に相当する値を含みます。調査のためでも、[URL](/glossary/url/)全体を公開[ログ](/glossary/ログ/)、課題管理、チャットへ貼り付けないでください。

### 署名後にリクエストが変わっていないか確認する

署名を作った後から[AWS](/glossary/aws/)へ届くまでに内容が変わると、計算結果は一致しません。代理[サーバー](/glossary/サーバー/)、[API](/glossary/api/)管理基盤、[HTTP](/glossary/http/)[ライブラリ](/glossary/ライブラリ/)、独自の再試行処理などが、見出しや[URL](/glossary/url/)を書き換えていないか確認します。

特に、署名対象として列挙した`SignedHeaders`と、実際に[送信](/glossary/送信/)された見出しを比較してください。署名に含めた見出しの値が送信時に変わると失敗します。

```text
SignedHeaders=content-type;host;x-amz-date
```

この例では、`content-type`、`host`、`x-amz-date`が署名時と送信時で一致する必要があります。[HTTP](/glossary/http/)[ライブラリ](/glossary/ライブラリ/)が`Content-Type`を自動追加または変更する構成では、署名を作る時点の値と実送信値を確認してください。

[AWS](/glossary/aws/)公式文書では、`IncompleteSignatureException`の調査として、送信前の`Authorization`見出しをSHA-256で要約し、Base64へ変換した値を[エラー](/glossary/エラー/)文と比較する方法も示されています。これは途中で`Authorization`見出しが変更されたかを調べる手順であり、[秘密鍵](/glossary/秘密鍵/)や見出しそのものを[ログ](/glossary/ログ/)へ出さずに比較できます。

ただし、通常の`SignatureDoesNotMatch`で比較用の値が返されない場合には使えません。その場合は、送信前後のCanonical Requestを安全な検証環境で記録し、秘密情報を除いて差分を確認します。

## 近いエラーとの違い

`AccessDenied`は、[認証](/glossary/認証/)された利用者や[ロール](/glossary/ロール/)に操作権限がない場合、バケットポリシーなどで明示的に拒否された場合に出ます。S3では`SignatureDoesNotMatch`と同じ403でも、調べる対象は[IAM](/glossary/iam/)[ポリシー](/glossary/ポリシー/)やバケットポリシーです。

`InvalidAccessKeyId`は、指定したアクセスキー[ID](/glossary/id/)が[AWS](/glossary/aws/)側に存在しない状態です。`SignatureDoesNotMatch`では、アクセスキーと組になるシークレットアクセスキーが違う、または署名計算が違う可能性を調べます。

`ExpiredToken`は、一時的な資格情報が期限切れになった状態です。事前署名[URL](/glossary/url/)は、[設定](/glossary/設定/)した[URL](/glossary/url/)の期限より先に元の資格情報が失効すると利用できなくなります。

`RequestTimeTooSkewed`は、S3が[リクエスト](/glossary/リクエスト/)時刻と[サーバー](/glossary/サーバー/)時刻の差が大きすぎると判断した状態です。[S3公式のエラー一覧](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ErrorCodeBilling.html)では403として掲載されています。

`MissingAuthenticationToken`または`Missing Authentication Token`は、必要な署名が付いていない場合に返る[エラー](/glossary/エラー/)です。署名はあるが値が一致しない`SignatureDoesNotMatch`とは異なります。

## 解決手順のまとめ

最初に`aws configure list`で使用中のプロファイル、アクセスキーの取得元、リージョンを確認します。`aws sts get-caller-identity`や対象サービスの[AWS](/glossary/aws/) [CLI](/glossary/cli/)[コマンド](/glossary/コマンド/)で同じ資格情報を試し、[CLI](/glossary/cli/)でも失敗するかを切り分けてください。

[CLI](/glossary/cli/)は成功し、独自実装だけが失敗する場合は、Canonical RequestとString to Signを出力し、[AWS](/glossary/aws/)の[エラー](/glossary/エラー/)応答に比較対象があれば[改行](/glossary/改行/)や符号化を含めて照合します。Credential Scopeの日付、リージョン、サービス名、`aws4_request`も確認してください。

S3の事前署名[URL](/glossary/url/)では、[URL](/glossary/url/)、[HTTP](/glossary/http/)[メソッド](/glossary/メソッド/)、署名対象の見出し、`Content-Type`、リージョン、有効期限を発行時と一致させます。[URL](/glossary/url/)を途中で変更する代理[サーバー](/glossary/サーバー/)や処理を外して再現するかも調べます。

[IAM](/glossary/iam/)[権限](/glossary/権限/)を広げる前に、[エラーコード](/glossary/エラーコード/)が`SignatureDoesNotMatch`なのか`AccessDenied`なのかを確認することが重要です。署名処理を自作する必要がなければ、[AWS](/glossary/aws/) [SDK](/glossary/sdk/)または[AWS](/glossary/aws/) [CLI](/glossary/cli/)へ置き換えることで計算や正規化の誤りを避けられます。

免責事項：本記事の内容は[AWS](/glossary/aws/) Signature Version 4とAmazon S3の一般的な構成を前提としています。[本番環境](/glossary/本番環境/)で資格情報や署名処理を変更する前に、現在の[設定](/glossary/設定/)を[保存](/glossary/保存/)し、検証環境で確認してください。アクセスキー、シークレットアクセスキー、セッショントークン、事前署名[URL](/glossary/url/)を[ログ](/glossary/ログ/)や[リポジトリ](/glossary/リポジトリ/)へ記録しないでください。
