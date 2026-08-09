---
title: "Kubernetes の 429 エラー：原因と解決策"
date: 2026-08-03
description: "Kubernetes の 429 は「要求が多すぎる」だけを意味しません。出どころが3つあり、退避が PodDisruptionBudget に阻まれた場合の 429 は過負荷とは無関係です。さらに、429 に見えて 429 ではないもの（クライアント側で待たされている状態）もあります。最初にやるのは、どれなのかを確定させることです。"
tags: ["Kubernetes"]
errorCode: "429"
lastmod: 2026-08-03
service: "Kubernetes"
error_type: "429"
components: ["kube-apiserver", "Eviction API", "kubelet"]
related_services: ["kubectl", "PodDisruptionBudget", "Container Registry"]
trend_incident: false
---

## 冒頭まとめ

[Kubernetes](/glossary/kubernetes/) の 429 Too Many Requests には、出どころの違う3つの系統があります。

1つ目は、[API](/glossary/api/) [サーバー](/glossary/サーバー/)の過負荷保護です。優先度と公平性の仕組み（[API](/glossary/api/) Priority and Fairness）が、混雑時に要求を落とします。2つ目は、Pod の退避が PodDisruptionBudget に阻まれた場合です。**これは過負荷とは無関係で、「今は許可できない」という意味の拒否です**。3つ目は、[API](/glossary/api/) [サーバー](/glossary/サーバー/)以外、たとえば[イメージ](/glossary/イメージ/)の取得元が返す制限です。

さらに厄介なのが、429 に見えて 429 ではないものです。[ログ](/glossary/ログ/)に「client-side throttling, not priority and fairness」と出ている場合、要求は[サーバー](/glossary/サーバー/)にまだ送られていません。[クライアント](/glossary/クライアント/)側が自分で待っているだけです。この文言は、[ソフトウェア](/glossary/ソフトウェア/)側の実装で「優先度と公平性の仕組みではない」と明示的に書かれています。ここを取り違えると、[サーバー](/glossary/サーバー/)側をいくら調べても何も出てきません。

したがって、429 に当たったら最初にやるのは原因の推測ではなく、**どこが返したのかの確定**です。応答の区分、`details` の内容、`Retry-After` の値、この3つで系統が決まります。

## エラーの概要

過負荷保護による 429 は、素っ気ない応答です。優先度と公平性の仕組みが要求を落とすとき、実装は `Retry-After` [ヘッダー](/glossary/ヘッダー/)を付けたうえで、本文に短い文言だけを返します。

```text
HTTP/1.1 429 Too Many Requests
Retry-After: 3

Too many requests, please try again later.
```

一方、退避が拒否された場合の応答は、構造化された情報を持ちます。

```json
{
  "kind": "Status",
  "status": "Failure",
  "message": "Cannot evict pod as it would violate the pod's disruption budget.",
  "reason": "TooManyRequests",
  "details": {
    "causes": [
      {
        "reason": "DisruptionBudget",
        "message": "The disruption budget web-pdb needs 7 healthy pods and has 6 currently"
      }
    ]
  },
  "code": 429
}
```

同じ 429 でも、`details.causes` の有無で系統が分かれます。`DisruptionBudget` が入っていれば退避の拒否であり、混雑とは関係ありません。

[イメージ](/glossary/イメージ/)の取得元が返す 429 は、そもそも [API](/glossary/api/) [サーバー](/glossary/サーバー/)を経由していません。Pod の出来事として現れます。

```text
Warning  Failed   kubelet  Failed to pull image "example/app:latest":
  ... 429 Too Many Requests - Server message: toomanyrequests: ...
Normal   BackOff  kubelet  Back-off pulling image "example/app:latest"
```

`kubectl describe pod` の出来事の欄に、理由 `Failed` や `BackOff` として出ていれば、この系統です。[API](/glossary/api/) [サーバー](/glossary/サーバー/)の 429 は応答であって、Pod の出来事には出ません。

## まず最初に：どこが返したかを確定する

第一に、[ログ](/glossary/ログ/)に「client-side throttling, not priority and fairness」が出ていないかを見ます。出ていれば 429 は返っていません。原因3に進んでください。

