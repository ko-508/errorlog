---
title: "FailedSchedulingの原因と対処法"
date: 2026-09-25
draft: false
description: "KubernetesのFailedSchedulingは、Podを配置できるノードが見つからないときに記録されるイベントです。0/N nodes are availableに続く理由の読み方と、リソース、Affinity、Taint、PVCごとの対処法を解説します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_failedscheduling.png"]
errorCode: "FailedScheduling"
urgency: "high"
service: "Kubernetes"
error_type: "FailedScheduling"
components: ["kube-scheduler", "Pod", "Node"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

[Kubernetes](/glossary/kubernetes/)でPodが`Pending`のままになり、`kubectl describe pod`のEventsに次のような警告が出ることがあります。

```text
Warning  FailedScheduling  default-scheduler
0/3 nodes are available: 1 Insufficient cpu, 2 node(s) had taints that the pod didn't tolerate.
```

`FailedScheduling`は、kube-schedulerがPodを配置できるノードを見つけられなかったことを示す[イベント](/glossary/イベント/)です。[エラー](/glossary/エラー/)名だけでは原因を判断できません。`0/3 nodes are available:`の後ろにある理由を、最後まで確認する必要があります。

最初に次の[コマンド](/glossary/コマンド/)を実行してください。

```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -n <namespace> \
  --field-selector reason=FailedScheduling \
  --sort-by=.metadata.creationTimestamp
```

理由が`Insufficient cpu`なら[CPU](/glossary/cpu/)の要求量、`didn't match Pod's node affinity/selector`ならラベルと配置条件、`had taints that the pod didn't tolerate`ならTaintとTolerationを調べます。複数の理由が並んでいる場合は、1つ直しただけでは配置できないことがあります。

## FailedSchedulingとは

`FailedScheduling`はPodの状態ではなく、スケジューラーが記録する[イベント](/glossary/イベント/)のReasonです。Podの状態は`Pending`のままで、`PodScheduled`条件は`False`になります。

kube-schedulerは、まだ配置先が決まっていないPodを監視し、次のような条件で候補ノードを絞り込みます。

- Podが要求する[CPU](/glossary/cpu/)や[メモリ](/glossary/メモリ/)を確保できるか
- `nodeSelector`やNode Affinityに一致するか
- ノードのTaintをPodが許容しているか
- 使用するボリュームの配置条件を満たすか

すべてのノードがいずれかの条件で候補から外れると、配置に失敗して`FailedScheduling`が記録されます。この仕組みは[Kubernetes Schedulerの公式ドキュメント](https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/)で確認できます。

同じ`Pending`でも、すでに配置先ノードが決まり、[イメージ](/glossary/イメージ/)取得や[コンテナ](/glossary/コンテナ/)作成を待っている場合はスケジューラーの問題ではありません。`FailedScheduling`が出ている場合は、Podを起動する処理より前の「配置先を決める段階」で止まっています。

## 0/N nodes are availableの読み方

[イベント](/glossary/イベント/)は、次の形式で表示されます。

```text
0/<ノード数> nodes are available: <配置できなかった理由>
```

よく表示される理由と、最初に確認する項目は次のとおりです。

| 理由 | 確認する項目 |
|---|---|
| `Insufficient cpu` | Podの[CPU](/glossary/cpu/) requestsとノードのAllocatable |
| `Insufficient memory` | Podの[メモリ](/glossary/メモリ/)requestsとノードのAllocatable |
| `Insufficient ephemeral-storage` | 一時[ストレージ](/glossary/ストレージ/)のrequestsとノード[容量](/glossary/容量/) |
| `Too many pods` | ノードに配置済みのPod数と配置可能数 |
| `Insufficient <resource-name>` | GPUなどの拡張リソース |
| `node(s) didn't match Pod's node affinity/selector` | ノードのラベルとPodの配置条件 |
| `node(s) had taints that the pod didn't tolerate` | ノードのTaintとPodのToleration |
| ボリュームのNode Affinityに関する理由 | PVのゾーンと配置可能なノード |

たとえば、次の[イベント](/glossary/イベント/)では1台が[CPU](/glossary/cpu/)不足、残り2台がTaintによって候補から外れています。

```text
0/3 nodes are available: 1 Insufficient cpu, 2 node(s) had taints that the pod didn't tolerate.
```

[CPU](/glossary/cpu/)不足だけを解消しても、PodがTaintを許容できなければ配置先は見つかりません。[イベント](/glossary/イベント/)に複数の理由があるときは、すべてをPodの[設定](/glossary/設定/)と照合してください。

また、リソース不足には「空きができれば配置できる場合」と「現在のどのノードにも収まらない場合」があります。[Kubernetes](/glossary/kubernetes/)の実装では両者を区別していますが、この内部区分が[イベント](/glossary/イベント/)にそのまま表示されるわけではありません。Podの要求量と各ノードの最大割り当て量を比較して判断します。

## Insufficient cpu・memoryの対処

`Insufficient cpu`や`Insufficient memory`が出たら、Podの`resources.requests`とノードの`Allocatable`を確認します。

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml
kubectl describe nodes
```

`kubectl describe nodes`の`Allocated resources`には、ノード上のPodが要求している[CPU](/glossary/cpu/)や[メモリ](/glossary/メモリ/)の合計が表示されます。ここで比較するのは、監視画面に出る現在の使用率ではなく、スケジューラーが配置時に使う要求量です。

```bash
kubectl top nodes
```

`kubectl top nodes`は実際の使用状況を調べる補助にはなりますが、使用率が低いことだけを理由に「空きがある」とは判断できません。スケジューラーはPodのrequestsとノードのAllocatableを基準に配置可否を判定します。公式の調査手順は[Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)に掲載されています。

切り分けは次の2通りです。

1. Podの要求量が、すべてのノードのAllocatableを超えている
2. 要求量は単独なら収まるが、配置済みPodのrequestsを差し引くと空きがない

1の場合は、ほかのPodが終了しても配置できません。[アプリケーション](/glossary/アプリケーション/)の実測値をもとにrequestsを適正化するか、Podが収まるノードを追加します。

```yaml
# 修正前：既存ノードに収まらない要求
resources:
  requests:
    cpu: "8"
    memory: "16Gi"
```

```yaml
# 修正例：計測結果に基づいて要求量を調整
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
```

修正例の数値は一般的な正解ではありません。requestsを必要以上に下げると、ノードの過密化や性能低下につながります。

2の場合は、不要なワークロードの縮小、処理中のJobの完了待ち、条件を満たすノードの追加などで空きを作ります。原因を確認せず、稼働中のPodを[削除](/glossary/削除/)して空きを作る方法は避けてください。コントローラーによって同じPodが再作成され、状況が変わらないこともあります。

## nodeSelector・Affinityの対処

次の理由が出ている場合、Podが要求するラベル条件に一致するノードがありません。

```text
node(s) didn't match Pod's node affinity/selector
```

Podの[設定](/glossary/設定/)とノードのラベルを確認します。

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml
kubectl get nodes --show-labels
```

たとえば、Podに次の`nodeSelector`がある場合、`workload=batch`というラベルを持つノードだけが候補になります。

```yaml
spec:
  nodeSelector:
    workload: batch
```

意図した専用ノードにラベルが付いていないなら、対象を確認してからラベルを追加します。

```bash
kubectl label node <node-name> workload=batch
```

Pod側の指定が間違っている場合は、DeploymentやJobなど、Podを作成している元の[マニフェスト](/glossary/マニフェスト/)を[修正](/glossary/修正/)してください。実行中のPodだけを直しても、再作成時に元の[設定](/glossary/設定/)へ戻ります。

Node Affinityでは、`requiredDuringSchedulingIgnoredDuringExecution`は必須条件です。該当するノードがなければPodは配置されません。必須にする必要がない条件なら、`preferredDuringSchedulingIgnoredDuringExecution`で優先条件にできないか検討します。両者の違いは[Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)で説明されています。

## Taint・PVC・ノード状態の対処

次の理由は、配置候補のノードにPodが許容していないTaintがあることを示します。

```text
node(s) had taints that the pod didn't tolerate
```

ノードとPodの[設定](/glossary/設定/)を確認します。

```bash
kubectl describe node <node-name>
kubectl get pod <pod-name> -n <namespace> -o yaml
```

そのPodをTaint付きノードで動かす設計なら、対応するTolerationを追加します。

```yaml
spec:
  tolerations:
    - key: "dedicated"
      operator: "Equal"
      value: "gpu"
      effect: "NoSchedule"
```

TolerationはTaintを許容する[設定](/glossary/設定/)であり、そのノードへの配置を保証するものではありません。[CPU](/glossary/cpu/)やラベルなど、ほかの条件も引き続き判定されます。[Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)にも、この点が明記されています。

Taintをノードから[削除](/glossary/削除/)すると、同じTaintで除外されていたほかのPodも配置候補に入ります。専用ノードを分離するための[設定](/glossary/設定/)かを確認し、単に警告を消す目的では[削除](/glossary/削除/)しないでください。

PVCを使うPodでは、PVのNode Affinityやゾーンも確認します。PVが特定ゾーンのノードでしか使えないのに、そのゾーンに配置可能なノードがなければスケジューリングできません。

```bash
kubectl get pvc -n <namespace>
kubectl get pv
kubectl describe pv <pv-name>
kubectl get nodes -L topology.kubernetes.io/zone
```

PVのNode Affinityについては[Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#node-affinity)で確認できます。

[イベント](/glossary/イベント/)が`0/0 nodes are available`になっている場合や、候補となるノードが見当たらない場合は、ノードの状態も確認します。

```bash
kubectl get nodes
```

ノードが`NotReady`なら、Podの[設定](/glossary/設定/)を変更する前にノード障害を調べます。自動スケールを利用している場合は、ノード追加処理の成否と、追加されるノードがPodのリソース、ラベル、Taint、ゾーンの条件を満たすかを確認してください。

## Pending・Preempting・OOMKilledとの違い

`Pending`はPodの状態です。配置先が決まっていない場合だけでなく、配置後に[イメージ](/glossary/イメージ/)取得などの起動準備をしている場合も含みます。`FailedScheduling`は[イベント](/glossary/イベント/)であり、その中でも配置先を決められない状態を示します。

`Preempting`は、高いPriorityを持つPodの配置場所を作るため、低いPriorityのPodを退避させようとしていることを示す[イベント](/glossary/イベント/)です。Preemptionが動いても、Podの要求量がノードのAllocatableを超えている場合や、Affinity、Taint、PVの条件が合わない場合は解決しません。[Pod Priority and Preemption](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)でも、低優先度Podの退避によって配置可能になるノードがある場合にPreemptionを試みると説明されています。

`Evicted`は、すでにノードへ配置されていたPodが退避されたことを示します。配置先をまだ決められない`FailedScheduling`とは発生する段階が異なります。

`OOMKilled`は、配置後に[コンテナ](/glossary/コンテナ/)が[メモリ](/glossary/メモリ/)制限を超えて終了した状態です。`Insufficient memory`は配置前にPodの[メモリ](/glossary/メモリ/)requestsを確保できない状態なので、同じ「[メモリ](/glossary/メモリ/)不足」でも確認する[設定](/glossary/設定/)が異なります。

## 解決手順のまとめ

`FailedScheduling`が出たら、最初に`kubectl describe pod`を実行し、`0/N nodes are available:`の後ろにある理由をすべて確認します。

`Insufficient cpu`や`Insufficient memory`なら、PodのrequestsとノードのAllocatable、配置済みPodの要求量を比較してください。現在の使用率だけでは配置できるかを判断できません。

リソースに問題がなければ、nodeSelector、Node Affinity、TaintとToleration、PVのNode Affinityを順に照合します。ノード自体が存在しない場合や`NotReady`の場合は、Podではなくノード側の復旧が先です。

複数の理由が並んでいるときは、すべてを解消する必要があります。Podの[設定](/glossary/設定/)を変える場合は、実行中のPodではなく、DeploymentやJobなど作成元の[マニフェスト](/glossary/マニフェスト/)を[修正](/glossary/修正/)してください。

免責事項：本記事の内容は一般的な[Kubernetes](/glossary/kubernetes/)[環境](/glossary/環境/)を前提としています。リソース要求、配置条件、Taint、ノード構成を[本番環境](/glossary/本番環境/)で変更する前に、可用性、費用、[セキュリティ](/glossary/セキュリティ/)方針への影響を検証してください。
