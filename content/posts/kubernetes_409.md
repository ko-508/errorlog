---
title: "Kubernetes の 409 エラー：原因と解決策"
date: 2026-08-03
description: "Kubernetes の 409 には reason が2種類あり、Conflict はさらに2つに分かれます。既に存在する場合、楽観ロックの競合、そして Server-Side Apply のフィールド競合です。対処は正反対で、同じ要求を送り直して直るのは1つもありません。reason と details の読み方から始めます。"
tags: ["Kubernetes"]
errorCode: "409"
lastmod: 2026-08-03
service: "Kubernetes"
error_type: "409"
components: ["kube-apiserver", "kubectl"]
related_services: ["kubectl", "client-go", "Server-Side Apply"]
trend_incident: false
---

## 冒頭まとめ

[Kubernetes](/glossary/kubernetes/) の 409 Conflict は、1つの意味を持つ[エラー](/glossary/エラー/)ではありません。実装を読むと、409 を返す構築関数が3つあります。

1つ目は、同じ名前のものが既に存在する場合です。区分は `AlreadyExists`、文言は対象の名前に「already exists」を付けた形になります。

2つ目は、更新しようとした対象が、読み取ってから書き込むまでの間に他者に変更されていた場合です。区分は `Conflict`、文言は「Operation cannot be fulfilled on ...」で始まり、中に「the object has been modified; please apply your changes to the latest version and try again」が入ります。

3つ目は、Server-Side Apply で[フィールド](/glossary/フィールド/)の所有権が衝突した場合です。区分は同じ `Conflict` ですが、**`details.causes` に[フィールド](/glossary/フィールド/)ごとの衝突と、その所有者の名前が入ります**。文言は「Apply failed with N conflict(s)」の形です。

この3つは、対処が正反対です。1つ目は既存を使うか名前を変える。2つ目は**読み直してからやり直す**。3つ目は所有権を奪うか、手放すか、共有するかを選ぶ。**同じ要求をそのまま送り直して直るものは、1つもありません**。

したがって、409 を見たら最初にやるのは `reason` の確認、次に `details` の確認です。`kubectl` は区分を括弧付きで表示するので、`Error from server (AlreadyExists)` か `Error from server (Conflict)` かがそのまま手がかりになります。

## エラーの概要

既に存在する場合の応答です。

```json
{
  "kind": "Status",
  "status": "Failure",
  "message": "configmaps \"app-config\" already exists",
  "reason": "AlreadyExists",
  "details": { "kind": "configmaps", "name": "app-config" },
  "code": 409
}
```

楽観ロックの競合は、区分も文言も変わります。

```text
Error from server (Conflict): Operation cannot be fulfilled on deployments.apps
  "web": the object has been modified; please apply your changes to the latest
  version and try again
```

Server-Side Apply の競合は、`details` に情報が入る点が決定的に違います。

```text
error: Apply failed with 1 conflict: conflict with "kubectl-edit" using apps/v1:
  .spec.template.spec.containers[name="app"].image
Please review the fields above--they currently have other managers. Here
are the ways you can resolve this warning:
* If you intend to manage all of these fields, please re-run the apply
  command with the `--force-conflicts` flag.
...
```

**衝突した相手の名前が文言に出ます**。上の例では `kubectl-edit`、つまり誰かが `kubectl edit` で直接編集した痕跡です。この案内文は `kubectl` が付け加えているもので、公式文書への [URL](/glossary/url/) も含まれます。

## まず最初に：reason と details で3つに振り分ける

第一に、`reason` を読みます。`AlreadyExists` なら1つ目、`Conflict` なら2つ目か3つ目です。

第二に、`Conflict` の場合は文言の先頭を見ます。「Operation cannot be fulfilled」で始まれば楽観ロックの競合です。

第三に、「Apply failed with」で始まれば Server-Side Apply の競合です。この場合は `details.causes` に[フィールド](/glossary/フィールド/)ごとの情報が入ります。

第四に、衝突した相手の名前を読みます。`kubectl-edit`、`kubectl-client-side-apply`、`helm` など、**誰がその[フィールド](/glossary/フィールド/)を管理しているかが名前で分かります**。

## よくある原因と解決手順

### 原因1：既に存在するものを作ろうとしている

[自動化](/glossary/自動化/)を2回実行した場合や、前回の実行が途中まで進んでいた場合に起きます。[API](/glossary/api/) の規約にも、既存と同じ名前で作成した場合は 409 を返さなければならない、と明記されています。

**Before（重複を異常として止める）：**

```bash
kubectl create configmap app-config --from-file=./conf
# → 2回目以降は必ず失敗する
```

**After（宣言的な適用に変える）：**

```bash
kubectl apply -f configmap.yaml
```

`apply` は存在すれば更新、無ければ作成なので、繰り返し実行できます。作成の[コマンド](/glossary/コマンド/)をそのまま繰り返す設計自体を見直すのが本筋です。