第二に、応答の `reason` と `details` を見ます。`TooManyRequests` かつ `causes` に `DisruptionBudget` があれば、退避の拒否です。

第三に、Pod の出来事に出ているかを見ます。理由が `Failed` や `BackOff` なら、取得元の制限です。

第四に、`Retry-After` の値を見ます。優先度と公平性の仕組みによる値は状況に応じて変動し、初期値は1秒、上限は32秒です。この仕組みを無効にしている場合は固定で1秒になります。**値が動いているかどうかが、経路の手がかりになります**。

## よくある原因と解決手順

### 原因1：退避が PodDisruptionBudget に阻まれている

`kubectl drain` が進まない場合の典型です。公式文書によれば、退避の要求に対する応答は3種類あり、許可なら 200、PodDisruptionBudget により現在許可されない場合が 429、複数の PodDisruptionBudget が同じ Pod を参照するなどの設定不備が 500 です。対象の Pod が PodDisruptionBudget の管理下になければ、常に 200 が返ります。

読むべきは `causes` の中身です。実装を見ると、同じ文言でも中身が2通りあります。空きがゼロの場合は、必要な健全な Pod の数と現在の数（あるいは[同期](/glossary/同期/)の失敗理由）が入り、再試行までの推奨秒数は0になります。それ以外の場合は「まだ処理中」という趣旨の文言と、推奨秒数10が入ります。ただし、削除時の競合で拒否された場合も後者と同じ形になるため、**応答から区別できるのは「空きがゼロ」かどうかまで**です。

**Before（メッセージだけを見て諦める）：**

```bash
kubectl drain node-1 --ignore-daemonsets
# → error when evicting pods/"web-xxxxx" (will retry after 5s): Cannot evict pod...
```

**After（causes と PodDisruptionBudget の状態を確認する）：**

```bash
kubectl get pdb -A
kubectl describe pdb <名前> -n <名前空間>
```

`ALLOWED DISRUPTIONS` が0なら、Pod を増やすか、budget を緩めない限り退避できません。

なお、Pod が壊れていて健全にならない場合、退避は永久に許可されません。公式文書には、この状態では 429 か 500 が返り続けると明記されています。対処として `.spec.unhealthyPodEvictionPolicy` に `AlwaysAllow` を指定する方法が用意されています。既定の `IfHealthyBudget` は、起動しているが健全でない Pod の退避を制限するため、公式文書自身が「ノードの退避作業を阻害する」と述べています。CrashLoopBackOff の Pod が PodDisruptionBudget に守られてしまう場合が典型です（[Kubernetes の CrashLoopBackOff の記事](/posts/kubernetes_crashloopbackoff/)）。この項目は v1.31 で安定版になりました。

### 原因2：優先度と公平性の仕組みが拒否している

こちらが本来の過負荷です。この仕組みは v1.29 で安定版になり、既定で有効です。優先度レベルごとに許容並行数があり、超過分は設定によって即座に拒否されるか、キューに入ります。

拒否の理由は3種類に分かれており、指標で確認できます。枠が空かない場合、キューが満杯の場合、キューの中で時間切れになった場合です。どれなのかで対処が変わります。

```bash
# 拒否の内訳を優先度レベルと FlowSchema ごとに見る
kubectl get --raw /metrics | grep apiserver_flowcontrol_rejected_requests_total

# 指標が取れない場合は専用の窓口を使う
kubectl get --raw /debug/api_priority_and_fairness/dump_priority_levels
```

後者は CSV 形式で、優先度レベルごとに待機中・実行中・拒否・時間切れ・取り消しの件数が並びます。どのレベルで詰まっているかが一目で分かります。

対処は公式文書に整理されています。要求の頻度を下げること、高価な要求を同時に大量に投げないこと、一覧の取得を分割して1回あたりの負荷を下げること、一覧の取得を監視に置き換えることです。

見落としやすい注意も書かれています。**要求の数が増えていなくても、1件あたりの処理が遅くなれば拒否は始まります**。枠を占有する時間が延びるためです。さらに、複数の優先度レベルで同時に拒否が出ているなら、利用側や設定ではなく、制御系そのものの性能問題を疑うべきだ、とされています。

### 原因3：クライアント側で待たされているだけ（429 ではない）

