---
draft: true
title: "Minikube の 403 エラー：原因と解決策"
date: 2026-05-30
lastmod: 2026-06-14
description: "RBAC設定によりリソースへのアクセスが拒否された"
tags: ["Minikube"]
errorCode: "403"
service: "Minikube"
error_type: "403"
components: ["Pod", "Deployment", "Service", "ServiceAccount", "Role", "RoleBinding", "ClusterRoleBinding", "Namespace"]
related_services: ["Kubernetes", "kubectl"]
---

## エラーの概要

Minikubeで403[エラー](/glossary/エラー/)が返される場合、[RBAC](/glossary/rbac/)（ロールベースアクセス制御）による[アクセス権限](/glossary/アクセス権限/)の拒否が原因です。この[エラー](/glossary/エラー/)は、PodやServiceAccountが[Kubernetes](/glossary/kubernetes/)リソースへのアクセスを試みた際に、十分な[権限](/glossary/権限/)がない状態で発生します。開発環境での動作確認から本番運用まで、権限設定の誤りは頻繁に遭遇する問題です。

## 実際のエラーメッセージ例

kubectl[コマンド](/glossary/コマンド/)実行時の[エラー](/glossary/エラー/)：

```
error: deployments.apps "my-app" is forbidden: User "system:serviceaccount:default:default" cannot get resource "deployments" in API group "apps" in the namespace "default"
```

Pod内から[API](/glossary/api/)サーバーアクセス時の[エラー](/glossary/エラー/)：

```json
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "pods \"my-pod\" is forbidden: User \"system:serviceaccount:default:default\" cannot get resource \"pods\" in API group \"\" in the namespace \"default\"",
  "reason": "Forbidden",
  "details": {
    "name": "my-pod",
    "kind": "pods"
  },
  "code": 403
}
```

## よくある原因と解決手順

### 原因1：デフォルトServiceAccountに必要な権限がない

Minikubeのデフォルト名前空間では、`default` ServiceAccountが使用されますが、この[アカウント](/glossary/アカウント/)には最小限の[権限](/glossary/権限/)しか持っていません。Deploymentの一覧取得やPodの作成といった操作を試みると、権限不足により403[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-app
  namespace: default
spec:
  serviceAccountName: default
  containers:
  - name: app
    image: my-app:latest
    command: ["kubectl", "get", "pods"]
```

**After（修正後）：**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-serviceaccount
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pod-reader-binding
  namespace: default
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: pod-reader
subjects:
- kind: ServiceAccount
  name: my-serviceaccount
  namespace: default
---
apiVersion: v1
kind: Pod
metadata:
  name: my-app
  namespace: default
spec:
  serviceAccountName: my-serviceaccount
  containers:
  - name: app
    image: my-app:latest
    command: ["kubectl", "get", "pods"]
```

### 原因2：RoleBindingが存在しない、または間違った名前空間に設定されている

Roleを作成してもRoleBindingで適切なServiceAccountに紐付けなければ、[権限](/glossary/権限/)は有効になりません。また、名前空間固有の操作をする場合、RoleBindingが異なる名前空間に存在していないか確認が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: deployment-manager
  namespace: default
rules:
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "create", "update"]
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: deployer
  namespace: default
# RoleBindingがないため、deployerServiceAccountは権限がない
```

**After（修正後）：**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: deployment-manager
  namespace: default
rules:
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "create", "update"]
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: deployer
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: deployer-binding
  namespace: default
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: deployment-manager
subjects:
- kind: ServiceAccount
  name: deployer
  namespace: default
```

### 原因3：複数の名前空間にアクセスする場合にClusterRoleが必要

単一の名前空間内での操作はRoleで十分ですが、複数の名前空間にまたがったリソースへのアクセスや、クラスタ全体のリソース（Node、StorageClass等）にアクセスする場合はClusterRoleとClusterRoleBindingが必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: multi-ns-user
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
# このRoleはdefault名前空間のみ対象のため、他の名前空間ではアクセス不可
```

**After（修正後）：**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: multi-ns-user
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pod-reader-cluster
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["nodes"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: pod-reader-cluster-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: pod-reader-cluster
subjects:
- kind: ServiceAccount
  name: multi-ns-user
  namespace: default
```

## Minikube固有の注意点

**[RBAC](/glossary/rbac/)有効化の確認**

Minikubeではデフォルトでアドミッションコントローラーとして[RBAC](/glossary/rbac/)が有効です。[RBAC](/glossary/rbac/)が意図的に無効化されていないか確認するには、以下の[コマンド](/glossary/コマンド/)で確認できます。

```bash
minikube start --extra-config=apiserver.enable-admission-plugins=RBAC
```

既存のMinikubeクラスタで[RBAC](/glossary/rbac/)設定を確認する場合：

```bash
kubectl api-resources
kubectl describe clusterrole system:masters
```

**ServiceAccount[トークン](/glossary/トークン/)の確認**

Pod内から[API](/glossary/api/)[サーバー](/glossary/サーバー/)へアクセスする際、ServiceAccountの[トークン](/glossary/トークン/)が正しくマウントされているか確認します。

```bash
kubectl describe pod <pod-name> -n <namespace>
# Mounts セクションで /var/run/secrets/kubernetes.io/serviceaccount が存在するか確認
```

**[デバッグ](/glossary/デバッグ/)用の一時的なアクセス許可**

開発環境で素早く[テスト](/glossary/テスト/)する場合、クラスタロール`cluster-admin`をServiceAccountに一時的に付与することができます。本番環境では絶対に使用しないでください。

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: temp-admin-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- kind: ServiceAccount
  name: my-serviceaccount
  namespace: default
```

## それでも解決しない場合

**[ログ](/glossary/ログ/)の確認と[デバッグ](/glossary/デバッグ/)**

[Kubernetes](/glossary/kubernetes/)の詳細な[ログ](/glossary/ログ/)を確認するには、以下の[コマンド](/glossary/コマンド/)を実行します。

```bash
minikube logs
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
kubectl describe pod <pod-name> -n <namespace>
```

kubectl[コマンド](/glossary/コマンド/)実行時に詳細な情報を表示する場合：

```bash
kubectl get pods -v=8
```

**[権限](/glossary/権限/)の確認[コマンド](/glossary/コマンド/)**

特定のServiceAccountが持つ[権限](/glossary/権限/)を確認するには`kubectl auth can-i`[コマンド](/glossary/コマンド/)を使用します。

```bash
kubectl auth can-i get pods --as=system:serviceaccount:default:default
kubectl auth can-i create deployments --as=system:serviceaccount:default:deployer -n default
```

**公式リソース**

- [Kubernetes公式：RBAC認可](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Kubernetes公式：ServiceAccount](https://kubernetes.io/docs/concepts/configuration/assign-pod-node/)
- [Minikube公式ドキュメント](https://minikube.sigs.k8s.io/)

GitHub Issuesでは、Minikube固有の[RBAC](/glossary/rbac/)問題が報告されています。[エラーメッセージ](/glossary/エラーメッセージ/)の詳細な文言で検索すると、同じ問題を解決した事例が見つかる可能性があります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*