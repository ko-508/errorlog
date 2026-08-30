---
title: "Kubernetes の 504 エラー：原因と解決策"
date: 2026-07-28
description: "Kubernetes の 504 は、API サーバーが自分で打ち切った場合と、経路上の中継役が返した場合に分かれます。前者の文言はソースで一意に定義されており、既定の待ち時間は60秒です。重要なのは、クライアント側で待ち時間を伸ばしても、サーバー側の締め切りは伸びないことです。この規則もソースに明示されています。"
tags: ["Kubernetes"]
errorCode: "504"
lastmod: 2026-07-28
service: "Kubernetes"
error_type: "504"
components: ["kube-apiserver", "Ingress"]
related_services: ["kubectl", "etcd", "Admission Webhook"]
trend_incident: false
---

## 冒頭まとめ

[Kubernetes](/glossary/kubernetes/) で 504 Gateway Timeout に出会う場面は、大きく2つに分かれます。[API](/glossary/api/) [サーバー](/glossary/サーバー/)が自分の締め切りに達して要求を打ち切った場合と、Ingress などの中継役が背後の応答を待ちきれずに返した場合です。前者はクラスタの操作そのものが止まり、後者は利用者向けの[通信](/glossary/通信/)が止まります。原因も対処もまったく別です。

[API](/glossary/api/) [サーバー](/glossary/サーバー/)が打ち切った場合、文言は一意に定まっています。ソースを読むと、時間切れの応答は `Timeout: request did not complete within the allotted timeout` という文言で、区分は `Timeout`、状態[コード](/glossary/コード/)は 504 として組み立てられます。`kubectl` からは `Error from server (Timeout):` の形で表示されます。この文言が出ていれば、打ち切ったのは [API](/glossary/api/) [サーバー](/glossary/サーバー/)自身です。

締め切りの既定値は60秒です。[API](/glossary/api/) [サーバー](/glossary/サーバー/)の起動時の指定として定義されており、変更にはクラスタ側の[設定変更](/glossary/設定変更/)が要ります。

ここで重要なのが、[クライアント](/glossary/クライアント/)側の指定との関係です。要求に待ち時間を付けて送ることはできますが、ソースの処理を読むと、指定された値が0より大きく、かつ[サーバー](/glossary/サーバー/)側の上限より小さい場合にだけ採用される、と書かれています。つまり、[クライアント](/glossary/クライアント/)側で長い値を指定しても、[サーバー](/glossary/サーバー/)側の締め切りは伸びません。短くすることはできても、伸ばすことはできない、という一方通行です。「待ち時間を伸ばす」という定番の対処が効かない理由がここにあります。

なお、監視や実行、[ログ](/glossary/ログ/)の追従といった長時間動き続ける種類の要求は、この打ち切りの対象から外れます。ソースでも、該当する要求はそのまま通す分岐になっています。

## エラーの概要

`kubectl` からは次の形で見えます。

```text
Error from server (Timeout): error when creating "example.yaml":
Timeout: request did not complete within the allotted timeout
```

応答そのものは次の構造です。区分と状態[コード](/glossary/コード/)が対応しています。

```json
{
  "kind": "Status",
  "status": "Failure",
  "message": "Timeout: request did not complete within the allotted timeout",
  "reason": "Timeout",
  "code": 504
}
```

[API](/glossary/api/) [サーバー](/glossary/サーバー/)側の記録には、要求ごとの処理時間と結果が残ります。時間切れになった要求は、要した時間とともに記録されます。

```text
"HTTP" verb="GET" URI="/api/v1/namespaces/example/endpoints/sample?timeout=10s"
latency="15.79s" resp=504
```

この例では、要求に10秒の指定が付いているにもかかわらず、15.79秒かかっています。指定した値と実際の処理時間は一致しません。

一方、Ingress が返す 504 には、この文言も区分もありません。応答は中継役が作った簡素なもので、詳細は中継役側の[ログ](/glossary/ログ/)にあります。文言の有無が、系統を見分ける最初の手がかりです。

## まず最初に：文言と出どころを確定する

第一に、`Timeout: request did not complete within the allotted timeout` が出ているかを見ます。出ていれば [API](/glossary/api/) [サーバー](/glossary/サーバー/)が打ち切っています。出ていなければ、経路上の中継役か、別の仕組みの時間切れです。

第二に、`kubectl` の操作で出たのか、利用者向けの[通信](/glossary/通信/)で出たのかを見ます。前者はクラスタの制御に関わる話、後者は[コンテナ](/glossary/コンテナ/)の中の処理に関わる話で、調べる対象が違います。

第三に、対象の種類と件数を見ます。一覧の取得で出ているなら、件数が多すぎる可能性があります。単一の資源の作成で出ているなら、途中の処理が遅れている可能性が高くなります。

## よくある原因と解決手順

### 原因1：一覧の取得が重すぎる

