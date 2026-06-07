---
title: "Kubernetes の 401 エラー：原因と解決策"
date: 2026-05-25
description: "Kubernetesで401エラーが発生するのは、APIサーバーへのリクエストに対して認証に失敗した状態を示します。認証トークンの有効期限切れ、認証情報の不足、または権限がないServiceAccountの使用が典型的な原因です。"
tags: ["Kubernetes"]
errorCode: "401"
lastmod: 2026-05-31
---

## エラーの概要

[Kubernetes](/glossary/kubernetes/)で401[エラー](/glossary/エラー/)が発生するのは、[API](/glossary/api/)[サーバー](/glossary/サーバー/)への[リクエスト](/glossary/リクエスト/)に対して[認証](/glossary/認証/)に失敗した状態を示します。[認証](/glossary/認証/)[トークン](/glossary/トークン/)の有効期限切れ、認証情報の不足、または[権限](/glossary/権限/)がないServiceAccountの使用が典型的な原因です。この[エラー](/glossary/エラー/)が出ると、kubectl[コマンド](/glossary/コマンド/)の実行やPodから[API](/glossary/api/)[サーバー](/glossary/サーバー/)へのアクセスが拒否されます。

## 実際のエラーメッセージ例

```
error: You must be logged in to the server (Unauthorized)
```

```json
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "Unauthorized",
  "reason": "Unauthorized",
  "code": 401
}
```

## よくある原因と解決手順

### 原因1: kubeconfig認証情報の有効期限切れ

[Kubernetes](/glossary/kubernetes/)の[認証](/glossary/認証/)[トークン](/glossary/トークン/)には有効期限があります。[トークン](/glossary/トークン/)が期限切れになると、[API](/glossary/api/)[サーバー](/glossary/サーバー/)が要求を拒否します。

**Before（[エラー](/glossary/エラー/)が起きる状態）:**

```bash
kubectl get pods
# error: You must be logged in to the server (Unauthorized)
```

**After（修正後）:**

```bash
# 現在のクラスタ情報を確認
kubectl cluster-info

# kubeconfig を更新（EKS の場合）
aws eks update-kubeconfig --region <your-region> --name <your-cluster>

# または GKE の場合
gcloud container clusters get-credentials <your-cluster> --region <your-region>

# 修正後、動作確認
kubectl get nodes
```

### 原因2: ServiceAccountの認証トークンが無効または不足している

Podが[API](/glossary/api/)[サーバー](/glossary/サーバー/)にアクセスする際、ServiceAccountの[トークン](/glossary/トークン/)が必要です。[トークン](/glossary/トークン/)がマウントされていない、または無効な場合に401が発生します。

**Before（[エラー](/glossary/エラー/)が起きる状態）:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  serviceAccountName: test-account
  automountServiceAccountToken: false  # トークンがマウントされない
  containers:
  - name: app
    image: curlimages/curl
    command: ["curl", "-v", "https://kubernetes.default.svc.cluster.local/api/v1/namespaces"]
```

**After（修正後）:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  serviceAccountName: test-account
  automountServiceAccountToken: true  # トークンをマウント
  containers:
  - name: app
    image: curlimages/curl
    command: ["curl", "-v", "https://kubernetes.default.svc.cluster.local/api/v1/namespaces", "--cacert", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt", "-H", "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"]
```

### 原因3: RBACロールバインディングが設定されていない

[Kubernetes](/glossary/kubernetes/)の[認証](/glossary/認証/)に成功しても[RBAC](/glossary/rbac/)（ロールベースアクセス制御）で[権限](/glossary/権限/)がない場合、403ではなく401として返されることがあります。ServiceAccountに適切なClusterRoleやRoleがバインドされていません。

**Before（[エラー](/glossary/エラー/)が起きる状態）:**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: minimal-account
  namespace: default
---
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: default
spec:
  serviceAccountName: minimal-account
  containers:
  - name: app
    image: curlimages/curl
    command: ["curl", "-v", "https://kubernetes.default.svc.cluster.local/api/v1/pods", "-H", "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)", "--cacert", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"]
```

**After（修正後）:**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: minimal-account
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pod-reader
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: pod-reader-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: pod-reader
subjects:
- kind: ServiceAccount
  name: minimal-account
  namespace: default
---
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: default
spec:
  serviceAccountName: minimal-account
  containers:
  - name: app
    image: curlimages/curl
    command: ["curl", "-v", "https://kubernetes.default.svc.cluster.local/api/v1/pods", "-H", "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)", "--cacert", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"]
```

## Kubernetes固有の注意点

**認証方式の確認:** [Kubernetes](/glossary/kubernetes/)は複数の認証方式をサポートしています。クラスタの認証設定を確認してください。

```bash
# APIサーバーの起動オプションを確認（マスターノードでの実行）
ps aux | grep kube-apiserver | grep -E "authentication|authorization"
```

**ServiceAccount [トークン](/glossary/トークン/)のマウント確認:** デフォルトではすべてのServiceAccountの[トークン](/glossary/トークン/)が自動的にPodにマウントされます。マウント先は `/var/run/secrets/kubernetes.io/serviceaccount/` です。

```bash
# Pod内でトークンを確認
kubectl exec <pod-name> -- cat /var/run/secrets/kubernetes.io/serviceaccount/token
```

**名前空間を指定した[認証](/glossary/認証/):** RoleBindingとClusterRoleBindingを混同しないでください。名前空間限定の[権限](/glossary/権限/)が必要な場合はRoleを、クラスタ全体なら ClusterRoleを使用します。

```bash
# RoleBindingの確認
kubectl get rolebindings --all-namespaces
kubectl get clusterrolebindings
```

## それでも解決しない場合

**kubectlの詳細[ログ](/glossary/ログ/)を確認:**

```bash
kubectl get pods -v 8
# または
export KUBECONFIG=~/.kube/config
kubectl get pods --alsologtostderr=true --v=10
```

**[API](/glossary/api/)[サーバー](/glossary/サーバー/)の[ログ](/glossary/ログ/)を確認（クラスタ管理者向け）:**

```bash
# マスターノードでのログ確認
journalctl -u kubelet -n 100
# または
kubectl logs -n kube-system <api-server-pod-name>
```

**kubeconfig の内容を検証:**

```bash
kubectl config view
# 認証情報の詳細を確認
kubectl auth can-i get pods --as=system:serviceaccount:default:default
```

公式ドキュメントの「[Authenticating](https://kubernetes.io/docs/reference/access-authn-authz/authentication/)」および「[RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)」ページで詳細な設定方法が記載されています。GitHub Issues で類似の事例を検索する際は、kubeconfig の認証方式（aws-iam-authenticator、gcloud、certificate など）を明示すると解決しやすくなります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*