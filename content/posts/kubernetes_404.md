---
title: "Kubernetes の 404 エラー：原因と解決策"
date: 2026-05-26
description: "Kubernetesの404エラーは、APIサーバーが指定したリソース（Pod・Service・Deploymentなど）や、アクセスしようとしたエンドポイントが存在しないことを示します。"
tags: ["Kubernetes"]
errorCode: "404"
lastmod: 2026-05-31
---

## エラーの概要

[Kubernetes](/glossary/kubernetes/)の404エラーは、[API](/glossary/api/)サーバーが指定したリソース（Pod・Service・Deploymentなど）や、アクセスしようとした[エンドポイント](/glossary/エンドポイント/)が存在しないことを示します。`kubectl`コマンド実行時や[Kubernetes](/glossary/kubernetes/) [API](/glossary/api/)への[HTTP](/glossary/http/)[リクエスト](/glossary/リクエスト/)時に発生し、リソースの削除後のアクセスや存在しない[Namespace](/glossary/namespace/)へのクエリで特に見られます。このエラーはデータ消失を意味しませんが、リソースが実際に動作していない状態を示しているため、早期の対応が必要です。

## 実際のエラーメッセージ例

```bash
$ kubectl get pod my-app -n production
Error from server (NotFound): pods "my-app" not found
```

```json
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "deployments.apps \"web-server\" not found",
  "reason": "NotFound",
  "details": {
    "name": "web-server",
    "group": "apps",
    "kind": "deployments"
  },
  "code": 404
}
```

## よくある原因と解決手順

### 原因1：Namespace指定の誤りまたは省略

[Kubernetes](/glossary/kubernetes/)は複数の[Namespace](/glossary/namespace/)を持ち、デフォルトは`default`です。別の[Namespace](/glossary/namespace/)にリソースが存在する場合、指定せずにアクセスすると404が発生します。

**Before（エラーが起きる状況）**
```bash
$ kubectl get pod my-app
Error from server (NotFound): pods "my-app" not found
```

**After（修正後）**
```bash
# 正しいNamespaceを確認してから実行
$ kubectl get pod my-app -n production
# または全Namespaceを検索
$ kubectl get pod my-app --all-namespaces
```

### 原因2：リソース名の綴りミスまたは削除済み

Pod名やDeployment名などを誤入力した場合、またはリソースが既に削除されている場合に404が発生します。

**Before（エラーが起きる状況）**
```bash
$ kubectl get pod my-ap  # 綴りミス
Error from server (NotFound): pods "my-ap" not found

$ kubectl describe service api-server  # 削除済みリソース
Error from server (NotFound): services "api-server" not found
```

**After（修正後）**
```bash
# リソースの正確な名前を確認
$ kubectl get pods
NAME          READY   STATUS    RESTARTS   AGE
my-app        1/1     Running   0          2h
web-server    2/2     Running   0          5h

# 正しい名前でアクセス
$ kubectl get pod my-app
$ kubectl describe service web-server
```

### 原因3：APIのバージョン指定が誤っている

[Kubernetes](/glossary/kubernetes/) [API](/glossary/api/)は複数のバージョン（`v1`、`apps/v1`など）をサポートしています。古いバージョンや不正なバージョンを指定すると404が返されます。

**Before（エラーが起きる状況）**
```yaml
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  template:
    # ...
```

```bash
$ kubectl apply -f deployment.yaml
error: resource mapping not found for name: "my-app" namespace: "default" from "deployment.yaml": no matches for kind "Deployment" in version "extensions/v1beta1"
```

**After（修正後）**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: app
        image: my-app:1.0
```

### 原因4：リソースの初期化に時間がかかっている

新しいリソースを[デプロイ](/glossary/デプロイ/)した直後にアクセスすると、[API](/glossary/api/)サーバーがまだリソースを完全に登録していない可能性があります。

**Before（エラーが起きる状況）**
```bash
$ kubectl apply -f my-service.yaml
$ kubectl get svc my-service
Error from server (NotFound): services "my-service" not found
```

**After（修正後）**
```bash
$ kubectl apply -f my-service.yaml
$ sleep 5  # 数秒待機
$ kubectl get svc my-service
NAME         TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
my-service   ClusterIP   10.96.123.45   <none>        80/TCP    2s
```

## Kubernetes固有の注意点

**[RBAC](/glossary/rbac/)（Role-Based Access Control）による権限不足**

404が返されるのではなく、実際には403（Forbidden）エラーが発生していないか確認してください。ただし、SAC（Service Account）の権限不足により、存在するリソースへのアクセスが404として報告される場合もあります。

```bash
# 現在のユーザー・ServiceAccountの権限を確認
$ kubectl auth can-i get pods --as=system:serviceaccount:default:my-app
yes

# 権限がない場合、RoleBindingを確認
$ kubectl get rolebinding -n <namespace>
$ kubectl describe rolebinding <binding-name> -n <namespace>
```

**ServiceAccountの存在確認**

Podが使用するServiceAccountが存在しない場合、Podの作成が失敗することがあります。

```bash
# ServiceAccountを確認
$ kubectl get serviceaccount -n <namespace>

# 必要に応じて作成
$ kubectl create serviceaccount my-app-sa -n production
$ kubectl get serviceaccount my-app-sa -n production
```

**CRD（Custom Resource Definition）の未登録**

カスタムリソースタイプを使う場合、CRDがクラスタに登録されていないと404が発生します。

```bash
# CRDを確認
$ kubectl get crd
$ kubectl get crd my-custom-resource.example.com

# 登録されていない場合は追加
$ kubectl apply -f custom-resource-definition.yaml
```

## それでも解決しない場合

**[API](/glossary/api/)サーバーのログを確認**

```bash
# マスターノードのログを確認（自分でホストしている場合）
$ journalctl -u kubelet | grep "404"

# マネージドサービスの場合は管理画面でログを確認
```

**詳細なエラー情報を取得**

```bash
# 冗長モードで実行して詳細情報を表示
$ kubectl get pod my-app -v=9

# APIサーバーへの直接クエリ
$ kubectl get --raw /api/v1/namespaces/default/pods/my-app
```

**リソースの確認コマンド集**

```bash
# すべてのリソースを表示
$ kubectl get all -n <namespace>

# 特定リソースタイプの全インスタンスを表示
$ kubectl get <resource-type> --all-namespaces

# リソースの詳細情報を取得
$ kubectl describe <resource-type> <name> -n <namespace>
```

公式ドキュメント「[Kubernetes API Documentation](https://kubernetes.io/docs/reference/generated/kubernetes-api/)」と「[RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)」で、詳細な仕様を確認できます。また、[Stack Overflow](https://stackoverflow.com/questions/tagged/kubernetes)の[Kubernetes](/glossary/kubernetes/)タグや[Kubernetes Slack](https://kubernetes.slack.com)コミュニティでも類似の問題が報告されていることが多いです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*