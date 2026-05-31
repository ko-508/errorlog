---
title: "Minikube の 400 エラー：原因と解決策"
date: 2026-05-29
description: "Minikubeクラスターへのリクエスト形式が正しくない場合に発生します。YAMLマニフェストの構文エラーやkubectlオプションの誤りなど、Minikube 400エラーの原因と解決策を解説。"
tags: ["Minikube"]
errorCode: "400"
---
Minikubeクラスターへの[リクエスト](/glossary/リクエスト/)形式が正しくなく、[マニフェスト](/glossary/マニフェスト/)の[YAML](/glossary/yaml/)構文エラーやオプション指定の誤りが原因で発生するエラーです。本記事では原因特定と解決方法をステップバイステップで解説します。

## よくある原因

### kubectl applyするマニフェストのYAMLに構文エラーがある

[YAML](/glossary/yaml/)はインデント（スペース数）に厳密です。タブ文字を使ったり、インデント幅が不統一だったりすると、Minikubeは[リクエスト](/glossary/リクエスト/)を正しく解析できず400エラーが発生します。また、コロン（:）やハイフン（-）の位置がズレていても同様です。例えば `kind: Pod` と `kind:Pod` では後者が構文エラーになります。

### 必須フィールドが欠けているか型が間違っている

[Kubernetes](/glossary/kubernetes/)リソースには必ず指定する必須フィールドがあります。Deploymentなら `apiVersion`、`kind`、`metadata`、`spec` は必須です。また `replicas` は整数型なのに文字列 `"3"` で指定したり、`ports` の `containerPort` に文字列を指定すると、Minikubeが型の不一致を検出して400エラーを返します。

### minikubeコマンドのオプション指定が誤っている

`minikube start --vm-driver=docker` のように廃止されたオプションを使ったり、オプションの形式が間違っていたりすると400エラーが発生します。バージョンアップに伴いオプション名が変更されることもあるため、使用しているMinikubeバージョンに対応したオプションを確認する必要があります。

## 解決手順

### 1. マニフェストをdry-runで事前確認する

マニフェストファイルを実際に適用する前に、構文エラーと必須フィールドの不足を検出します。

```bash
kubectl apply --dry-run=client -f <マニフェスト.yaml>
```

例えば以下のコマンドを実行します。

```bash
kubectl apply --dry-run=client -f deployment.yaml
```

出力にエラーメッセージが表示されれば、その箇所を修正してください。成功時は `deployment.apps/example created (dry run)` と表示されます。

### 2. マニフェストのYAML構文をチェックする

[YAML](/glossary/yaml/)の妥当性を検証するオンラインツール（例：yamllint）を使うか、ローカルでlintツールを実行します。

```bash
# yamllintをインストール
pip install yamllint

# マニフェストをチェック
yamllint deployment.yaml
```

インデント幅は通常2スペースか4スペースで統一してください。タブ文字は使わないようにします。

### 3. 正しいオプションをminikube --helpで確認する

使用しているMinikubeのバージョンで有効なオプションを確認します。

```bash
minikube start --help
```

出力例から、現在有効なオプションを確認してください。例えば `--vm-driver` は古いバージョンのMinikubeでは `--driver` に変更されています。

### 4. kubectl explainで必須フィールドと型情報を確認する

リソースの必須フィールドと期待される型を確認します。

```bash
kubectl explain deployment.spec
```

このコマンドでDeploymentのspec以下に必須な構造を確認できます。より詳しい情報には以下を実行します。

```bash
kubectl explain deployment --recursive
```

### 5. マニフェスト例で正しい構造を確認する

最小限の正しい[マニフェスト](/glossary/マニフェスト/)の例です。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sample-deployment
  namespace: default
spec:
  replicas: 3
  selector:
    matchLabels:
      app: sample
  template:
    metadata:
      labels:
        app: sample
    spec:
      containers:
      - name: sample-container
        image: nginx:latest
        ports:
        - containerPort: 80
```

`replicas` は整数型、`containerPort` も整数型であることに注意してください。

### 6. Minikubeクラスターとkubectlの接続を確認する

クラスター側の問題でないか確認します。

```bash
minikube status
```

出力が以下のようになっていることを確認してください。

```
minikube: Running
kubelet: Running
apiserver: Running
```

もし何かが `Stopped` なら、以下を実行します。

```bash
minikube start
```

## それでも解決しない場合

以下の手段を試してください。

- **詳細なエラーメッセージを取得する**：[マニフェスト](/glossary/マニフェスト/)適用時に `-v=8` フラグを追加して詳細[ログ](/glossary/ログ/)を表示します。
```bash
kubectl apply -f deployment.yaml -v=8
```

- **Minikubeのバージョンを確認し更新する**：古いバージョンはオプション仕様が異なる場合があります。
```bash
minikube version
```

- **クラスターの再起動**：一時的な状態異常が原因の場合があります。
```bash
minikube delete
minikube start
```

- **kubectl describe podで詳細を確認する**：Pod適用後にエラーが出ている場合、以下を実行します。
```bash
kubectl describe pod <pod-name>
```

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*