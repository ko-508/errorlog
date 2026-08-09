---
title: "Kubernetes の Evicted：原因と解決策"
date: 2026-08-03
description: "Evicted は Pod が使いすぎたという意味ではありません。ノード側が閾値を割ったため、kubelet が誰かを選んで落とした結果です。文言に並ぶ使用量と要求量は選ばれた理由であって、退避が起きた原因ではありません。まず資源名と閾値から読みます。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_evicted.png"]
errorCode: "Evicted"
lastmod: 2026-08-03
service: "Kubernetes"
error_type: "Evicted"
components: ["kubelet", "Node"]
related_services: ["kubectl", "PodDisruptionBudget"]
trend_incident: false
---

## 冒頭まとめ

`Evicted` は、[Kubernetes](/glossary/kubernetes/) の kubelet が**ノードの資源を守るために Pod を落とした**状態です。実装では理由の文字列が `Evicted` と定義され、Pod は失敗として終了します。

最初に押さえるべきは、**これは Pod が使いすぎたという意味ではない**ことです。公式文書によれば、kubelet は退避シグナルを閾値と比較して退避を決めます。判定の対象はノード側の空き資源です。既定のハード閾値は次のとおりです。

```text
memory.available   < 100Mi（Linux）／< 500Mi（Windows）
nodefs.available   < 10%
imagefs.available  < 15%
nodefs.inodesFree  < 5%（Linux）
imagefs.inodesFree < 5%（Linux）
```

つまり、**ノードがこの線を割った瞬間に、誰かが落とされます**。落とされる側の使用量の多さは、順番を決める材料にすぎません。

ここが最大の誤解の元です。文言には「Container X was using 122Ki, request is 0」のような使用量と要求量が並びますが、**これは選ばれた理由であって、退避が起きた原因ではありません**。この表現が分かりにくいという指摘は、公式の課題として複数回登録されています。

もう1つ、`OOMKilled` との違いも重要です。公式文書に明記があり、**[コンテナ](/glossary/コンテナ/)が OOM で落とされた場合は再起動方針に従って再起動されますが、Pod の退避では再起動されません**。

## エラーの概要

一覧では状態として現れます。

```text
NAME                    READY   STATUS    RESTARTS   AGE
app-7d8f767544-pk4ch    0/1     Evicted   0          12m
app-7d8f767544-q2n8x    0/1     Evicted   0          12m
```

詳細を見ると、フェーズは失敗、理由が `Evicted`、そして本文に経緯が入ります。

```text
Status:   Failed
Reason:   Evicted
Message:  The node was low on resource: ephemeral-storage.
          Threshold quantity: 94576558032, available: 92034400Ki.
          Container app was using 122Ki, request is 0,
          has larger consumption of ephemeral-storage.
```

実装を読むと、この文言は部品の組み合わせで作られています。**どの資源が不足したか**、**閾値と実際の空き**、そして**選ばれた[コンテナ](/glossary/コンテナ/)の使用量と要求量**です。ほかに、ノードの状態を示す形式、一時領域の上限を超えた場合、一時的なボリュームの使用量が上限を超えた場合の文言も定義されています。

読むべき順番は決まっています。**まず資源名、次に閾値と空き、最後に[コンテナ](/glossary/コンテナ/)の情報**です。3つ目から読むと誤解します。

## まず最初に：どの資源が枯渇したかを確定する

第一に、本文の資源名を読みます。`ephemeral-storage` なのか `memory` なのかで、調べる先がまったく違います。

第二に、閾値と空きの数値を読みます。ここに、退避が起きた瞬間のノードの状態が記録されています。

第三に、ノードの状態を確認します。`MemoryPressure`、`DiskPressure`、`PIDPressure` のどれが立っていたかを見ます。

第四に、[コンテナ](/glossary/コンテナ/)の使用量は最後に読みます。順番を決めた材料であって、原因ではありません。

## よくある原因と解決手順

### 原因1：一時領域（ephemeral-storage）の枯渇

最も多い形です。ノードの[ファイル](/glossary/ファイル/)システムが埋まると `DiskPressure` になり、退避が始まります。埋める側の代表は、[コンテナ](/glossary/コンテナ/)の[ログ](/glossary/ログ/)、一時的なボリューム、[イメージ](/glossary/イメージ/)の層の3つです。

**Before（要求量も上限も指定しない）：**

```yaml
resources: {}      # ephemeral-storage の指定なし
```

この状態では要求量が 0 として扱われ、後述の選択順により**最初に落とされる側に回ります**。

**After（一時領域にも要求量と上限を指定する）：**

```yaml
resources:
  requests:
    ephemeral-storage: "1Gi"
  limits:
    ephemeral-storage: "2Gi"
```

注意点があります。公式の課題として報告されているとおり、**文言に出る使用量には一時的なボリュームの使用が含まれません**。実装上、根[ファイル](/glossary/ファイル/)システムと[ログ](/glossary/ログ/)の使用量だけを合算しているためです。したがって「122Ki しか使っていないのに退避された」という状況が起こります。実際に埋めているのは別の場所だと考えてください。

