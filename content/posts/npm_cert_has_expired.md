---
title: "npmのCERT_HAS_EXPIRED対処法"
date: 2026-09-21
draft: false
description: "npm installでCERT_HAS_EXPIREDが出る場合の確認手順と対処法を解説します。接続先の証明書、npmのca・cafile設定、Node.jsの内蔵CA、社内プロキシを順に切り分けます。"
tags: ["npm"]
images: ["og/posts/npm_cert_has_expired.png"]
errorCode: "npm error code CERT_HAS_EXPIRED"
urgency: "high"
service: "npm"
error_type: "CERT_HAS_EXPIRED"
components: ["TLS", "CA certificate", "npm registry"]
related_services: ["Node.js"]
trend_incident: false
---

## 冒頭まとめ

`npm install`などで次のエラーが出る場合、npmがHTTPS通信で検証した証明書の有効期限が切れています。

```text
npm error code CERT_HAS_EXPIRED
npm error errno CERT_HAS_EXPIRED
```

最初に接続先URLとnpmレジストリを確認してください。公式レジストリではなく、社内レジストリ、ミラー、プロキシを経由している場合は、その途中で提示された証明書が原因になることもあります。

次にnpmの`ca`と`cafile`、Node.jsのバージョンを確認します。古いCA証明書が明示的に設定されている場合は設定を更新し、Node.jsが古い場合はサポート中の版へ更新します。証明書の検証を無効にする`strict-ssl=false`は、安全な解決方法ではありません。

## CERT_HAS_EXPIREDの意味

`CERT_HAS_EXPIRED`は、Node.jsのTLS処理が返すX.509証明書エラーです。Node.js公式文書では「証明書の有効期限が切れている」状態として定義されています。

npmはパッケージやメタデータをHTTPSで取得するとき、接続先から提示された証明書をNode.jsで検証します。証明書チェーンの検証対象に期限切れの証明書が含まれていると、npmは通信を中止し、このコードを表示します。

