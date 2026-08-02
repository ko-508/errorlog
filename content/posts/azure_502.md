---
title: "Azure の 502 エラー：原因と解決策"
date: 2026-07-29
description: "Azure の 502 は、Application Gateway が背後へ到達できなかったことを示す場合がほとんどです。公式文書は原因を6つ挙げており、その多くは正常性の判定が通っていないことに帰着します。v1 では応答が既定の20秒以内に返らない場合も 502 になる、と明記されています。判断の起点は背後の正常性の状態です。"
tags: ["Azure"]
errorCode: "502"
lastmod: 2026-07-29
service: "Azure"
error_type: "502"
components: ["Application Gateway", "Backend Pool"]
related_services: ["Application Gateway", "Azure Front Door", "App Service"]
trend_incident: false
---

## 冒頭まとめ

Azure で 502 Bad Gateway を受け取る場面は、Application Gateway を前段に置いた構成に集中します。表示される文言も定型で、要求を取り次いだ側が背後から正しい応答を得られなかった、という趣旨のものです。

公式のトラブルシューティング文書は、この[エラー](/glossary/エラー/)の原因を明確に列挙しています。[ネットワーク](/glossary/ネットワーク/)の遮断規則・利用者定義の経路・独自の名前解決による遮断、既定の正常性確認が背後に届かないこと、独自の正常性確認の設定不備、背後の一覧が未設定または空であること、一覧の中に正常な相手が1つも無いこと、要求の時間切れや接続の問題、そして背後の[証明書](/glossary/証明書/)が一致しないことです。

並べてみると、多くが1点に帰着します。背後が正常だと判定されていない、ということです。同じ文書には、一覧内のすべてが正常でないと判定された場合、要求は転送されず 502 が返る、と明記されています。したがって調査の起点は、設定[ファイル](/glossary/ファイル/)ではなく背後の正常性の状態です。

もう1つ、時間に関する記述があります。要求を受け取った Application Gateway は、背後からの応答を一定時間待ちます。既定は20秒です。そして「v1 では、この時間内に応答が返らないと利用者は 502 を受け取る」と、版を明示したうえで書かれています。版を明示しているということは、別の版では同じ状況が同じ結果にならない可能性がある、ということです。自分の[環境](/glossary/環境/)がどちらの版かを先に確認してください。

## エラーの概要

利用者側には定型の文言が表示されます。応答が無効だった、という趣旨のものです。

```text
Server Error: 502 - Web server received an invalid response
while acting as a gateway or proxy server.
```

判断の材料は、この画面ではなく背後の正常性の状態です。公式文書には、一覧内のすべてが正常でないと判定された場合に 502 が返ることと、詳細を示す欄に表示される内容から調査を始めるべきことが書かれています。

正常性の確認の既定の挙動も定義されています。確認の要求は `<プロトコル>://127.0.0.1:<番号>` の形で送られ、番号と[プロトコル](/glossary/プロトコル/)は設定から引き継がれます。そして、正常と見なされる応答は 200 から 399 までの状態[コード](/glossary/コード/)だけです。この範囲外を返す[パス](/glossary/パス/)を確認先にしていると、背後が正しく動いていても正常でないと判定されます。

## まず最初に：背後の正常性を見る

第一に、背後の正常性の状態を確認します。すべてが正常でないと判定されていれば、原因はそこにあります。[アプリケーション](/glossary/アプリケーション/)の中身を調べる前に、判定が通るようにしてください。

第二に、詳細を示す欄の内容を読みます。公式文書には、接続を確立できない場合の文言として、確認に使う番号で背後が応答しているかを確かめること、そして遮断の設定が邪魔していないかを確かめることが挙げられています。

第三に、正常と判定されているのに 502 が出る場合を分けて考えます。この場合、判定は通っているので、疑うのは実際の[通信](/glossary/通信/)の側です。[証明書](/glossary/証明書/)の不一致や、名前の扱いの食い違いが候補になります。

