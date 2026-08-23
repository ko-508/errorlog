---
title: "Azure の 504 エラー：原因と解決策"
date: 2026-07-28
description: "Azure の 504 は、管理側の窓口が返すものと、経路上の中継役が返すものに分かれます。管理側の文言にはリソースプロバイダ名が入るため、どこが応答しなかったかが特定できます。最も注意すべきは、504 でも操作が完了している場合があることと、Azure の SDK が既定で POST と PATCH まで自動で再送することです。"
tags: ["Azure"]
errorCode: "504"
lastmod: 2026-07-28
service: "Azure"
error_type: "504"
components: ["Resource Manager", "Application Gateway"]
related_services: ["Azure Resource Manager", "Application Gateway", "Azure Front Door"]
trend_incident: false
---

## 冒頭まとめ

Azure で 504 Gateway Timeout を受け取ったとき、出どころは2系統に分かれます。資源の作成や設定変更を受け付ける管理側の窓口が返すものと、利用者からの[通信](/glossary/通信/)を取り次ぐ中継役が返すものです。前者は Azure Resource Manager、後者は Application Gateway や Azure Front Door などが該当します。

管理側の 504 には、原因を絞り込める特徴があります。文言に、応答しなかったリソースプロバイダの名前が含まれるためです。`The gateway did not receive a response from 'Microsoft.Web' within the specified time period.` のような形で、`Microsoft.Web` や `Microsoft.App` といった名前が入ります。この名前は、どの機能群が応答しなかったかを示します。自分が操作している資源の種類と一致していれば、その資源の担当が遅れています。一致していなければ、内部で呼ばれている別の機能群が遅れています。

最も注意すべき点は2つあります。1つ目は、504 を受け取っても操作が完了している場合があることです。管理側の窓口は要求を受け取って担当へ渡しており、担当の処理は続いています。応答が返る前に取り次ぎ役が待つのをやめただけ、という状況が実際に起きます。

2つ目は、Azure の[ソフトウェア](/glossary/ソフトウェア/)開発キットの既定の挙動です。共通部分のソースを読むと、再試行の対象となる状態[コード](/glossary/コード/)は 408・429・500・502・503・504 と定義されています。そのうえで、通常は再送しない POST と PATCH についても、500・503・504 のときだけは再試行する、という例外が明示的に書かれています。つまり、資源を作る要求が 504 で戻った場合、利用者が何もしなくても同じ要求がもう一度送られる可能性があります。

## エラーの概要

管理側から返る場合、応答には[コード](/glossary/コード/)名と、リソースプロバイダ名を含む文言が入ります。

```json
{
  "error": {
    "code": "GatewayTimeout",
    "message": "The gateway did not receive a response from 'Microsoft.App' within the specified time period."
  }
}
```

各社の道具を経由している場合も、この文言はそのまま持ち回されます。たとえば構成管理の道具からは、次のような形で表示されます。

```text
Status=504 Code="GatewayTimeout" Message="The gateway did not receive a
response from 'Microsoft.App' within the specified time period."
```

[コマンド](/glossary/コマンド/)行の道具から実行した場合、識別用の番号が添えられることがあります。この番号は問い合わせの際に必要になるので、控えておいてください。

```text
GatewayTimeout : The gateway did not receive a response from
'Microsoft.DevTestLab' within the specified time period.
CorrelationId: 00000000-0000-0000-0000-000000000000
```

中継役から返る場合は、リソースプロバイダ名が入りません。応答は簡素なもので、詳細は中継役側の[ログ](/glossary/ログ/)にあります。文言にリソースプロバイダ名があるかどうかが、系統を見分ける最初の手がかりです。

## まず最初に：文言とリソースプロバイダ名を見る

第一に、`Microsoft.` で始まる名前が文言に入っているかを見ます。入っていれば管理側、入っていなければ中継役や経路側です。

第二に、管理側だった場合、その名前が自分の操作対象と一致するかを確認します。仮想機械を作っていて `Microsoft.Compute` が出るなら、その担当が遅れています。一方、別の名前が出ることもあります。ある資源の設定を読むために、内部で別の機能群へ問い合わせている場合です。この場合、遅いのは自分が操作している資源そのものではありません。