ただし例外があります。規約には、`metadata.generateName` で名前を生成させた場合、生成された名前が既に存在すれば区分 `AlreadyExists` の 409 を返し、**[クライアント](/glossary/クライアント/)は再試行すべき**だ（応答に待ち時間の指定があればその時間だけ待つ）と書かれています。名前を明示した場合と違い、こちらは再試行が正しい対処です。生成される名前が変わるためです。

### 原因2：楽観ロックの競合（読み直さずに送り直している）

区分が `Conflict` で、文言に「the object has been modified」が含まれる場合です。

[API](/glossary/api/) の規約に仕組みが説明されています。すべての資源は `resourceVersion` を持ち、更新時に保存済みの値と照合されます。一致しなければ 409 で失敗します。読み取りから書き込みまでの間に他の変更が入っていないことを、この値で検証する仕組みです。

したがって、**古い値を握ったまま送り直しても、同じ競合を繰り返すだけ**です。

**Before（取得を1回だけ行う）：**

```go
obj, _ := client.Get(ctx, name, metav1.GetOptions{})   // 1回だけ取得
for i := 0; i < 3; i++ {
    obj.Spec.Replicas = ptr.To[int32](3)
    _, err := client.Update(ctx, obj, metav1.UpdateOptions{})
    if err == nil { break }
    time.Sleep(time.Second)                            // 古い値のまま再送
}
```

**After（毎回取得し直す）：**

```go
err := retry.RetryOnConflict(retry.DefaultRetry, func() error {
    obj, err := client.Get(ctx, name, metav1.GetOptions{})   // 毎回取得する
    if err != nil { return err }
    obj.Spec.Replicas = ptr.To[int32](3)
    _, err = client.Update(ctx, obj, metav1.UpdateOptions{})
    return err
})
```

公式の[ソフトウェア](/glossary/ソフトウェア/)部品には、この形のための補助関数が用意されています。説明にも、競合が出た場合は現在の版を取り直してから自分の変更を加える必要があるため、**毎回の試行で取得をやり直すこと**と明記されています。

既定の再試行の設定は、10ミリ秒間隔で最大5回です。間隔を伸ばす別の設定も用意されており、こちらは4回で、1回ごとに5倍に伸びます。頻繁に競合する対象では後者が適します。

### 原因3：Server-Side Apply のフィールド競合

区分は `Conflict` ですが、意味が違います。公式文書では、別の管理者が管理を主張している[フィールド](/glossary/フィールド/)を変更しようとしたときに起きる特別な状態[エラー](/glossary/エラー/)、と定義されています。意図しない上書きを防ぐ仕組みです。

公式文書は解決策を3つ挙げています。上書きして単独の管理者になる（`--force-conflicts` を付ける）、値を変えずに管理の主張を手放す（自分の[ファイル](/glossary/ファイル/)からその項目を消す）、値を変えずに共有の管理者になる（相手の現在値に合わせて書く）です。

**Before（とりあえず強制する）：**

```bash
kubectl apply --server-side --force-conflicts -f deploy.yaml
```

**After（誰が管理しているかを確認してから決める）：**

```bash
# 現在の管理者と管理フィールドを確認する
kubectl get deploy web -o yaml --show-managed-fields | grep -A5 managedFields
```

相手が水平[自動](/glossary/自動化/)調整の仕組みなら、`replicas` は自分の[ファイル](/glossary/ファイル/)から消すのが正解です。相手が `kubectl-edit` なら、手作業の変更を上書きしてよいか判断してから強制します。**強制は正解の1つですが、常に正解ではありません**。

なお、`--force-conflicts` は `--server-side` と併用しないと使えません。実装でも、単独指定は[エラー](/glossary/エラー/)になります。

### 原因4：apply と update で競合の意味が違う

同じ「競合」でも、操作によって扱いが違います。公式文書に対比が書かれています。強制の指定が無い限り、[フィールド](/glossary/フィールド/)の衝突が起きた apply は**常に失敗**します。一方、update（[HTTP](/glossary/http/) の PUT）で管理された[フィールド](/glossary/フィールド/)に影響する変更をしても、衝突が失敗を引き起こすことはありません。

つまり、`kubectl replace` や[プログラム](/glossary/プログラム/)からの更新では、[フィールド](/glossary/フィールド/)の所有権による 409 は出ません。出るのは `resourceVersion` の不一致による 409 だけです。原因2と原因3のどちらを疑うべきかは、使っている操作で絞り込めます。

### 原因5：自動化の記録が競合で埋まる

制御[ループ](/glossary/ループ/)を持つ[自動化](/glossary/自動化/)では、楽観ロックの競合はある程度まで正常な現象です。複数の担当が同じ対象を更新すれば必ず起きます。

問題は、それが持続する場合です。規約にも、監視の仕組みが供給する[キャッシュ](/glossary/キャッシュ/)は直近の書き込みを反映していないことがあるため、`resourceVersion` を前提条件にして競合を検出するのが一般的な作法だ、と書かれています。[キャッシュ](/glossary/キャッシュ/)の古い値をそのまま送れば、競合は繰り返されます。

