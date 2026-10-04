---
title: "kubectlのAPIが見つからない対処法"
date: 2026-09-30
draft: false
description: "kubectlのthe server could not find the requested resourceやno matches for kindが出たとき、接続先のAPI一覧、CRDの登録状態、apiVersionを確認する手順を解説します。個別のオブジェクトが見つからないNotFoundとの違いも整理します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_server_could_not_find.png"]
errorCode: "the server could not find the requested resource"
urgency: "medium"
service: "Kubernetes"
error_type: "api_resource_not_found"
components: ["kubectl", "API server", "CRD"]
related_services: ["Helm"]
trend_incident: false
---

## 冒頭まとめ

`kubectl apply`や`kubectl get`が、次の[エラー](/glossary/エラー/)で止まることがあります。

```text
Error from server (NotFound): the server could not find the requested resource
```

まず、**接続先のクラスターが、指定した種類と[バージョン](/glossary/バージョン/)の[API](/glossary/api/)を提供しているか**を確認します。[API](/glossary/api/)は、PodやDeploymentなどを作成・取得するための窓口です。[マニフェスト](/glossary/マニフェスト/)の`apiVersion`と`kind`を控え、現在の接続先と[API](/glossary/api/)一覧を調べてください。

```bash
kubectl config current-context
kubectl api-versions
kubectl api-resources --cached=false
```

カスタムリソースなら、その種類を追加する定義であるCRD（CustomResourceDefinition）が必要です。CRDを先に適用して登録を待ち、その後にカスタムリソースを適用します。組み込みリソースなら、`apiVersion`の誤りや、クラスターの更新で提供されなくなった旧[API](/glossary/api/)を確認します。

ただし、この文言だけでCRD不足と断定はできません。404は要求先が見つからなかった応答で、接続先や途中の[プロキシ](/glossary/プロキシ/)が誤っている場合も調査対象になります。

## 3つのエラー文言の違い

似た状況で次の文言も出ますが、発生する処理は異なります。

| 文言 | 示していること |
|---|---|
| `the server could not find the requested resource` | 要求先から404相当の応答を受けた。要求した[API](/glossary/api/)の[パス](/glossary/パス/)と応答元を確認する |
| `no matches for kind "MyApp" in version "myorg.example.com/v1"` | kubectl側で、指定した`kind`と[API](/glossary/api/)[バージョン](/glossary/バージョン/)を[対応](/glossary/対応/)する[API](/glossary/api/)へ変換できなかった |
| `the server doesn't have a resource type "myapps"` | kubectl側で、指定したリソース名に[対応](/glossary/対応/)する[API](/glossary/api/)を見つけられなかった |