エラーはパッケージの依存関係や`package-lock.json`の内容そのものを示すものではありません。DNS解決とTCP接続の後に行われるTLS証明書の検証で失敗しています。[Node.js公式のTLSエラーコード一覧](https://nodejs.org/api/tls.html#x509-certificate-error-codes)で定義を確認できます。

## 最初に接続先と設定を確認する

エラーの前後に表示されたURLを確認します。npmが使用する既定レジストリも調べてください。

```bash
npm config get registry
```

`https://registry.npmjs.org/`以外が表示された場合は、社内レジストリやミラーの証明書を確認します。ただし、レジストリが公式URLでも、HTTPSプロキシが通信を中継していれば、実際に検証している証明書はプロキシが発行したものかもしれません。

続いて、Node.jsのバージョンとnpmの証明書設定を確認します。

```bash
node -v
npm config get ca
npm config get cafile
npm config get strict-ssl
```

`ca`または`cafile`に値がある場合は、その設定が意図したものか、参照先の証明書が現在も有効かを確認します。`strict-ssl`の既定値は`true`です。

環境変数も確認します。macOSやLinuxでは次を実行します。

```bash
printf '%s\n' "$NODE_EXTRA_CA_CERTS"
```

PowerShellでは次のように確認できます。

```powershell
$env:NODE_EXTRA_CA_CERTS
```

## 接続先やプロキシの証明書が期限切れの場合

社内レジストリ、キャッシュ用ミラー、HTTPSプロキシなどの証明書が期限切れなら、サーバーまたはプロキシ側で証明書を更新する必要があります。利用者側でnpmの検証を無効にしても、期限切れそのものは解消しません。

OpenSSLを利用できる環境では、実際の接続先ホストを指定して証明書の有効期間を確認できます。

```bash
openssl s_client -connect example.com:443 -servername example.com < /dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

`notAfter`が有効期限です。ただし、プロキシを経由する環境でこのコマンドがnpmと同じ通信経路を通るとは限りません。ブラウザ、プロキシ管理画面、組織の証明書管理手段も併用し、npmが実際に受け取った証明書を確認してください。

公開レジストリ側の障害が疑われる場合は、npmの[サービス稼働状況](https://status.npmjs.org/)も確認します。社内レジストリやプロキシの場合は、管理者へ接続先URL、発生時刻、証明書の発行者と有効期限を伝えると調査しやすくなります。

## npmのcaまたはcafileが古い場合

npmの`ca`は、レジストリとのSSL接続で信頼するCA証明書を直接指定する設定です。`cafile`は、1つ以上のCA証明書を含むファイルのパスを指定します。どちらも既定値は`null`です。[npm公式のconfig文書](https://docs.npmjs.com/cli/v11/using-npm/config/#ca)に仕様があります。

過去に社内CAや古い証明書を登録し、その設定だけが残っていると、現在の正しい証明書チェーンを検証できないことがあります。設定が不要になったことを確認できた場合は削除します。

```bash
npm config delete ca
npm config delete cafile
```

削除後に値を確認し、もう一度インストールします。

```bash
npm config get ca
npm config get cafile
npm install
```

社内プロキシへの接続に独自CAが必要な環境では、設定を単に削除すると別の証明書エラーへ変わります。その場合は、管理者から現在有効なCA証明書を受け取り、`cafile`の参照先を更新してください。

```bash
npm config set cafile /path/to/current-corporate-ca.pem
```

PowerShellではWindows上の実際のパスを指定します。

```powershell
npm config set cafile "C:\certs\current-corporate-ca.pem"
```

証明書ファイルは、信頼できる管理者や組織の配布経路から取得してください。エラーを消すために、出所を確認できない証明書を信頼対象へ追加してはいけません。

## 古いNode.jsの内蔵CAを更新する

Node.jsは、利用する設定によってNode.jsに同梱されたCAストアを使います。このストアはMozillaのCAストアをNode.jsのリリース時点で固定したスナップショットです。そのため、古いNode.jsではCAの追加や更新が反映されていない可能性があります。

まず`node -v`で版を確認し、サポートが終了した古い版なら、公式の[Node.jsリリース情報](https://nodejs.org/en/about/previous-releases)を確認してサポート中のLTS版へ更新します。更新後は、新しいシェルで次を確認してからnpmを再実行してください。

```bash
node -v
npm -v
npm install
```

ただし、Node.jsを更新すれば必ず直るわけではありません。npmの`ca`や`cafile`でCAを明示している場合や、接続先が本当に期限切れの証明書を提示している場合は、それぞれの設定や証明書を修正する必要があります。

## 社内CAはNODE_EXTRA_CA_CERTSで追加できる

既定の信頼済みCAを残したまま社内CAを追加する場合は、Node.jsの`NODE_EXTRA_CA_CERTS`を利用できます。指定するファイルには、PEM形式の信頼済み証明書を1つ以上含めます。

macOSやLinuxでは、npmを起動する前に設定します。

```bash
export NODE_EXTRA_CA_CERTS=/path/to/current-corporate-ca.pem
npm install
```

PowerShellでは次のように設定します。

```powershell
$env:NODE_EXTRA_CA_CERTS = "C:\certs\current-corporate-ca.pem"
npm install
```

この環境変数は、Node.jsプロセスの起動時にだけ読み込まれます。実行中のNode.jsで値を変更しても、そのプロセスには反映されません。[Node.js公式のコマンドライン文書](https://nodejs.org/api/cli.html#node_extra_ca_certsfile)にも明記されています。

また、TLSクライアント側で`ca`が明示されている場合、Node.jsの既定CAと`NODE_EXTRA_CA_CERTS`の追加CAは使われません。npmの`ca`や`cafile`に値がある場合は、環境変数を追加するだけで解決するとは限らないため、設定を併せて確認してください。

## strict-ssl=falseを使わない

次の設定は、証明書エラーを見えなくするだけで、安全な対処ではありません。

```bash
npm config set strict-ssl false
```

npmの`strict-ssl`は、HTTPSでレジストリへアクセスするときにSSL鍵の検証を行うかを決める設定です。`false`にすると、通信相手の正当性を証明書で確認できなくなり、改ざんされたパッケージや認証情報の窃取を防げないおそれがあります。

すでに無効にしていた場合は、原因となった証明書やCA設定を修正したうえで元に戻します。

```bash
npm config set strict-ssl true
npm config get strict-ssl
```

同様に、`NODE_TLS_REJECT_UNAUTHORIZED=0`もTLS証明書の検証を無効にするため、回避策として使わないでください。

## 設定の出所を確認する

npmの設定は、コマンドライン、環境変数、複数の`.npmrc`などから読み込まれます。`npm config get`で想定外の値が出た場合は、どの設定ファイルが使われているか確認してください。

```bash
npm config get userconfig
npm config get globalconfig
```

プロジェクト直下の`.npmrc`、利用者用の`.npmrc`、グローバル設定に`ca`、`cafile`、`registry`、`strict-ssl`が残っていないかを調べます。CIでは、ジョブ内の環境変数や生成された`.npmrc`も確認してください。

設定を削除または変更すると、同じ設定を使う他のプロジェクトにも影響する場合があります。共有環境では、変更前の値と設定ファイルを記録してから作業します。

## 近い証明書エラーとの違い

`SELF_SIGNED_CERT_IN_CHAIN`は、証明書チェーンに自己署名証明書があり、信頼できない場合に出ます。`UNABLE_TO_GET_ISSUER_CERT_LOCALLY`は、発行元証明書をローカルで取得できず、チェーンを検証できない状態です。

`CERT_NOT_YET_VALID`は、証明書の有効期間がまだ始まっていない場合のエラーです。`CERT_HAS_EXPIRED`は、有効期間がすでに終了した場合に対応します。

`ECONNRESET`は通信中に接続が切断された状態、`EAI_AGAIN`は一時的な名前解決失敗です。どちらもTLS証明書の有効期限とは調べる場所が異なります。

## 解決手順のまとめ

最初にエラー付近のURLと`npm config get registry`を確認し、どのレジストリ、ミラー、プロキシへ接続しているかを特定します。接続先が提示する証明書の期限が切れていれば、サーバーまたはプロキシ側で更新してください。

次に`npm config get ca`と`npm config get cafile`を調べます。不要な古い設定なら削除し、社内CAが必要なら信頼できる配布元から新しい証明書を取得して差し替えます。

Node.jsが古い場合はサポート中の版へ更新します。既定CAへ社内CAを追加するときは`NODE_EXTRA_CA_CERTS`をNode.jsの起動前に設定してください。

証明書検証を無効にする`strict-ssl=false`や`NODE_TLS_REJECT_UNAUTHORIZED=0`は使わず、期限切れの証明書または古いCA設定を修正することが重要です。

免責事項：本記事の内容は一般的なnpm、Node.js、HTTPSプロキシ環境を前提としています。本番環境や共有CIで証明書とnpm設定を変更する前に、現在の設定を保存し、証明書の入手元、適用範囲、他のプロジェクトへの影響を確認してください。