[ログ](/glossary/ログ/)に「client-side throttling, not priority and fairness」が出ている場合です。前述のとおり、要求は送られていません。

原因は、[クライアント](/glossary/クライアント/)側の毎秒あたりの上限が低いことです。標準の[ソフトウェア](/glossary/ソフトウェア/)部品の既定値は毎秒5件、瞬間的な上限は10件で、これは控えめな値です。[Kubernetes](/glossary/kubernetes/) 自身の構成要素はこの既定を使っておらず、明示的に引き上げています。制御系の管理役は毎秒20件・上限30件、割り当て役と各ノードの担当役は毎秒50件・上限100件です。

**Before（並列度だけを上げる）：**

```bash
--worker-threads=100
# → 送信前の待機が原因なので、速くならない
```

**After（[クライアント](/glossary/クライアント/)側の上限を引き上げる）：**

```bash
--kube-api-qps=50 --kube-api-burst=100
```

自作の[自動化](/glossary/自動化/)や第三者製の部品が遅い場合、既定値のまま使っているケースが多くあります。引き上げる際は、[API](/glossary/api/) [サーバー](/glossary/サーバー/)側に負荷が移ることを意識してください。原因2を誘発しては本末転倒です。

### 原因4：イメージの取得元の制限

Pod の出来事として現れる 429 です。取得元が返した文言は、そのまま出来事の本文に載ります。

[Docker](/glossary/docker/) Hub の場合、公式文書によれば未認証は IPv4 アドレスまたは IPv6 の /64 単位で6時間あたり100回、認証済みの個人向け契約で200回です。第三者の基盤を経由すると同じアドレスに集約されるため、[認証](/glossary/認証/)していても制限に当たることがあります。

対処は、認証情報を設定する、控えを持つ取得元に切り替える、取得の回数自体を減らす、のいずれかです。再試行の間隔は自動的に伸び、上限は300秒（5分）と公式文書に明記されています（[Kubernetes の ImagePullBackOff の記事](/posts/kubernetes_imagepullbackoff/)）。

### 原因5：分類から漏れて予備の枠に落ちている

自分で FlowSchema を定義している場合の落とし穴です。どの FlowSchema にも当てはまらない要求は、必須の予備の枠に割り当てられます。公式文書には、この枠は**並行シェアが非常に小さく、キューイングもしない**と明記されています。通常は使われない前提の設定だからです。

つまり、分類から漏れた要求は少量でも拒否されます。応答の[ヘッダー](/glossary/ヘッダー/) `X-Kubernetes-PF-FlowSchema-UID` と `X-Kubernetes-PF-PriorityLevel-UID` で、実際にどこへ割り当てられたかを確認できます。[クライアント](/glossary/クライアント/)側でこの[ヘッダー](/glossary/ヘッダー/)を見るには、`-v=8` 以上の詳細表示が必要です。

## 補足：似ているが別のもの

応答できる Pod が存在しない場合は 503 です（[Kubernetes の 503 の記事](/posts/kubernetes_503/)）。混雑という点では似ていますが、429 は「受け付けられない」、503 は「宛先がいない」という違いがあります。

締め切りに達して打ち切られた場合は 504 です（[Kubernetes の 504 の記事](/posts/kubernetes_504/)）。処理が内部で失敗した場合は 500 です（[Kubernetes の 500 の記事](/posts/kubernetes_500/)）。退避の要求で 500 が返る場合は、複数の PodDisruptionBudget が同じ Pod を参照しているなどの設定不備を疑ってください。

退避の要求では、403 が返る場合もあります。空きの値が負になっている場合や、未確定の退避が溜まりすぎている場合です。429 とは分岐が違うので、区分で見分けてください。

実行や[ログ](/glossary/ログ/)の追従のように長時間動き続ける要求は、優先度と公平性の仕組みの対象外です。これらが遅い場合、原因は 429 側にはありません。監視の要求は対象に含まれます。

同じ 429 でも、GCP では応答の `details` に上限の識別子と待ち時間が入ります（[GCP の 429 の記事](/posts/gcp_429/)）。読むべき場所が違うので、他の基盤の経験をそのまま持ち込まないでください。

## 切り分けの順序