資源の数が多い[環境](/glossary/環境/)で起きやすい形です。全件を一度に取得しようとして、締め切りに間に合いません。

**Before（全件を一度に取得する）：**

```bash
kubectl get pods --all-namespaces
```

**After（分割して取得する）：**

```bash
# 件数を区切って取得する
kubectl get pods --all-namespaces --chunk-size=500

# 対象を絞る
kubectl get pods -n example -l app=web
```

`--chunk-size` は、内部で複数回に分けて取得する指定です。1回あたりの要求が軽くなるため、締め切りに収まりやすくなります。件数そのものを減らす絞り込みと併用すると効果的です。

まず、どれだけの件数があるかを確認してください。

```bash
kubectl get pods --all-namespaces --no-headers | wc -l
```

### 原因2：クライアント側の待ち時間を伸ばしても効かない

よく行われるのが、道具の側で待ち時間を長く指定する対処です。

```bash
kubectl get pods --all-namespaces --request-timeout=10m
```

しかし前述のとおり、[サーバー](/glossary/サーバー/)側は、指定された値が[サーバー](/glossary/サーバー/)の上限より小さい場合にだけそれを採用します。上限より大きい値を指定しても、[サーバー](/glossary/サーバー/)側の締め切りは伸びません。この指定で変わるのは、道具が応答を待つ時間の側だけです。

したがって、この対処で解決するのは、道具側の待ち時間のほうが短かった場合に限られます。[サーバー](/glossary/サーバー/)側で打ち切られている場合、つまり `Timeout: request did not complete...` の文言が出ている場合は、この指定では変わりません。

[サーバー](/glossary/サーバー/)側の締め切りを伸ばすには、[API](/glossary/api/) [サーバー](/glossary/サーバー/)の起動時の指定を変更します。これはクラスタ全体に影響する変更なので、管理者の判断が要ります。まずは原因1の方向、つまり要求を軽くする側で対処するのが順当です。

### 原因3：保存側の処理が遅れている

[API](/glossary/api/) [サーバー](/glossary/サーバー/)の背後にある[保存](/glossary/保存/)の仕組みが遅いと、あらゆる要求が締め切りに近づきます。この場合、特定の操作だけでなく、幅広い操作で時間切れが出ます。

[API](/glossary/api/) [サーバー](/glossary/サーバー/)の記録に、保存側の名前を含む[エラー](/glossary/エラー/)が混じっていないかを確認します。

```bash
kubectl logs -n kube-system <API サーバーのポッド名> | grep -i "timed out\|leader changed\|slow"
```

保存側の応答が遅れている場合、504 は結果であって原因ではありません。[API](/glossary/api/) [サーバー](/glossary/サーバー/)の設定を触っても直りません。保存側の負荷、書き込みの速さ、機器の状態を確認してください。

### 原因4：入力検査の仕組みが時間切れになっている

資源の作成や更新のときだけ 504 が出る場合、途中に挟まっている検査の仕組みを疑います。この仕組みには待ち時間の設定があり、公式の定義では1秒から30秒の範囲で、既定は10秒と記されています。

検査の宛先が応答しない場合、設定次第で要求全体が失敗します。まず、どのような検査が登録されているかを確認してください。

```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# 待ち時間と失敗時の扱いを確認する
kubectl get validatingwebhookconfigurations -o custom-columns=\
'NAME:.metadata.name,TIMEOUT:.webhooks[*].timeoutSeconds,POLICY:.webhooks[*].failurePolicy'
```

検査の宛先が動いていない、あるいは到達できない場合、その検査が対象とする操作はすべて止まります。宛先の状態を確認し、必要なら対象の範囲を絞ってください。

### 原因5：Ingress など経路上の中継役が返している

利用者向けの[通信](/glossary/通信/)で 504 が出る場合です。この場合、`Timeout:` で始まる文言は付きません。中継役が、背後の[コンテナ](/glossary/コンテナ/)からの応答を待ちきれずに返しています。

中継役の[ログ](/glossary/ログ/)を確認します。

```bash
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=100 | grep " 504 "
```

対処は、待ち時間の設定を実際の処理時間に合わせることです。設定の書き方は中継役の実装ごとに違うので、使っているものの文書を確認してください。ただし、伸ばす前に、なぜ処理に時間がかかっているかを確認する価値があります。

背後の[コンテナ](/glossary/コンテナ/)が応答しているかどうかは、中継役を経由せずに直接確かめられます。

```bash
kubectl run tmp --rm -it --image=curlimages/curl --restart=Never -- \
  curl -sS -o /dev/null -w "status:%{http_code} time:%{time_total}\n" \
  http://<サービス名>.<名前空間>.svc.cluster.local/
```

直接なら速い、中継役を通すと遅い、という結果であれば、原因は中継役側の設定にあります。

## 補足：似ているが別のもの