```bash
# ノードの実際の空きを確認する
kubectl get --raw "/api/v1/nodes/<ノード名>/proxy/stats/summary" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)['node']
fs=d['fs']; print('nodefs available:', fs.get('availableBytes'), '/ inodesFree:', fs.get('inodesFree'))
r=d.get('runtime',{}).get('imageFs',{}); print('imagefs available:', r.get('availableBytes'))
"
```

### 原因2：メモリの枯渇

`memory.available` が閾値を割った場合です。既定は 100Mi（Linux）という、かなり際どい線です。

ここで `OOMKilled` との区別が要ります。**どちらも[メモリ](/glossary/メモリ/)不足ですが、主体が違います**。退避は kubelet がノードを守るために行い、Pod は再起動されません。OOM による停止は基本[ソフトウェア](/glossary/ソフトウェア/)側の仕組みが行い、[コンテナ](/glossary/コンテナ/)は再起動方針に従って再起動されます（[Kubernetes の OOMKilled の記事](/posts/kubernetes_oomkilled/)）。

公式には既知の問題も記載されています。kubelet は一定間隔で使用量を集めるため、**急激に増えた場合は圧迫を検知する前に基本[ソフトウェア](/glossary/ソフトウェア/)側が動く**ことがあります。つまり同じ原因でも、増え方の速さによって `Evicted` になるか `OOMKilled` になるかが変わり得ます。

対処として、公式には、極端な使用率を狙わないのであればシステム用に資源を予約する指定が現実的な回避策だと書かれています。

### 原因3：空きがあるのに退避される

報告の多い形です。[容量](/glossary/容量/)を見ても十分あるのに退避が続く、という状況です。疑う点が3つあります。

1つ目は、監視されているのが**どの[ファイル](/glossary/ファイル/)システムか**です。ノードの[ファイル](/glossary/ファイル/)システムと[イメージ](/glossary/イメージ/)用の[ファイル](/glossary/ファイル/)システムは別々に評価され、閾値も 10% と 15% で違います。

2つ目は、**[容量](/glossary/容量/)ではなく管理情報の枯渇**です。`inodesFree` が 5% を割っても同じ結果になります。[容量](/glossary/容量/)だけを見ていると気付けません。

3つ目は、閾値が**割合で指定されている**ことです。大きなディスクほど、割合で見た余裕は早く尽きます。

```bash
# 容量と管理情報の両方を見る（ノード上で）
df -h /var/lib/kubelet
df -i /var/lib/kubelet
```

なお、処理識別子の枯渇（`pid.available`）でも退避は起きます。`PIDPressure` が立っている場合はこちらです。

### 原因4：落とされる順番

公式文書に順序が明記されています。まず**使用量が要求量を超えているか**、次に**優先度**、最後に**要求量に対する超過の大きさ**です。

結果として、要求量を超えている `BestEffort` と `Burstable` の Pod が先に落ち、要求量の範囲に収まっている Pod は後になります。

重要な注記もあります。**kubelet は Pod の品質区分そのものを順序の決定には使いません**。区分は目安であり、とくに一時領域については区分の考え方が当てはまらない、と書かれています。

したがって、落とされたくない Pod には**要求量を正しく指定する**ことが最も効きます。指定していない Pod は常に真っ先に候補になります。

### 原因5：Evicted の Pod が溜まり続ける

退避された Pod は削除されず、失敗した状態のまま残ります。これは調査を可能にするための仕様ですが、放置すると一覧が埋まります。

自動的な回収はありますが、閾値は高めです。制御系の管理役には終了済み Pod の保持数の設定があり、**既定値は 12500** です。この数に達するまで回収されません。

```bash
# 溜まった Evicted の Pod をまとめて削除する
kubectl get pods -A --field-selector status.phase=Failed \
  -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,REASON:.status.reason' --no-headers \
  | awk '$3=="Evicted" {print $1, $2}' \
  | xargs -r -n2 sh -c 'kubectl delete pod -n "$0" "$1"'
```

削除は状況の解決ではありません。**原因が残っていれば、また溜まります**。

## 補足：似ているが別のもの

[コンテナ](/glossary/コンテナ/)が[メモリ](/glossary/メモリ/)の上限で停止した場合は `OOMKilled` です。前述のとおり、再起動されるかどうかが決定的に違います（[Kubernetes の OOMKilled の記事](/posts/kubernetes_oomkilled/)）。

割り当て先が決まらない場合は `Pending` です。退避は起動後、`Pending` は起動前という違いがあります（[Kubernetes の Pending の記事](/posts/kubernetes_pending/)）。

**退避には、まったく別の系統もあります**。利用者や道具が [API](/glossary/api/) を通じて明示的に要求する退避で、こちらは PodDisruptionBudget に阻まれると 429 が返ります（[Kubernetes の 429 の記事](/posts/kubernetes_429/)）。本記事が扱うのはノードの圧迫による退避で、仕組みも対処も別です。

ノードの状態が閾値の前後で揺れる場合、状態の切り替えには猶予があります。公式には、切り替えまでの待機時間の既定が5分と書かれています。解消したように見えても、条件が消えるまでには時間差があります。