## よくある原因と解決手順

### 原因1：遮断の設定で、確認の通信が届いていない

公式文書が最初に挙げている原因です。[ネットワーク](/glossary/ネットワーク/)の遮断規則、利用者定義の経路、独自の名前解決のいずれかが、Application Gateway から背後への到達を妨げていると、正常性の確認が失敗し、結果として 502 になります。

同じ文書には、これらの設定が Application Gateway 側の区画にある場合と、背後の機器がある区画にある場合の両方がありうる、と書かれています。片方だけを見て安心しないでください。

さらに、管理用の[通信](/glossary/通信/)に必要な範囲も決まっています。公式の正常性に関する文書によれば、v1 では 65503 から 65534、v2 では 65200 から 65535 への[受信](/glossary/受信/)を許可しておく必要があります。この範囲を塞ぐと、背後の設定が正しくても機能しません。

```bash
# 区画に紐づく規則を確認する
az network vnet subnet show --resource-group my-rg --vnet-name my-vnet \
  --name my-appgw-subnet --query "{nsg:networkSecurityGroup.id, rt:routeTable.id}"
```

### 原因2：正常性の確認の設定が実態と合っていない

確認先の[パス](/glossary/パス/)が、200 から 399 の範囲を返さない場合です。[認証](/glossary/認証/)が必要な[パス](/glossary/パス/)を指定していて、実際には 401 や 403 が返っている、という形が典型です。背後は正しく動いているのに、判定だけが失敗します。

**Before（保護された[パス](/glossary/パス/)を確認先にしている）：**

```bash
az network application-gateway probe show \
  --gateway-name my-gateway --resource-group my-rg --name my-probe \
  --query "{path:path, protocol:protocol, statusCodes:match.statusCodes}"
```

**After（[認証](/glossary/認証/)の要らない専用の[パス](/glossary/パス/)を用意する）：**

```bash
az network application-gateway probe update \
  --gateway-name my-gateway --resource-group my-rg --name my-probe \
  --path /healthz
```

公式文書には、間隔・待ち時間・異常と判定するまでの回数が、許容される範囲に収まっていることを確認するようにとも書かれています。極端な値を入れていないかを見てください。

[暗号化](/glossary/暗号化/)した確認を使う場合の注意も記載があります。背後が名前の指定を必須としている場合は、背後側に代替の[証明書](/glossary/証明書/)を設定して、必須でなくする必要があります。

### 原因3：背後の一覧が空、または正常な相手が居ない

公式文書が挙げている原因のうち、最も単純な2つです。一覧に何も登録されていない場合と、登録されているがすべてが正常でないと判定されている場合です。

```bash
# 背後の正常性の状態をまとめて確認する
az network application-gateway show-backend-health \
  --name my-gateway --resource-group my-rg \
  --query "backendAddressPools[].backendHttpSettingsCollection[].servers[].{address:address, health:health}" \
  --output table
```

すべてが正常でなければ、原因1と原因2に戻ります。一部だけが正常でない場合は、その相手だけを一時的に外して切り分けると原因が絞れます。

### 原因4：v1で、応答が20秒以内に返っていない

前述のとおり、公式文書には v1 における既定の待ち時間が20秒であること、その時間内に応答が返らないと 502 になることが明記されています。

時間のかかる処理を通している場合、この値を伸ばす必要があります。

```bash
az network application-gateway http-settings update \
  --gateway-name my-gateway --resource-group my-rg --name my-settings \
  --timeout 120
```

ただし、伸ばす前に、なぜ時間がかかっているかを確認する価値があります。また、自分の[環境](/glossary/環境/)がどの版かを確認してください。版によって、同じ状況が 502 になるとは限りません（[Azure の 504 の記事](/posts/azure_504/)）。

### 原因5：背後の証明書が一致していない

公式文書が挙げている原因の1つです。背後との[通信](/glossary/通信/)を[暗号化](/glossary/暗号化/)している構成で、提示される[証明書](/glossary/証明書/)が想定と合わない場合に起きます。