第三に、操作の種類を確認します。読み取りなら再実行して構いません。作成・更新・[削除](/glossary/削除/)なら、実際にどうなったかを確認してから次を決めます。

## よくある原因と解決手順

### 原因1：504を受けたが、資源は作られている

管理側の 504 で最も注意が必要な形です。取り次ぎ役が待つのをやめただけで、担当側では処理が完了していることがあります。

再実行の前に、実物を確認してください。

```bash
# 資源が存在するかを確認する
az resource list --resource-group my-rg --output table

# 直近の操作の記録を確認する（成功か失敗かが残る）
az monitor activity-log list --resource-group my-rg \
  --start-time 2026-07-28T00:00:00Z --output table
```

活動の記録には、管理側が受け付けた操作の結果が残ります。504 を受け取っていても、記録上は成功していることがあります。その場合、資源は出来ているので、再実行してはいけません。

構成管理の道具を使っている場合は、道具側の記録と実物が食い違います。実物があるのに記録に無ければ、取り込みの操作で揃えてください。この食い違いは、時間が経つほど厄介になります。

### 原因2：SDKが自動でPOSTやPATCHを再送している

前述のとおり、Azure の開発キットの共通部分には、POST と PATCH を 500・503・504 のときに再試行する指定が明示的に書かれています。通常、これらは同じ要求を2回送ると結果が変わりうる種類なので、再送の対象から外すのが一般的です。しかし Azure の実装では例外として扱われています。

この挙動自体は、多くの場合に有益です。管理側の操作は同じ内容を2回送っても結果が変わらないよう作られていることが多いためです。ただし、そうでない操作もあります。意図しない再送を避けたい場合は、再試行の設定を明示します。

**Before（既定のまま、自動で再送される）：**

```python
from azure.mgmt.resource import ResourceManagementClient

client = ResourceManagementClient(credential, subscription_id)
```

**After（再試行の回数を指定する）：**

```python
client = ResourceManagementClient(
    credential, subscription_id,
    retry_total=0,          # 自動の再試行を行わない
)
```

再試行を止める場合、失敗の扱いは自分で書く必要があります。504 を受けたら実物を確認し、無ければもう一度送る、という手順を明示的に組んでください。

なお、応答に待機の指示が含まれている場合は、状態[コード](/glossary/コード/)に関わらず再試行される、ともソースに書かれています。待機の指示があるかどうかも、挙動を読むうえでの手がかりになります。

### 原因3：中継役のバックエンド待ち時間が短い

Application Gateway や Azure Front Door を経由している構成で、背後の応答が設定された時間内に返らない場合です。この場合、文言にリソースプロバイダ名は入りません。

対処は、待ち時間の設定を実際の処理時間に合わせることです。Application Gateway では、[バックエンド](/glossary/バックエンド/)の [HTTP](/glossary/http/) 設定にある要求の待ち時間がこれにあたります。現在の値を確認してください。

```bash
az network application-gateway http-settings list \
  --gateway-name my-gateway --resource-group my-rg \
  --query "[].{name:name, timeout:requestTimeout}" --output table
```

値を伸ばす前に、なぜ処理に時間がかかっているかを確認する価値があります。待ち時間の設定は、遅さを覆い隠すための道具ではありません。時間のかかる処理が一部の経路だけであれば、その経路だけ別の設定を当てるほうが影響が小さく済みます。

### 原因4：特定の機能群や地域だけで起きている

同じ操作が、ある地域では通り、別の地域では 504 になる、という形があります。この場合、原因は自分の設定ではなく、その地域の担当側にあります。

確認の順序としては、まず文言のリソースプロバイダ名を見て、次に別の地域で同じ操作を試します。片方だけで再現するなら、設定を疑う必要はありません。

```bash
# 同じ操作を別の地域で試す
az group create --name test-rg --location japanwest
```

なお、公開されている稼働状況の表示が正常でも、特定の機能群だけが応答していないことはあります。表示だけを根拠に「問題は自分側にある」と判断しないでください。識別用の番号を控えて問い合わせる材料にします。

## 補足：似ているが別のもの

