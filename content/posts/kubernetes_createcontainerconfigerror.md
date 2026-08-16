---
title: "Kubernetes の CreateContainerConfigError：原因と解決策"
date: 2026-08-03
description: "CreateContainerConfigError は状態欄に出る分類名で、原因は書かれていません。原因は Pod のイベントの側にあり、参照先が無いのか、キーが無いのかで文言が変わります。kubelet は再試行し続けるため、後から作れば Pod を作り直さずに起動します。"
tags: ["Kubernetes"]
errorCode: "CreateContainerConfigError"
lastmod: 2026-08-03
service: "Kubernetes"
error_type: "CreateContainerConfigError"
components: ["kubelet", "ConfigMap", "Secret"]
related_services: ["kubectl", "Helm"]
trend_incident: false
---

## 冒頭まとめ

`CreateContainerConfigError` は、[Kubernetes](/glossary/kubernetes/) が[コンテナ](/glossary/コンテナ/)を起動する前段階、**設定を組み立てる段階で失敗した**ことを示します。[イメージ](/glossary/イメージ/)の取得は成功しており、[コンテナ](/glossary/コンテナ/)の作成にも到達していません。

重要なのは、**この文字列自体には原因が書かれていない**ことです。実装を見ると、これは分類のための名前で、`kubectl get pods` の状態欄にはこの名前だけが出ます。実際の原因は、`kubectl describe pod` の[イベント](/glossary/イベント/)の側に入ります。しかも、その[イベント](/glossary/イベント/)の理由欄は `CreateContainerConfigError` ではなく **`Failed`** です。実装で理由の定数がそう定義されています。

原因の大半は、[環境変数](/glossary/環境変数/)として参照している ConfigMap や Secret が解決できないことです。文言は2種類に分かれます。**参照先そのものが無い**場合は `secret "app-secrets" not found` の形、**参照先はあるが[キー](/glossary/キー/)が無い**場合は `couldn't find key API_KEY in Secret default/app-secrets` の形になります。実装でも、この2つは別々の分岐で作られています。

もう1つ、実務で効く性質があります。kubelet は失敗しても作成を繰り返します。したがって、**足りない ConfigMap や Secret を後から作れば、Pod を作り直さなくても起動します**。実際の報告を見ても、[イベント](/glossary/イベント/)には同じ失敗が数分間で8回といった形で記録されています。

## エラーの概要

まず状態欄です。分類名だけが出ます。

```text
NAME                     READY   STATUS                       RESTARTS   AGE
app-6f8d9c7b5-x4k2h      0/1     CreateContainerConfigError   0          64s
```

原因は[イベント](/glossary/イベント/)にあります。理由欄が `Failed` である点に注意してください。

```text
Events:
  Type     Reason   Age                From     Message
  ----     ------   ----               ----     -------
  Normal   Pulled   3m (x8 over 9m)    kubelet  Successfully pulled image "app:v1.2"
  Warning  Failed   3m (x8 over 9m)    kubelet  Error: secret "app-secrets" not found
```

[コンテナ](/glossary/コンテナ/)の状態を直接読むこともできます。分類名と文言が対で入っています。

```bash
kubectl get pod <Pod名> -o jsonpath='{.status.containerStatuses[0].state.waiting}'
# {"message":"secret \"app-secrets\" not found","reason":"CreateContainerConfigError"}
```

なお、この状態の Pod では[ログ](/glossary/ログ/)が取得できません。`kubectl logs` は、[コンテナ](/glossary/コンテナ/)が起動待ちである旨を返します。[コンテナ](/glossary/コンテナ/)がまだ作られていないため、[ログ](/glossary/ログ/)自体が存在しないからです。**[ログ](/glossary/ログ/)を追おうとして行き詰まるのは、この[エラー](/glossary/エラー/)の典型的な入口**です。見るべきは[イベント](/glossary/イベント/)です。

## まず最初に：イベントの文言を読む

第一に、`kubectl describe pod` を実行し、理由が `Failed` の[イベント](/glossary/イベント/)を探します。ここに原因の文言が入っています。

第二に、文言の形を見ます。`not found` で終わっていれば参照先が存在しません。`couldn't find key` で始まっていれば、参照先はあるが[キー](/glossary/キー/)がありません。

第三に、文言に含まれる名前空間を確認します。[キー](/glossary/キー/)欠落の文言には `名前空間/名前` の形で入るため、意図した名前空間かどうかがその場で分かります。

第四に、`x8 over 9m` のような繰り返し回数を見ます。増え続けていれば、kubelet が再試行を続けている状態です。**参照先を用意すれば、そのまま起動します**。

## よくある原因と解決手順

### 原因1：参照先の ConfigMap や Secret が存在しない

最も多い形です。文言は `secret "app-secrets" not found` や `configmap "app-config" not found` になります。

公式文書の制約の項に明記があります。ConfigMap は Pod の仕様で参照する前に作成しておく必要があり、存在しない ConfigMap を参照し、かつ参照を任意と指定していない場合、Pod は起動しません。

原因は多くの場合、名前の綴り違いか、名前空間の取り違えです。