監視や実行、[ログ](/glossary/ログ/)の追従といった長時間動く要求は、[API](/glossary/api/) [サーバー](/glossary/サーバー/)の打ち切りの対象外です。これらが途中で切れる場合、原因は別のところにあります。なお、監視の要求には別の待ち時間の指定があり、その指定は監視の処理だけが参照し、指定値より少し上の値を無作為に選んで接続の期限とする、とソースの説明に書かれています。同時に多数の接続が切れて再接続が集中するのを避けるための仕組みです。

背後の資源が見つからない場合は 404、[権限](/glossary/権限/)が足りない場合は 403 です（[Kubernetes の 404 の記事](/posts/kubernetes_404/)、[403 の記事](/posts/kubernetes_403/)）。処理そのものが失敗した場合は 500 です（[Kubernetes の 500 の記事](/posts/kubernetes_500/)）。応答できる相手が居ない場合は 503 で、時間切れとは別です（[Kubernetes の 503 の記事](/posts/kubernetes_503/)）。

道具の側の締め切りが先に切れた場合は、504 になりません。応答が届いていないので状態[コード](/glossary/コード/)が存在しないためです。この場合は時間切れの文言だけが出ます。504 が出ているということは、応答は届いている、ということです。

## 切り分けの順序

1. `Timeout: request did not complete within the allotted timeout` が出ているかを見る。出ていれば [API](/glossary/api/) [サーバー](/glossary/サーバー/)が打ち切っている。
2. 出ていなければ、経路上の中継役を疑う。中継役の[ログ](/glossary/ログ/)に 504 が記録されているかを見る。
3. [API](/glossary/api/) [サーバー](/glossary/サーバー/)側なら、対象の件数を確認する。一覧の取得なら、まず件数を数える。
4. 分割して取得する指定や、絞り込みで要求を軽くする。これが最初に試す方向。
5. 道具側で待ち時間を伸ばしても、[サーバー](/glossary/サーバー/)側の締め切りは伸びない。文言が出ている場合、この対処は効かない。
6. 幅広い操作で出ているなら、保存側の遅れを疑う。[API](/glossary/api/) [サーバー](/glossary/サーバー/)の記録を確認する。
7. 作成や更新のときだけ出るなら、入力検査の仕組みとその宛先を確認する。

## 確認コマンド集

```bash
# 1. 件数を数える（一覧の取得が重いかを判断する）
kubectl get pods --all-namespaces --no-headers | wc -l

# 2. 分割して取得する
kubectl get pods --all-namespaces --chunk-size=500

# 3. API サーバーの記録から時間切れを探す
kubectl logs -n kube-system <API サーバーのポッド名> | grep -i "timeout\|timed out"

# 4. 入力検査の設定を一覧する
kubectl get validatingwebhookconfigurations -o custom-columns=\
'NAME:.metadata.name,TIMEOUT:.webhooks[*].timeoutSeconds,POLICY:.webhooks[*].failurePolicy'

# 5. 中継役のログから 504 を探す
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=200 | grep " 504 "

# 6. 中継役を通さずに背後へ直接届くかを確かめる
kubectl run tmp --rm -it --image=curlimages/curl --restart=Never -- \
  curl -sS -o /dev/null -w "status:%{http_code} time:%{time_total}\n" \
  http://<サービス名>.<名前空間>.svc.cluster.local/

# 7. API サーバーの応答時間の傾向を見る
kubectl get --raw /metrics | grep apiserver_request_duration_seconds_count | head
```

## Editor's Note

締め切りが常に守られるとは限らない、という事実を記録した報告があります（[List request timeout not respected during response write stage](https://github.com/kubernetes/kubernetes/issues/119415)）。2023年7月、[API](/glossary/api/) [サーバー](/glossary/サーバー/)の待ち時間の指定が、応答を組み立てて書き出す段階では適用されていない、という内容です。保存側から読み出す段階では適用されているのに、書き出す段階では効かない、と指摘されています。

再現の手順も具体的です。5万件の秘密情報を作り、[受信](/glossary/受信/)を意図的に遅くした道具で全件の取得を行う、というものです。報告に貼られた監査の記録には、段階ごとの所要時間が並んでいます。保存側からの読み出しが約13.5秒、応答の書き出しが約5分21秒、応答の組み立てが約5分22秒、全体が約5分36秒。60秒の指定があっても、5分半を超えて要求が生き続けていたことになります。

この状態が問題なのは、単に遅いからではありません。報告では、その要求が実行中ずっと処理の枠を占有し続けるため、同じ区分を使う他の利用者が締め出される、と説明されています。1つの遅い要求が、周囲の要求を巻き込む構図です。

この記録から得られる教訓は2つあります。1つは、待ち時間の設定は上限の宣言であって保証ではないこと。もう1つは、監査の記録に段階ごとの所要時間が残るので、どこで時間を使ったのかを推測ではなく数字で確認できることです。504 に繰り返し当たっているなら、設定を変える前に、その数字を見てください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*