---
title: "Terminating：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "Terminating はPodのphaseではなく、削除要求を受けたオブジェクトをkubectlが示す表示です。まずdeletionTimestamp、猶予期間、finalizers、配置先ノードを分けて確認します。強制削除はプロセス停止の確認にならないため、最後の手段です。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_terminating.png"]
errorCode: "Terminating"
lastmod: 2026-08-05T00:00:00+09:00
service: "Kubernetes"
error_type: "Terminating"
components: ["kubelet", "API Server", "Finalizer"]
related_services: ["kubectl", "StatefulSet", "Admission Webhook"]
trend_incident: false
---

## 冒頭まとめ

`Terminating` は、Podの `phase` ではありません。削除要求を受け、`.metadata.deletionTimestamp` が入ったPodを `kubectl` が一覧で示す表示です。

```text
NAME                   READY   STATUS        RESTARTS   AGE
app-7d8f767544-pk4ch   1/1     Terminating   0          3d
```

削除要求が[API](/glossary/api/) Serverに受理されても、Podはすぐには消えません。[Kubernetes公式のPod終了処理](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination-flow)では、既定で30秒の猶予期間が設けられ、その間に `preStop`、終了シグナル、接続の退避、[コンテナ](/glossary/コンテナ/)停止などが進みます。finalizerがある場合は、そのfinalizerを管理するコントローラーの後処理が終わるまで、[API](/glossary/api/)上の[オブジェクト](/glossary/オブジェクト/)も残ります。

したがって、数十秒の `Terminating` は異常とは限りません。長時間変わらない場合は、次の4つを分けて確認します。

1. 猶予期間中の正常な終了処理なのか。
2. `preStop` または[アプリケーション](/glossary/アプリケーション/)の終了処理が完了しないのか。
3. finalizerを管理するコントローラーが後処理を完了できないのか。
4. 配置先ノードまたはkubeletと[通信](/glossary/通信/)できず、停止を確認できないのか。

ここで最も重要な事実訂正があります。

```bash
kubectl delete pod <Pod名> -n <名前空間> --grace-period=0 --force
```

この強制削除は、**ノード上のプロセスを確実に停止してからPodを消す操作ではありません**。[`kubectl delete` の公式リファレンス](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_delete/)は、[API](/glossary/api/) Serverがkubeletによる終了確認を待たず、同じ識別情報を持つ処理が別のマシンで動き続け、データの不整合や損失につながる可能性を警告しています。

強制削除は一覧をきれいにする操作ではありません。古い処理が停止済み、または二度と共有資源へ接続できないと確認した後に限る、最後の手段です。

## エラーの概要

Podを通常削除すると、[API](/glossary/api/) Serverは[オブジェクト](/glossary/オブジェクト/)へ削除時刻と猶予期間を記録します。

```yaml
metadata:
  deletionTimestamp: "2026-08-05T03:12:44Z"
  deletionGracePeriodSeconds: 30
```

この時点で削除要求は失敗していません。[finalizerの公式説明](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/)によれば、finalizerを持つ[オブジェクト](/glossary/オブジェクト/)への削除要求は `202 Accepted` で受理され、`.metadata.deletionTimestamp` が設定されます。その後、必要な後処理が済み、finalizerの一覧が空になると削除が完了します。

`Terminating` は、この途中経過を `kubectl` が表示したものです。[API](/glossary/api/)上のPodの `status.phase` は、終了処理中も `Running` や `Pending` のままの場合があります。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.status.phase}{"\t"}{.metadata.deletionTimestamp}{"\t"}{.metadata.finalizers}{"\n"}'
```

```text
Running    2026-08-05T03:12:44Z    [batch.kubernetes.io/job-tracking]
```

もう1つ混同しやすいのが、次の3種類の時間です。

```text
terminationGracePeriodSeconds  Podが終了処理に使える時間
kubectl delete --grace-period  今回の削除で指定する猶予期間
kubectl delete --wait          kubectlが削除完了を待つかどうか
```

`--wait=false` は、手元の `kubectl` を先に終了させるだけです。Podの終了処理、finalizerの後処理、[API](/glossary/api/)上の削除は引き続き進みます。対して `--grace-period=0 --force` は、停止確認を待たずに[API](/glossary/api/)からPodを消します。見た目は似ていても、意味と危険性はまったく違います。

## まず最初に：削除要求・猶予期間・finalizer・ノードを分ける

第一に、削除要求が入っているかを確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.metadata.deletionTimestamp}{"\n"}{.metadata.deletionGracePeriodSeconds}{"\n"}'
```

