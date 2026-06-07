---
title: "Kubernetes の 503 エラー：原因と解決策"
date: 2026-05-27
description: "Kubernetes環境で503エラーが発生するのは、クライアントからのリクエストに対応できるPodが存在しない、または全てのPodが利用不可状態にあることを示しています。"
tags: ["Kubernetes"]
errorCode: "503"
lastmod: 2026-05-31
---

## エラーの概要

[Kubernetes](/glossary/kubernetes/)環境で503[エラー](/glossary/エラー/)が発生するのは、クライアントからの[リクエスト](/glossary/リクエスト/)に対応できるPodが存在しない、または全てのPodが利用不可状態にあることを示しています。Service経由でアクセスした際、[バックエンド](/glossary/バックエンド/)のPodがすべてダウンしていたり、起動途中だったり、リソース不足で応答できない状態で表示される[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)です。本[エラー](/glossary/エラー/)は一時的な問題である場合が多く、Podの自動復旧により解決することもあります。

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
  "reason": "ServiceUnavailable",
  "code": 503
}
```

## よくある原因と解決手順

### 原因1：対象ServiceのEndpointsが空の状態

**なぜ発生するか**
Serviceに紐づくPodがすべて停止しているか、Selectorラベルが一致していない場合、Endpointsが生成されず、トラフィックを受け取るPodが存在しない状態になります。

**Before（[エラー](/glossary/エラー/)が起きる状況）**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: app-service
spec:
  selector:
    app: myapp
  ports:
  - port: 80
    targetPort: 8080
---
apiVersion: v1
kind: Pod
metadata:
  name: app-pod
  labels:
    app: wrongapp  # Selectorと一致していない
spec:
  containers:
  - name: app
    image: myapp:latest
    ports:
    - containerPort: 8080
```

**After（修正後）**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: app-service
spec:
  selector:
    app: myapp
  ports:
  - port: 80
    targetPort: 8080
---
apiVersion: v1
kind: Pod
metadata:
  name: app-pod
  labels:
    app: myapp  # Selectorと一致させる
spec:
  containers:
  - name: app
    image: myapp:latest
    ports:
    - containerPort: 8080
```

**確認[コマンド](/glossary/コマンド/)**
```bash
kubectl get endpoints <service-name> -n <namespace>
# 出力にIPアドレスがあれば正常。<none>なら原因1の可能性が高い
```

### 原因2：Podの起動に失敗している、またはリソース不足

**なぜ発生するか**
Podが[イメージ](/glossary/イメージ/)の取得失敗、メモリ/CPU不足、Readiness Probeの失敗などによってRunning状態に至らず、トラフィック処理能力がない状態です。

**Before（[エラー](/glossary/エラー/)が起きる状況）**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-deployment
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
      - name: app
        image: myapp:nonexistent  # 存在しないイメージタグ
        ports:
        - containerPort: 8080
      resources:
        requests:
          memory: "512Mi"
          cpu: "500m"
```

**After（修正後）**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-deployment
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
      - name: app
        image: myapp:v1.0  # 正しいイメージタグ
        ports:
        - containerPort: 8080
      resources:
        requests:
          memory: "256Mi"
          cpu: "100m"
        limits:
          memory: "512Mi"
          cpu: "500m"
      readinessProbe:
        httpGet:
          path: /health
          port: 8080
        initialDelaySeconds: 5
        periodSeconds: 10
```

**確認[コマンド](/glossary/コマンド/)**
```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
```

### 原因3：IngressまたはLoadBalancerの設定ミス

**なぜ発生するか**
IngressやLoadBalancerの設定で、[バックエンド](/glossary/バックエンド/)Serviceへのルーティング先が間違っていたり、[ポート](/glossary/ポート/)番号が一致していない場合、有効な[バックエンド](/glossary/バックエンド/)に到達できません。

**Before（[エラー](/glossary/エラー/)が起きる状況）**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
spec:
  rules:
  - host: example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: wrong-service  # 存在しないService名
            port:
              number: 80
```

**After（修正後）**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
spec:
  rules:
  - host: example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: app-service  # 正しいService名
            port:
              number: 80
```

## Kubernetes固有の注意点

### Pod起動状態の確認
複数のPodが存在する場合、一部だけダウンしていると段階的に503が増加します。以下で全Pod状態を確認してください：

```bash
kubectl get pods -n <namespace> -o wide
kubectl top nodes  # ノードのリソース使用状況
kubectl top pods -n <namespace>  # Pod単位のリソース使用状況
```

### Livenessプローブ vs Readinessプローブ
- **Livenessプローブ失敗**：Podが再起動されるため、一時的に全Podがダウンして503発生
- **Readinessプローブ失敗**：Podは起動したままだが、Endpointsから除外されて503発生

アプリケーション起動時間が長い場合、`initialDelaySeconds`を適切に設定してください。

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30  # アプリの起動時間に合わせる
  periodSeconds: 10
  failureThreshold: 3
```

### RBAC権限とNetworkPolicy
ServiceAccountの権限不足やNetworkPolicyによる通信制限も503の原因になります。必要な[RBAC](/glossary/rbac/)設定を確認してください：

```bash
kubectl auth can-i get pods --as=system:serviceaccount:<namespace>:<sa-name>
kubectl get networkpolicies -n <namespace>
```

## それでも解決しない場合

### 確認すべきログとデバッグコマンド

```bash
# Pod内のアプリケーションログ確認
kubectl logs <pod-name> -n <namespace> --previous  # 前回のコンテナログ
kubectl logs <pod-name> -n <namespace> --tail=50

# イベント確認（Pod作成失敗の理由が表示される）
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -n <namespace> --sort-by='.lastTimestamp'

# Service設定の詳細確認
kubectl describe service <service-name> -n <namespace>

# Endpoints確認
kubectl get endpoints <service-name> -n <namespace> -o yaml
```

### 公式ドキュメント参照
- **[Kubernetes](/glossary/kubernetes/)デバッグガイド**：https://kubernetes.io/docs/tasks/debug/debug-application/
- **Pod Lifecycle とProbes**：https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#container-probes
- **Service and Ingress**：https://kubernetes.io/docs/concepts/services-networking/service/

### コミュニティリソース
[Kubernetes](/glossary/kubernetes/)の公式Slack（#kubernetes-users）、または GitHub Issues（https://github.com/kubernetes/kubernetes/issues）で同様の事例を検索することで、より詳細な解決策が見つかることがあります。特に「503 Service Unavailable Endpoints」で検索すると有用です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*