---
title: "Minikube の 403 エラー：原因と解決策"
date: 2026-05-30
lastmod: 2026-05-31
description: "RBAC設定によりリソースへのアクセスが拒否された。Minikube 403 エラーの原因と解決策を解説します。"
tags: ["Minikube"]
errorCode: "403"
---
Minikubeでリソースへのアクセスを試みたときに403[エラー](/glossary/エラー/)が返される場合、[RBAC](/glossary/rbac/)（ロールベースアクセス制御）設定によって[アクセス権限](/glossary/アクセス権限/)が拒否されています。この[エラー](/glossary/エラー/)は開発環境でも本番環境でも発生し、適切な権限設定で解決します。

## よくある原因

**デフォルトのServiceAccountに必要な[権限](/glossary/権限/)がない**

Minikubeではデフォルトで`default` ServiceAccountが使用されますが、このアカウントには最小限の[権限](/glossary/権限/)しか持っていません。Podやその他のリソースに対して読み取り・書き込み操作を行おうとすると、デフォルトServiceAccountに対応する[権限](/glossary/権限/)がないため403[エラー](/glossary/エラー/)が発生します。

**RoleBindingまたはClusterRoleBindingが設定されていない**

Roleを作成しても、そのRoleをServiceAccountに紐付けるRoleBindingが存在しないと[権限](/glossary/権限/)は有効になりません。ServiceAccountとRoleの結合関係が欠落している場合、403[エラー](/glossary/エラー/)で操作が拒否されます。

**Minikubeのアドオン（[ダッシュボード](/glossary/ダッシュボード/)など）に必要な[権限](/glossary/権限/)が付与されていない**

Minikubeに含まれる[ダッシュボード](/glossary/ダッシュボード/)やメトリクス取得機能などのアドオンは、クラスタ内で特定のリソースにアクセスする必要があります。アドオンが有効化されていない、または不完全な権限設定で実行されている場合、[ダッシュボード](/glossary/ダッシュボード/)やメトリクス取得時に403[エラー](/glossary/エラー/)が発生します。

## 解決手順

**ステップ1：現在の[権限](/glossary/権限/)を確認する**

`kubectl auth can-i`[コマンド](/glossary/コマンド/)を使用して、現在のユーザーがリソースに対して特定の操作を実行できるかを確認します。

```bash
# デフォルトのdefault ServiceAccountで確認
kubectl auth can-i get pods --as=system:serviceaccount:default:default

# 特定の操作が許可されているか確認
kubectl auth can-i create deployments --as=system:serviceaccount:default:default

# 詳細な理由を表示
kubectl auth can-i get pods --as=system:serviceaccount:default:default -v=9
```

この[コマンド](/glossary/コマンド/)で`no`と返される場合、[権限](/glossary/権限/)がないことが確定します。

**ステップ2：必要な[権限](/glossary/権限/)を持つRoleを作成する**

アクセスしたいリソースに対するRoleを作成します。例えば、Podの読み取りと作成が必要な場合：

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: default
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["create", "update", "patch", "delete"]
```

この[YAML](/glossary/yaml/)を`role.yaml`として保存し、以下の[コマンド](/glossary/コマンド/)で適用します：

```bash
kubectl apply -f role.yaml
```

**ステップ3：RoleBindingを作成してServiceAccountに[権限](/glossary/権限/)を付与する**

作成したRoleを`default` ServiceAccountに紐付けます：

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: default
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: pod-reader
subjects:
- kind: ServiceAccount
  name: default
  namespace: default
```

この[YAML](/glossary/yaml/)を`rolebinding.yaml`として保存し、適用します：

```bash
kubectl apply -f rolebinding.yaml
```

**ステップ4：権限付与後の動作を確認する**

RoleBindingを適用した後、再度権限確認を実行します：

```bash
kubectl auth can-i get pods --as=system:serviceaccount:default:default
```

この[コマンド](/glossary/コマンド/)で`yes`と返されれば、[権限](/glossary/権限/)が正常に付与されています。

**ステップ5：Minikubeのアドオンを有効化する**

[ダッシュボード](/glossary/ダッシュボード/)やメトリクス関連の403[エラー](/glossary/エラー/)が発生している場合、アドオンを有効化します：

```bash
# ダッシュボードを有効化
minikube addons enable dashboard

# メトリクスサーバーを有効化（メトリクス取得エラーの場合）
minikube addons enable metrics-server

# 有効化されているアドオンを確認
minikube addons list
```

アドオン有効化後、以下の[コマンド](/glossary/コマンド/)で[ダッシュボード](/glossary/ダッシュボード/)にアクセスできます：

```bash
minikube dashboard
```

## それでも解決しない場合

権限確認とRoleBinding設定を実施しても403[エラー](/glossary/エラー/)が継続する場合は、以下の対応を検討してください。

ClusterRoleを使用する必要がないか確認します。特定のnamespaceに限定されず、全クラスタでのアクセスが必要な場合は、RoleとRoleBindingではなくClusterRoleとClusterRoleBindingを使用する必要があります。

```bash
# クラスタレベルの権限を確認
kubectl auth can-i get nodes --as=system:serviceaccount:default:default
```

Minikubeの[キャッシュ](/glossary/キャッシュ/)をリセットし、新規にクラスタを構築することで権限設定を初期化することも有効です：

```bash
minikube delete
minikube start
```

また、`kubectl describe rolebinding <name>`でRoleBinding設定を確認し、roleRefとsubjectsが正しく指定されているか検証してください。[YAML](/glossary/yaml/)形式の誤りやnamespace指定の誤りが権限付与失敗の原因になることがあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*