正常性の判定は通っているのに実際の[通信](/glossary/通信/)だけが失敗する、という形になりやすいのが特徴です。判定と本番で使う設定が同じかどうかを確認してください。背後を名前で登録している場合、その名前が[証明書](/glossary/証明書/)に含まれているかも確認の対象です。

## 補足：似ているが別のもの

管理側の窓口が返す時間切れは 504 で、文言にリソースプロバイダ名が入ります（[Azure の 504 の記事](/posts/azure_504/)）。本記事で扱っている 502 は、利用者向けの[通信](/glossary/通信/)を取り次ぐ側の話で、性質が違います。

窓口が一時的に処理できない場合は 503、内部で処理が失敗した場合は 500 です（[Azure の 503 の記事](/posts/azure_503/)、[500 の記事](/posts/azure_500/)）。[権限](/glossary/権限/)の不足は 403 です（[Azure の 403 の記事](/posts/azure_403/)）。

## 切り分けの順序

1. 背後の正常性の状態を確認する。すべてが正常でなければ、そこが原因。
2. 詳細を示す欄の文言を読む。接続できないのか、応答が想定外なのかを見分ける。
3. 遮断の設定を、Application Gateway 側の区画と背後側の区画の両方で確認する。管理用の範囲も塞いでいないかを見る。
4. 確認先の[パス](/glossary/パス/)が 200 から 399 を返すかを、背後の機器から直接叩いて確かめる。
5. 一覧が空でないか、登録内容が正しいかを確認する。
6. 正常と判定されているのに 502 が出るなら、[証明書](/glossary/証明書/)と名前の扱いを疑う。
7. 時間のかかる処理なら、待ち時間の設定と自分の版を確認する。

## 確認コマンド集

```bash
# 1. 背後の正常性をまとめて確認する
az network application-gateway show-backend-health \
  --name my-gateway --resource-group my-rg --output table

# 2. 確認の設定を見る
az network application-gateway probe list \
  --gateway-name my-gateway --resource-group my-rg \
  --query "[].{name:name, path:path, protocol:protocol, interval:interval, timeout:timeout}" \
  --output table

# 3. 待ち時間の設定を見る
az network application-gateway http-settings list \
  --gateway-name my-gateway --resource-group my-rg \
  --query "[].{name:name, port:port, timeout:requestTimeout, protocol:protocol}" --output table

# 4. 区画に紐づく遮断の設定を確認する
az network vnet subnet show --resource-group my-rg --vnet-name my-vnet \
  --name my-appgw-subnet --query "{nsg:networkSecurityGroup.id, rt:routeTable.id}"

# 5. 背後の機器から、確認先のパスを直接叩く
curl -sS -o /dev/null -w "status:%{http_code}\n" http://127.0.0.1:8080/healthz
```

## Editor's Note

Application Gateway の 502 は、公式文書が原因を列挙しているという点で、調べやすい部類の[エラー](/glossary/エラー/)です。それでも取り違えが起きるのは、6つの原因のうち複数が「正常性の判定が通らない」という同じ症状に集まるためです。判定が通らない理由が、遮断の設定なのか、確認先の[パス](/glossary/パス/)なのか、[設定値](/glossary/設定値/)の範囲なのかは、症状からは区別できません。

だからこそ、公式文書が詳細を示す欄から調査を始めるよう案内していることには意味があります。そこには、接続できなかったのか、応答が想定外だったのかが書かれています。この一段の情報があるかないかで、確認すべき対象の数が大きく変わります。

なお、原因の並びを見ると、Application Gateway 自身の不具合を疑うべき項目が1つも無いことに気付きます。列挙されているのはすべて、周辺の設定か背後の状態です。502 は取り次ぐ側の[エラー](/glossary/エラー/)ですが、取り次ぐ側の故障を意味しません。まず背後を見る、という順序を守ってください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*