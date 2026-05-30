---
title: "Minikube の 503 エラー：原因と解決策"
date: 2026-05-30
lastmod: 2026-05-31
description: "Minikubeクラスターのサービスが一時的に利用できない。Minikube 503 エラーの原因と解決策を解説します。"
tags: ["Minikube"]
errorCode: "503"
---
Minikubeでサービスにアクセスしたときに503エラーが返される場合、クラスター自体が正常に動作していないか、デプロイしたサービスが停止している状態です。この記事では、原因の特定方法と解決手順を説明します。

## よくある原因

**Minikubeが停止または起動中の状態**

Minikubeクラスターが完全に起動していないか、停止している場合、すべてのサービスへのリクエストが503エラーになります。起動処理が途中で止まっているケースもあり、この場合はクラスターが部分的にしか動作していないため、一部のサービスだけが利用できなくなります。

**Podがクラッシュループに陥っている**

デプロイしたPodがコンテナーの起動に失敗し、再起動を繰り返すクラッシュループ状態に陥ると、そのPod内で動作するサービスは利用できず503エラーが返されます。これはアプリケーションのバグ、設定ファイルの誤り、環境変数の不足などが原因で発生します。

**リソース不足**

Minikubeに割り当てたCPUやメモリが不足すると、Podが正常に起動できなくなり、サービスが停止します。特にメモリ不足でPodが強制終了された場合、リクエストを処理するリソースがないため503エラーが返されます。

## 解決手順

**1. クラスターの状態を確認する**

まずMinikubeが正常に動作しているか確認します。

```bash
minikube status
```

出力例：
```
minikube
type: Control Plane
host: Running
kubelet: Running
apiserver: Running
```

すべてが「Running」になっていることを確認してください。もし「Stopped」と表示される場合は、以下のコマンドで起動します。

```bash
minikube start
```

起動処理には数分かかります。完了後、再度 `minikube status` で確認してください。

**2. Podの状態を確認する**

クラスターが起動している場合、次にデプロイしたPodの状態を確認します。

```bash
kubectl get pods -A
```

出力例：
```
NAMESPACE     NAME                              READY   STATUS
default       my-app-deployment-5d4f8c9b2       1/1     Running
kube-system   coredns-558bd4d5ec-abc12          1/1     Running
```

「CrashLoopBackOff」または「ImagePullBackOff」というステータスのPodがないか確認してください。問題のあるPodが見つかった場合、詳細情報を取得します。

```bash
kubectl describe pod <pod-name> -n <namespace>
```

例：
```bash
kubectl describe pod my-app-deployment-5d4f8c9b2 -n default
```

出力の「Events」セクションにエラー内容が表示されます。ログを確認する場合は以下を実行します。

```bash
kubectl logs <pod-name> -n <namespace>
```

**3. リソースを増やして再起動する**

メモリやCPUが不足している場合、Minikubeに割り当てるリソースを増やします。

```bash
minikube config set memory 4096
minikube config set cpus 2
```

その後、Minikubeを再起動します。

```bash
minikube stop
minikube start
```

再起動後、Podが正常に起動したか確認します。

```bash
kubectl get pods -A
```

すべてのPodが「Running」ステータスになれば、503エラーは解消されます。

## それでも解決しない場合

Podのログに明確なエラーメッセージがある場合は、そのメッセージに応じてアプリケーション側の設定を修正してください。デプロイメントの定義ファイル（YAML）で環境変数やイメージ名に誤りがないか確認し、修正後に `kubectl apply -f deployment.yaml` で再デプロイしてください。

Minikubeをクリーンアップして完全にリセットしたい場合は、以下を実行します。

```bash
minikube delete
minikube start
```

ただしこの操作ですべてのPodと設定が削除されるため、本番環境で使用する場合は実施しないでください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*