---
title: "Kubernetes の 400 エラー：原因と解決策"
date: 2026-05-25
description: "Kubernetes APIサーバーへのリクエストが不正な形式や内容であることを示すHTTP 400エラーです。マニフェストファイルの構文エラー、API仕様に違反するフィールド値、または不完全なリクエストボディが原因となります。"
tags: ["Kubernetes"]
errorCode: "400"
lastmod: 2026-05-31
service: "Kubernetes"
error_type: "400"
components: ["Pod", "Deployment", "Service"]
related_services: ["YAML", "HTTP", "API"]
trend_incident: true
---

## エラーの概要

[Kubernetes](/glossary/kubernetes/) [API](/glossary/api/)[サーバー](/glossary/サーバー/)への[リクエスト](/glossary/リクエスト/)が不正な形式や内容であることを示す[HTTP](/glossary/http/) 400[エラー](/glossary/エラー/)です。マニフェストファイルの構文[エラー](/glossary/エラー/)、[API](/glossary/api/)仕様に違反するフィールド値、または不完全な[リクエストボディ](/glossary/リクエストボディ/)が原因となります。この[エラー](/glossary/エラー/)はクラスタとの[通信](/glossary/通信/)に成功した後、[サーバー](/glossary/サーバー/)側で[リクエスト](/glossary/リクエスト/)の妥当性検証に失敗したときに発生する重要な診断シグナルです。

## 実際のエラーメッセージ例

```json
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "error validating data: ValidationError(Pod.spec.containers[0].resources.limits): invalid type for io.k8s.api.core.v1.ResourceList: got \"string\", expected \"object\"",
  "reason": "BadRequest",
  "code": 400
}
```

```bash
error: error validating "deployment.yaml": error validating data: 
[ValidationError(Deployment.spec.template.spec.containers[0].ports[0].containerPort): 
invalid type for io.k8s.api.core.v1.ContainerPort: got "string", expected "integer", 
ValidationError(Deployment.spec.template.spec.containers[0].image): string length must be non-empty]
```

## よくある原因と解決手順

### 原因1: YAML構文エラーまたはフィールド型の不一致

**なぜ発生するか：** [Kubernetes](/glossary/kubernetes/)マニフェストファイルで、数値型フィールドを文字列で指定したり、[オブジェクト](/glossary/オブジェクト/)型フィールドにスカラー値を渡したりするときに発生します。特に[ポート](/glossary/ポート/)番号やリソース制限でこの問題が頻発します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx-pod
spec:
  containers:
  - name: nginx
    image: nginx:latest
    ports:
    - containerPort: "8080"  # 文字列型で指定
    resources:
      limits:
        memory: 512Mi          # オブジェクト型だが不正
        cpu: "1"              # 数値型だが文字列
```

**After（修正後）：**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx-pod
spec:
  containers:
  - name: nginx
    image: nginx:latest
    ports:
    - containerPort: 8080      # 整数型で指定
    resources:
      limits:
        memory: 512Mi
        cpu: "1"               # CPU値は文字列でも有効
      requests:
        memory: 256Mi
        cpu: "500m"
```

### 原因2: 必須フィールドの欠落

**なぜ発生するか：** [Kubernetes](/glossary/kubernetes/)リソースの必須フィールド（例：`metadata.name`、[コンテナ](/glossary/コンテナ/)の`image`）が定義されていない場合に発生します。[API](/glossary/api/)[サーバー](/glossary/サーバー/)は最小限のリソース定義すら受け付けません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web-container
        # imageフィールドが欠落
        ports:
        - containerPort: 80
```

**After（修正後）：**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web-container
        image: nginx:1.21      # 必須フィールドを追加
        ports:
        - containerPort: 80
```

### 原因3: APIバージョンまたはリソース種別の不一致

**なぜ発生するか：** 廃止された[API](/glossary/api/)バージョンを使用したり、クラスタにインストールされていないカスタムリソース定義（CRD）にアクセスしたりするときに発生します。[Kubernetes](/glossary/kubernetes/) 1.16以降でv1beta1 extensionsが廃止されるなど、バージョン間での互換性問題が頻繁に起きます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```bash
kubectl apply -f - <<EOF
apiVersion: extensions/v1beta1  # Kubernetes 1.16+で廃止
kind: Deployment
metadata:
  name: old-deployment
spec:
  replicas: 2
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
      - name: myapp
        image: myapp:1.0
EOF
```

