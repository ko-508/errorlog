---
title: "Kubernetes の 401 エラー：原因と解決策"
date: 2026-05-25
description: "Kubernetesで401エラーが発生するのは、APIサーバーへのリクエストに対して認証に失敗した状態を示します。認証トークンの有効期限切れ、認証情報の不足、または権限がないServiceAccountの使用が典型的な原因です。"
tags: ["Kubernetes"]
errorCode: "401"
lastmod: 2026-06-14
service: "Kubernetes"
error_type: "401"
components: ["Pod", "ServiceAccount", "ClusterRole", "Role"]
related_services: ["kubectl", "EKS", "GKE", "RBAC"]
trend_incident: true
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

```
kubectl logs pod-name -n default
Error from server (Unauthorized): pods "pod-name" is forbidden: User "system:serviceaccount:default:default" cannot get resource "pods" in API group "" in the namespace "default"
```

## よくある原因と解決手順

### 原因1：kubeconfig設定の無効化または存在しない認証情報

kubeconfig内の証明書や[トークン](/glossary/トークン/)が無効になっている、または参照しているファイルが削除されている場合に401[エラー](/glossary/エラー/)が発生します。クラスタをセットアップした時点での認証情報が失われたり、パスが誤っていたりすることが多いです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# ~/.kube/config
apiVersion: v1
clusters:
- cluster:
    certificate-authority: /etc/kubernetes/pki/ca.crt  # ファイルが削除済み
    server: https://10.0.0.1:6443
  name: my-cluster
contexts:
- context:
    cluster: my-cluster
    user: admin-user
  name: my-context
current-context: my-context
users:
- name: admin-user
  user:
    client-certificate: /home/user/.certs/client.crt  # パスが誤っている
    client-key: /home/user/.certs/client.key
```

**After（修正後）：**

```yaml
# ~/.kube/config
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTi...（Base64エンコードされた証明書）
    server: https://10.0.0.1:6443
  name: my-cluster
contexts:
- context:
    cluster: my-cluster
    user: admin-user
  name: my-context
current-context: my-context
users:
- name: admin-user
  user:
    client-certificate-data: LS0tLS1CRUdJTi...（Base64エンコードされた証明書）
    client-key-data: LS0tLS1CRUdJTi...（Base64エンコードされた秘密鍵）
```

### 原因2：ServiceAccountのRBAC権限不足

Podが[API](/glossary/api/)呼び出しを試みる際、割り当てられたServiceAccountに必要なRole/ClusterRoleバインディングがないか、RoleBinding自体が誤った権限設定になっている場合です。PodはServiceAccountの認証情報は持っていますが、その用途に対する[権限](/glossary/権限/)がないため401に見える実質403[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# ServiceAccountは存在するが、Role/RoleBindingがない
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
  namespace: production
---
# Podの定義
apiVersion: v1
kind: Pod
metadata:
  name: app-pod
  namespace: production
spec:
  serviceAccountName: app-sa
  containers:
  - name: app
    image: myapp:latest
    # Podがこの先APIサーバーにアクセスするが権限がない
```

**After（修正後）：**

```yaml
# ServiceAccountの定義
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
  namespace: production
---
# Roleの定義
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: app-role
  namespace: production
rules:
- apiGroups: [""]
  resources: ["pods", "services"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list"]
---
# RoleBindingでServiceAccountにRoleを割り当て
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-rolebinding
  namespace: production
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: app-role
subjects:
- kind: ServiceAccount
  name: app-sa
  namespace: production
---
# Podの定義
apiVersion: v1
kind: Pod
metadata:
  name: app-pod
  namespace: production
spec:
  serviceAccountName: app-sa
  containers:
  - name: app
    image: myapp:latest
```

### 原因3：トークンの有効期限切れまたは無効なトークン

