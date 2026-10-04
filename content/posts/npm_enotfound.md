---
title: "npm ENOTFOUNDの原因と対処法"
date: 2026-10-01
draft: false
description: "npmのENOTFOUNDは、通信に必要なホスト名をIPアドレスへ変換できなかったときに発生します。ログのホスト名から、取得先・プロキシ・社内DNS・コンテナの設定を切り分ける手順を解説します。"
tags: ["npm"]
images: ["og/posts/npm_enotfound.png"]
errorCode: "ENOTFOUND"
urgency: "medium"
service: "npm"
error_type: "ENOTFOUND"
components: ["npm", "Node.js", "DNS"]
related_services: ["Docker"]
trend_incident: false
---

## 冒頭まとめ

`npm install`や`npm ci`で`ENOTFOUND`が出た場合、[通信](/glossary/通信/)に必要なホスト名を[IPアドレス](/glossary/ipアドレス/)へ変換できていません。最初に見るのは、[ログ](/glossary/ログ/)の`getaddrinfo ENOTFOUND`の直後にあるホスト名です。

```text
npm error code ENOTFOUND
npm error network request to https://registry.npmjs.org/express failed, reason: getaddrinfo ENOTFOUND registry.npmjs.org
```

この例なら`registry.npmjs.org`を調べます。社内の取得先や[プロキシ](/glossary/プロキシ/)の名前が表示されているなら、そのホストの[設定](/glossary/設定/)と名前解決を確認してください。取得先の[URL](/glossary/url/)だけを見て、npmの公開[サーバー](/glossary/サーバー/)に障害があると判断するのは早い段階です。

同じ実行環境で名前解決を確認し、失敗するホストに[対応](/glossary/対応/)する[設定](/glossary/設定/)を直します。社内の取得先を使う[プロジェクト](/glossary/プロジェクト/)では、公開の取得先や外部の[DNS](/glossary/dns/)へ一律に変更しないでください。

## ENOTFOUNDが示す失敗

[DNS](/glossary/dns/)は、ホスト名から[IPアドレス](/glossary/ipアドレス/)を調べる仕組みです。ただし、[ログ](/glossary/ログ/)にある`getaddrinfo`は[OS](/glossary/os/)の名前解決処理を指し、[DNS](/glossary/dns/)への問い合わせだけを行うとは限りません。Node.jsの`dns.lookup()`はこの[OS](/glossary/os/)の仕組みを使います。

