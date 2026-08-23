---
title: "Kubernetes の 422 エラー：原因と解決策"
date: 2026-08-03
description: "Kubernetes の 422 は区分 Invalid で、details.causes にどのフィールドがなぜ駄目かが機械可読で入ります。一方、知らないフィールドや型違いは 422 ではなく 400 です。読めなかったのが 400、読めたが内容が通らなかったのが 422、という境界が切り分けの起点になります。"
tags: ["Kubernetes"]
errorCode: "422"
lastmod: 2026-08-03
service: "Kubernetes"
error_type: "422"
components: ["kube-apiserver", "kubectl"]
related_services: ["kubectl", "CustomResourceDefinition"]
trend_incident: false
---

## 冒頭まとめ

[Kubernetes](/glossary/kubernetes/) の 422 Unprocessable Entity は、区分が `Invalid` の[エラー](/glossary/エラー/)です。意味は明快で、**内容は読めたが、検証を通らなかった**という状態を指します。

この[エラー](/glossary/エラー/)の扱いやすさは、応答の `details.causes` にあります。実装を読むと、検証の[エラー](/glossary/エラー/)一覧がそのまま `causes` に変換され、各要素に **どの[フィールド](/glossary/フィールド/)か（`field`）** と **なぜ駄目か（`reason`）** が入ります。`reason` に入る値は決まっていて、必須項目の欠落なら `FieldValueRequired`、値が不正なら `FieldValueInvalid`、対応していない値なら `FieldValueNotSupported`、禁止された操作なら `FieldValueForbidden` といった具合です。つまり、**推測は不要です**。どこがなぜ駄目かは応答に書かれています。

もう1つ、実務で最も誤解されている点があります。**知らない[フィールド](/glossary/フィールド/)を書いても 422 にはなりません**。公式文書には、検証の水準を厳格にした場合、未知または重複した[フィールド](/glossary/フィールド/)を検出すると **400 Bad Request** で拒否する、と明記されています。さらに但し書きとして、既知の[フィールド](/glossary/フィールド/)に型の違う値を入れた場合も 400 になる、とも書かれています。

したがって境界はこうなります。**読めなかったのが 400、読めたが内容が通らなかったのが 422**。綴りを間違えた、型を間違えた、というよくある失敗は 400 側に落ちます。422 が返っているなら、書式の問題ではなく意味の問題です。

## エラーの概要

応答の構造は次の形です。`details.causes` が本体で、`message` はその要約にすぎません。

```json
{
  "kind": "Status",
  "status": "Failure",
  "message": "Deployment.apps \"web\" is invalid: spec.selector: Invalid value: ...: field is immutable",
  "reason": "Invalid",
  "details": {
    "group": "apps",
    "kind": "Deployment",
    "name": "web",
    "causes": [
      {
        "reason": "FieldValueInvalid",
        "field": "spec.selector",
        "message": "Invalid value: ...: field is immutable"
      }
    ]
  },
  "code": 422
}
```

`kubectl` からの見え方には特徴があります。実装を読むと、区分が `Invalid` の場合だけ専用の整形が行われ、他の[エラー](/glossary/エラー/)のような `Error from server (...)` の形にはなりません。

```text
The Deployment "web" is invalid: spec.selector: Invalid value: ...: field is immutable
```

対象の種類と名前を頭に置き、`causes` を箇条書きで並べる形です。**`Error from server` が付いていない[エラー](/glossary/エラー/)は 422 の可能性が高い**、という見分け方が成り立ちます。

## まず最初に：causes の field と reason を読む

第一に、`details.causes` を開きます。ここに、問題のある[フィールド](/glossary/フィールド/)が列挙されています。複数ある場合はすべて出ます。

第二に、各要素の `field` を読みます。[フィールド](/glossary/フィールド/)の位置が完全な経路で書かれているため、[ファイル](/glossary/ファイル/)のどこを直すかがそのまま分かります。

第三に、`reason` を読みます。`FieldValueRequired` なら書き忘れ、`FieldValueInvalid` なら値そのものの問題、`FieldValueNotSupported` なら選択肢の外、`FieldValueForbidden` なら状況的に許されない操作です。

第四に、`message` の末尾を見ます。`field is immutable` とあれば、値が悪いのではなく**変更してはいけない項目を変えた**という意味です。

## よくある原因と解決手順

### 原因1：不変のフィールドを変更しようとしている

実務で最も多く、そして最も紛らわしい形です。実装では、変更不可の項目に手が入ると `field is immutable` という文言の検証[エラー](/glossary/エラー/)が作られ、区分は `FieldValueInvalid` になります。**値が不正だと言われますが、値そのものは正しい**のです。問題は、その項目が変更を受け付けないことです。

