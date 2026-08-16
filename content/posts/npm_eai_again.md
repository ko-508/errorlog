---
title: "npm の EAI_AGAIN エラー：原因と解決策"
date: 2026-08-08
description: "EAI_AGAIN は名前解決が一時的に失敗したという意味で、npm には専用の説明が用意されていないため、レジストリへの到達確認と名前を引く側の設定から切り分けます。"
tags: ["npm"]
images: ["og/posts/npm_eai_again.png"]
errorCode: "EAI_AGAIN"
error_name: "getaddrinfo EAI_AGAIN registry.npmjs.org"
error_aliases:
  - "npm error code EAI_AGAIN"
  - "npm ERR! code EAI_AGAIN"
  - "npm error syscall getaddrinfo"
  - "getaddrinfo EAI_AGAIN"
lastmod: 2026-08-08
service: "npm"
error_type: "EAI_AGAIN"
components: ["npm CLI", "Node.js"]
related_services: ["Docker", "GitHub Actions"]
error_cases:
  - id: "container-dns-unreachable"
    situation: "コンテナの中でのみ失敗し、同じ設定のホスト側では成功する"
    messages:
      - "npm error code EAI_AGAIN"
      - "npm error syscall getaddrinfo"
      - "request to <url> failed, reason: getaddrinfo EAI_AGAIN registry.npmjs.org"
    cause: "コンテナから名前を引く先へ届いていない可能性がある"
    check: "同じコンテナの中で cat /etc/resolv.conf を実行し、記載されている宛先へ疎通があるかを確認する"
    fix: "コンテナに届く名前解決の宛先を指定し直す"
  - id: "proxy-resolves-locally"
    situation: "社内の回線でのみ失敗し、中継設定は入っているのに失敗する"
    messages:
      - "npm error code EAI_AGAIN"
      - "npm error syscall getaddrinfo"
    cause: "中継先を経由せず自分で名前を引こうとしている可能性がある"
    check: "npm config get proxy と npm config get https-proxy の値を確認し、失敗しているのが中継先の名前か接続先の名前かをエラー文の末尾で見分ける"
    fix: "中継設定を npm へ揃え、除外一覧に接続先が入っていないかを確認する"
  - id: "transient-resolver-failure"
    situation: "同じコマンドを時間をおいて実行すると成功することがある"
    messages:
      - "npm error code EAI_AGAIN"
      - "request to <url> failed, reason: getaddrinfo EAI_AGAIN registry.npmjs.org"
    cause: "名前を引く先が一時的に応答していない可能性がある"
    check: "npm ping を数回実行し、成功と失敗が混ざるかどうかを見る"
    fix: "名前解決の宛先を安定した別の宛先へ変えるか、経路の復旧を待って実行し直す"
  - id: "custom-registry-host"
    situation: "社内のレジストリを指定したときだけ失敗し、公開レジストリでは成功する"
    messages:
      - "npm error code EAI_AGAIN"
      - "request to <url> failed, reason: getaddrinfo EAI_AGAIN <host>"
    cause: "指定した向き先の名前が、その回線からは引けない可能性がある"
    check: "npm config get registry で向き先を確認し、エラー文の末尾に出ている名前と一致するかを見る"
    fix: "その名前を引ける回線から実行するか、向き先の指定を見直す"
trend_incident: false
---

## 結論

`npm error code EAI_AGAIN` は、名前を引く処理が一時的に失敗したという意味です。`syscall` の行には `getaddrinfo` が入ります。宛先の[サーバー](/glossary/サーバー/)へ接続する前の段階で止まっており、[レジストリ](/glossary/レジストリ/)の応答内容は関係ありません。

注意すべき点があります。npm はこの[コード](/glossary/コード/)に専用の説明を持っていません。実装の[コード](/glossary/コード/)ごとの分岐には `ENOTFOUND` や `EAI_FAIL` はありますが、`EAI_AGAIN` は含まれておらず既定の扱いになります。したがって、`ECONNRESET` のときに出る「中継設定を確認してください」という案内も表示されません。表示されるのは、失敗した要求の内容を示す1文だけです。

切り分けの材料は[エラー](/glossary/エラー/)文の末尾にあります。`getaddrinfo EAI_AGAIN` の後ろに、引こうとした名前が入ります。ここが[レジストリ](/glossary/レジストリ/)の名前なのか、中継先の名前なのかで、疑う場所が変わります。

## 最初に確認すること

まず、失敗している名前を特定します。

```bash
npm install 2>&1 | grep -o "EAI_AGAIN [^ ]*"
```

次に、[レジストリ](/glossary/レジストリ/)へ届くかを npm 自身の手段で確かめます。

```bash
npm ping
```

