---
title: "Kubernetes の 500 エラー：原因と解決策"
date: 2026-05-27
description: "Kubernetes環境で500エラーが発生した場合、APIサーバーまたはコントロールプレーンコンポーネントで予期しない内部エラーが生じています。このエラーはクラスタ全体の管理機能に影響を与える可能性があり、迅速な対応が必要です。"
tags: ["Kubernetes"]
errorCode: "500"
lastmod: 2026-05-31
---

## エラーの概要

[Kubernetes](/glossary/kubernetes/)環境で500[エラー](/glossary/エラー/)が発生した場合、[API](/glossary/api/)[サーバー](/glossary/サーバー/)またはコントロールプレーンコンポーネントで予期しない内部[エラー](/glossary/エラー/)が生じています。この[エラー](/glossary/エラー/)はクラスタ全体の管理機能に影響を与える可能性があり、迅速な対応が必要です。500[エラー](/glossary/エラー/)が返される場合、リソースの作成・更新・削除やクラスタ情報の取得が失敗することになります。

## 実際のエラーメッセージ例

```bash
$ kubectl apply -f deployment.yaml
Error from server (InternalError): error when creating "deployment.yaml": Internal error occurred: <unknown>
```

```json
{
  "apiVersion": "v1",
  "kind": "Status",
  "metadata": {},
  "status": "Failure",
  "message": "Internal error occurred: etcd server failed",
  "reason": "InternalError",
  "code": 500
}
```

## よくある原因と解決手順

### 1. etcdデータベースの障害

**なぜ発生するか**：etcdは[Kubernetes](/glossary/kubernetes/)クラスタの状態を保持する分散キー・バリューストアです。etcdが応答しない、ディスク満杯、または不整合が発生すると[API](/glossary/api/)[サーバー](/glossary/サーバー/)は500[エラー](/glossary/エラー/)を返します。

**Before（[エラー](/glossary/エラー/)が起きる状態）**：
```bash
$ kubectl get nodes
Error from server (InternalError): Internal error occurred: etcd server failed
```

**After（解決手順）**：
```bash
# 1. etcdのヘルスチェック実行
kubectl exec -it etcd-<master-node-name> -n kube-system -- etcdctl endpoint health

# 2. etcdメンバーの状態確認
kubectl exec -it etcd-<master-node-name> -n kube-system -- etcdctl member list

# 3. etcdポッドを再起動（自動復旧を待つ）
kubectl delete pod etcd-<master-node-name> -n kube-system

# 4. APIサーバーのログを確認
kubectl logs -n kube-system -l component=kube-apiserver --tail=100
```

### 2. APIサーバーのメモリ不足またはクラッシュ

**なぜ発生するか**：[API](/glossary/api/)[サーバー](/glossary/サーバー/)はクラスタのすべてのリソース定義をメモリに保持しています。大規模クラスタやメモリ制限が厳しい環境では、メモリ不足（OOM）によりプロセスがクラッシュし500[エラー](/glossary/エラー/)が多発します。

**Before（[エラー](/glossary/エラー/)が起きる状態）**：
```yaml
# メモリ制限が不足している設定例
apiVersion: v1
kind: Pod
metadata:
  name: kube-apiserver
  namespace: kube-system
spec:
  containers:
  - name: kube-apiserver
    image: k8s.gcr.io/kube-apiserver:v1.24.0
    resources:
      limits:
        memory: "256Mi"  # 不足している
      requests:
        memory: "128Mi"
```

**After（修正後）**：
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kube-apiserver
  namespace: kube-system
spec:
  containers:
  - name: kube-apiserver
    image: k8s.gcr.io/kube-apiserver:v1.24.0
    resources:
      limits:
        memory: "2Gi"  # 十分なメモリを確保
      requests:
        memory: "1Gi"
```

### 3. RBAC設定またはServiceAccountの権限不足

**なぜ発生するか**：[API](/glossary/api/)[サーバー](/glossary/サーバー/)が特定のリソースへの[アクセス権限](/glossary/アクセス権限/)を適切に検証できない、または[権限](/glossary/権限/)チェック中に[エラー](/glossary/エラー/)が発生すると500[エラー](/glossary/エラー/)が返されます。特にカスタムリソースに対して[RBAC](/glossary/rbac/)ルールが不完全な場合に顕著です。

**Before（[エラー](/glossary/エラー/)が起きる状態）**：
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: incomplete-role
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
  # watch権限が不足している
```