`deletionTimestamp` が空なら、この記事で扱う削除処理中の状態ではありません。画面や監視側が古い情報を表示していないかも確認します。

第二に、Podに設定された終了猶予期間と `preStop` を確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.spec.terminationGracePeriodSeconds}{"\n"}'

kubectl get pod <Pod名> -n <名前空間> -o yaml
```

第三に、finalizerを確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .metadata.finalizers[*]}{.}{"\n"}{end}'
```

文字列がある場合は、それを追加したコントローラーを特定します。finalizerの文字列自体が後処理を実行するわけではありません。対象のコントローラーが削除を検知し、外部資源や依存関係を片付け、最後に自分のfinalizerを外します。

第四に、配置先ノードの状態を確認します。

```bash
NODE=$(kubectl get pod <Pod名> -n <名前空間> -o jsonpath='{.spec.nodeName}')
kubectl get node "$NODE"
kubectl describe node "$NODE"
kubectl get lease "$NODE" -n kube-node-lease -o yaml
```

ノードが `NotReady` または `Unknown` なら、[API](/glossary/api/)上の表示だけでノード上の処理が停止したとは判断できません。強制削除を検討する前に、ノードが停止済みか、隔離済みか、共有[ストレージ](/glossary/ストレージ/)や[ネットワーク](/glossary/ネットワーク/)へ再接続できないかを確認します。

## よくある原因と解決手順

### 原因1：まだ正常な猶予期間内にいる

Podの `terminationGracePeriodSeconds` の[既定値は30秒](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination-flow)です。削除要求を受けたkubeletは、猶予期間が0でなく `preStop` があれば先に実行し、その後[コンテナ](/glossary/コンテナ/)のプロセス1へ終了シグナルを送ります。猶予期間を過ぎても処理が残れば、[コンテナ](/glossary/コンテナ/)実行基盤が強制終了します。

`preStop` が猶予期間の終了時にも動いている場合、kubeletは一度だけ2秒の延長を要求します。この2秒を含め、`preStop` と[アプリケーション](/glossary/アプリケーション/)の終了処理は同じ猶予時間を使います。

**Before（終了処理に必要な時間より短い）：**

```yaml
spec:
  terminationGracePeriodSeconds: 10
  containers:
    - name: app
      lifecycle:
        preStop:
          exec:
            command: ["sh", "-c", "/app/drain.sh"]
```

**After（実測した終了時間に余裕を持たせる）：**

```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: app
      lifecycle:
        preStop:
          exec:
            command: ["sh", "-c", "/app/drain.sh"]
```

時間を増やすだけでなく、`drain.sh` が有限時間で終わるか、[アプリケーション](/glossary/アプリケーション/)が終了シグナルを受けて新規受付を止め、処理中の要求を終えられるかを確認します。猶予期間を短くして表示を早く消すと、処理中の要求や書き込みを途中で切るだけになる場合があります。

### 原因2：preStopまたはアプリケーションの終了処理が完了しない

削除から猶予期間を大きく超えても残る場合は、実際にどこまで進んだかを確認します。

```bash
kubectl describe pod <Pod名> -n <名前空間>
kubectl logs <Pod名> -n <名前空間> --all-containers --since=30m
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp
```

確認するのは、`preStop` が外部サービスの応答を無期限に待っていないか、[アプリケーション](/glossary/アプリケーション/)が終了シグナルを処理しているか、サイドカーを含む全[コンテナ](/glossary/コンテナ/)が終了できているかです。

なお、削除中のEndpointはEndpointSliceから直ちに消えるとは限りません。[Pod終了処理の公式説明](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination-flow)では、終了中のEndpointは `ready=false` になり、通常の[通信](/glossary/通信/)には使われない状態になると説明されています。[ロードバランサー](/glossary/ロードバランサー/)側の接続退避とPod内の終了処理は別に進むため、必要な待ち時間を実測して設計します。

### 原因3：finalizerを管理するコントローラーが後処理を完了できない

finalizerが残っていると、[コンテナ](/glossary/コンテナ/)が停止済みでも[API](/glossary/api/)上の[オブジェクト](/glossary/オブジェクト/)は削除されません。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.metadata.finalizers}{"\n"}'
```

たとえばJobのPodには `batch.kubernetes.io/job-tracking` が付くことがあります。[Jobの公式文書](https://kubernetes.io/docs/concepts/workloads/controllers/job/#job-tracking-with-finalizers)によれば、JobコントローラーはPodの終了をJobの状態へ反映してから、このfinalizerを外します。この文字列が長く残るなら、JobとJobコントローラー側を確認します。

```bash
kubectl get job -n <名前空間>
kubectl describe job <Job名> -n <名前空間>
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.metadata.ownerReferences}{"\n"}'
```

独自OperatorやCSI関連のfinalizerなら、そのコントローラーのPod、[ログ](/glossary/ログ/)、[権限](/glossary/権限/)、外部[API](/glossary/api/)への接続を調べます。

```bash
kubectl get pods -A | grep -i <コントローラー名>
kubectl logs <コントローラーPod名> -n <名前空間> --since=30m
kubectl auth can-i update pods/finalizers \
  --as=system:serviceaccount:<名前空間>:<ServiceAccount名> \
  -n <Podの名前空間>