最初の文言は、[Kubernetesの`NewGenericServerResponse()`](https://github.com/kubernetes/apimachinery/blob/master/pkg/api/errors/errors.go)が[HTTP](/glossary/http/) 404に[対応](/glossary/対応/)して組み立てるメッセージです。要求した操作、リソースの種類、名前が分かる場合は、末尾に`(get deployments.apps my-app)`などが付きます。

**すべての404がこの固定文言になるわけではありません。** [client-goの応答処理](https://github.com/kubernetes/client-go/blob/master/rest/request.go)は、[Kubernetes](/glossary/kubernetes/)の形式で返された[エラー](/glossary/エラー/)情報を利用し、読み取れない応答には汎用的な[エラー](/glossary/エラー/)を作ります。そのため、固定文言だけで、リソースの種類がないのか、個別の名前がないのか、別の[サーバー](/glossary/サーバー/)が応答しているのかを決めないでください。

残りの2つは、[RESTMapperのエラー定義](https://github.com/kubernetes/apimachinery/blob/master/pkg/api/meta/errors.go)と[kubectlの表示処理](https://github.com/kubernetes/kubectl/blob/master/pkg/cmd/util/helpers.go)に由来します。RESTMapperは、種類やリソース名を[API](/glossary/api/)の宛先へ対応付ける仕組みです。対象[オブジェクト](/glossary/オブジェクト/)の操作へ進む前に失敗しますが、対応付けに使う[API](/glossary/api/)一覧を[サーバー](/glossary/サーバー/)から取得することがあります。接続を一度も試していないという意味ではありません。

## 接続先とAPI一覧を確認する

同じ[マニフェスト](/glossary/マニフェスト/)でも、開発用クラスターにはCRDがあり、本番用にはない場合があります。最初に現在のcontext（接続先の[設定](/glossary/設定/)）を確認します。

```bash
kubectl config current-context
kubectl config get-contexts
```

接続先が正しければ、`apiVersion`と`kind`を照合します。たとえば`apiVersion: apps/v1`、`kind: Deployment`なら、次を実行します。

```bash
kubectl api-versions
kubectl api-resources --api-group=apps --cached=false
```

`api-versions`では`apps/v1`が提供されているか、`api-resources`では`Deployment`に[対応](/glossary/対応/)するリソースがあるかを調べます。後者は[API](/glossary/api/)グループで絞り込む[コマンド](/glossary/コマンド/)で、指定したすべての版を一覧にするものではありません。版の確認には両方を使ってください。[kubectl本体の実装](https://github.com/kubernetes/kubectl/blob/master/pkg/cmd/apiresources/apiresources.go)では、`--cached=false`の場合に[API](/glossary/api/)一覧の取得情報を更新します。

一覧にあるのに404が続く場合は、読み取り[コマンド](/glossary/コマンド/)で具体的な[API](/glossary/api/)[パス](/glossary/パス/)を確認できます。次は`apps/v1`の[API](/glossary/api/)一覧を要求する例です。

```bash
kubectl get --raw /apis/apps/v1
```

[JSON](/glossary/json/)の一覧が返れば、その[パス](/glossary/パス/)は提供されています。404なら、要求したグループ・版と接続先を再確認します。標準的な[API](/glossary/api/)の[パス](/glossary/パス/)でも404になり、HTMLなど[Kubernetes](/glossary/kubernetes/)の[API](/glossary/api/)応答と異なる内容が返る場合は、kubeconfigの`server`や経路上の[プロキシ](/glossary/プロキシ/)も確認してください。必要なら失敗した読み取り[コマンド](/glossary/コマンド/)に`--v=7`を付け、要求[URL](/glossary/url/)と[HTTP](/glossary/http/)応答を調べます。詳細[ログ](/glossary/ログ/)を共有する際は、接続先や内部情報を確認してから渡してください。

## CRDを先に適用して登録を待つ

`kind: MyApp`のような独自の種類には、[対応](/glossary/対応/)するCRDが必要です。Operatorを使う手順なら、配布元が指定するCRDの導入方法を確認してください。Operatorは独自リソースの状態に応じて処理する[プログラム](/glossary/プログラム/)で、CRDの登録と、その[プログラム](/glossary/プログラム/)の稼働は別の確認項目です。

```bash
kubectl get crd
kubectl api-resources --api-group=myorg.example.com --cached=false
```

対象CRDがない場合は、製品やOperatorの[対応版](/glossary/対応版/)に付属するCRDを先に適用します。次は、CRDを`crds/`、それを使う定義を`resources/`に分けた場合の例です。CRD名は実際の名前に置き換えてください。

```bash
kubectl apply -f crds/
kubectl wait --for=condition=Established crd/myapps.myorg.example.com --timeout=60s
kubectl api-resources --api-group=myorg.example.com --cached=false
kubectl apply -f resources/
```

各[コマンド](/glossary/コマンド/)の成功を確認してから次へ進みます。CRDが複数あるなら、利用する種類に[対応](/glossary/対応/)するCRDすべてについて登録を待ってください。[Kubernetes公式のCRD手順](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/)は、[API](/glossary/api/)の作成に数秒かかることがあり、`Established`条件が真になるか、[API](/glossary/api/)一覧に種類が現れるのを確認すると説明しています。

待機が[タイムアウト](/glossary/タイムアウト/)した場合は、先へ進まず登録状態を調べます。

```bash
kubectl describe crd myapps.myorg.example.com
kubectl get crd myapps.myorg.example.com -o yaml
```

CRDが存在しても、[マニフェスト](/glossary/マニフェスト/)に指定した版を提供していない場合があります。CRDの`spec.group`、`spec.names.kind`、`spec.versions`を確認し、要求した版の`served`が`true`かを照合します。[CRDのバージョン管理](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definition-versioning/)に各設定の意味が記載されています。

[ファイル名](/glossary/ファイル名/)を並べ替えるだけでは、CRDの登録完了を待つことにはなりません。CRDとそれを使うリソースを同じ[ディレクトリ](/glossary/ディレクトリ/)へ入れて一度に適用するより、上のように適用と待機を分けると、失敗した段階を確認できます。`--server-side`や`--force-conflicts`は、存在しない[API](/glossary/api/)を登録するための指定ではありません。

## apiVersionの誤りと削除されたAPIを直す

組み込みリソースで`no matches for kind`が出るなら、CRDを入れる前に`apiVersion`を確認します。たとえばDeploymentは`apps/v1`を使います。Podなどで使う`v1`を、そのままDeploymentへ指定しても一致しません。

クラスターの更新後に止まり始めた場合は、以前使っていた[API](/glossary/api/)[バージョン](/glossary/バージョン/)が提供されなくなっていないかを調べます。[Kubernetes公式の移行ガイド](https://kubernetes.io/docs/reference/using-api/deprecation-guide/)では、CronJobの`batch/v1beta1`は[Kubernetes](/glossary/kubernetes/) 1.25から提供されず、`batch/v1`へ移行する必要があると説明しています。

```yaml
# 旧APIを指定している例
apiVersion: batch/v1beta1
kind: CronJob
```

```yaml
# 移行先のAPIを指定する例
apiVersion: batch/v1
kind: CronJob
```

これは変更する冒頭部分の例で、単独では適用できません。実際の[マニフェスト](/glossary/マニフェスト/)全体について、移行ガイドの項目変更も確認します。[API](/glossary/api/)によっては、`apiVersion`を書き換えるだけでは不十分です。Helmを使っている場合は、手元の出力だけでなく、クラスターの版に[対応](/glossary/対応/)したchartへ更新する必要があるかも調べてください。

## Helmで失敗した場合の確認点

Helmのchartは、[アプリケーション](/glossary/アプリケーション/)の導入に使う定義一式です。[Helm公式のCRD説明](https://helm.sh/docs/chart_best_practices/custom_resource_definitions/)では、chartの`crds/`に配置されたCRDを`helm install`で先に導入する方式を説明しています。一方、`--skip-crds`を付けるとこの導入を省き、既存CRDの更新も自動で済むとは限りません。chartがCRDを別配布している場合は、その導入手順に従います。

`--set crds.install=true`はすべてのchartに共通する指定ではありません。chartがその[設定](/glossary/設定/)を実装している場合にだけ使えます。`--wait`を追加するだけで、CRD不足や旧[API](/glossary/api/)の使用が解消すると考えないでください。また、`--dry-run`ではCRD自体を登録できないため、まだ存在しないカスタムリソースを検証できない場合があります。

実例として、[Argo Workflowsの報告](https://github.com/argoproj/argo-helm/issues/2751)では、CRDの導入時に`no matches for kind "CustomResourceDefinition" in version "apiextensions.k8s.io/v1beta1"`が出ています。[返信](https://github.com/argoproj/argo-helm/issues/2751#issuecomment-2155989787)では、当時の新しいchartがその旧[API](/glossary/api/)を使っていないことと、導入できた検証結果が示されています。

このように、[エラー](/glossary/エラー/)にCRDが出ていても、原因がCRDの未導入ではなく、**CRD定義そのものの[API](/glossary/api/)[バージョン](/glossary/バージョン/)**にある場合があります。`kind: CustomResourceDefinition`で止まったのか、それを使う`kind: MyApp`などで止まったのかを分けて確認してください。

## 似たエラーとの違い

```text
Error from server (NotFound): deployments.apps "my-app" not found
```

この表示なら、まず指定した名前のDeploymentと名前空間を確認します。リソースの種類を増やすためにCRDを導入する場面とは異なります。

```bash
kubectl get deployments.apps -n <namespace>
kubectl get deployments.apps -A
```

`-A`はすべての名前空間を調べる指定で、その範囲を読む[権限](/glossary/権限/)が必要です。[オブジェクト](/glossary/オブジェクト/)が別の名前空間にあるなら、[コマンド](/glossary/コマンド/)の`-n`や[マニフェスト](/glossary/マニフェスト/)の`metadata.namespace`を合わせます。名前空間を変えても、クラスターが提供していない[API](/glossary/api/)の版は使えるようになりません。

`Unable to connect to the server`は、接続や[TLS](/glossary/tls/)などの失敗を調べる文言です。今回の404は[HTTP](/glossary/http/)応答を受けている点が異なります。ただし、期待した[API](/glossary/api/)[サーバー](/glossary/サーバー/)から返っているかは別途確認が必要です。`Error from server (Forbidden)`なら、表示された操作に対する[権限](/glossary/権限/)を確認してください。

## 解決手順のまとめ

最初にcontextを確認し、[マニフェスト](/glossary/マニフェスト/)の`apiVersion`と`kind`を、接続先の[API](/glossary/api/)一覧へ照合します。独自の種類ならCRDの有無と提供する版を確認し、CRDを適用して`Established`を待った後にカスタムリソースを適用してください。

組み込み[API](/glossary/api/)やCRD定義そのものの旧[バージョン](/glossary/バージョン/)が原因なら、公式の移行手順に従って[マニフェスト](/glossary/マニフェスト/)やchartを更新します。[API](/glossary/api/)が一覧にあるのに404が続く場合は、実際の要求[パス](/glossary/パス/)と応答元を調べます。個別の名前が見つからないNotFoundなら、名前と名前空間の確認へ進みます。

免責事項：本記事の内容は一般的な[Kubernetes](/glossary/kubernetes/)[環境](/glossary/環境/)を前提としています。CRDやchartを[本番環境](/glossary/本番環境/)で変更する前に、利用中のカスタムリソースと[対応](/glossary/対応/)する[API](/glossary/api/)[バージョン](/glossary/バージョン/)への影響を確認してください。
