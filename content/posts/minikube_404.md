---
title: "Minikube の 404 エラー：原因と解決策"
date: 2026-05-30
lastmod: 2026-06-14
description: "指定したKubernetesリソースが見つからない"
tags: ["Minikube"]
errorCode: "404"
service: "Minikube"
error_type: "404"
components: ["Pod", "Deployment", "Service", "Namespace"]
related_services: ["Kubernetes", "kubectl"]
---

## エラーの概要

Minikube で 404 [エラー](/glossary/エラー/)が発生した場合、指定した [Kubernetes](/glossary/kubernetes/) リソースが見つからないことを示しています。この[エラー](/glossary/エラー/)は Pod、Service、Deployment などのリソースに対して `kubectl` [コマンド](/glossary/コマンド/)で アクセスしようとした際に、指定した [Namespace](/glossary/namespace/) やリソース名が一致しないときに返されます。開発環境での検証時に頻繁に遭遇し、原因が特定できれば迅速に解決できる[エラー](/glossary/エラー/)です。

## 実際のエラーメッセージ例

```
Error from server (NotFound): pods "my-app" not found
```

```json
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "pods \"my-pod\" not found",
  "reason": "NotFound",
  "code": 404
}
```

```
error: the server doesn't have a resource type "ingres"
```

## よくある原因と解決手順

**原因1：[Namespace](/glossary/namespace/) の指定が間違っているか省略されている**