```bash
# 同じ名前空間に存在するかを確認する
kubectl get secret,configmap -n <名前空間>

# Pod が参照している名前を洗い出す
kubectl get pod <Pod名> -o jsonpath='{range .spec.containers[*]}{.envFrom}{.env}{"\n"}{end}'
```

配備の道具を使っている場合、**作成の順序が原因**であることもあります。Deployment が先に作られ、Secret が後から作られる構成では、その間だけこの状態になります。前述のとおり kubelet は再試行するため、Secret が作られた時点で自動的に起動します。慌てて Pod を削除する必要はありません。

### 原因2：参照先はあるが、キーが無い

文言が `couldn't find key <キー> in Secret <名前空間>/<名前>` の形になります。ConfigMap の場合も同様です。実装では、参照先の取得に成功したあと、[キー](/glossary/キー/)の存在を確認する段階で作られます。

公式文書にも、存在しない[キー](/glossary/キー/)への参照も同様に Pod の起動を妨げる、と書かれています。

```bash
# 実際に入っているキーの一覧を確認する
kubectl get secret <名前> -n <名前空間> -o jsonpath='{.data}' | tr ',' '\n'
kubectl get configmap <名前> -n <名前空間> -o jsonpath='{.data}' | tr ',' '\n'
```

**Before（[キー](/glossary/キー/)名を推測で書く）：**

```yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-secret
        key: password        # 実際は postgresql-password だった
```

**After（実際の[キー](/glossary/キー/)名に合わせる）：**

```yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-secret
        key: postgresql-password
```

この形は、外部の配布物を使うときによく起きます。作り手が使う[キー](/glossary/キー/)名と、こちらが書いた[キー](/glossary/キー/)名がずれているためです。推測せず、実物の一覧を確認してください。

### 原因3：任意扱いにすべき参照を必須のままにしている

参照を任意と指定すれば、存在しなくても起動します。公式文書によれば、任意と指定した場合、ConfigMap が存在しなければその[環境変数](/glossary/環境変数/)は空になり、存在しても[キー](/glossary/キー/)が無ければ同じく空になります。

```yaml
env:
  - name: FEATURE_FLAG
    valueFrom:
      configMapKeyRef:
        name: optional-config
        key: flag
        optional: true      # 無ければ空のまま起動する
```

ただし、**無条件に指定するのは危険**です。必須の資格情報を任意にすると、値が空のまま起動し、[アプリケーション](/glossary/アプリケーション/)の中でより分かりにくい失敗に変わります。任意にしてよいのは、無くても動作が定義できる項目だけです。

なお、実装を読むと、任意の指定が効くのは参照先が「見つからない」場合に限られます。[権限](/glossary/権限/)不足など別の理由で取得に失敗した場合は、任意でも失敗します。

### 原因4：環境変数の設定以外が原因

頻度は下がりますが、設定を組み立てる段階には他の処理も含まれます。実装では、[イメージ](/glossary/イメージ/)の利用者の解決や、`runAsNonRoot` の検証、[ログ](/glossary/ログ/)用[ディレクトリ](/glossary/ディレクトリ/)の作成もこの段階で行われ、いずれの失敗も同じ分類名になります。

したがって、[イベント](/glossary/イベント/)の文言が ConfigMap や Secret に触れていない場合は、そちらを疑ってください。とくに `runAsNonRoot` を指定しているのに[イメージ](/glossary/イメージ/)が root で動く設定になっている場合が該当します。

### 原因5：分類名だけで判断してしまう

対処ではなく、進め方の問題です。この分類名は原因を含まないため、名前だけを検索しても自分の状況には辿り着きません。

```bash
# 状態と文言を同時に取り出す（複数コンテナにも対応）
kubectl get pod <Pod名> -o jsonpath='{range .status.containerStatuses[*]}{.name}{"\t"}{.state.waiting.reason}{"\t"}{.state.waiting.message}{"\n"}{end}'
```

複数の[コンテナ](/glossary/コンテナ/)を持つ Pod では、どの[コンテナ](/glossary/コンテナ/)で失敗しているかも重要です。補助的な[コンテナ](/glossary/コンテナ/)だけが失敗している場合もあります。

## 補足：似ているが別のもの

`CreateContainerError` は別の分類です。実装では定数からして別物で、こちらは設定の組み立てではなく、[コンテナ](/glossary/コンテナ/)の作成そのものに失敗した場合に使われます。名前が似ているため取り違えやすいので、文字列を最後まで読んでください。

[イメージ](/glossary/イメージ/)が取得できない場合は `ImagePullBackOff` です（[Kubernetes の ImagePullBackOff の記事](/posts/kubernetes_imagepullbackoff/)）。この[エラー](/glossary/エラー/)は[イメージ](/glossary/イメージ/)の取得に成功したあとの段階なので、両者は排他です。

[コンテナ](/glossary/コンテナ/)が起動したあとで落ちる場合は `CrashLoopBackOff` です（[Kubernetes の CrashLoopBackOff の記事](/posts/kubernetes_crashloopbackoff/)）。設定は組み立てられているため、原因は[アプリケーション](/glossary/アプリケーション/)側にあります。