**After（修正後）**：
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: complete-role
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
- apiGroups: [""]
  resources: ["pods/status"]
  verbs: ["get"]
```

### 4. APIサーバーのプラグイン・アドミッション設定エラー

**なぜ発生するか**：MutatingAdmissionWebhookやValidatingAdmissionWebhookが正常に動作していない場合、または[Webhook](/glossary/webhook/)が応答しない場合、[API](/glossary/api/)[サーバー](/glossary/サーバー/)はすべての[リクエスト](/glossary/リクエスト/)に対して500[エラー](/glossary/エラー/)を返すことがあります。

**Before（[エラー](/glossary/エラー/)が起きる状態）**：
```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: failing-webhook
webhooks:
- name: validate.example.com
  clientConfig:
    url: "https://webhook.example.com:443/validate"
  rules:
  - operations: ["CREATE", "UPDATE"]
    apiGroups: [""]
    apiVersions: ["v1"]
    resources: ["pods"]
  failurePolicy: Fail  # Webhookが応答しないと全リクエストが失敗
```

**After（修正後）**：
```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: safe-webhook
webhooks:
- name: validate.example.com
  clientConfig:
    url: "https://webhook.example.com:443/validate"
    caBundle: <base64-encoded-ca-cert>
  rules:
  - operations: ["CREATE", "UPDATE"]
    apiGroups: [""]
    apiVersions: ["v1"]
    resources: ["pods"]
  failurePolicy: Ignore  # Webhook失敗時も処理を継続
  timeoutSeconds: 5
```

## Kubernetes固有の注意点

**kube-apiserverの[ログ](/glossary/ログ/)確認**：
```bash
# マスターノード上で直接ログを確認
journalctl -u kubelet -f | grep apiserver

# または kubeadm環境では
kubectl logs -n kube-system deployment/kube-apiserver --tail=200
```

**etcdの容量確認**：etcdのディスク使用率が95%以上に達するとアラームが発生し、書き込み操作が失敗します。
```bash
kubectl exec -it etcd-<master-node-name> -n kube-system -- etcdctl alarm list
```

**[API](/glossary/api/)[サーバー](/glossary/サーバー/)のフラグ確認**：不正なフラグや互換性のないバージョン指定も500[エラー](/glossary/エラー/)を引き起こします。
```bash
kubectl get pod -n kube-system kube-apiserver-<master-node-name> -o jsonpath='{.spec.containers[0].command}' | tr ',' '\n'
```

**[Webhook](/glossary/webhook/)・Admission制御チェーン**：複数の[Webhook](/glossary/webhook/)がある場合、どれが失敗しているか特定するために[Webhook](/glossary/webhook/)の[ログ](/glossary/ログ/)を確認してください。
```bash
kubectl logs -n kube-system -l component=webhook-server --tail=100
```

## それでも解決しない場合

**確認すべき[ログ](/glossary/ログ/)の場所**：
- マスターノードのsyslog：`journalctl -u kubelet -f`
- [API](/glossary/api/)サーバーコンテナログ：`kubectl logs -n kube-system -l component=kube-apiserver`
- etcd[ログ](/glossary/ログ/)：`kubectl logs -n kube-system -l component=etcd`
- kube-controller-manager[ログ](/glossary/ログ/)：`kubectl logs -n kube-system -l component=kube-controller-manager`

**デバッグコマンド**：
```bash
# APIサーバーの詳細情報取得
kubectl cluster-info dump --output-directory=./cluster-dump

# kubeAPIサーバーのメトリクス確認
kubectl top nodes
kubectl top pods -n kube-system

# イベント確認
kubectl get events -n kube-system --sort-by='.lastTimestamp'
```

**公式ドキュメント参照**：
- [Troubleshooting Kubernetes clusters](https://kubernetes.io/docs/tasks/debug-application-cluster/debug-cluster/)
- [API Server Authentication and Authorization](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)
- [Admission Controllers](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/)

**コミュニティリソース**：
- [Kubernetes GitHub Issues](https://github.com/kubernetes/kubernetes/issues)
- [Stack Overflow - kubernetes tag](https://stackoverflow.com/questions/tagged/kubernetes)
- [Kubernetes Slack Community](https://kubernetes.slack.com)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*