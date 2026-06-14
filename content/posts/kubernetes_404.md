---
title: "Kubernetes の 404 エラー：原因と解決策"
date: 2026-05-26
description: "Kubernetesの404エラーは、APIサーバーが指定したリソース（Pod・Service・Deploymentなど）や、アクセスしようとしたエンドポイントが存在しないことを示します。"
tags: ["Kubernetes"]
errorCode: "404"
lastmod: 2026-06-14
service: "Kubernetes"
error_type: "404"
components: ["Pod", "Service", "Deployment", "Namespace", "ConfigMap", "Secret"]
related_services: ["kubectl"]
trend_incident: true
---

## エラーの概要

Kubernetesの404エラーは、APIサーバーが指定したリソース（Pod・Service・Deploymentなど）やアクセスしようとしたエンドポイントが存在しないことを示します。`kubectl`コマンド実行時やKubernetes APIへのHTTPリクエスト時に発生し、リソースの削除後のアクセスや存在しないNamespaceへのクエリで特に見られます。このエラーはデータ消失を意味しませんが、リソースが実際に動作していない状態を示しているため、早期の対応が必要です。

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
  "message": "pods \"web-server\" not found",
  "reason": "NotFound",
  "details": {
    "name": "web-server",
    "kind": "pods"
  },
  "code": 404
}
```

## よくある原因と解決手順

### 原因1：リソースが削除されている

**なぜ発生するか：**
Podやサービスが意図せず削除されたり、別のプロセスによって削除された後もアクセスしようとした場合に発生します。Deployment経由でPodを管理している場合、Podは自動的に再作成されることもあります。

**Before（エラーが起きるコード）：**

```bash
kubectl delete pod my-app
kubectl get pod my-app
# Error: pods "my-app" not found
```

**After（修正後）：**

```bash
# リソースが本来管理されるべきDeploymentから再作成させる
kubectl get deployment
kubectl describe deployment my-app-deployment
# または新しいPodを作成
kubectl run my-app --image=my-image:latest
```

### 原因2：Namespaceの指定ミス

**なぜ発生するか：**
リソースがあるNamespaceと異なるNamespaceを指定した場合、APIサーバーはそのNamespace内のリソースを探すため404となります。デフォルトの`default` Namespaceではなく、`production`や`staging`などのNamespaceにリソースが存在することを見落とすことが多くあります。

**Before（エラーが起きるコード）：**

```bash
# リソースが production Namespace に存在するのに default で検索
kubectl get pod my-app
# Error: pods "my-app" not found

# 実際のリソースの場所
kubectl get pod my-app -n production
# NAME      READY   STATUS    RESTARTS   AGE
# my-app    1/1     Running   0          2d
```

**After（修正後）：**

```bash
# 常に -n フラグで正しい Namespace を指定
kubectl get pod my-app -n production

# または kubectl コンテキストのデフォルト Namespace を変更
kubectl config set-context --current --namespace=production
```

### 原因3：APIバージョンやリソースタイプの指定ミス

**なぜ発生するか：**
KubernetesはAPIバージョンの進化に伴い、リソースの名称や形式が変更されることがあります。存在しないAPIバージョン（例：`apiVersion: v1beta1`）や誤ったリソースタイプを指定した場合、APIサーバーはそれを認識できません。

**Before（エラーが起きるコード）：**

```yaml
apiVersion: apps/v1beta1
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
      - name: my-app
        image: my-image:latest
```

**After（修正後）：**

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
      - name: my-app
        image: my-image:latest
```

### 原因4：RBAC（Role-Based Access Control）による権限不足

**なぜ発生するか：**
RBACが有効な環境で、ユーザーまたはServiceAccountが特定のリソースへのアクセス権限を持っていない場合、APIサーバーはそのリソースを見つけられないように振る舞うことがあります。これはセキュリティ上の理由で、存在しないリソースと同じ404エラーを返します。

**Before（エラーが起きるコード）：**

```bash
# ServiceAccount に Pod 閲覧権限がない場合
kubectl get pod --as=system:serviceaccount:default:my-app-sa
# Error from server (NotFound): pods not found
```

**After（修正後）：**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-viewer
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pod-viewer-binding
  namespace: default
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: pod-viewer
subjects:
- kind: ServiceAccount
  name: my-app-sa
  namespace: default
```

## ツール固有の注意点

**Namespace分離の設計：**
Kubernetesでは複数のNamespaceを使用する場合、デフォルトで異なるNamespace間のリソースには直接アクセスできません。ServiceDiscoveryを使用する場合は、DNSの形式が`<service-name>.<namespace-name>.svc.cluster.local`となります。別のNamespaceのServiceにアクセスする際には、このFQDNを明記する必要があります。

**Ingress・Service・Pod間の連携エラー：**
IngressがServiceを参照する際、存在しないServiceを指定すると404が発生します。Ingressが設定されていても、バックエンドのServiceやPodが削除されると、トラフィックは応答できなくなります。`kubectl describe ingress`でバックエンドの状態を確認してください。

**CRD（Custom Resource Definition）のコンテキスト：**
カスタムリソースを使用する場合、CRDが登録されていないクラスタではそのリソースを取得する際に404が発生します。`kubectl get crd`でCRDが存在するか確認し、必要に応じてCRD定義をクラスタに適用してください。

**クラスタバージョン間の互換性：**
異なるKubernetesバージョン間でマニフェストファイルを使用する場合、新しいバージョン特有のAPIエンドポイントが古いクラスタに存在しないことがあります。`kubectl api-resources`コマンドで現在のクラスタで利用可能なリソースを確認してください。

## それでも解決しない場合

**ログとデバッグコマンド：**
APIサーバーのログを確認して詳細なエラー情報を取得します。

```bash
# リソースが本当に存在しないか確認
kubectl get all -n <namespace>

# 別の Namespace を含めてすべてのリソースを検索
kubectl get pod --all-namespaces | grep <resource-name>

# 特定のリソースの詳細情報を確認
kubectl describe pod <pod-name> -n <namespace>

# APIサーバーのログを確認（マスターノードへのアクセスが必要）
kubectl logs -n kube-system -l component=kube-apiserver
```

**Kubernetesダッシュボード・GUIツール：**
`kubectl proxy`を使用してダッシュボードにアクセスし、リソースが実際に存在するか視覚的に確認することもできます。

```bash
kubectl proxy
# http://localhost:8001/ui にアクセス
```

**公式ドキュメント：**
Kubernetesの公式リファレンス「API Resources」や「Accessing the Kubernetes API」のセクションで、各APIバージョンと利用可能なエンドポイントを確認してください。また「RBAC Authorization」ドキュメントで権限設定の詳細を参照してください。

**コミュニティリソース：**
Kubernetes GitHubのIssuesセクション（`kubernetes/kubernetes`リポジトリ）やStackOverflow、Kubernetes Slackコミュニティで類似事例を検索することで、複雑な設定ミスの解決策を見つけることができます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*