---
title: "Kubernetes の 403 エラー：原因と解決策"
date: 2026-05-25
description: "Kubernetes の 403 エラーは「Forbidden」を意味し、リクエストの認証は成功しているものの、そのリソースに対する操作権限（RBAC: Role-Based Access Control）がないことを示します。"
tags: ["Kubernetes"]
errorCode: "403"
lastmod: 2026-06-14
service: "Kubernetes"
error_type: "403"
components: ["Pod", "Deployment", "ServiceAccount", "Role", "RoleBinding", "ClusterRole", "Namespace"]
related_services: ["RBAC", "kubectl"]
trend_incident: true
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
  "message": "deployments.apps \"nginx\" is forbidden: User \"system:serviceaccount:kube-system:default\" cannot create resource \"deployments\" in API group \"apps\" in the namespace \"kube-system\"",
  "reason": "Forbidden",
  "details": {
    "name": "nginx",
    "group": "apps",
    "kind": "deployments"
  },
  "code": 403
}
```

## よくある原因と解決手順

### 原因1: ServiceAccount に適切な Role が割り当てられていない

ServiceAccount は [Kubernetes](/glossary/kubernetes/) 内の[アカウント](/glossary/アカウント/)であり、Pod がリソースにアクセスする際に使用されます。この[アカウント](/glossary/アカウント/)に必要な[権限](/glossary/権限/)を持つ Role が紐付けられていない場合、403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-account
  namespace: default
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  template:
    spec:
      serviceAccountName: app-account
      containers:
      - name: app
        image: myapp:latest
```

**After（修正後）：**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-account
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: app-role
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods", "pods/logs"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-rolebinding
  namespace: default
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: app-role
subjects:
- kind: ServiceAccount
  name: app-account
  namespace: default
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  template:
    spec:
      serviceAccountName: app-account
      containers:
      - name: app
        image: myapp:latest
```

### 原因2: Namespace が異なる RoleBinding を参照している

RoleBinding は特定の [Namespace](/glossary/namespace/) に紐付きます。Pod が存在する [Namespace](/glossary/namespace/) と、RoleBinding が定義されている [Namespace](/glossary/namespace/) が異なる場合、[権限](/glossary/権限/)が認識されず 403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# namespace: kube-system に RoleBinding を定義
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-rolebinding
  namespace: kube-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: app-role
subjects:
- kind: ServiceAccount
  name: app-account
  namespace: default  # 異なる namespace の ServiceAccount を指定
---
# Deployment は default namespace に存在
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  template:
    spec:
      serviceAccountName: app-account
```

**After（修正後）：**

```yaml
# RoleBinding を正しい namespace に定義
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-rolebinding
  namespace: default  # Pod と同じ namespace に統一
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: app-role
subjects:
- kind: ServiceAccount
  name: app-account
  namespace: default
```

### 原因3: 必要な API グループが Role に指定されていない

[Kubernetes](/glossary/kubernetes/) リソースは [API](/glossary/api/) グループ（例: `apps`, `batch`, `networking.k8s.io`）に属しており、Role で適切な [API](/glossary/api/) グループを指定しなければアクセスできません。`apiGroups: [""]` は core [API](/glossary/api/) グループのみを対象とするため、拡張リソースには無効です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: app-role
  namespace: default
rules:
- apiGroups: [""]  # core API グループのみ
  resources: ["pods"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["deployments"]  # ❌ deployments は "apps" グループ
  verbs: ["get", "list"]
```

**After（修正後）：**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: app-role
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods", "pods/logs", "configmaps", "services"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets", "daemonsets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "create"]
```

### 原因4: デフォルト ServiceAccount が使用されている

Pod 定義で `serviceAccountName` を明示的に指定しない場合、デフォルトの `default` ServiceAccount が使用されます。この `default` [アカウント](/glossary/アカウント/)には通常、リソースへの[アクセス権限](/glossary/アクセス権限/)がないため、403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  template:
    spec:
      # serviceAccountName を指定していないため、
      # デフォルトの "default" ServiceAccount が使用される
      containers:
      - name: app
        image: myapp:latest
```

**After（修正後）：**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-account
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: app-role
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-rolebinding
  namespace: default
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: app-role
subjects:
- kind: ServiceAccount
  name: app-account
  namespace: default
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  template:
    spec:
      serviceAccountName: app-account  # 明示的に指定
      containers:
      - name: app
        image: myapp:latest
```

## Kubernetes 固有の注意点

### Cluster 全体に適用する権限が必要な場合は ClusterRole を使用

[Namespace](/glossary/namespace/) を超えて全体的な[権限](/glossary/権限/)が必要な場合、Role と RoleBinding ではなく ClusterRole と ClusterRoleBinding を使用します。例えば、全 [Namespace](/glossary/namespace/) の Pod を監視する監視エージェントや[ログ](/glossary/ログ/)収集エージェントは ClusterRole が必須です。

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: log-collector
rules:
- apiGroups: [""]
  resources: ["pods", "pods/logs"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: log-collector-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: log-collector
subjects:
- kind: ServiceAccount
  name: log-collector
  namespace: kube-system
```

### リソースの詳細なパーミッション制御（特定の Pod のみアクセス許可）

Role では特定の Pod 名を直接指定することはできませんが、Label Selector を活用することで粒度の細かい制御が可能です。ただし [RBAC](/glossary/rbac/) では Label ベースのフィルタリングが直接機能しないため、webhook ベースの[認可](/glossary/認可/)[ポリシー](/glossary/ポリシー/)を検討してください。

### 標準的な Role テンプレート（view, edit, admin）

[Kubernetes](/glossary/kubernetes/) は組み込みの ClusterRole を提供しており、これらを参考にすることで適切な権限構成を決定できます。

```bash
kubectl get clusterrole
```

`view`、`edit`、`admin` といった標準[ロール](/glossary/ロール/)が存在し、これらを RoleBinding で参照する方法も有効です。

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-view
  namespace: default
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: view
subjects:
- kind: ServiceAccount
  name: app-account
  namespace: default
```

## それでも解決しない場合

### kubectl auth can-i コマンドで権限を確認

特定の ServiceAccount が特定のアクションを実行可能か事前に確認できます。

```bash
kubectl auth can-i create deployments --as=system:serviceaccount:default:app-account -n default
```

成功時は `yes` が、失敗時は `no` が返されます。

### API サーバーのログを確認

Cluster 管理者は [API](/glossary/api/) [サーバー](/glossary/サーバー/)の[ログ](/glossary/ログ/)を調査して詳細な拒否理由を確認できます。

```bash
kubectl logs -n kube-system -l component=kube-apiserver | grep "Forbidden"
```

### kubectl describe で Role / RoleBinding を確認

定義されている Role や RoleBinding が正しく参照されているか確認します。

```bash
kubectl describe rolebinding app-rolebinding -n default
kubectl describe role app-role -n default
```

### 公式ドキュメント

- [Kubernetes RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [ServiceAccounts](https://kubernetes.io/docs/concepts/security/service-accounts/)
- [Managing Service Accounts](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*