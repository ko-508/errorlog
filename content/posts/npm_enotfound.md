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

`npm install`や`npm ci`で`ENOTFOUND`が出た場合、通信に必要なホスト名をIPアドレスへ変換できていません。最初に見るのは、ログの`getaddrinfo ENOTFOUND`の直後にあるホスト名です。

```text
npm error code ENOTFOUND
npm error network request to https://registry.npmjs.org/express failed, reason: getaddrinfo ENOTFOUND registry.npmjs.org
```

この例なら`registry.npmjs.org`を調べます。社内の取得先やプロキシの名前が表示されているなら、そのホストの設定と名前解決を確認してください。取得先のURLだけを見て、npmの公開サーバーに障害があると判断するのは早い段階です。

同じ実行環境で名前解決を確認し、失敗するホストに対応する設定を直します。社内の取得先を使うプロジェクトでは、公開の取得先や外部のDNSへ一律に変更しないでください。

## ENOTFOUNDが示す失敗

DNSは、ホスト名からIPアドレスを調べる仕組みです。ただし、ログにある`getaddrinfo`はOSの名前解決処理を指し、DNSへの問い合わせだけを行うとは限りません。Node.jsの`dns.lookup()`はこのOSの仕組みを使います。

[Node.jsの公式文書](https://nodejs.org/api/dns.html#dnslookuphostname-options-callback)は、`ENOTFOUND`がホスト名の不存在だけでなく、ファイル記述子の不足など、ほかの理由で名前解決に失敗した場合にも出ると説明しています。したがって、この符号だけで「DNSサーバーに届き、その名前は存在しないと回答された」とは断定できません。

npmの表示はバージョンによって`npm error`や`npm ERR!`などが異なります。共通して確認するのは`ENOTFOUND`と、解決できなかったホスト名です。

[npmのエラー表示の実装](https://github.com/npm/cli/blob/latest/lib/utils/error-message.js)では、`ENOTFOUND`は`ECONNRESET`や`ETIMEDOUT`などと同じ分岐で、ネットワークやプロキシを確認する案内を出しています。その案内が表示されたからといって、プロキシが原因だと決まるわけではありません。

## ログのホスト名を同じ環境で確認する

ログの取得先URLと、`getaddrinfo ENOTFOUND`の後ろにある名前を分けて読みます。

```text
request to https://registry.npmjs.org/leftpad failed, reason: getaddrinfo ENOTFOUND invalid
```

この例で解決できていないのは`registry.npmjs.org`ではなく`invalid`です。[npm/cliのIssue #6835](https://github.com/npm/cli/issues/6835)には、npm 9.8.1で`HTTPS_PROXY=http://invalid`を指定した際のこのログが記録されています。プロキシの名前解決が失敗しても、要求先のURLにはnpmの取得先が表示されます。この報告は特定バージョンの比較なので、すべてのnpmで同じ挙動になる証拠としては扱いません。

まず、失敗した環境で次を実行します。最後の引数は、ログに表示された実際のホスト名に置き換えてください。URL全体ではなく、ホスト名だけを渡します。

```bash
node -e "require('node:dns').lookup(process.argv[1], {all:true}, (e,a)=>{if(e){console.error(e.code,e.message);process.exitCode=1}else{console.log(a)}})" registry.npmjs.org
```

成功した場合はアドレスの一覧、失敗した場合は符号と説明文が出ます。実際の値は環境によって異なります。

補助的な確認には次も使えます。

```bash
nslookup registry.npmjs.org
```

`nslookup`とNode.jsのOS経由の名前解決は、同じ結果になるとは限りません。片方だけ成功する場合は、その違いも調査材料になります。Docker内で失敗しているならコンテナ内、CIで失敗しているなら該当ジョブで確認してください。

## registryとスコープ別の設定を直す

registryは、npmがパッケージを取得するサーバーの設定です。現在の設定を確認します。

```bash
npm config get registry
```

`@myorg/package`のように組織名付きのパッケージで失敗する場合は、スコープ別の設定も確認します。`@myorg`は実際のスコープに置き換えてください。

```bash
npm config get @myorg:registry
```

[npmの.npmrc公式文書](https://docs.npmjs.com/cli/v11/configuring-npm/npmrc/)には、スコープごとに別のregistryを指定する例があります。通常のregistryが正しくても、スコープ別の設定に古い社内ホストが残っていれば、そのパッケージだけ別の取得先を使います。

設定はプロジェクトの`.npmrc`、ユーザーの`.npmrc`、環境変数などから読み込まれます。どのファイルの設定か分からない場合は、次の出力で確認します。共有する際は、社内URLや認証情報を含んでいないか確認してください。

```bash
npm config list
```

公開のnpm registryを使うことが正しいプロジェクトで、プロジェクト設定に誤りがある場合は次のように修正できます。

```bash
npm config set registry https://registry.npmjs.org/ --location=project
```

ユーザー設定の誤りなら`--location=user`を使います。設定のある場所を確認してから変更してください。スコープ別の設定や取得URLが別に残っている場合は、通常のregistryだけを変更しても解消しません。

社内の取得先を使う予定なら、公開registryへ切り替えるのではなく、管理者が指定する正しいホスト名と接続方法に合わせます。

## プロキシのホスト名と設定元を確認する

プロキシは、外部への通信を中継するサーバーです。ログの末尾がプロキシのホスト名なら、その名前の入力ミス、古い設定、社内ネットワークへの未接続を確認します。

```bash
npm config get proxy
npm config get https-proxy
```

[npmの設定文書](https://docs.npmjs.com/cli/v11/using-npm/config/#https-proxy)には、`HTTPS_PROXY`、`https_proxy`、`HTTP_PROXY`、`http_proxy`の環境変数も記載されています。npmの設定が`null`でも、環境変数による指定がないとは限りません。

値を表示せず、設定されている変数名だけを確認する場合は次を使えます。

```bash
node -e "for(const k of Object.keys(process.env)){if(/^(https?_proxy|no_proxy|npm_config_(proxy|https_proxy|registry))$/i.test(k))console.log(k)}"
```

不要なプロキシがユーザー設定に残っていると確認できた場合は、次で削除します。

```bash
npm config delete proxy --location=user
npm config delete https-proxy --location=user
```

プロジェクト設定なら`--location=project`に変更します。環境変数による指定は、`npm config delete`では消えません。ターミナルの起動設定、CIの変数、コンテナの設定など、実際に定義している場所で修正してください。

プロキシが必要な環境では削除せず、管理者が指定するURLへ直します。認証情報を含むURLを、そのままログや公開の相談先へ貼り付けないでください。

## VPNとDockerの名前解決を確認する

社内の取得先やプロキシは、社内DNSでのみ名前を解決できる構成があります。その場合はVPNへの接続と、指定されたDNSが使われているかを確認します。外部のDNSへ変更しても、社内の名前を解決できるとは限りません。

Dockerでは、ホストで成功するか、コンテナで成功するかを分けて調べます。ホストでのみ成功する場合は、コンテナが使うDNSとネットワークを確認します。

[Docker公式文書](https://docs.docker.com/engine/network/#dns-services)によると、既定のbridgeネットワークではホストの`/etc/resolv.conf`をもとにDNS設定を受け取り、カスタムネットワークでは組み込みDNSを使います。コンテナのDNSを指定する`--dns`も用意されています。

Linuxコンテナでは、設定確認の一例として次を使えます。`container_name`は対象の名前に置き換えてください。

```bash
docker exec container_name cat /etc/resolv.conf
```

そのうえで、コンテナ内から対象ホストを解決できるか確認します。使用するイメージにNode.jsが入っていれば、前述の`dns.lookup()`による確認が使えます。

DNSの指定を直す場合は、社内ホストも解決でき、コンテナから到達できるDNSを選びます。`8.8.8.8`などの公開DNSを一律に指定する方法を、このエラー全般の解決策にはしません。

## 似ているエラーと対処の違い

| エラー | 示している失敗と確認箇所 |
|---|---|
| `ENOTFOUND` | 名前解決が失敗。対象ホスト、設定、実行環境を確認 |
| `EAI_AGAIN` | 名前解決の一時的な失敗。接続状態や再発の有無を確認 |
| `ECONNRESET` | 通信がリセットされた。途中の接続や中継機器を確認 |
| `ETIMEDOUT` | 処理が時間内に完了しなかった。失敗箇所をログで確認 |
| `CERT_HAS_EXPIRED` | 証明書の期限に関する失敗。対象証明書を確認 |

`ENOTFOUND`と`EAI_AGAIN`は、どちらも名前解決の調査が必要です。ただし、`ENOTFOUND`でも環境の一時的な不調で起きる可能性があるため、「再試行で絶対に直らない」とは言えません。繰り返し同じ名前で失敗する場合は、その名前を指定した設定と、その環境での解決結果を確認します。

一時的な名前解決の失敗は[EAI_AGAINの記事](/posts/npm_eai_again/)、通信のリセットは[ECONNRESETの記事](/posts/npm_econnreset/)も参照してください。

## 解決手順のまとめ

最初に`getaddrinfo ENOTFOUND`の直後のホスト名を確認します。取得先のURLと異なる名前なら、プロキシなど中継先の設定を調べます。

次に、失敗した処理と同じ環境でNode.jsの名前解決を確認します。取得先の指定に誤りがあればregistryやスコープ別設定を直し、社内ホストならVPNと社内DNS、コンテナ内だけの失敗ならDockerの設定を確認してください。

修正後は、失敗した`npm install`や`npm ci`を同じ条件で再実行します。名前解決の失敗に対して、先にlockfileを削除したり、証明書検証を無効にしたりする必要はありません。

免責事項：本記事の内容は一般的なnpmおよびNode.jsの構成を前提としています。取得先、プロキシ、DNSを変更する前に、組織のネットワーク方針と設定元を確認してください。認証情報を含む設定やログを公開しないでください。