[Node.jsの公式文書](https://nodejs.org/api/dns.html#dnslookuphostname-options-callback)は、`ENOTFOUND`がホスト名の不存在だけでなく、[ファイル](/glossary/ファイル/)記述子の不足など、ほかの理由で名前解決に失敗した場合にも出ると説明しています。したがって、この符号だけで「[DNSサーバー](/glossary/dnsサーバー/)に届き、その名前は存在しないと回答された」とは断定できません。

npmの表示は[バージョン](/glossary/バージョン/)によって`npm error`や`npm ERR!`などが異なります。共通して確認するのは`ENOTFOUND`と、解決できなかったホスト名です。

[npmのエラー表示の実装](https://github.com/npm/cli/blob/latest/lib/utils/error-message.js)では、`ENOTFOUND`は`ECONNRESET`や`ETIMEDOUT`などと同じ分岐で、[ネットワーク](/glossary/ネットワーク/)や[プロキシ](/glossary/プロキシ/)を確認する案内を出しています。その案内が表示されたからといって、[プロキシ](/glossary/プロキシ/)が原因だと決まるわけではありません。

## ログのホスト名を同じ環境で確認する

[ログ](/glossary/ログ/)の取得先[URL](/glossary/url/)と、`getaddrinfo ENOTFOUND`の後ろにある名前を分けて読みます。

```text
request to https://registry.npmjs.org/leftpad failed, reason: getaddrinfo ENOTFOUND invalid
```

この例で解決できていないのは`registry.npmjs.org`ではなく`invalid`です。[npm/cliのIssue #6835](https://github.com/npm/cli/issues/6835)には、npm 9.8.1で`HTTPS_PROXY=http://invalid`を指定した際のこの[ログ](/glossary/ログ/)が記録されています。[プロキシ](/glossary/プロキシ/)の名前解決が失敗しても、要求先の[URL](/glossary/url/)にはnpmの取得先が表示されます。この報告は特定[バージョン](/glossary/バージョン/)の比較なので、すべてのnpmで同じ挙動になる証拠としては扱いません。

まず、失敗した[環境](/glossary/環境/)で次を実行します。最後の[引数](/glossary/引数/)は、[ログ](/glossary/ログ/)に表示された実際のホスト名に置き換えてください。[URL](/glossary/url/)全体ではなく、ホスト名だけを渡します。

```bash
node -e "require('node:dns').lookup(process.argv[1], {all:true}, (e,a)=>{if(e){console.error(e.code,e.message);process.exitCode=1}else{console.log(a)}})" registry.npmjs.org
```

成功した場合はアドレスの一覧、失敗した場合は符号と説明文が出ます。実際の値は[環境](/glossary/環境/)によって異なります。

補助的な確認には次も使えます。

```bash
nslookup registry.npmjs.org
```

`nslookup`とNode.jsの[OS](/glossary/os/)経由の名前解決は、同じ結果になるとは限りません。片方だけ成功する場合は、その違いも調査材料になります。[Docker](/glossary/docker/)内で失敗しているなら[コンテナ](/glossary/コンテナ/)内、CIで失敗しているなら該当ジョブで確認してください。

## registryとスコープ別の設定を直す

registryは、npmが[パッケージ](/glossary/パッケージ/)を取得する[サーバー](/glossary/サーバー/)の[設定](/glossary/設定/)です。現在の[設定](/glossary/設定/)を確認します。

```bash
npm config get registry
```

`@myorg/package`のように組織名付きの[パッケージ](/glossary/パッケージ/)で失敗する場合は、[スコープ](/glossary/スコープ/)別の[設定](/glossary/設定/)も確認します。`@myorg`は実際の[スコープ](/glossary/スコープ/)に置き換えてください。

```bash
npm config get @myorg:registry
```

[npmの.npmrc公式文書](https://docs.npmjs.com/cli/v11/configuring-npm/npmrc/)には、[スコープ](/glossary/スコープ/)ごとに別のregistryを指定する例があります。通常のregistryが正しくても、[スコープ](/glossary/スコープ/)別の[設定](/glossary/設定/)に古い社内ホストが残っていれば、その[パッケージ](/glossary/パッケージ/)だけ別の取得先を使います。

[設定](/glossary/設定/)は[プロジェクト](/glossary/プロジェクト/)の`.npmrc`、ユーザーの`.npmrc`、[環境変数](/glossary/環境変数/)などから読み込まれます。どの[ファイル](/glossary/ファイル/)の[設定](/glossary/設定/)か分からない場合は、次の出力で確認します。共有する際は、社内[URL](/glossary/url/)や認証情報を含んでいないか確認してください。

```bash
npm config list
```

公開のnpm registryを使うことが正しい[プロジェクト](/glossary/プロジェクト/)で、[プロジェクト](/glossary/プロジェクト/)[設定](/glossary/設定/)に誤りがある場合は次のように[修正](/glossary/修正/)できます。

```bash
npm config set registry https://registry.npmjs.org/ --location=project
```

ユーザー[設定](/glossary/設定/)の誤りなら`--location=user`を使います。[設定](/glossary/設定/)のある場所を確認してから変更してください。[スコープ](/glossary/スコープ/)別の[設定](/glossary/設定/)や取得[URL](/glossary/url/)が別に残っている場合は、通常のregistryだけを変更しても解消しません。

社内の取得先を使う予定なら、公開registryへ切り替えるのではなく、管理者が指定する正しいホスト名と接続方法に合わせます。

## プロキシのホスト名と設定元を確認する

[プロキシ](/glossary/プロキシ/)は、外部への[通信](/glossary/通信/)を中継する[サーバー](/glossary/サーバー/)です。[ログ](/glossary/ログ/)の末尾が[プロキシ](/glossary/プロキシ/)のホスト名なら、その名前の入力ミス、古い[設定](/glossary/設定/)、社内[ネットワーク](/glossary/ネットワーク/)への未接続を確認します。

```bash
npm config get proxy
npm config get https-proxy
```

[npmの設定文書](https://docs.npmjs.com/cli/v11/using-npm/config/#https-proxy)には、`HTTPS_PROXY`、`https_proxy`、`HTTP_PROXY`、`http_proxy`の[環境変数](/glossary/環境変数/)も記載されています。npmの[設定](/glossary/設定/)が`null`でも、[環境変数](/glossary/環境変数/)による指定がないとは限りません。

値を表示せず、[設定](/glossary/設定/)されている変数名だけを確認する場合は次を使えます。

```bash
node -e "for(const k of Object.keys(process.env)){if(/^(https?_proxy|no_proxy|npm_config_(proxy|https_proxy|registry))$/i.test(k))console.log(k)}"
```

不要な[プロキシ](/glossary/プロキシ/)がユーザー[設定](/glossary/設定/)に残っていると確認できた場合は、次で[削除](/glossary/削除/)します。

```bash
npm config delete proxy --location=user
npm config delete https-proxy --location=user
```

[プロジェクト](/glossary/プロジェクト/)[設定](/glossary/設定/)なら`--location=project`に変更します。[環境変数](/glossary/環境変数/)による指定は、`npm config delete`では消えません。[ターミナル](/glossary/ターミナル/)の起動設定、CIの[変数](/glossary/変数/)、[コンテナ](/glossary/コンテナ/)の[設定](/glossary/設定/)など、実際に定義している場所で[修正](/glossary/修正/)してください。

[プロキシ](/glossary/プロキシ/)が必要な[環境](/glossary/環境/)では[削除](/glossary/削除/)せず、管理者が指定する[URL](/glossary/url/)へ直します。認証情報を含む[URL](/glossary/url/)を、そのまま[ログ](/glossary/ログ/)や公開の相談先へ貼り付けないでください。

## VPNとDockerの名前解決を確認する

社内の取得先や[プロキシ](/glossary/プロキシ/)は、社内[DNS](/glossary/dns/)でのみ名前を解決できる構成があります。その場合はVPNへの接続と、指定された[DNS](/glossary/dns/)が使われているかを確認します。外部の[DNS](/glossary/dns/)へ変更しても、社内の名前を解決できるとは限りません。

[Docker](/glossary/docker/)では、ホストで成功するか、[コンテナ](/glossary/コンテナ/)で成功するかを分けて調べます。ホストでのみ成功する場合は、[コンテナ](/glossary/コンテナ/)が使う[DNS](/glossary/dns/)と[ネットワーク](/glossary/ネットワーク/)を確認します。

[Docker公式文書](https://docs.docker.com/engine/network/#dns-services)によると、既定のbridge[ネットワーク](/glossary/ネットワーク/)ではホストの`/etc/resolv.conf`をもとに[DNS設定](/glossary/dns設定/)を受け取り、カスタムネットワークでは組み込み[DNS](/glossary/dns/)を使います。[コンテナ](/glossary/コンテナ/)の[DNS](/glossary/dns/)を指定する`--dns`も用意されています。

[Linux](/glossary/linux/)[コンテナ](/glossary/コンテナ/)では、設定確認の一例として次を使えます。`container_name`は対象の名前に置き換えてください。

```bash
docker exec container_name cat /etc/resolv.conf
```

そのうえで、[コンテナ](/glossary/コンテナ/)内から対象ホストを解決できるか確認します。使用する[イメージ](/glossary/イメージ/)にNode.jsが入っていれば、前述の`dns.lookup()`による確認が使えます。

[DNS](/glossary/dns/)の指定を直す場合は、社内ホストも解決でき、[コンテナ](/glossary/コンテナ/)から到達できる[DNS](/glossary/dns/)を選びます。`8.8.8.8`などの公開[DNS](/glossary/dns/)を一律に指定する方法を、この[エラー](/glossary/エラー/)全般の解決策にはしません。

## 似ているエラーと対処の違い

| [エラー](/glossary/エラー/) | 示している失敗と確認箇所 |
|---|---|
| `ENOTFOUND` | 名前解決が失敗。対象ホスト、[設定](/glossary/設定/)、実行環境を確認 |
| `EAI_AGAIN` | 名前解決の一時的な失敗。接続状態や再発の有無を確認 |
| `ECONNRESET` | [通信](/glossary/通信/)が[リセット](/glossary/リセット/)された。途中の接続や中継機器を確認 |
| `ETIMEDOUT` | 処理が時間内に完了しなかった。失敗箇所を[ログ](/glossary/ログ/)で確認 |
| `CERT_HAS_EXPIRED` | [証明書](/glossary/証明書/)の期限に関する失敗。対象証明書を確認 |

`ENOTFOUND`と`EAI_AGAIN`は、どちらも名前解決の調査が必要です。ただし、`ENOTFOUND`でも[環境](/glossary/環境/)の一時的な不調で起きる可能性があるため、「再試行で絶対に直らない」とは言えません。繰り返し同じ名前で失敗する場合は、その名前を指定した[設定](/glossary/設定/)と、その[環境](/glossary/環境/)での解決結果を確認します。

一時的な名前解決の失敗は[EAI_AGAINの記事](/posts/npm_eai_again/)、[通信](/glossary/通信/)の[リセット](/glossary/リセット/)は[ECONNRESETの記事](/posts/npm_econnreset/)も参照してください。

## 解決手順のまとめ

最初に`getaddrinfo ENOTFOUND`の直後のホスト名を確認します。取得先の[URL](/glossary/url/)と異なる名前なら、[プロキシ](/glossary/プロキシ/)など中継先の[設定](/glossary/設定/)を調べます。

次に、失敗した処理と同じ[環境](/glossary/環境/)でNode.jsの名前解決を確認します。取得先の指定に誤りがあればregistryや[スコープ](/glossary/スコープ/)別設定を直し、社内ホストならVPNと社内[DNS](/glossary/dns/)、[コンテナ](/glossary/コンテナ/)内だけの失敗なら[Docker](/glossary/docker/)の[設定](/glossary/設定/)を確認してください。

修正後は、失敗した`npm install`や`npm ci`を同じ条件で再実行します。名前解決の失敗に対して、先にlockfileを[削除](/glossary/削除/)したり、証明書検証を無効にしたりする必要はありません。

免責事項：本記事の内容は一般的なnpmおよびNode.jsの構成を前提としています。取得先、[プロキシ](/glossary/プロキシ/)、[DNS](/glossary/dns/)を変更する前に、組織の[ネットワーク](/glossary/ネットワーク/)方針と設定元を確認してください。認証情報を含む[設定](/glossary/設定/)や[ログ](/glossary/ログ/)を公開しないでください。