**After（修正後）：**
```bash
kubectl apply -f - <<EOF
apiVersion: apps/v1  # 現在サポートされているバージョン
kind: Deployment
metadata:
  name: old-deployment
spec:
  replicas: 2
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
      - name: myapp
        image: myapp:1.0
EOF
```

### 原因4: セレクタラベルの不一致

**なぜ発生するか：** Deployment、Service、StatefulSetなどで定義した`selector`のラベルが、Pod テンプレートの`labels`と一致していない場合に発生します。これにより、リソースが自身が管理すべきポッドを識別できず、検証[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-deploy
spec:
  selector:
    matchLabels:
      app: myapp
      environment: production
  template:
    metadata:
      labels:
        app: myapp
        # environmentラベルが欠落
        version: v1
```

**After（修正後）：**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-deploy
spec:
  selector:
    matchLabels:
      app: myapp
      environment: production
  template:
    metadata:
      labels:
        app: myapp
        environment: production  # セレクタと一致させる
        version: v1
```

## Kubernetes固有の注意点

### ServiceAccountとRBAC設定
400[エラー](/glossary/エラー/)は[認可](/glossary/認可/)[エラー](/glossary/エラー/)（403）ではなく検証[エラー](/glossary/エラー/)ですが、ServiceAccountが適切に設定されていない場合、リソース作成時に引き続き400が発生することがあります。`kubectl auth can-i`[コマンド](/glossary/コマンド/)で権限確認を併せて実施してください。

```bash
kubectl auth can-i create deployments --as=system:serviceaccount:default:my-sa -n default
```

### Namespace指定の欠落
リソース定義で`metadata.namespace`を明示しない場合、デフォルト[Namespace](/glossary/namespace/)に作成されます。別の[Namespace](/glossary/namespace/)に配置する場合は、明示的に指定するか、`-n`フラグを使用してください。

```bash
kubectl apply -f deployment.yaml -n production
```

### CRD（CustomResourceDefinition）のバージョン不一致
インストール済みのCRDのバージョンと、マニフェストファイルの[API](/glossary/api/)バージョンが一致していない場合、400[エラー](/glossary/エラー/)が発生します。`kubectl api-resources`で確認可能です。

```bash
kubectl api-resources | grep customresource
```

### 環境変数置換の不完全性
テンプレート化されたマニフェストファイルで、プレースホルダーが置換されないまま送信された場合、不正な[YAML](/glossary/yaml/)値として認識されます。envsubstやkustomizeを使用する際は、置換前のファイルをバイパスしないよう注意してください。

## それでも解決しない場合

### ログ確認とデバッグコマンド

[API](/glossary/api/)[サーバー](/glossary/サーバー/)の[ログ](/glossary/ログ/)を直接確認して、より詳細な[エラーメッセージ](/glossary/エラーメッセージ/)を取得してください。

```bash
# クラスタログの確認（マネージドKubernetesの場合はプロバイダーのコンソール使用）
kubectl logs -n kube-system deployment/kube-apiserver --tail=100

# リクエストの詳細を確認
kubectl apply -f deployment.yaml -v=8  # 最高レベルのverbosity

# マニフェストの検証（サーバーに送信前にドライラン）
kubectl apply -f deployment.yaml --dry-run=client -o yaml
```

### 公式ドキュメントへの参照

- **[Kubernetes](/glossary/kubernetes/) [API](/glossary/api/)仕様** - https://kubernetes.io/docs/reference/kubernetes-api/ で各リソースの[スキーマ](/glossary/スキーマ/)定義を確認
- **[API](/glossary/api/)[サーバー](/glossary/サーバー/)の検証ルール** - https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#validation
- **廃止[API](/glossary/api/)バージョンのマイグレーション** - https://kubernetes.io/docs/reference/using-api/deprecation-guide/

### コミュニティリソース

問題が解決しない場合は、以下で検索してください。

- **[Kubernetes](/glossary/kubernetes/) GitHub Issues** - https://github.com/kubernetes/kubernetes/issues （[API](/glossary/api/)バージョンやバリデーション関連のバグ報告）
- **Stack Overflow** - `[kubernetes] 400` タグでの質問検索
- **CNCF Slack** - #kubernetes-users チャネルでの相談

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*