```

finalizerを手で消す前に、誰が何を片付けるために付けたものかを確認してください。公式文書も、目的を理解せずfinalizerを手動で削除することを避けるよう警告しています。外部[ストレージ](/glossary/ストレージ/)、[ネットワーク](/glossary/ネットワーク/)、[クラウド](/glossary/クラウド/)資源などの後処理を飛ばすと、リークや二重管理が残ります。

### 原因4：ノードまたはkubeletへ到達できない

Podの終了処理は配置先ノードのkubeletが進めます。ノードが停止、分断、またはkubeletが応答不能なら、コントロールプレーンからは実際の[コンテナ](/glossary/コンテナ/)停止を確認できません。

```bash
kubectl get pod <Pod名> -n <名前空間> -o wide
kubectl get node <ノード名>
kubectl describe node <ノード名>
kubectl get events -A --field-selector involvedObject.name=<ノード名> \
  --sort-by=.lastTimestamp
```

一時的な通信断なら、ノードとkubeletを復旧させ、通常の終了処理を完了させます。ノードを再起動すればPodが必ず止まる、という判断も危険です。[公式文書](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)は、kubeletを再起動しても実行中のPodや[コンテナ](/glossary/コンテナ/)は停止せず、動作を続けると説明しています。

ノードが恒久的に失われた場合は、基盤側で電源停止または隔離を確認し、[ストレージ](/glossary/ストレージ/)の安全な切り離しやノード削除の手順へ進みます。[API](/glossary/api/)上のPodを先に消すのではなく、古い処理が復帰できない状態を先に作るのが順序です。

### 原因5：Admission Webhookが削除途中の更新を拒否する

削除要求そのものは受理されても、その後の状態更新やfinalizerの除去をAdmission [Webhook](/glossary/webhook/)が拒否し、終了処理が進まない場合があります。

```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
kubectl get events -A --sort-by=.lastTimestamp | tail -50
```

[Podのデバッグに関する公式文書](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/#my-pod-stays-terminating)は、削除中のPodが既存の規則違反を直せないために更新を拒まれる形を説明しています。[Webhook](/glossary/webhook/)がPodの `UPDATE` を対象にしているか、削除中の[オブジェクト](/glossary/オブジェクト/)を拒否していないか、[Webhook](/glossary/webhook/)サービスと[証明書](/glossary/証明書/)が正常かを確認します。

[Webhook](/glossary/webhook/)全体を無効にする前に、失敗している規則と対象範囲を絞ります。削除途中のPodを通す例外を設ける場合も、通常の作成や更新の検査まで外さないようにします。

### 原因6：StatefulSetで古いPodの停止を確認できない

StatefulSetのPodは、名前、[ネットワーク](/glossary/ネットワーク/)識別、[ストレージ](/glossary/ストレージ/)を安定して保つ前提で動きます。たとえば `db-0` を強制削除すると、StatefulSetコントローラーは同じ名前の新しいPodを作れるようになります。しかし、古い `db-0` が分断先のノードで動き続けていれば、同じ役割を持つ2つの処理が同時に存在します。

[StatefulSet Podの強制削除に関する公式文書](https://kubernetes.io/docs/tasks/run-application/force-delete-stateful-set-pod/)は、これが「最大1つ」という前提を破り、分断状態やデータ損失を起こし得ると警告しています。

強制削除を検討できるのは、古いPodが二度とStatefulSetのほかの構成要素と[通信](/glossary/通信/)しないと断言できる場合だけです。[データベース](/glossary/データベース/)、合意形成を行う処理、共有ボリュームへ書く処理では、一覧上の `Terminating` より二重起動の方が危険です。

### 原因7：親オブジェクトのforeground削除が依存先を待っている

Deployment、ReplicaSet、StatefulSetなどを `--cascade=foreground` で削除すると、所有する側は依存する[オブジェクト](/glossary/オブジェクト/)の削除完了を待ちます。[所有者と依存先の公式文書](https://kubernetes.io/docs/concepts/overview/working-with-objects/owners-dependents/#foreground-cascading-deletion)では、この待機に `foregroundDeletion` finalizerが使われると説明されています。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.metadata.ownerReferences}{"\n"}'

kubectl get deployment,replicaset,statefulset,job -n <名前空間>
```