ノード側のディスクが埋まる点では、[コンテナ](/glossary/コンテナ/)基盤そのものの容量問題とも地続きです（[Docker の no space left on device の記事](/posts/docker_no_space_left_on_device/)）。

## 切り分けの順序

1. 本文の資源名を読む。`ephemeral-storage` か `memory` かで調べる先が変わる。
2. 閾値と空きの数値を読む。退避時のノードの状態が記録されている。
3. ノードの状態（圧迫の種類）を確認する。
4. [コンテナ](/glossary/コンテナ/)の使用量は最後に読む。順番の材料であって原因ではない。
5. 一時領域なら、[ログ](/glossary/ログ/)・一時ボリューム・[イメージ](/glossary/イメージ/)の層を疑う。文言の使用量にボリュームは含まれない。
6. 空きがあるのに退避されるなら、[ファイル](/glossary/ファイル/)システムの別と管理情報の枯渇を確認する。
7. 落とされたくない Pod には要求量を指定する。未指定は常に先頭候補。
8. 溜まった Pod の削除は後始末。原因が残れば再発する。

## 確認コマンド集

```bash
# 1. 退避された Pod を理由つきで一覧する
kubectl get pods -A --field-selector status.phase=Failed \
  -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,REASON:.status.reason,NODE:.spec.nodeName'

# 2. 退避の本文（資源・閾値・使用量）を取り出す
kubectl get pod <Pod名> -n <名前空間> -o jsonpath='{.status.message}{"\n"}'

# 3. どのノードで多発しているかを数える
kubectl get pods -A --field-selector status.phase=Failed \
  -o jsonpath='{range .items[?(@.status.reason=="Evicted")]}{.spec.nodeName}{"\n"}{end}' \
  | sort | uniq -c | sort -rn

# 4. ノードの圧迫状態を確認する
kubectl get nodes -o custom-columns='NAME:.metadata.name,MEM:.status.conditions[?(@.type=="MemoryPressure")].status,DISK:.status.conditions[?(@.type=="DiskPressure")].status,PID:.status.conditions[?(@.type=="PIDPressure")].status'

# 5. ノードの実際の空き（容量と管理情報）を見る
kubectl get --raw "/api/v1/nodes/<ノード名>/proxy/stats/summary" | head -c 1200

# 6. 退避のイベントを時系列で見る
kubectl get events -A --field-selector reason=Evicted --sort-by=.lastTimestamp | tail -20

# 7. 要求量を指定していない Pod を洗い出す
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[0].resources.requests}{"\n"}{end}' \
  | awk -F'\t' '$3=="" || $3=="map[]"'

# 8. kubelet の閾値設定を確認する
kubectl get --raw "/api/v1/nodes/<ノード名>/proxy/configz" \
  | python3 -c "import json,sys; k=json.load(sys.stdin)['kubeletconfig']; print('evictionHard:', k.get('evictionHard')); print('evictionSoft:', k.get('evictionSoft'))"
```

## Editor's Note

この状態の分かりにくさは、**文言が原因を説明していない**ことに尽きます。それを公式の課題として指摘した記録があります（[when the pod is evicted due to low imagefs.available, the prompt is difficult to understand](https://github.com/kubernetes/kubernetes/issues/111553)）。

2022年7月の報告です。[イメージ](/glossary/イメージ/)用[ファイル](/glossary/ファイル/)システムの空きが閾値を割って退避が起きたのに、表示されたのは「一時領域が不足していた。[コンテナ](/glossary/コンテナ/)は 20977608Ki を使っており、要求量 0 を超えている」という趣旨の文言でした。

報告者の指摘は明快です。**この[コンテナ](/glossary/コンテナ/)は「要求量 0 を超えたから」退避されたのではない。ノードが設定された退避の閾値に達したから退避された**。だから「要求量 0 を超えている」という表示はやめるべきだ、と述べています。

同じ構造の指摘は、3年後にも出ています（[correct the usage of ephemeral storage volumes in the eviction message](https://github.com/kubernetes/kubernetes/issues/130439)）。2025年2月、一時的なボリュームに大量に書き込んで退避を起こしたところ、文言に出た使用量はわずか 122Ki でした。実装がこの数値を根[ファイル](/glossary/ファイル/)システムと[ログ](/glossary/ログ/)の合算として計算しており、ボリュームの使用量を含めていないためです。報告にはこう書かれています。**これほど少ししか使っていないように見えるのに、なぜ退避されるのかと利用者を混乱させかねない**。

2つの指摘は同じ地点を指しています。文言に並ぶ数値は、**kubelet が「誰を落とすか」を決めた過程の記録**であって、「なぜ落とす必要があったか」の説明ではありません。同じ誤解が3年を隔てて繰り返し報告されている事実が、この読み違えやすさを物語っています。

`Evicted` を見たら、[コンテナ](/glossary/コンテナ/)の数字から読まないでください。読むべきは資源名と閾値です。ノードで何が尽きたのか。答えは常にそちらにあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*