OIDCやその他の外部認証を使用している場合、[ID](/glossary/id/)[トークン](/glossary/トークン/)やアクセストークンの有効期限が切れていることがあります。または、手動で作成した[トークン](/glossary/トークン/)が無効になっている可能性もあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 有効期限切れのトークンでログイン試行
kubectl config set-credentials user-with-expired-token \
  --token=eyJhbGciOiJSUzI1NiIsImtpZCI6IjEwIn0.eyJleHAiOjE2MDAwMDAwMDB9.invalid

# または環境変数で無効なトークンを指定
export KUBECONFIG=/path/to/config
# configファイルに無効なtoken文字列が記載されている
```

**After（修正後）：**

```bash
# 新しい有効なトークンを取得して設定（クラスタの管理者に確認）
kubectl config set-credentials user-with-valid-token \
  --token=$(kubectl create token <serviceaccount-name> -n <namespace>)

# または対話的にログイン情報を更新
aws eks update-kubeconfig --name <cluster-name> --region <region>
# またはGKEの場合
gcloud container clusters get-credentials <cluster-name> --zone <zone>
```

## ツール固有の注意点

### Kubernetes RBAC設定の検証

[エラー](/glossary/エラー/)が本当に401（認証失敗）なのか、403（認可失敗）なのかを区別することが重要です。以下の[コマンド](/glossary/コマンド/)で現在のユーザー・ServiceAccountの[権限](/glossary/権限/)を確認できます。

```bash
# 現在のコンテキストとユーザーを確認
kubectl config current-context
kubectl config get-contexts

# ServiceAccountのトークンを確認（Podから実行）
cat /run/secrets/kubernetes.io/serviceaccount/token

# 特定のServiceAccountに割り当てられたロールを確認
kubectl get rolebinding -n <namespace> -o wide
kubectl get clusterrolebinding -o wide | grep <serviceaccount-name>

# APIサーバーのアクセス権限を一覧表示
kubectl auth can-i --list --as=system:serviceaccount:<namespace>:<sa-name>
```

### マルチクラスタ環境での認証

複数の[Kubernetes](/glossary/kubernetes/)クラスタを管理する場合、kubeconfig内に複数のクラスタ定義が存在しており、誤ったコンテキストで操作している可能性があります。

```bash
# 設定されているすべてのクラスタを表示
kubectl config get-clusters

# 特定のクラスタに切り替え
kubectl config use-context <cluster-name>

# 切り替え後に接続確認
kubectl cluster-info
```

### 外部認証プロバイダー（OIDC）の場合

OIDCを使用している場合、[トークン](/glossary/トークン/)の更新が自動的に行われていない可能性があります。kubeloginなどのOIDCヘルパーが正しく設定されているか確認してください。

```bash
# OIDCの認証情報が正しく設定されているか確認
kubectl config view | grep oidc
```

## それでも解決しない場合

### デバッグコマンドと確認事項

```bash
# APIサーバーへの詳細なリクエストログを出力
kubectl -v=8 get pods

# 現在のユーザー情報を確認
kubectl whoami

# kube-apiserverのログを確認（クラスタ管理者権限が必要）
kubectl logs -n kube-system -l component=kube-apiserver --tail=100

# ノード上のkubelet認証ログを確認（マスターノードにSSH接続）
sudo journalctl -u kubelet -n 50
```

### 確認すべきログの場所

- **kube-apiserver [ログ](/glossary/ログ/)**：`/var/log/pods/kube-system_kube-apiserver-*/` またはコンテナログ
- **kubelet [ログ](/glossary/ログ/)**：`journalctl -u kubelet` または `/var/log/kubelet.log`
- **kubectl の[デバッグ](/glossary/デバッグ/)出力**：`-v=6` から `-v=10` のフラグを使用

### 公式ドキュメント参照

- [Kubernetesの認証ドキュメント](https://kubernetes.io/docs/reference/access-authn-authz/authentication/)
- [RBAC認可ドキュメント](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [kubeconfig ドキュメント](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/)

### コミュニティリソース

- [Kubernetes GitHub Issues](https://github.com/kubernetes/kubernetes/issues)：認証関連の既知問題を検索
- [Kubernetes Slack コミュニティ](https://kubernetes.slack.com/)：`#general` チャネルで質問

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*