代表例は Deployment の `spec.selector` です。

**Before（版の情報を選別条件に含める）：**

```yaml
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: web
      app.kubernetes.io/version: "1.2.3"   # 更新のたびに変わる
```

この書き方では、版を上げるたびに選別条件が変わり、そのたびに 422 になります。

**After（変わらない値だけで選別する）：**

```yaml
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: web
  template:
    metadata:
      labels:
        app.kubernetes.io/name: web
        app.kubernetes.io/version: "1.2.3"   # 印としては付けてよい
```

すでに作成済みの対象で変更が必要な場合、更新では通りません。[削除](/glossary/削除/)して作り直すか、別の名前で新しく作ることになります。`kubectl apply` を繰り返しても状況は変わりません。

Deployment の選別条件のほか、Job の雛形、PersistentVolumeClaim の一部の項目なども同じ扱いです。共通の見分け方は、`message` の末尾が `field is immutable` であることです。

### 原因2：必須項目が欠けている

`reason` が `FieldValueRequired` の場合です。`field` に欠けている項目の経路がそのまま入ります。

```text
The Pod "app" is invalid: spec.containers[0].image: Required value
```

`causes` は複数返るため、一度にすべての不足を確認できます。1つ直しては試す、という進め方をせず、返ってきた一覧をまとめて直すほうが早く終わります。

### 原因3：値が仕様の範囲外

`reason` が `FieldValueInvalid`、`FieldValueNotSupported`、`FieldValueTooLong` などの場合です。名前の形式違反はこの系統でよく見ます。

```text
The Service "My-App" is invalid: metadata.name: Invalid value: "My-App":
  a lowercase RFC 1123 subdomain must consist of lower case alphanumeric
  characters, '-' or '.', ...
```

`FieldValueNotSupported` の場合、多くは許される値の一覧が `message` に併記されます。選択肢を調べ直す前に、まず[エラー](/glossary/エラー/)本文を読んでください。

カスタム資源でも同じ仕組みが働きます。実装を追うと、独自資源の検証も検証[エラー](/glossary/エラー/)一覧として返され、同じ 422 に変換されます。定義側に検証規則を書いている場合、その違反もここに現れます。

### 原因4：400 を 422 だと思っている

冒頭で述べた境界です。次の3つは 422 ではなく 400 になります。

1つ目は、知らない[フィールド](/glossary/フィールド/)を書いた場合。公式文書によれば、検証の水準は `Ignore`・`Warn`・`Strict` の3つがあり、`Strict` では未知または重複した[フィールド](/glossary/フィールド/)を検出すると 400 で拒否されます。`kubectl` の既定は `--validate=true`、つまり厳格な検証です。

2つ目は、同じ[フィールド](/glossary/フィールド/)を重複して書いた場合。これも同じ扱いです。

3つ目は、既知の[フィールド](/glossary/フィールド/)に型の違う値を入れた場合。公式文書の但し書きに、この場合は 400 が返り、しかも未知[フィールド](/glossary/フィールド/)の情報は示されず、最初に遭遇した致命的な[エラー](/glossary/エラー/)だけが報告される、と書かれています。

```bash
# 未知フィールドの検出を警告に留める（400 を回避して内容の検証まで進める）
kubectl apply -f manifest.yaml --validate=warn
```

綴り間違いを疑うなら 400 側、意味の間違いを疑うなら 422 側。この振り分けを最初に済ませると、調べる場所を間違えません。

### 原因5：適用する前に検出する

422 は、実際に適用しなくても検出できます。[サーバー](/glossary/サーバー/)側で検証だけを行う指定があります。

```bash
# 検証だけ行い、実際には変更しない
kubectl apply -f manifest.yaml --dry-run=server

# 手元だけの確認（サーバー側の検証は行われない）
kubectl apply -f manifest.yaml --dry-run=client
```

重要なのは、手元だけの確認では不変[フィールド](/glossary/フィールド/)の違反を検出できないことです。既存の状態と比較する必要があるためです。[自動化](/glossary/自動化/)の中で事前確認を入れるなら、[サーバー](/glossary/サーバー/)側の指定を使ってください。

## 補足：似ているが別のもの

内容が読めない場合は 400 です。書式の壊れ、未知の[フィールド](/glossary/フィールド/)、重複、型違いがここに入ります。実装でも、復号に失敗した場合は 400 を作る[関数](/glossary/関数/)が呼ばれています。