管理側が一時的に処理できない場合は 503 で、時間切れとは区分が違います（[Azure の 503 の記事](/posts/azure_503/)）。要求の頻度が上限を超えた場合は 429 です（[Azure の 429 の記事](/posts/azure_429/)）。処理が内部で失敗した場合は 500 です（[Azure の 500 の記事](/posts/azure_500/)）。[権限](/glossary/権限/)の不足は 403 で、待っても変わりません（[Azure の 403 の記事](/posts/azure_403/)）。

同じ資源に対する操作が競合している場合は 409 です（[Azure の 409 の記事](/posts/azure_409/)）。504 で中断したあとに再実行して 409 が出る場合、前の操作がまだ動いている合図なので、待つのが正解です。

呼び出す側の締め切りが先に切れた場合は、504 になりません。応答が届いていないので状態[コード](/glossary/コード/)が存在しないためです。この場合は道具ごとの時間切れの文言になります。504 が出ているということは、少なくとも中継役からの応答は届いている、ということです。

## 切り分けの順序

1. 文言に `Microsoft.` で始まる名前があるかを見る。あれば管理側、無ければ中継役や経路側。
2. 管理側なら、その名前が自分の操作対象と一致するかを確認する。一致しなければ、内部で呼ばれている別の機能群が遅れている。
3. 操作の種類を確認する。作成・更新・[削除](/glossary/削除/)なら、再実行の前に実物と活動の記録を確認する。
4. 使っている開発キットや道具が、自動で再送していないかを確認する。POST と PATCH も再送の対象になりうる。
5. 中継役の系統なら、[バックエンド](/glossary/バックエンド/)の待ち時間の設定と、実際の処理時間を突き合わせる。
6. 別の地域で同じ操作を試す。片方だけで再現するなら、自分の設定の問題ではない。
7. 識別用の番号を控える。問い合わせの際に必要になる。

## 確認コマンド集

```bash
# 1. 資源が実際に存在するかを確認する（再実行の前に必ず行う）
az resource list --resource-group my-rg --output table

# 2. 活動の記録から、操作の結果を確認する
az monitor activity-log list --resource-group my-rg \
  --start-time 2026-07-28T00:00:00Z \
  --query "[].{time:eventTimestamp, op:operationName.value, status:status.value}" \
  --output table

# 3. 詳細な通信内容を表示して、どの要求が504になったかを見る
az resource show --ids <資源の識別子> --debug 2>&1 | grep -i "504\|GatewayTimeout"

# 4. Application Gateway の待ち時間の設定を確認する
az network application-gateway http-settings list \
  --gateway-name my-gateway --resource-group my-rg \
  --query "[].{name:name, timeout:requestTimeout}" --output table

# 5. 進行中の配置の状態を確認する
az deployment group list --resource-group my-rg \
  --query "[].{name:name, state:properties.provisioningState}" --output table
```

## Editor's Note

504 が状態の食い違いを生む様子を、そのまま記録した報告があります（[504 GatewayTimeout Error while creating a ContainerApp caused Pulumi to fail and not add it to state despite the resource being created](https://github.com/pulumi/pulumi-azure-native/issues/3200)）。2024年4月、構成管理の道具で容器アプリを作成した際に 504 を受け取り、道具側は失敗として扱ったものの、資源そのものは作られていた、という内容です。標題が状況をそのまま述べています。

報告には、道具の内部の動きも書かれています。まず存在するかを問い合わせ、無ければ作成の要求を送り、返ってきた追跡用の場所を繰り返し確認して完了を待つ、という流れです。報告者は、504 がどの段階で出たのかは手元の記録からは確定できない、と正直に書いたうえで、504 を受け取ったときに一定時間おいてもう一度存在を確認し、それでも無ければ失敗として扱う、という処理を入れられないか、と提案しています。

この提案が示しているのは、504 に対する正しい反応が「再送」ではなく「確認」だということです。同じ趣旨の記録は Azure の配置の道具にも残っており、設定の更新で 504 を受け取ったが実際には反映されていた、という報告があります。そちらの記録には、道具が 504 を再試行可能な状態[コード](/glossary/コード/)として扱った旨も出力されています。

管理側の 504 は、文言にリソースプロバイダ名が入るという点で、他の[クラウド](/glossary/クラウド/)より手がかりが多い部類です。どこが応答しなかったかが分かるからです。しかし、応答しなかったことと、処理されなかったことは別です。名前を読んだら、次は実物を見てください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*