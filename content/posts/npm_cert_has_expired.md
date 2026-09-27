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

`npm install`などで次の[エラー](/glossary/エラー/)が出る場合、npmが[HTTPS](/glossary/https/)[通信](/glossary/通信/)で検証した[証明書](/glossary/証明書/)の有効期限が切れています。

```text
npm error code CERT_HAS_EXPIRED
npm error errno CERT_HAS_EXPIRED
```

最初に接続先[URL](/glossary/url/)とnpm[レジストリ](/glossary/レジストリ/)を確認してください。公式[レジストリ](/glossary/レジストリ/)ではなく、社内[レジストリ](/glossary/レジストリ/)、ミラー、[プロキシ](/glossary/プロキシ/)を経由している場合は、その途中で提示された[証明書](/glossary/証明書/)が原因になることもあります。

次にnpmの`ca`と`cafile`、Node.jsの[バージョン](/glossary/バージョン/)を確認します。古いCA[証明書](/glossary/証明書/)が明示的に[設定](/glossary/設定/)されている場合は[設定](/glossary/設定/)を更新し、Node.jsが古い場合はサポート中の版へ更新します。[証明書](/glossary/証明書/)の検証を無効にする`strict-ssl=false`は、安全な解決方法ではありません。

## CERT_HAS_EXPIREDの意味

`CERT_HAS_EXPIRED`は、Node.jsの[TLS](/glossary/tls/)処理が返すX.509[証明書](/glossary/証明書/)[エラー](/glossary/エラー/)です。Node.js公式文書では「[証明書](/glossary/証明書/)の有効期限が切れている」状態として定義されています。

npmは[パッケージ](/glossary/パッケージ/)や[メタデータ](/glossary/メタデータ/)を[HTTPS](/glossary/https/)で取得するとき、接続先から提示された[証明書](/glossary/証明書/)をNode.jsで検証します。[証明書](/glossary/証明書/)チェーンの検証対象に期限切れの[証明書](/glossary/証明書/)が含まれていると、npmは[通信](/glossary/通信/)を中止し、この[コード](/glossary/コード/)を表示します。