親だけを見てfinalizerを消すのではなく、残っている依存先、その依存先のfinalizer、コントローラーの状態を下流へたどります。

## 補足：似ているが別のもの

`Pending` は、Podがまだ実行開始まで進んでいないphaseです。`Terminating` は削除要求後の表示なので、時間の向きが逆です。

`Completed` は、Pod内の処理が正常終了したことを示す表示です。終了済みでも、削除要求がなければ[API](/glossary/api/)上に残ります。

`Unknown` は、通常、Podの状態をノードから取得できないことを示します。ノード分断による `Terminating` と同時に問題になることはありますが、削除要求そのものを意味しません。

`Evicted` は、ノードの資源圧迫などを理由にkubeletがPodを終了させた結果です（[Kubernetes の Evicted の記事](/posts/kubernetes_evicted/)）。`Terminating` は原因ではなく削除途中の表示なので、Eventsと `deletionTimestamp` を見て区別します。

PodDisruptionBudgetに拒否された退避では、Eviction [API](/glossary/api/)が `429 Too Many Requests` を返し、削除要求が始まらないことがあります。この場合、通常は `deletionTimestamp` が入らず、`Terminating` にも進みません。直接の `kubectl delete pod` はPodDisruptionBudgetによる保護と同じ経路ではありません。

[Namespace](/glossary/namespace/)の `Terminating` は、[Namespace](/glossary/namespace/)コントローラーが配下の資源と[Namespace](/glossary/namespace/)のfinalizerを処理する話です。本記事はPodを中心にしています。[Namespace](/glossary/namespace/)で発生している場合は、残存する[API](/glossary/api/)資源、利用不能なAPIService、[Namespace](/glossary/namespace/)のconditionsを別に確認します。

## 強制削除またはfinalizer除去を行う前の確認

強制削除は、次のすべてを確認した後の最後の手段です。

1. 通常の猶予期間と `preStop` の実行時間を過ぎている。
2. Events、アプリケーションログ、コントローラーログを保存した。
3. finalizerの所有者と、本来行う後処理を特定した。
4. 後処理が別の方法で完了済み、または不要だと確認した。
5. 配置先ノード上で古い[コンテナ](/glossary/コンテナ/)が停止済み、あるいはノードが電源停止・隔離済みである。
6. StatefulSetなどで同じ識別情報の処理が二重起動しない。
7. 共有[ストレージ](/glossary/ストレージ/)、外部[API](/glossary/api/)、[データベース](/glossary/データベース/)へ古い処理が再接続しない。

手元の[コマンド](/glossary/コマンド/)を待たせたくないだけなら、強制削除ではなく次を使います。

```bash
kubectl delete pod <Pod名> -n <名前空間> --wait=false
```

通常の削除が完了しない原因を解消し、対象が消えるかを監視します。

```bash
kubectl wait --for=delete pod/<Pod名> -n <名前空間> --timeout=120s
```

古い処理が停止済みと確認でき、[API](/glossary/api/)上のPodだけが残った場合の強制削除は次です。

```bash
kubectl delete pod <Pod名> -n <名前空間> \
  --grace-period=0 --force
```

finalizerの後処理を別の方法で完了し、対象のfinalizerを管理するコントローラーが復旧できない場合に限り、最終手段としてfinalizerを除去します。

```bash
# 実行前に現在の一覧を保存する
kubectl get pod <Pod名> -n <名前空間> -o yaml > pod-before-finalizer-removal.yaml

# すべてのfinalizerを除去するため、目的を理解した場合だけ実行する
kubectl patch pod <Pod名> -n <名前空間> --type=merge \
  -p '{"metadata":{"finalizers":[]}}'
```

この操作は後処理を実行しません。後処理が終わったことにして、削除を先へ進めるだけです。原因調査の第一手として使わないでください。

## 切り分けの順序