この[コマンド](/glossary/コマンド/)は現在の向き先へ疎通を試み、往復にかかった時間を表示します。ここで同じ[コード](/glossary/コード/)が返れば、原因は取得処理ではなく経路にあります。成功したり失敗したりする場合は、一時的な不調です。

名前を引く側の設定も確認してください。

```bash
cat /etc/resolv.conf
npm config get registry
npm config get proxy
```

## 原因別の確認方法と解決策

### 原因1：コンテナから名前を引く先へ届いていない {#container-dns-unreachable}

[コンテナ](/glossary/コンテナ/)の中でのみ失敗する場合です。実行環境が参照している宛先が、その[コンテナ](/glossary/コンテナ/)からは到達できません。

確認方法は、[コンテナ](/glossary/コンテナ/)の内側から見ることです。

```bash
docker compose exec app sh -c 'cat /etc/resolv.conf'
```

記載されている宛先が、[コンテナ](/glossary/コンテナ/)の外側でしか使えないものになっていることがあります。その場合、外側では成功して内側でだけ失敗します。

対処は、届く宛先を指定し直すことです。

```yaml
services:
  app:
    dns:
      - 1.1.1.1
```

組織の[ネットワーク](/glossary/ネットワーク/)では、内部の宛先を指定する必要がある場合があります。管理者の指定に従ってください。

### 原因2：中継先を経由せず自分で名前を引いている {#proxy-resolves-locally}

社内の[回線](/glossary/回線/)で、中継の設定は入っているのに失敗する場合です。[エラー](/glossary/エラー/)文の末尾に出ている名前が、中継先ではなく接続先になっていれば、中継を経由していません。

確認方法は[設定値](/glossary/設定値/)と失敗名の突き合わせです。

```bash
npm config get proxy
npm config get https-proxy
npm config get noproxy
```

除外の一覧に接続先が含まれていると、その宛先だけ中継を通しません。結果として自分で名前を引こうとして失敗します。

対処は、設定を揃えたうえで除外の一覧を見直すことです。環境変数側にだけ値が入っている場合も同じ結果になるため、両方を確認してください。

### 原因3：名前を引く先が一時的に応答していない {#transient-resolver-failure}

時間をおくと成功する場合です。この[コード](/glossary/コード/)は名称のとおり、再試行すれば通る可能性がある種類の失敗を表します。

確認方法は繰り返しの実行です。

```bash
npm ping
```

数回実行して成功と失敗が混ざるなら確定です。すべて失敗するなら、一時的ではありません。

対処は、宛先を安定したものへ変えるか、復旧を待つことです。継続的インテグレーションでは、この形の失敗が一定の割合で混ざることがあります。再試行の設定を増やしても、名前を引く段階の失敗は npm の取得の再試行では吸収されないことがあるため、実行そのものをやり直す仕組みのほうが確実です。

### 原因4：指定した向き先の名前が引けない {#custom-registry-host}

社内の[レジストリ](/glossary/レジストリ/)を指定したときだけ失敗する場合です。[エラー](/glossary/エラー/)文の末尾に、その名前が出ます。

確認方法は向き先の照会です。

```bash
npm config get registry
npm config list | grep registry
```

範囲ごとに向き先を変えている場合、そちらの設定も確認してください。対処は、その名前を引ける[回線](/glossary/回線/)から実行することです。社外の[回線](/glossary/回線/)や、接続していない状態では引けません。

向き先の指定そのものが古い場合もあります。組織の案内と突き合わせてください。公開[レジストリ](/glossary/レジストリ/)へ切り替える対処は、社内の方針に反する場合があります。切り替える前に確認してください。

## 近いエラーとの違い

`ENOTFOUND` は、その名前が存在しないという結果です。`EAI_AGAIN` が一時的な失敗を表すのに対し、こちらは確定した結果になります。npm の実装ではこちらだけが[ネットワーク](/glossary/ネットワーク/)系の分岐に含まれており、中継設定の確認を促す説明が表示されます。説明文の有無で見分けられます。

`ECONNRESET` は、名前は引けたが接続が切られた場合です。段階が1つ先に進んでいます。

`ETIMEDOUT` は、接続を試みたが応答が返らなかった場合です。こちらも名前は引けています。

`CERT_HAS_EXPIRED` は接続が成立したあとの検証で止まっています。名前解決とは無関係です。

## 参考資料

- [npm ping](https://docs.npmjs.com/cli/latest/commands/npm-ping)
- [npm config（registry、proxy、noproxy）](https://docs.npmjs.com/cli/latest/using-npm/config)
- [エラー文言の生成（error-message.js）](https://github.com/npm/cli/blob/latest/lib/utils/error-message.js)
- [npm ping の実装（ping.js）](https://github.com/npm/cli/blob/latest/lib/commands/ping.js)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*