[Kubernetes](/glossary/kubernetes/) ではすべてのリソースは [Namespace](/glossary/namespace/) に属しています。`kubectl get pod` のように [Namespace](/glossary/namespace/) を明示しない[コマンド](/glossary/コマンド/)を実行すると、デフォルトの `default` [Namespace](/glossary/namespace/) のみを検索します。リソースが別の [Namespace](/glossary/namespace/)（例：`kube-system`、`monitoring`）に存在する場合、404 [エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
kubectl get pod my-app
# default namespace を検索するため、別の namespace に存在するリソースなら 404 になる
```

**After（修正後）：**

```bash
# 1. すべての namespace のリソースを確認
kubectl get pod --all-namespaces

# 2. 特定の namespace を指定して取得
kubectl get pod my-app -n kube-system

# 3. 現在のコンテキスト namespace を確認・変更
kubectl config get-contexts
kubectl config set-context --current --namespace=monitoring
```

**原因2：リソース名が誤字している、または存在しないリソースにアクセスしている**

Minikube に[デプロイ](/glossary/デプロイ/)したリソース名と kubectl [コマンド](/glossary/コマンド/)で指定したリソース名が完全に一致していない場合、404 [エラー](/glossary/エラー/)が発生します。大文字小文字の区別や、ハイフン・アンダースコア の違いも原因になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
kubectl get pod my_app
# deployment に "my-app" という名前で作成したが "my_app" で検索している

kubectl get pods myapp
# 実際に存在するリソース名は "my-app" だが "myapp" で検索している
```

**After（修正後）：**

```bash
# 1. 実際に存在するリソースを確認
kubectl get pod
kubectl get pods -o wide

# 2. 正確な名前で取得
kubectl get pod my-app

# 3. デプロイメント定義を確認して metadata.name を確認
kubectl get deployment -o yaml | grep "name:"
```

**原因3：リソースタイプの表記が誤っている（複数形・単数形・短縮形の混乱）**

`pod` と `pods`、`service` と `svc`、`ingress` と `ingres` など、リソースタイプの指定に誤りがあると 404 [エラー](/glossary/エラー/)が発生します。[Kubernetes](/glossary/kubernetes/) [API](/glossary/api/) はリソースタイプの表記に厳密です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
kubectl get ingres my-ingress
# "ingres" は存在しないリソースタイプ

kubectl get svc: my-service
# コロンで区切っている（誤り）
```

**After（修正後）：**

```bash
# 1. 正しいリソースタイプを使用
kubectl get ingress my-ingress

# 2. 短縮形と正式名を確認
kubectl api-resources | grep -i ingress

# 3. 正確に指定
kubectl get service my-service
# または短縮形
kubectl get svc my-service
```

**原因4：Minikube クラスタ自体が起動していないか、コンテキストが切り替わっている**

複数の [Kubernetes](/glossary/kubernetes/) クラスタ（他の minikube [インスタンス](/glossary/インスタンス/)、[Docker](/glossary/docker/) Desktop、EKS など）を使い分けている場合、現在のコンテキストが Minikube を指していないと、リソースは存在しても 404 [エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
minikube stop
kubectl get pod my-app
# クラスタが停止しているため接続できない

# または別クラスタのコンテキストに切り替わっている
kubectl get pod my-app
# 別のクラスタを対象としているため見つからない
```

**After（修正後）：**

```bash
# 1. Minikube の状態を確認・起動
minikube status
minikube start

# 2. 現在のコンテキストを確認
kubectl config current-context

# 3. Minikube コンテキストに切り替え
kubectl config use-context minikube

# 4. リソースの取得
kubectl get pod my-app
```

## ツール固有の注意点

**Minikube [ダッシュボード](/glossary/ダッシュボード/)でリソースを確認する**

`kubectl` [コマンド](/glossary/コマンド/)以外にも、Minikube [ダッシュボード](/glossary/ダッシュボード/)上で視覚的にリソースを確認できます。[コマンド](/glossary/コマンド/)が失敗する場合、[ダッシュボード](/glossary/ダッシュボード/)経由で同じリソースが表示されるかを確認することで、[Namespace](/glossary/namespace/) やリソース存在の問題を即座に判断できます。

```bash
minikube dashboard
```

[ダッシュボード](/glossary/ダッシュボード/)の左側メニューで [Namespace](/glossary/namespace/) を切り替え、該当するリソースが表示されるか確認してください。

**Minikube 内部のコンテナログを確認する**

404 [エラー](/glossary/エラー/)がリソースの作成失敗に由来する場合、Minikube ノード内のコンテナログを確認することで根本原因が判明することがあります。

```bash
minikube ssh
# Minikube 内のシェルに接続

docker ps
# 実行中のコンテナを確認

docker logs <container-id>
# コンテナログを確認
```

**Minikube の [DNS](/glossary/dns/) 設定による Service 検索の失敗**

Minikube 内の Service に対して Pod から接続できない場合、Minikube の [DNS](/glossary/dns/) [キャッシュ](/glossary/キャッシュ/)がリセットされていない可能性があります。Service を削除・再作成した直後に 404 が返される場合は、[DNS](/glossary/dns/) の キャッシュクリアを試みてください。

```bash
minikube ssh
sudo systemctl restart coredns
```

## それでも解決しない場合

**Minikube のデバッグログを有効にする**

詳細な[デバッグ](/glossary/デバッグ/)情報を取得する場合、kubectl [コマンド](/glossary/コマンド/)に `-v` フラグを付けることで [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)・[レスポンス](/glossary/レスポンス/)の詳細が表示されます。

```bash
kubectl get pod my-app -v=8
# API リクエスト・レスポンスの詳細が出力される
```

**Minikube のリソース定義を確認する**

Pod や Deployment の定義ファイルを確認し、[メタデータ](/glossary/メタデータ/)が正確に記述されているか検証してください。

```bash
kubectl get pod my-app -o yaml
# リソースの完全な定義を確認

kubectl describe pod my-app
# リソースの状態と関連イベントを確認
```

**公式ドキュメントとコミュニティリソース**

- [Kubernetes 公式ドキュメント：kubectl リファレンス](https://kubernetes.io/docs/reference/kubectl/)
- [Minikube 公式ドキュメント：Troubleshooting](https://minikube.sigs.k8s.io/docs/handbook/troubleshooting/)
- [GitHub：Minikube Issues](https://github.com/kubernetes/minikube/issues)

問題が解決しない場合、Minikube のバージョンアップや再インストールを検討してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*