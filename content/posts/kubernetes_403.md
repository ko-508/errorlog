---
title: "Kubernetes の 403 エラー：原因と解決策"
date: 2026-05-25
description: "Kubernetes の 403 エラーは「Forbidden」を意味し、リクエストの認証は成功しているものの、そのリソースに対する操作権限（RBAC: Role-Based Access Control）がないことを示します。"
tags: ["Kubernetes"]
errorCode: "403"
lastmod: 2026-05-31
service: "Kubernetes"
error_type: "403"
components: ["Pod", "Deployment", "ServiceAccount", "Role", "RoleBinding", "ClusterRole", "Namespace"]
related_services: ["RBAC", "kubectl"]
---

## エラーの概要

[Kubernetes](/glossary/kubernetes/) の 403 [エラー](/glossary/エラー/)は「Forbidden」を意味し、[リクエスト](/glossary/リクエスト/)の[認証](/glossary/認証/)は成功しているものの、そのリソースに対する操作権限（[RBAC](/glossary/rbac/): Role-Based Access Control）がないことを示します。Pod の実行、リソースの取得・更新・削除など、特定の操作がセキュリティポリシーにより拒否された状態です。[API](/glossary/api/) [サーバー](/glossary/サーバー/)や[マニフェスト](/glossary/マニフェスト/)適用時、kubectl [コマンド](/glossary/コマンド/)実行時に頻繁に発生します。

## 実際のエラーメッセージ例

```
Error from server (Forbidden): pods "my-pod" is forbidden: User "system:serviceaccount:default:app" cannot get resource "pods" in API group "" in the namespace "default"
```

```json
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "deployments.apps \"my-app\" is forbidden: User \"user@example.com\" cannot create resource \"deployments\" in API group \"apps\" in the namespace \"production\"",
  "reason": "Forbidden",
  "code": 403
}
```

## よくある原因と解決手順

### 原因1: ServiceAccount に必要な Role がバインドされていない

**なぜ発生するか：**
Pod 内のアプリケーションが [Kubernetes](/glossary/kubernetes/) [API](/glossary/api/) にアクセスする際、その Pod が使用する ServiceAccount に適切な Role や ClusterRole がバインドされていないと、403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きる設定）:**
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
  namespace: default
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      serviceAccountName: app-sa
      containers:
      - name: app
        image: myapp:latest
        # アプリが pod リストを取得しようとするが権限がない
```

**After（修正後）:**
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: app-reader
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-reader-binding
  namespace: default
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: app-reader
subjects:
- kind: ServiceAccount
  name: app-sa
  namespace: default
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      serviceAccountName: app-sa
      containers:
      - name: app
        image: myapp:latest
```

### 原因2: Namespace 間でのリソースアクセス権限が不足している

**なぜ発生するか：**
あるユーザーや[サービスアカウント](/glossary/サービスアカウント/)が、別の [Namespace](/glossary/namespace/) に属するリソースへのアクセスを試みる場合、その [Namespace](/glossary/namespace/) に対する[権限](/glossary/権限/)がないと 403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きる設定）:**
```bash
# development namespace に所属するユーザーが production 内のリソースにアクセス
kubectl get pods -n production
# Error from server (Forbidden): pods is forbidden: User "dev-user" cannot list resource "pods" in API group "" in the namespace "production"
```

**After（修正後）:**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: cross-ns-reader
  namespace: production
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: dev-user-access
  namespace: production
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: cross-ns-reader
subjects:
- kind: User
  name: dev-user
  apiGroup: rbac.authorization.k8s.io
```

### 原因3: ユーザー認証情報の kubeconfig が古い、または権限が異なる

**なぜ発生するか：**
kubeconfig ファイルが古い認証情報を保持していたり、異なる[ロール](/glossary/ロール/)に属する設定になっていたりすると、[API](/glossary/api/) [サーバー](/glossary/サーバー/)が現在のユーザー[権限](/glossary/権限/)を正しく認識できず 403 が返されます。

**Before（[エラー](/glossary/エラー/)が起きる設定）:**
```bash
# 古い kubeconfig で実行
kubectl --kubeconfig=old-config.yaml apply -f deployment.yaml
# Error from server (Forbidden): error when creating "deployment.yaml": deployments.apps is forbidden
```

**After（修正後）:**
```bash
# kubeconfig を再取得
aws eks update-kubeconfig --region us-east-1 --name my-cluster
# または
gcloud container clusters get-credentials my-cluster --zone us-central1-a

# 正しい認証情報で実行確認
kubectl auth can-i create deployments --namespace default
# yes

kubectl apply -f deployment.yaml
```

## Kubernetes 固有の注意点

### RBAC の確認と診断コマンド

[RBAC](/glossary/rbac/) が複雑に設定されている場合、以下の[コマンド](/glossary/コマンド/)で[権限](/glossary/権限/)を検証します：

```bash
# 現在のユーザーが特定のアクションを実行できるかチェック
kubectl auth can-i create deployments -n production

# ServiceAccount の権限をチェック
kubectl auth can-i list pods --as=system:serviceaccount:default:app-sa -n default

# 特定のリソースに対する全権限を表示
kubectl describe role app-reader -n default
kubectl describe rolebinding app-reader-binding -n default
```

### Cluster Admin と ClusterRole の関係

クラスター全体への[権限](/glossary/権限/)が必要な場合は、Role ではなく ClusterRole を使用します：

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: admin-role
rules:
- apiGroups: ["*"]
  resources: ["*"]
  verbs: ["*"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: admin-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: admin-role
subjects:
- kind: User
  name: admin-user
  apiGroup: rbac.authorization.k8s.io
```

### ServiceAccount の デフォルト動作

[Kubernetes](/glossary/kubernetes/) 1.24 以降、ServiceAccount は自動的にシークレットを生成しなくなったため、手動でシークレットを作成する必要があります：

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-sa-token
  namespace: default
  annotations:
    kubernetes.io/service-account.name: app-sa
type: kubernetes.io/service-account-token
```

## それでも解決しない場合

### 確認すべきログとデバッグ方法

```bash
# API サーバーのログを確認（マネージドサービスの場合はコントロールプレーンログ）
kubectl logs -n kube-system deployment/kube-apiserver

# 自分の現在の認証情報を確認
kubectl auth whoami

# 詳細なエラー情報を出力
kubectl apply -f deployment.yaml -v=8

# ServiceAccount トークンの有効性確認
kubectl get secret <secret-name> -o jsonpath='{.data.token}' | base64 -d
```

### 公式ドキュメント

[Kubernetes](/glossary/kubernetes/) の [RBAC](/glossary/rbac/) 公式ドキュメント（https://kubernetes.io/docs/reference/access-authn-authz/rbac/）に詳細な設定例が記載されています。特に「Using [RBAC](/glossary/rbac/) Authorization」セクションを参照してください。

### コミュニティリソース

GitHub の [Kubernetes](/glossary/kubernetes/) Issues（https://github.com/kubernetes/kubernetes/issues）や [Kubernetes](/glossary/kubernetes/) Slack の #rbac チャネルで、類似の問題報告と解決策が共有されています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*