1. [ログ](/glossary/ログ/)に「client-side throttling, not priority and fairness」が無いか確認する。あれば 429 は返っていない。
2. Pod の出来事に出ているかを見る。理由が `Failed` や `BackOff` なら取得元の制限。
3. 応答の `details.causes` を見る。`DisruptionBudget` があれば退避の拒否で、過負荷ではない。
4. 退避の拒否なら `kubectl get pdb` で空きを確認する。0なら Pod を増やすか budget を見直す。
5. 過負荷なら拒否の指標を理由ごとに見る。枠不足・キュー満杯・時間切れで対処が変わる。
6. `Retry-After` の値が動いているかを見る。固定で1なら仕組みが無効になっている可能性がある。
7. 応答の[ヘッダー](/glossary/ヘッダー/)で割り当て先を確認する。予備の枠に落ちていれば分類の設定漏れ。
8. 複数の優先度レベルで同時に拒否が出ているなら、制御系そのものの性能を疑う。

## 確認コマンド集

```bash
# 1. 退避の拒否かどうかを応答の構造で判定する
kubectl get --raw \
  "/api/v1/namespaces/<名前空間>/pods/<Pod名>/eviction" 2>&1 | head

# 2. PodDisruptionBudget の空きを確認する
kubectl get pdb -A -o wide
kubectl describe pdb <名前> -n <名前空間>

# 3. 優先度と公平性の仕組みによる拒否の内訳を見る
kubectl get --raw /metrics | grep apiserver_flowcontrol_rejected_requests_total

# 4. 優先度レベルごとの状態を一覧で見る（拒否・時間切れの列がある）
kubectl get --raw /debug/api_priority_and_fairness/dump_priority_levels

# 5. 実行中の要求と、待機しているキューを見る
kubectl get --raw /debug/api_priority_and_fairness/dump_queues
kubectl get --raw '/debug/api_priority_and_fairness/dump_requests?includeRequestDetails=1'

# 6. 自分の要求がどこに割り当てられたかを確認する（-v=8 でヘッダーが出る）
kubectl get pods -v=8 2>&1 | grep -i "X-Kubernetes-PF"

# 7. UID から FlowSchema と優先度レベルの名前を引く
kubectl get flowschemas -o custom-columns="uid:{metadata.uid},name:{metadata.name}"
kubectl get prioritylevelconfigurations -o custom-columns="uid:{metadata.uid},name:{metadata.name}"

# 8. イメージ取得の失敗を出来事から確認する
kubectl describe pod <Pod名> -n <名前空間> | sed -n '/Events:/,$p'
```

## Editor's Note

429 の応答には、原因を特定できるだけの情報が入っています。問題は、その情報が利用者まで届くとは限らないことです。

それを記録した報告があります（[kubectl drain must print warnings about eviction errors](https://github.com/kubernetes/kubectl/issues/172)）。2017年12月、`kubectl drain` が一向に終わらないが画面には何も出ない、という内容です。報告者が詳細表示を最大まで上げて初めて、退避の要求が 429 で失敗し続けていたことが分かりました。貼られている応答には、区分が `TooManyRequests`、原因が `DisruptionBudget`、そして「web-pdb は健全な Pod が7つ必要だが現在6つ」という具体的な数字まで入っています。

つまり、[サーバー](/glossary/サーバー/)は最初から答えを返していました。それを表示しない道具の側で情報が消えていたわけです。この報告は修正され、現在の `kubectl` は退避の失敗を画面に出します。実装を読むと、429 を受け取ったときは「5秒後に再試行する」という趣旨の文言とともに[エラー](/glossary/エラー/)の中身を表示し、待ってから再度試みる作りになっています。全体の待ち時間を指定していなければ、これが延々と続きます。

この経緯から得られる教訓は2つあります。1つは、`kubectl drain` が長く止まっているとき、それは無反応ではなく、5秒ごとに拒否され続けている可能性が高いということ。もう1つは、道具の表示だけで判断せず、応答そのものを見る習慣です。原因が `DisruptionBudget` なのか、混雑なのか、そもそも[サーバー](/glossary/サーバー/)に届いていないのか。それは 429 という数字ではなく、`details` と[ログ](/glossary/ログ/)の文言が教えてくれます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*