1. `.metadata.deletionTimestamp` を確認し、削除要求が入った時刻を確定する。
2. `.metadata.deletionGracePeriodSeconds` と `.spec.terminationGracePeriodSeconds` を確認する。
3. 削除からの経過時間が猶予期間内なら、`preStop` と[アプリケーション](/glossary/アプリケーション/)の正常終了を待つ。
4. Eventsと全[コンテナ](/glossary/コンテナ/)の[ログ](/glossary/ログ/)から、終了処理の停止位置を確認する。
5. `.metadata.finalizers` を確認し、各finalizerを管理するコントローラーを特定する。
6. Podの所有者がJobやStatefulSetなら、親[オブジェクト](/glossary/オブジェクト/)とコントローラーの状態を確認する。
7. 配置先ノード、Lease、kubeletの到達性を確認する。
8. Admission [Webhook](/glossary/webhook/)が削除途中の更新を拒否していないか確認する。
9. 通常の後処理を復旧させる。手元だけ待たない場合は `--wait=false` を使う。
10. 古い処理の停止または隔離を確認できた場合だけ、強制削除やfinalizer除去を検討する。

## 確認コマンド集

```bash
# 1. Terminating表示のPodをdeletionTimestampから抽出する
kubectl get pods -A -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,NODE:.spec.nodeName,PHASE:.status.phase,DELETING:.metadata.deletionTimestamp' \
  | awk 'NR==1 || $5!="<none>"'

# 2. 削除時刻・今回の猶予期間・Podの既定設定・finalizerをまとめて見る
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='deletionTimestamp={.metadata.deletionTimestamp}{"\n"}deletionGracePeriodSeconds={.metadata.deletionGracePeriodSeconds}{"\n"}terminationGracePeriodSeconds={.spec.terminationGracePeriodSeconds}{"\n"}finalizers={.metadata.finalizers}{"\n"}'

# 3. 現在のphaseと全コンテナの状態を見る
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.status.phase}{"\n"}{range .status.containerStatuses[*]}{.name}{"\t"}{.state}{"\n"}{end}'

# 4. 所有者を確認する
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .metadata.ownerReferences[*]}{.kind}{"\t"}{.name}{"\t"}{.uid}{"\n"}{end}'

# 5. Eventsを時系列で確認する
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp

# 6. 配置先ノードと最終更新時刻を見る
NODE=$(kubectl get pod <Pod名> -n <名前空間> -o jsonpath='{.spec.nodeName}')
kubectl get node "$NODE" -o wide
kubectl get lease "$NODE" -n kube-node-lease \
  -o jsonpath='{.spec.renewTime}{"\n"}'

# 7. Podの定義とログを削除前に保存する
kubectl get pod <Pod名> -n <名前空間> -o yaml > pod-terminating.yaml
kubectl logs <Pod名> -n <名前空間> --all-containers --since=30m \
  > pod-terminating.log

# 8. Admission Webhookの対象規則を確認する
kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations -o yaml
```

## Editor's Note

`Terminating` が分かりにくい理由は、**1つの表示に複数の待ち時間が重なって見える**ことです。[アプリケーション](/glossary/アプリケーション/)の終了、ボリュームや通信環境の片付け、finalizerを管理するコントローラー、到達不能なノード。どれが止まっても一覧の文字は同じです。

この性質は、[Kubernetes](/glossary/kubernetes/)の課題にも長く現れています。2017年の[Pods stuck on terminating](https://github.com/kubernetes/kubernetes/issues/51835)では、Podが数時間 `Terminating` のまま残る事象が報告されました。議論では、ボリュームの片付け中に `device or resource busy` が発生し、kubelet側の削除が完了しない記録が示されています。`Terminating` という表示だけでは、その停止位置までは分からない例です。

一方、表示を消すために削除を先へ進めると、別の危険が生まれます。2025年の[The pod garbage collector deletes the old pod ... and the new pod is started](https://github.com/kubernetes/kubernetes/issues/131775)では、StatefulSetの古いPodに関する通信環境の後処理が終わる前に同名の新しいPodが作られ、古い削除処理が新しいPodの通信環境を壊した事象が報告されました。報告された個別条件をすべての[環境](/glossary/環境/)へ一般化はできませんが、**[API](/glossary/api/)上の削除完了とノード側の後処理完了は同じではない**ことを具体的に示しています。

だから、`Terminating` の解決を「強制削除[コマンド](/glossary/コマンド/)を通すこと」と定義してはいけません。解決とは、本来の終了処理がどこで止まったかを特定し、プロセス、通信環境、[ストレージ](/glossary/ストレージ/)、外部資源の後処理を安全に完了させることです。

finalizerは邪魔な文字列ではなく、その確認を削除完了より先に行わせるための印です。猶予期間も単なる待ち時間ではなく、処理中の要求や書き込みを終えるための予算です。両方を飛ばす強制削除は、原因を直す操作ではありません。

`Terminating` を見たら、まず `deletionTimestamp`、次に猶予期間、finalizer、配置先ノードの順で読んでください。強制削除は、その順序をすべて確認した後にだけ残る、最後の手段です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