[エラー](/glossary/エラー/)は[パッケージ](/glossary/パッケージ/)の依存関係や`package-lock.json`の内容そのものを示すものではありません。[DNS](/glossary/dns/)解決とTCP接続の後に行われる[TLS](/glossary/tls/)[証明書](/glossary/証明書/)の検証で失敗しています。[Node.js公式のTLSエラーコード一覧](https://nodejs.org/api/tls.html#x509-certificate-error-codes)で定義を確認できます。

## 最初に接続先と設定を確認する

[エラー](/glossary/エラー/)の前後に表示された[URL](/glossary/url/)を確認します。npmが使用する既定[レジストリ](/glossary/レジストリ/)も調べてください。

```bash
npm config get registry
```

`https://registry.npmjs.org/`以外が表示された場合は、社内[レジストリ](/glossary/レジストリ/)やミラーの[証明書](/glossary/証明書/)を確認します。ただし、[レジストリ](/glossary/レジストリ/)が公式[URL](/glossary/url/)でも、[HTTPS](/glossary/https/)[プロキシ](/glossary/プロキシ/)が[通信](/glossary/通信/)を中継していれば、実際に検証している[証明書](/glossary/証明書/)は[プロキシ](/glossary/プロキシ/)が発行したものかもしれません。

続いて、Node.jsの[バージョン](/glossary/バージョン/)とnpmの証明書設定を確認します。

```bash
node -v
npm config get ca
npm config get cafile
npm config get strict-ssl
```

`ca`または`cafile`に値がある場合は、その[設定](/glossary/設定/)が意図したものか、参照先の[証明書](/glossary/証明書/)が現在も有効かを確認します。`strict-ssl`の既定値は`true`です。

[環境変数](/glossary/環境変数/)も確認します。macOSや[Linux](/glossary/linux/)では次を実行します。

```bash
printf '%s\n' "$NODE_EXTRA_CA_CERTS"
```

PowerShellでは次のように確認できます。

```powershell
$env:NODE_EXTRA_CA_CERTS
```

## 接続先やプロキシの証明書が期限切れの場合

社内[レジストリ](/glossary/レジストリ/)、[キャッシュ](/glossary/キャッシュ/)用ミラー、[HTTPS](/glossary/https/)[プロキシ](/glossary/プロキシ/)などの[証明書](/glossary/証明書/)が期限切れなら、[サーバー](/glossary/サーバー/)または[プロキシ](/glossary/プロキシ/)側で[証明書](/glossary/証明書/)を更新する必要があります。利用者側でnpmの検証を無効にしても、期限切れそのものは解消しません。

OpenSSLを利用できる[環境](/glossary/環境/)では、実際の接続先ホストを指定して[証明書](/glossary/証明書/)の有効期間を確認できます。

```bash
openssl s_client -connect example.com:443 -servername example.com < /dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

`notAfter`が有効期限です。ただし、[プロキシ](/glossary/プロキシ/)を経由する[環境](/glossary/環境/)でこの[コマンド](/glossary/コマンド/)がnpmと同じ通信経路を通るとは限りません。[ブラウザ](/glossary/ブラウザ/)、[プロキシ](/glossary/プロキシ/)管理画面、組織の証明書管理手段も併用し、npmが実際に受け取った[証明書](/glossary/証明書/)を確認してください。

公開[レジストリ](/glossary/レジストリ/)側の障害が疑われる場合は、npmの[サービス稼働状況](https://status.npmjs.org/)も確認します。社内[レジストリ](/glossary/レジストリ/)や[プロキシ](/glossary/プロキシ/)の場合は、管理者へ接続先[URL](/glossary/url/)、発生時刻、[証明書](/glossary/証明書/)の発行者と有効期限を伝えると調査しやすくなります。

## npmのcaまたはcafileが古い場合

npmの`ca`は、[レジストリ](/glossary/レジストリ/)との[SSL](/glossary/ssl/)接続で信頼するCA[証明書](/glossary/証明書/)を直接指定する[設定](/glossary/設定/)です。`cafile`は、1つ以上のCA[証明書](/glossary/証明書/)を含む[ファイル](/glossary/ファイル/)の[パス](/glossary/パス/)を指定します。どちらも既定値は`null`です。[npm公式のconfig文書](https://docs.npmjs.com/cli/v11/using-npm/config/#ca)に仕様があります。

過去に社内CAや古い[証明書](/glossary/証明書/)を登録し、その[設定](/glossary/設定/)だけが残っていると、現在の正しい[証明書](/glossary/証明書/)チェーンを検証できないことがあります。[設定](/glossary/設定/)が不要になったことを確認できた場合は[削除](/glossary/削除/)します。

```bash
npm config delete ca
npm config delete cafile
```

削除後に値を確認し、もう一度[インストール](/glossary/インストール/)します。

```bash
npm config get ca
npm config get cafile
npm install
```

社内[プロキシ](/glossary/プロキシ/)への接続に独自CAが必要な[環境](/glossary/環境/)では、[設定](/glossary/設定/)を単に[削除](/glossary/削除/)すると別の[証明書](/glossary/証明書/)[エラー](/glossary/エラー/)へ変わります。その場合は、管理者から現在有効なCA[証明書](/glossary/証明書/)を受け取り、`cafile`の参照先を更新してください。

```bash
npm config set cafile /path/to/current-corporate-ca.pem
```

PowerShellではWindows上の実際の[パス](/glossary/パス/)を指定します。

```powershell
npm config set cafile "C:\certs\current-corporate-ca.pem"
```

[証明書](/glossary/証明書/)[ファイル](/glossary/ファイル/)は、信頼できる管理者や組織の配布経路から取得してください。[エラー](/glossary/エラー/)を消すために、出所を確認できない[証明書](/glossary/証明書/)を信頼対象へ追加してはいけません。

## 古いNode.jsの内蔵CAを更新する

Node.jsは、利用する[設定](/glossary/設定/)によってNode.jsに同梱されたCAストアを使います。このストアはMozillaのCAストアをNode.jsの[リリース](/glossary/リリース/)時点で固定したスナップショットです。そのため、古いNode.jsではCAの追加や更新が反映されていない可能性があります。

まず`node -v`で版を確認し、サポートが終了した古い版なら、公式の[Node.jsリリース情報](https://nodejs.org/en/about/previous-releases)を確認してサポート中のLTS版へ更新します。更新後は、新しい[シェル](/glossary/シェル/)で次を確認してからnpmを再実行してください。

```bash
node -v
npm -v
npm install
```

ただし、Node.jsを更新すれば必ず直るわけではありません。npmの`ca`や`cafile`でCAを明示している場合や、接続先が本当に期限切れの[証明書](/glossary/証明書/)を提示している場合は、それぞれの[設定](/glossary/設定/)や[証明書](/glossary/証明書/)を[修正](/glossary/修正/)する必要があります。

## 社内CAはNODE_EXTRA_CA_CERTSで追加できる

既定の信頼済みCAを残したまま社内CAを追加する場合は、Node.jsの`NODE_EXTRA_CA_CERTS`を利用できます。指定する[ファイル](/glossary/ファイル/)には、PEM形式の信頼済み[証明書](/glossary/証明書/)を1つ以上含めます。

macOSや[Linux](/glossary/linux/)では、npmを起動する前に[設定](/glossary/設定/)します。

```bash
export NODE_EXTRA_CA_CERTS=/path/to/current-corporate-ca.pem
npm install
```

PowerShellでは次のように[設定](/glossary/設定/)します。

```powershell
$env:NODE_EXTRA_CA_CERTS = "C:\certs\current-corporate-ca.pem"
npm install
```

この[環境変数](/glossary/環境変数/)は、Node.js[プロセス](/glossary/プロセス/)の起動時にだけ読み込まれます。実行中のNode.jsで値を変更しても、その[プロセス](/glossary/プロセス/)には反映されません。[Node.js公式のコマンドライン文書](https://nodejs.org/api/cli.html#node_extra_ca_certsfile)にも明記されています。

また、[TLS](/glossary/tls/)[クライアント](/glossary/クライアント/)側で`ca`が明示されている場合、Node.jsの既定CAと`NODE_EXTRA_CA_CERTS`の追加CAは使われません。npmの`ca`や`cafile`に値がある場合は、[環境変数](/glossary/環境変数/)を追加するだけで解決するとは限らないため、[設定](/glossary/設定/)を併せて確認してください。

## strict-ssl=falseを使わない

次の[設定](/glossary/設定/)は、[証明書](/glossary/証明書/)[エラー](/glossary/エラー/)を見えなくするだけで、安全な対処ではありません。

```bash
npm config set strict-ssl false
```

npmの`strict-ssl`は、[HTTPS](/glossary/https/)で[レジストリ](/glossary/レジストリ/)へアクセスするときに[SSL](/glossary/ssl/)鍵の検証を行うかを決める[設定](/glossary/設定/)です。`false`にすると、通信相手の正当性を[証明書](/glossary/証明書/)で確認できなくなり、改ざんされた[パッケージ](/glossary/パッケージ/)や認証情報の窃取を防げないおそれがあります。

すでに無効にしていた場合は、原因となった[証明書](/glossary/証明書/)やCA[設定](/glossary/設定/)を[修正](/glossary/修正/)したうえで元に戻します。

```bash
npm config set strict-ssl true
npm config get strict-ssl
```

同様に、`NODE_TLS_REJECT_UNAUTHORIZED=0`も[TLS](/glossary/tls/)[証明書](/glossary/証明書/)の検証を無効にするため、回避策として使わないでください。

## 設定の出所を確認する

npmの[設定](/glossary/設定/)は、[コマンドライン](/glossary/コマンドライン/)、[環境変数](/glossary/環境変数/)、複数の`.npmrc`などから読み込まれます。`npm config get`で想定外の値が出た場合は、どの[設定ファイル](/glossary/設定ファイル/)が使われているか確認してください。

```bash
npm config get userconfig
npm config get globalconfig
```

[プロジェクト](/glossary/プロジェクト/)直下の`.npmrc`、利用者用の`.npmrc`、グローバル[設定](/glossary/設定/)に`ca`、`cafile`、`registry`、`strict-ssl`が残っていないかを調べます。CIでは、ジョブ内の[環境変数](/glossary/環境変数/)や生成された`.npmrc`も確認してください。

[設定](/glossary/設定/)を[削除](/glossary/削除/)または変更すると、同じ[設定](/glossary/設定/)を使う他の[プロジェクト](/glossary/プロジェクト/)にも影響する場合があります。共有環境では、変更前の値と[設定ファイル](/glossary/設定ファイル/)を記録してから作業します。

## 近い証明書エラーとの違い

`SELF_SIGNED_CERT_IN_CHAIN`は、[証明書](/glossary/証明書/)チェーンに自己署名証明書があり、信頼できない場合に出ます。`UNABLE_TO_GET_ISSUER_CERT_LOCALLY`は、発行元証明書をローカルで取得できず、チェーンを検証できない状態です。

`CERT_NOT_YET_VALID`は、[証明書](/glossary/証明書/)の有効期間がまだ始まっていない場合の[エラー](/glossary/エラー/)です。`CERT_HAS_EXPIRED`は、有効期間がすでに終了した場合に対応します。

`ECONNRESET`は通信中に接続が切断された状態、`EAI_AGAIN`は一時的な名前解決失敗です。どちらも[TLS](/glossary/tls/)[証明書](/glossary/証明書/)の有効期限とは調べる場所が異なります。

## 解決手順のまとめ

最初に[エラー](/glossary/エラー/)付近の[URL](/glossary/url/)と`npm config get registry`を確認し、どの[レジストリ](/glossary/レジストリ/)、ミラー、[プロキシ](/glossary/プロキシ/)へ接続しているかを特定します。接続先が提示する[証明書](/glossary/証明書/)の期限が切れていれば、[サーバー](/glossary/サーバー/)または[プロキシ](/glossary/プロキシ/)側で更新してください。

次に`npm config get ca`と`npm config get cafile`を調べます。不要な古い[設定](/glossary/設定/)なら[削除](/glossary/削除/)し、社内CAが必要なら信頼できる配布元から新しい[証明書](/glossary/証明書/)を取得して差し替えます。

Node.jsが古い場合はサポート中の版へ更新します。既定CAへ社内CAを追加するときは`NODE_EXTRA_CA_CERTS`をNode.jsの起動前に[設定](/glossary/設定/)してください。

証明書検証を無効にする`strict-ssl=false`や`NODE_TLS_REJECT_UNAUTHORIZED=0`は使わず、期限切れの[証明書](/glossary/証明書/)または古いCA[設定](/glossary/設定/)を[修正](/glossary/修正/)することが重要です。

免責事項：本記事の内容は一般的なnpm、Node.js、[HTTPS](/glossary/https/)[プロキシ](/glossary/プロキシ/)[環境](/glossary/環境/)を前提としています。[本番環境](/glossary/本番環境/)や共有CIで[証明書](/glossary/証明書/)とnpm[設定](/glossary/設定/)を変更する前に、現在の[設定](/glossary/設定/)を[保存](/glossary/保存/)し、[証明書](/glossary/証明書/)の入手元、適用範囲、他の[プロジェクト](/glossary/プロジェクト/)への影響を確認してください。