競合が止まらない場合、疑うべきは3つです。同じ対象を複数の[自動化](/glossary/自動化/)が奪い合っていないか。取得を[キャッシュ](/glossary/キャッシュ/)から行い、書き込み前に取り直していないか。そして、更新の頻度が高すぎないか。再試行の回数を増やすのは、これらを確認したあとの選択肢です。

## 補足：似ているが別のもの

内容そのものが不正な場合は 422 で、区分は `Invalid` です。必須項目の欠落や値の形式違反はこちらで、409 とは別の系統です。

対象が見つからない場合は 404 です（[Kubernetes の 404 の記事](/posts/kubernetes_404/)）。[権限](/glossary/権限/)が足りない場合は 403 です（[Kubernetes の 403 の記事](/posts/kubernetes_403/)）。要求が多すぎる場合は 429 ですが、退避の拒否など過負荷以外の意味も含みます（[Kubernetes の 429 の記事](/posts/kubernetes_429/)）。

GCP でも 409 は2つの区分に対応し、既に存在する場合と同時実行の中断に分かれます（[GCP の 409 の記事](/posts/gcp_409/)）。「読み取りからやり直す」という対処は共通ですが、[Kubernetes](/glossary/kubernetes/) には Server-Side Apply という3つ目の系統がある点が違います。

## 切り分けの順序

1. `reason` を読む。`AlreadyExists` か `Conflict` かで最初の分岐が決まる。
2. `Conflict` なら文言の先頭を見る。「Operation cannot be fulfilled」なら楽観ロック、「Apply failed with」なら Server-Side Apply。
3. Server-Side Apply なら、衝突した相手の名前を読む。誰が管理しているかがそこに書かれている。
4. 楽観ロックなら、取得からやり直しているかを確認する。同じ要求の送り直しでは直らない。
5. `generateName` を使っているなら、`AlreadyExists` への対処は再試行が正しい。
6. 使っている操作を確認する。update では[フィールド](/glossary/フィールド/)の所有権による 409 は出ない。
7. 強制する前に、相手を手放すべきか共有すべきかを検討する。
8. 競合が持続するなら、複数の[自動化](/glossary/自動化/)による奪い合いと、[キャッシュ](/glossary/キャッシュ/)からの読み取りを疑う。

## 確認コマンド集

```bash
# 1. 応答の reason と details をそのまま見る
kubectl create -f manifest.yaml -v=8 2>&1 | grep -A10 '"code": 409'

# 2. 現在のフィールド管理者を確認する
kubectl get deploy <名前> -o yaml --show-managed-fields

# 3. 管理者ごとに管理しているフィールドを整理して見る
kubectl get deploy <名前> -o jsonpath='{range .metadata.managedFields[*]}{.manager}{"\t"}{.operation}{"\n"}{end}'

# 4. 適用を試すだけで、実際には変更しない
kubectl apply --server-side --dry-run=server -f manifest.yaml

# 5. resourceVersion の変化を追う（誰かが更新し続けていないか）
kubectl get deploy <名前> -o jsonpath='{.metadata.resourceVersion}' -w

# 6. 対象を更新している操作を記録から抽出する
kubectl get events --field-selector involvedObject.name=<名前> --sort-by=.lastTimestamp

# 7. 競合の発生を監査の記録から数える（code 409）
kubectl get --raw /metrics | grep 'apiserver_request_total.*code="409"'

# 8. 既存と衝突しない名前で作る（generateName の利用）
kubectl create -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  generateName: app-config-
EOF
```

## Editor's Note

Server-Side Apply の競合では、衝突した相手の名前が文言に出ます。この名前が、しばしば原因そのものを説明します。

象徴的な記録があります（[before-first-apply manager prevents resource updates](https://github.com/kubernetes/kubernetes/issues/89954)）。2020年4月、Server-Side Apply で更新しようとしたところ、`before-first-apply` という名前の管理者と衝突して失敗する、という報告です。この名前は、その対象が Server-Side Apply を使う前に作られたことを示しています。誰かの仕業ではなく、**移行前の状態がそのまま所有者として記録されていた**わけです。

同じ構造は、日常的な場面でも起きます。誰かが `kubectl edit` で一時的に値を変えると、その[フィールド](/glossary/フィールド/)の管理者として `kubectl-edit` が記録されます。次にその[ファイル](/glossary/ファイル/)を適用したとき、衝突するのはその痕跡です。文言に出る名前を読めば、いつ誰が触ったかを推測せずに済みます。

ただし、この情報にも限界があります。別の報告（[server-side apply conflict warning doesn't show which resource is causing the problem](https://github.com/kubernetes/kubernetes/issues/129898)）では、多数の[ファイル](/glossary/ファイル/)をまとめて適用したときに衝突の警告が大量に出るものの、文言にはグループと版しか含まれず、**どの対象で起きたのかが分からない**と指摘されています。一括適用のときは、対象を絞って再実行するのが結局は早道です。

409 は、区分と `details` を読むだけで3系統に分かれます。そして3つとも、送り直しでは直りません。読み直すのか、名前を変えるのか、所有権を決め直すのか。**409 が求めているのは再試行ではなく、判断です**。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*