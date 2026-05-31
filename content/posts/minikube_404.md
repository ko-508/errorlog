---
title: "Minikube の 404 エラー：原因と解決策"
date: 2026-05-30
lastmod: 2026-05-31
description: "指定したKubernetesリソースが見つからない。Minikube 404 エラーの原因と解決策を解説します。"
tags: ["Minikube"]
errorCode: "404"
---
Minikube で 404 エラーが出た場合、指定した [Kubernetes](/glossary/kubernetes/) リソースが見つからないことを示しています。このエラーは開発環境でよく発生し、適切な確認手順で迅速に解決できます。

## よくある原因

**[Namespace](/glossary/namespace/) の指定が間違っているか省略されている**

[Kubernetes](/glossary/kubernetes/) ではリソースは必ず [Namespace](/glossary/namespace/) 内に存在します。`kubectl get pod` のように [Namespace](/glossary/namespace/) を指定せずコマンドを実行すると、デフォルトの `default` [Namespace](/glossary/namespace/) のみを検索します。リソースが別の [Namespace](/glossary/namespace/) に存在する場合、404 エラーが返されます。例えば `kube-system` [Namespace](/glossary/namespace/) にあるシステムポッドは、[Namespace](/glossary/namespace/) 指定なしでは見つかりません。

**リソースがまだ[デプロイ](/glossary/デプロイ/)されていないか削除されている**

Deployment やポッドの作成コマンドを実行しても、イメージのダウンロードやスケジューリングに時間がかかります。その間に `kubectl get pod <pod-name>` を実行すると 404 になります。また、明示的に削除したリソースや、前回のセッションで作成したリソースも見つかりません。

**Minikube クラスターが停止している**

Minikube クラスターが停止している状態では、すべての [Kubernetes](/glossary/kubernetes/) [API](/glossary/api/) の[リクエスト](/glossary/リクエスト/)が失敗し、404 を含むエラーが返されます。クラスターが起動していても、kube-apiserver などのコアコンポーネントが正常に動作していない場合も同様です。

## 解決手順

**ステップ 1：Minikube クラスターの状態を確認する**

まず最初にクラスター全体が正常に起動しているか確認します。

```bash
minikube status
```

以下の出力が目標です。

```
minikube
type: Control Plane
host: Running
kubelet: Running
apiserver: Running
kubeconfig: Configured
```

クラスターが停止している場合は起動します。

```bash
minikube start
```

**ステップ 2：[Namespace](/glossary/namespace/) 全体でリソースを検索する**

次に、すべての [Namespace](/glossary/namespace/) 横断でリソースが実在するか確認します。`-A` フラグは全 [Namespace](/glossary/namespace/) 対象を意味します。

```bash
kubectl get pod -A
```

もしリソース名が分からない場合は、以下で全リソースを表示できます。

```bash
kubectl get all -A
```

特定のリソースタイプを検索する場合は、以下のように置き換えます。

```bash
kubectl get deployment -A
kubectl get service -A
kubectl get pvc -A
```

**ステップ 3：正しい [Namespace](/glossary/namespace/) を指定してアクセスする**

リソースが見つかった場合、その [Namespace](/glossary/namespace/) を指定して詳細を確認します。

```bash
kubectl describe pod <pod-name> -n <namespace-name>
```

例えば `kube-system` [Namespace](/glossary/namespace/) 内の `etcd` ポッドを確認する場合：

```bash
kubectl describe pod etcd-minikube -n kube-system
```

**ステップ 4：[デプロイ](/glossary/デプロイ/)失敗の原因を調査する**

リソースが見つからない場合、[デプロイ](/glossary/デプロイ/)が失敗している可能性があります。イベントログを確認します。

```bash
kubectl get events -A
```

特定の [Namespace](/glossary/namespace/) 内のイベントのみを表示する場合：

```bash
kubectl get events -n <namespace-name>
```

より詳細な情報を見る場合：

```bash
kubectl describe deployment <deployment-name> -n <namespace-name>
```

このコマンドで `Status` や `Conditions` を確認し、PullImageError や ImagePullBackOff など、[デプロイ](/glossary/デプロイ/)失敗の理由が表示されます。

**ステップ 5：リソース定義ファイルを再確認する**

[YAML](/glossary/yaml/) ファイルの [Namespace](/glossary/namespace/) 指定が正しいか確認します。

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: sample-pod
  namespace: default  # ここが正しい Namespace か確認
spec:
  containers:
  - name: nginx
    image: nginx:latest
```

[Namespace](/glossary/namespace/) 指定がない場合は `default` [Namespace](/glossary/namespace/) が使用されます。指定した [Namespace](/glossary/namespace/) に合わせて統一します。

## それでも解決しない場合

Minikube の[ログ](/glossary/ログ/)を確認することで、クラスターレベルの問題を特定できます。

```bash
minikube logs
```

クラスターをリセットして初期化する方法もあります。ただし既存のリソースがすべて削除されるため、慎重に実行してください。

```bash
minikube delete
minikube start
```

また、Minikube のバージョンが古い場合は更新も検討してください。

```bash
minikube version
```

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*