`ContainerCreating` のまま進まない場合は、多くがボリュームの割り当て待ちです。[イベント](/glossary/イベント/)の理由が `FailedMount` になります。

なお、`envFrom` で ConfigMap 全体を取り込む場合、環境変数名として使えない[キー](/glossary/キー/)は**読み飛ばされ、Pod は起動します**。公式文書によれば、この場合は[イベント](/glossary/イベント/)に `InvalidVariableNames` として記録されます。起動しているのに値が入っていない、という現象はこちらです。

## 切り分けの順序

1. `kubectl logs` ではなく `kubectl describe pod` を見る。[ログ](/glossary/ログ/)はまだ存在しない。
2. 理由が `Failed` の[イベント](/glossary/イベント/)を探す。原因の文言はそこにある。
3. 文言の形を見る。`not found` なら参照先が無い、`couldn't find key` なら[キー](/glossary/キー/)が無い。
4. 文言に含まれる名前空間を確認する。取り違えていないか。
5. 実物の一覧と突き合わせる。推測で[キー](/glossary/キー/)名を直さない。
6. 配備直後なら、順序の問題かもしれない。後から作れば自動的に起動する。
7. 文言が ConfigMap や Secret に触れていないなら、`runAsNonRoot` などの設定を疑う。
8. 複数[コンテナ](/glossary/コンテナ/)なら、どの[コンテナ](/glossary/コンテナ/)で失敗しているかを確認する。

## 確認コマンド集

```bash
# 1. 状態と原因の文言をまとめて取り出す
kubectl get pod <Pod名> -n <名前空間> -o jsonpath='{range .status.containerStatuses[*]}{.name}{"\t"}{.state.waiting.reason}{"\t"}{.state.waiting.message}{"\n"}{end}'

# 2. 原因のイベントだけを見る
kubectl describe pod <Pod名> -n <名前空間> | sed -n '/Events:/,$p'

# 3. 名前空間全体で同じ失敗が出ていないかを確認する
kubectl get events -n <名前空間> --field-selector reason=Failed \
  --sort-by=.lastTimestamp | tail -20

# 4. Pod が参照している ConfigMap と Secret を洗い出す
kubectl get pod <Pod名> -n <名前空間> -o json \
  | jq -r '.spec.containers[].env[]?.valueFrom | (.configMapKeyRef, .secretKeyRef) | select(.) | "\(.name)\t\(.key)"'

# 5. 実際に存在するキーの一覧を確認する
kubectl get secret <名前> -n <名前空間> -o jsonpath='{.data}' | tr ',' '\n'
kubectl get configmap <名前> -n <名前空間> -o jsonpath='{.data}' | tr ',' '\n'

# 6. 同じ名前空間に参照先が存在するかを確認する
kubectl get secret,configmap -n <名前空間>

# 7. 同じ状態の Pod を一覧化する
kubectl get pods -A --field-selector status.phase=Pending \
  -o custom-columns='NS:.metadata.namespace,POD:.metadata.name,REASON:.status.containerStatuses[0].state.waiting.reason'

# 8. 参照先を作ったあとの復帰を確認する
kubectl get pod <Pod名> -n <名前空間> -w
```

## Editor's Note

この[エラー](/glossary/エラー/)の分かりにくさは、**分類名と原因が別の場所にある**という構造に由来します。それを一目で示す記録があります（[Error: couldn't find key postgresql-password in Secret](https://github.com/sentry-kubernetes/charts/issues/1433)）。

貼られている出力では、`kubectl get pod` の状態欄に3つの Pod が `CreateContainerConfigError` と並んでいます。ここまでは、どれも同じに見えます。ところが[イベント](/glossary/イベント/)を見ると、内訳が違いました。ある Pod は `Error: couldn't find key postgresql-password in Secret test/my-postgresql`、別の Pod は `Error: secret "sentry-snuba-env" not found`。**前者は参照先はあるが[キー](/glossary/キー/)が違う、後者はそもそも参照先が無い**という、対処のまったく異なる2つの問題が、同じ分類名の下に混ざっていたわけです。

[イベント](/glossary/イベント/)の理由欄がどちらも `Failed` である点も、実装のとおりでした。分類名で検索しても解決しないのは、この構造のためです。

もう1つ、入口でつまずく例もあります（[CreateContainerConfigError on multiple pods after install](https://github.com/argoproj/argo-cd/issues/18993)）。報告者が原因を調べようと[ログ](/glossary/ログ/)を取得したところ、[コンテナ](/glossary/コンテナ/)が起動待ちである旨だけが返ってきています。この段階では[コンテナ](/glossary/コンテナ/)が存在しないため、当然の応答です。同じ報告の[イベント](/glossary/イベント/)には、失敗が9分間で8回繰り返された記録が残っており、kubelet が諦めずに再試行していることも読み取れます。

つまり、この[エラー](/glossary/エラー/)で最初にやるべきことは決まっています。[ログ](/glossary/ログ/)ではなく[イベント](/glossary/イベント/)を見る。文言が `not found` か `couldn't find key` かを読む。それだけで、作るべきものと直すべきものが分かれます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*