アドミッションの仕組みによる拒否も 422 ではありません。実装を読むと、[Webhook](/glossary/webhook/) が返した状態[コード](/glossary/コード/)がそのまま使われ、400 未満の場合は 400 に丸められます。文言に[Webhook](/glossary/webhook/)の名前が入っていれば、検証ではなく方針による拒否です。

同時実行や名前の衝突は 409 です（[Kubernetes の 409 の記事](/posts/kubernetes_409/)）。「変更できない」という点では不変[フィールド](/glossary/フィールド/)の 422 と似て見えますが、409 は他者との競合、422 は仕様上の制約という違いがあります。

[権限](/glossary/権限/)が足りない場合は 403 です（[Kubernetes の 403 の記事](/posts/kubernetes_403/)）。対象が見つからない場合は 404 です（[Kubernetes の 404 の記事](/posts/kubernetes_404/)）。

## 切り分けの順序

1. `details.causes` を開く。ここに、どの[フィールド](/glossary/フィールド/)がなぜ駄目かが列挙されている。
2. `reason` を読む。`FieldValueRequired` は書き忘れ、`FieldValueInvalid` は値の問題。
3. `message` の末尾に `field is immutable` があるかを見る。あれば値ではなく変更可否の問題。
4. 不変[フィールド](/glossary/フィールド/)なら、更新では通らない。作り直すか、その項目を変えない設計にする。
5. `causes` が複数あるなら、まとめて直す。1つずつ試すと往復が増える。
6. 422 ではなく 400 が返っているなら、綴り・重複・型を疑う。`--validate=warn` で先に進める。
7. `Error from server` の付かない[エラー](/glossary/エラー/)は 422 の可能性が高い。表示形式が違う。
8. 事前確認は[サーバー](/glossary/サーバー/)側の指定で行う。手元だけの確認では不変[フィールド](/glossary/フィールド/)を検出できない。

## 確認コマンド集

```bash
# 1. 応答の causes をそのまま見る
kubectl apply -f manifest.yaml -v=8 2>&1 | grep -A20 '"code": 422'

# 2. 適用せずにサーバー側で検証する
kubectl apply -f manifest.yaml --dry-run=server

# 3. 未知フィールドの扱いを変えて、内容の検証まで進める
kubectl apply -f manifest.yaml --validate=warn

# 4. 既存の不変フィールドの現在値を確認する（Deployment の選別条件）
kubectl get deploy <名前> -o jsonpath='{.spec.selector}{"\n"}'

# 5. 適用しようとしている内容と突き合わせる
kubectl apply -f manifest.yaml --dry-run=server -o jsonpath='{.spec.selector}{"\n"}'

# 6. そのフィールドの仕様を確認する（許される値と必須かどうか）
kubectl explain deployment.spec.selector
kubectl explain pod.spec.containers.image

# 7. 定義側の検証規則を確認する（カスタム資源の場合）
kubectl get crd <名前> -o jsonpath='{.spec.versions[0].schema}' | head -c 2000

# 8. 監査の記録から 422 を抽出する
kubectl get --raw /metrics | grep 'apiserver_request_total.*code="422"'
```

## Editor's Note

422 の応答には、原因を特定するのに十分な情報が入っています。それを実際の記録で確認できます（[Deployment of new version of application fails with field is immutable](https://github.com/quarkusio/quarkus/issues/39180)）。2024年3月、ある開発道具から配備したところ、版を上げるたびに失敗するようになった、という報告です。

貼られている応答が示唆的です。状態[コード](/glossary/コード/)は 422、`causes` には対象の[フィールド](/glossary/フィールド/)が `spec.selector`、区分が `FieldValueInvalid`、文言の末尾が `field is immutable`。さらに `details` には group が `apps`、kind が `Deployment`、name が対象名。**調べるべきことがすべて1つの応答に入っています**。

そして値を見ると、選別条件に版を示す印が含まれていました。版が上がるたびに選別条件が変わり、変更不可の項目を変えようとしていたわけです。「なぜ今回から失敗するようになったのか」の答えも、同じ応答の中にありました。

この構造を知っていると、対処の方向が変わります。`field is immutable` は、値が間違っているという意味ではありません。**その項目を変えようとしたこと自体が問題**です。したがって、値を直すのではなく、変えない設計にするか、作り直すかの二択になります。同種の報告では、対象を[削除](/glossary/削除/)して作り直すことで解決した例が多く見られます。

422 に当たったら、`message` の1行で判断せず、`causes` を開いてください。[フィールド](/glossary/フィールド/)の経路と区分の2つが揃えば、直す場所と直し方の両方が決まります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*