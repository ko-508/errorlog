---
title: "Kubernetes の 503 エラー：原因と解決策"
date: 2026-05-27
description: "Kubernetes環境で503エラーが発生するのは、クライアントからのリクエストに対応できるPodが存在しない、または全てのPodが利用不可状態にあることを示しています。"
tags: ["Kubernetes"]
errorCode: "503"
lastmod: 2026-06-14
service: "Kubernetes"
error_type: "503"
components: ["Pod", "Service", "Deployment", "Endpoints", "Readiness Probe"]
related_services: []
trend_incident: true
---

## エラーの概要

[Kubernetes](/glossary/kubernetes/)環境で503[エラー](/glossary/エラー/)が発生するのは、クライアントからの[リクエスト](/glossary/リクエスト/)に対応できるPodが存在しない、または全てのPodが利用不可状態にあることを示しています。Service経由でアクセスした際、[バックエンド](/glossary/バックエンド/)のPodがすべてダウンしていたり、起動途中だったり、リソース不足で応答できない状態で表示される[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)です。本[エラー](/glossary/エラー/)は一時的な問題である場合が多く、Podの自動復旧により解決することもありますが、根本原因の特定と対処が必要です。

## 実際のエラーメッセージ例

```
HTTP/1.1 503 Service Unavailable
Content-Type: text/html; charset=utf-8
Connection: close

<html>
<body><h1>503 Service Unavailable</h1>
No servers are available to handle this request.
</body></html>
```

```json
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "no endpoints available for service",
  "code": 503
}
```

## よくある原因と解決手順

### 原因1: Podがすべてダウン状態である

DeploymentやStatefulSetで定義したPodが何らかの理由でクラッシュしており、バックエンドサーバーが完全に停止している状態です。CrashLoopBackOff状態やExit Code 1などの異常終了が続いている場合に発生します。

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
      - name: app
        image: myapp:latest
        env:
        - name: DATABASE_URL
          value: "invalid-connection-string"
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
      - name: app
        image: myapp:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: connection-string
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
```

Podのステータスを確認する[コマンド](/glossary/コマンド/)：

```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
```

### 原因2: Readiness Probeに失敗している

Readiness Probeが設定されているものの、起動時間が長すぎたり、ヘルスチェックエンドポイントが応答しなかったりして、Podが「Ready」状態に到達していません。この場合、Podプロセスは動作していても、トラフィックがルーティングされません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: api-service:v1.0
        ports:
        - containerPort: 3000
        readinessProbe:
          httpGet:
            path: /ready
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 5
```

**After（修正後）：**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: api-service:v1.0
        ports:
        - containerPort: 3000
        readinessProbe:
          httpGet:
            path: /ready
            port: 3000
          initialDelaySeconds: 15
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        livenessProbe:
          httpGet:
            path: /health
            port: 3000
          initialDelaySeconds: 20
          periodSeconds: 10
```

Readiness Probeの状態を確認する[コマンド](/glossary/コマンド/)：

```bash
kubectl get pods -o wide -n <namespace>
kubectl describe pod <pod-name> -n <namespace> | grep -A 5 "Ready"
```

### 原因3: Serviceのエンドポイントが設定されていない

ServiceとPodのラベルセレクタが一致していない場合、Serviceは利用可能な[エンドポイント](/glossary/エンドポイント/)を持たず、トラフィックをルーティングできません。この場合、Service[オブジェクト](/glossary/オブジェクト/)は存在していても、[バックエンド](/glossary/バックエンド/)のPodが見つかりません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: backend
      tier: api
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: server
        image: backend-app:latest

---
# Service
apiVersion: v1
kind: Service
metadata:
  name: backend-service
spec:
  selector:
    app: backend
    tier: web
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
```

**After（修正後）：**

```yaml
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: backend
      tier: api
  template:
    metadata:
      labels:
        app: backend
        tier: api
    spec:
      containers:
      - name: server
        image: backend-app:latest
        ports:
        - containerPort: 8080

---
# Service
apiVersion: v1
kind: Service
metadata:
  name: backend-service
spec:
  selector:
    app: backend
    tier: api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
```

Serviceの[エンドポイント](/glossary/エンドポイント/)確認[コマンド](/glossary/コマンド/)：

```bash
kubectl get endpoints <service-name> -n <namespace>
kubectl describe service <service-name> -n <namespace>
```

## Kubernetes固有の注意点

### RBAC（Role-Based Access Control）による制限

ServiceAccountに対して必要なClusterRole/Roleが割り当てられていない場合、Podが外部リソースへのアクセスに失敗し、起動途中でクラッシュすることがあります。特に、PodがKubernetesAPI、CloudProvider [API](/glossary/api/)、その他外部サービスにアクセスする必要がある場合は、[RBAC](/glossary/rbac/)の設定を確認してください。

### リソースリクエスト・リミットの不足

CPUメモリリクエスト/リミットが不適切に設定されていると、Nodeのリソースが不足し、Podがスケジュールされなかったり、OOMKillerに強制終了されたりします。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
spec:
  containers:
  - name: app
    image: heavy-app:latest
    # リソース要件が記述されていない
```

**After（修正後）：**

```yaml
spec:
  containers:
  - name: app
    image: heavy-app:latest
    resources:
      requests:
        memory: "256Mi"
        cpu: "250m"
      limits:
        memory: "512Mi"
        cpu: "500m"
```

### Namespaceの隔離

異なる[Namespace](/glossary/namespace/)上のServiceにアクセスしようとしている場合、ServiceのFQDN（`<service-name>.<namespace>.svc.cluster.local`）を正確に指定する必要があります。

### Ingress設定の不備

IngressコントローラーがServiceを正しく検出できていない場合、Ingressを経由したアクセスで503が発生します。IngressのBackend設定とServiceのPort番号の一致を確認してください。

## それでも解決しない場合

### ログの確認

```bash
# Podのログを確認
kubectl logs <pod-name> -n <namespace> --tail=100

# 前回のクラッシュログを確認
kubectl logs <pod-name> -n <namespace> --previous

# 複数Podのログを同時に確認
kubectl logs -l app=<label-value> -n <namespace> --all-containers=true
```

### Eventの確認

```bash
kubectl describe node <node-name>
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

### kube-proxyのデバッグ

```bash
# kube-proxyのログを確認
kubectl logs -n kube-system -l k8s-app=kube-proxy

# ServiceのEndpointsが正しく作成されているか確認
kubectl get endpoints -A
```

### メトリクスの確認

Podのリソース使用率を確認して、リソース不足が原因でないか調査します。

```bash
kubectl top nodes
kubectl top pods -n <namespace>
```

### 公式ドキュメント参照

[Kubernetes](/glossary/kubernetes/)公式ドキュメントの「Debugging Services」セクションと「Troubleshooting」ガイドに、さらに詳細なトラブルシューティング手順が記載されています。また、使用している[Kubernetes](/glossary/kubernetes/)[バージョン](/glossary/バージョン/)に応じた互換性情報も確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*