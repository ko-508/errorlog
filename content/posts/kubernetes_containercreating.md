---
title: "ContainerCreating：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "ContainerCreating は原因名ではなく、コンテナをまだ開始できていないという表示です。FailedMount がある場合は、ボリューム準備のどの段階で止まったかをイベントの末尾から読みます。古い失敗記録と現在の状態を分けて確認します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_containercreating.png"]
errorCode: "ContainerCreating"
lastmod: 2026-08-05T00:00:00+09:00
service: "Kubernetes"
error_type: "ContainerCreating"
components: ["kubelet", "Volume Manager", "CSI"]
related_services: ["kubectl", "PersistentVolumeClaim", "StorageClass"]
trend_incident: false
---

## 冒頭まとめ

`ContainerCreating` は、根本原因を示す[エラー](/glossary/エラー/)名ではありません。`kubectl get pods` が、[Kubernetes](/glossary/kubernetes/)で[コンテナ](/glossary/コンテナ/)をまだ開始できていない状態を要約して表示したものです。

```text
NAME                      READY   STATUS              RESTARTS   AGE
app-7f6f8d9c75-2kq8m     0/1     ContainerCreating   0          8m
```

[API](/glossary/api/)上では、Podの段階は `Pending`、[コンテナ](/glossary/コンテナ/)の状態は `Waiting`、その理由が `ContainerCreating` になっていることがあります。

```text
Status:  Pending
State:   Waiting
  Reason: ContainerCreating
```

[Kubernetes公式のPodライフサイクル](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)は、`kubectl` の `STATUS` 欄をPodの `phase` と混同しないよう明記しています。`ContainerCreating` を見ただけでは、ボリューム、[イメージ](/glossary/イメージ/)取得、Podの通信環境、[コンテナ](/glossary/コンテナ/)実行基盤のどこで止まったかは決まりません。

そこで、次に `kubectl describe pod` の `Events` を読みます。

```text
Warning  FailedMount  2m (x8 over 7m)  kubelet
MountVolume.SetUp failed for volume "config" :
configmap "app-config" not found
```

この場合、`ContainerCreating` は現在の待機状態、`FailedMount` はボリュームの準備に失敗した試行の記録です。直す対象を示しているのは、`FailedMount` より後ろの文です。

```text
configmap "app-config" not found
rpc error: code = ... desc = ...
driver name ... not found in the list of registered CSI drivers
mount failed: exit status 32
volume is already exclusively attached to one node
```

つまり、**`ContainerCreating` を直接直すのではなく、最新[イベント](/glossary/イベント/)の具体的な失敗を直します**。`FailedMount` があるなら、最初に対象ボリューム名をPodの `volumes` と対応させ、参照先がSecret、ConfigMap、PVC、CSIのどれかを確定します。

もう1つ重要なのは、**`FailedMount` は現在も失敗中だという保証ではない**ことです。一度失敗しても、kubeletの再試行でマウントに成功し、Podが `Running` になることがあります。Eventsには過去の失敗が残るため、現在のPod状態、[イベント](/glossary/イベント/)の最終時刻、繰り返し回数を合わせて読みます。

## エラーの概要

公式文書によれば、[コンテナ](/glossary/コンテナ/)の状態は `Waiting`、`Running`、`Terminated` の3つです。`Waiting` は、[コンテナ](/glossary/コンテナ/)が起動に必要な処理をまだ終えていない状態で、[イメージ](/glossary/イメージ/)の取得やSecretの適用も含みます。

Podがノードへ割り当てられた後は、kubeletが必要なボリュームをマウントし、[コンテナ](/glossary/コンテナ/)実行基盤を通してPodの通信環境と[コンテナ](/glossary/コンテナ/)を準備します。[Podライフサイクルの公式説明](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-network-readiness)でも、必要なボリュームのマウント後に、Podの実行環境と通信設定を進める順序が示されています。

そのため、ボリュームの準備が終わらなければ、[アプリケーション](/glossary/アプリケーション/)の[コンテナ](/glossary/コンテナ/)はまだ動きません。

```text
Scheduled
  ↓
Volume attach / mount
  ↓
Pod sandbox / network
  ↓
Container start
```

この段階では、通常の `kubectl logs` に[アプリケーション](/glossary/アプリケーション/)の[ログ](/glossary/ログ/)がないことがあります。[アプリケーション](/glossary/アプリケーション/)が異常終了したのではなく、まだ開始されていないためです。原因はPodのEvents、PVCやPV、CSIドライバー、必要に応じてkubeletの[ログ](/glossary/ログ/)にあります。

`FailedMount` には、具体的な失敗と待機全体をまとめた失敗が混在します。

```text
# 具体的な失敗
MountVolume.SetUp failed for volume "config" :
configmap "app-config" not found

# 待機全体のまとめ
Unable to attach or mount volumes:
unmounted volumes=[config], unattached volumes=[config kube-api-access-x7q2m]:
timed out waiting for the condition
```

後者の `timed out waiting for the condition` だけでは、原因を特定できません。同じ時間帯にある、より具体的な `MountVolume.SetUp`、`MountVolume.MountDevice`、`MountVolume.WaitForAttach`、`FailedAttachVolume`、`rpc error` を探します。

## まず最初に：現在の状態・最新イベント・対象ボリュームを結ぶ

第一に、Podがノードへ割り当てられているかを確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> -o wide
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.status.phase}{"\t"}{.spec.nodeName}{"\n"}'
```

ノード名が空なら、マウントより前のスケジューリングで止まっています。`PodScheduled=False` と `FailedScheduling` を先に調べます。

第二に、現在の[コンテナ](/glossary/コンテナ/)状態と最近のEventsを確認します。

```bash
kubectl describe pod <Pod名> -n <名前空間>
kubectl events -n <名前空間> --for pod/<Pod名>
```

古い `kubectl` で `kubectl events` が使えない場合は、次の形でも確認できます。

```bash
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp
```

第三に、`FailedMount` に出たボリューム名をPodの定義と対応させます。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .spec.volumes[*]}{.name}{"\tPVC="}{.persistentVolumeClaim.claimName}{"\tSecret="}{.secret.secretName}{"\tConfigMap="}{.configMap.name}{"\n"}{end}'
```

たとえば、[イベント](/glossary/イベント/)に `volume "config"` とあり、結果が `ConfigMap=app-config` なら、最初に同じ名前空間の `app-config` を確認します。PVCなら、PVCからPV、StorageClass、CSIドライバーの順でたどります。

第四に、Podを削除する前に[イベント](/glossary/イベント/)を[保存](/glossary/保存/)します。kube-apiserverの `--event-ttl` の[既定値は1時間](https://kubernetes.io/docs/reference/command-line-tools-reference/kube-apiserver/#options)です。管理サービスでは設定が異なる場合がありますが、Eventsは長期保存を前提にした記録ではありません。

```bash
kubectl get pod <Pod名> -n <名前空間> -o yaml > pod-containercreating.yaml
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp > pod-events.txt
```

## よくある原因と解決手順

### 原因1：SecretまたはConfigMapが存在しない

代表的な形です。

```text
MountVolume.SetUp failed for volume "config" :
configmap "app-config" not found
```

```text
MountVolume.SetUp failed for volume "credentials" :
secret "app-secret" not found
```

まず、Podと同じ名前空間に対象があるかを確認します。

```bash
kubectl get configmap app-config -n <名前空間>
kubectl get secret app-secret -n <名前空間>
```

[ConfigMapの公式文書](https://kubernetes.io/docs/concepts/configuration/configmap/#configmaps-and-pods)では、PodとConfigMapは同じ名前空間に置く必要があると説明されています。Secretやprojected volumeの参照先も、Podと同じ名前空間が前提です。

名前の誤りなら、Podを作る元のDeploymentやStatefulSetを直します。

**Before（存在しない名前を参照）：**

```yaml
volumes:
  - name: config
    configMap:
      name: app-config-prodution
```

**After（実在する名前へ[修正](/glossary/修正/)）：**

```yaml
volumes:
  - name: config
    configMap:
      name: app-config-production
```

対象自体は存在していても、`items` で指定した[キー](/glossary/キー/)がなければ起動に失敗します。値を表示せず、[キー](/glossary/キー/)名だけ確認します。

```bash
kubectl get configmap app-config -n <名前空間> \
  -o go-template='{{range $k,$v := .data}}{{$k}}{{"\n"}}{{end}}'

kubectl get secret app-secret -n <名前空間> \
  -o go-template='{{range $k,$v := .data}}{{$k}}{{"\n"}}{{end}}'
```

[Secretの公式文書](https://kubernetes.io/docs/concepts/configuration/secret/#optional-secrets)には、必須のSecretまたは指定[キー](/glossary/キー/)が用意できるまで、Podの[コンテナ](/glossary/コンテナ/)は開始されないと記載されています。

`optional: true` にすれば、対象がなくても空の状態で進められます。ただし、[アプリケーション](/glossary/アプリケーション/)が設定なしで安全に動ける場合だけ使います。[エラー](/glossary/エラー/)を消す目的だけで必須の認証情報を任意扱いにすると、起動後の別の障害へ変わるだけです。

### 原因2：PVCが存在しない、またはPVへ結び付いていない

PodがPVCを参照している場合は、名前と状態を確認します。

```bash
kubectl get pvc -n <名前空間>
kubectl describe pvc <PVC名> -n <名前空間>
```

PVCが見つからない場合は、Podの `claimName` と作成順、名前空間を確認します。

```yaml
volumes:
  - name: data
    persistentVolumeClaim:
      claimName: app-data
```

PVCが `Pending` の場合は、Podを削除しても直りません。PVCのEventsを読み、要求容量、アクセスモード、StorageClass、動的作成を担当する処理を確認します。

```bash
kubectl get pvc <PVC名> -n <名前空間> -o wide
kubectl describe pvc <PVC名> -n <名前空間>
kubectl get storageclass
kubectl get storageclass <StorageClass名> -o yaml
```

[PersistentVolumeの公式文書](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#lifecycle-of-a-volume-and-claim)によれば、要求に合うPVがなければPVCは結び付かないまま残ります。要求容量だけでなく、StorageClass、アクセスモード、volumeMode、ラベル選択も一致する必要があります。

StorageClassが `volumeBindingMode: WaitForFirstConsumer` の場合、PVCがPod作成まで `Pending` なのは正常です。これは、Podの配置条件を見てから適切な場所にボリュームを用意する仕組みです。

ただし、[StorageClassの公式文書](https://kubernetes.io/docs/concepts/storage/storage-classes/#volume-binding-mode)は、この方式でPodの `nodeName` を直接指定するとスケジューラーを通らず、PVCが `Pending` のままになると注意しています。ノードを絞る場合は、`nodeSelector` やnode affinityを使います。

### 原因3：CSIドライバーが失敗ノードに登録されていない

永続ボリュームの多くは、CSIという[ストレージ](/glossary/ストレージ/)接続の共通方式を使います。次の文言なら、失敗したノードのkubeletが必要なCSIドライバーを使える状態ではありません。

```text
driver name disk.csi.example.com not found in the list of registered CSI drivers
```

まず、Podの配置先とPVが要求するドライバーを確認します。

```bash
NODE=$(kubectl get pod <Pod名> -n <名前空間> -o jsonpath='{.spec.nodeName}')

kubectl get csidriver
kubectl get csinode "$NODE" -o yaml
kubectl get pods -n kube-system -o wide --field-selector spec.nodeName="$NODE"
```

`CSINode` は、ノードに登録されたCSIドライバーの情報を持つ[オブジェクト](/glossary/オブジェクト/)です。[Kubernetes APIの公式資料](https://kubernetes.io/docs/reference/kubernetes-api/storage/csi-node-v1/)では、node-driver-registrarがkubeletへ登録すると、kubeletが `CSINode` を更新すると説明されています。

対象ドライバーが `CSINode` にない場合は、そのノードのCSI node Pod、`node-driver-registrar`、ソケットの登録、kubeletとの版の対応を確認します。対象ノードだけでCSI node Podが停止しているなら、PVCや[アプリケーション](/glossary/アプリケーション/)の定義ではなくノード側の問題です。

```bash
kubectl describe pod <CSI node Pod名> -n kube-system
kubectl logs <CSI node Pod名> -n kube-system -c <ドライバーのコンテナ名> --since=20m
kubectl logs <CSI node Pod名> -n kube-system -c node-driver-registrar --since=20m
```

CSIドライバーの名前空間や[コンテナ](/glossary/コンテナ/)名は製品ごとに異なります。`kube-system` と決めつけず、DaemonSetとPodの実際の配置を確認してください。

### 原因4：ボリュームの接続が終わっていない

[ネットワーク](/glossary/ネットワーク/)接続型や[クラウド](/glossary/クラウド/)のブロックストレージでは、ノードへの接続と、ノード内でのマウントが別の段階です。

```text
Warning  FailedAttachVolume
AttachVolume.Attach failed for volume "pvc-..." : ...

Warning  FailedMount
MountVolume.WaitForAttach failed for volume "pvc-..." : ...
```

この並びなら、`FailedMount` は接続失敗の後続結果です。先に `FailedAttachVolume` の具体的な文を直します。

```bash
kubectl get volumeattachment
kubectl describe volumeattachment <VolumeAttachment名>
kubectl get pv <PV名> -o yaml
```

よくあるのは、ReadWriteOnceのボリュームが以前のノードに接続されたまま、新しいノードへ移そうとしている場合です。

```text
Multi-Attach error for volume "pvc-..."
Volume is already exclusively attached to one node and can't be attached to another
```

ReadWriteOnceは、1つのノードから読み書きできる指定です。同じノード上の複数Podを必ず排除する指定ではありません。1つのPodだけに限定する必要がある場合は、対応するCSIドライバーで `ReadWriteOncePod` を使います。

古いノードやVolumeAttachmentを確認せず、[ストレージ](/glossary/ストレージ/)側で強制的に接続解除しないでください。以前のノードがまだ書き込んでいる状態で別ノードへ接続すると、ファイルシステムを壊す危険があります。ノードの生存、Podの終了、接続先、[ストレージ](/glossary/ストレージ/)提供元の手順を確認してから解除します。

また、PVの `nodeAffinity`、StorageClassの `allowedTopologies`、Podの配置先が異なる地域やゾーンを指していないかも確認します。

### 原因5：CSIまたはマウント処理の末尾に具体的な失敗がある

次の `exit status 32` や `rpc error` は、分類名であって原因そのものではありません。

```text
MountVolume.MountDevice failed for volume "pvc-..." :
rpc error: code = Internal desc = ...
```

```text
MountVolume.SetUp failed for volume "pvc-..." :
mount failed: exit status 32
Mounting command: mount
Mounting arguments: ...
Output: ...
```

読むべきなのは、`desc =` または `Output:` の後ろです。代表的な確認対象は次のとおりです。

```text
no such file or directory  → サーバー側の共有先、端末のパス、CSIの準備先
access denied              → ストレージ側の資格情報、NFS export、クラウド権限
wrong fs type              → PVやStorageClassのfsType、ノード側の補助道具
already mounted / busy     → 残ったマウント、同時処理、CSIの状態
context deadline exceeded  → CSI、ストレージAPI、ネットワークの無応答
```

PVとStorageClassの設定を確認します。

```bash
kubectl get pv <PV名> -o yaml
kubectl get storageclass <StorageClass名> -o yaml
```

その後、CSI controllerと失敗ノード上のCSI node Podの[ログ](/glossary/ログ/)を同じ時刻で確認します。PodのEventsが要約しか持たない場合でも、ドライバーの[ログ](/glossary/ログ/)には[ストレージ](/glossary/ストレージ/)提供元が返した識別子や理由が残ることがあります。

自己管理ノードで必要な場合は、kubeletの[ログ](/glossary/ログ/)も確認します。

```bash
sudo journalctl -u kubelet --since "20 minutes ago" --no-pager \
  | grep -E '<Pod名>|<PodのUID>|MountVolume|FailedMount'
```

マウント先の削除、手動 `umount`、CSI管理[ディレクトリ](/glossary/ディレクトリ/)の消去を最初の対処にしません。kubeletとCSIが管理する状態を手作業で変えると、実際の接続状態と記録がずれることがあります。

### 原因6：対象は存在するが、kubeletがSecretやConfigMapを取得できない

次の文言は、単純な名前の誤りと、kubelet側の取得遅延の両方で起こり得ます。

```text
failed to sync configmap cache: timed out waiting for the condition
failed to sync secret cache: timed out waiting for the condition
configmap "app-config" not found
```

最初に、同じ名前空間で対象が存在することを確認します。

```bash
kubectl get configmap app-config -n <名前空間>
kubectl get secret app-secret -n <名前空間>
```

対象が存在し、指定名と[キー](/glossary/キー/)も正しいのに、同じノードの複数Podで同時に失敗する場合は、kubeletと[API](/glossary/api/)[サーバー](/glossary/サーバー/)間の[通信](/glossary/通信/)、kubeletの監視処理、ノードの負荷を確認します。

[ConfigMapの公式文書](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically)には、kubeletがConfigMapの更新を監視または[キャッシュ](/glossary/キャッシュ/)し、定期的な[同期](/glossary/同期/)で内容を反映する仕組みが記載されています。`kubectl get` が成功するのは、操作端末から[API](/glossary/api/)[サーバー](/glossary/サーバー/)へ取得できたという事実です。失敗ノードのkubeletが同じ時刻に取得できた証明にはなりません。

実際に、公式課題（[Kubelet reports configmaps not found even though they do exist](https://github.com/kubernetes/kubernetes/issues/90725)）では、ConfigMapが存在して `kubectl get` でも取得できる一方、複数Podが `ContainerCreating` になり、kubeletが `configmap not found` を繰り返した事例が報告されています。

対象を削除して作り直す前に、失敗が1つのPodだけか、1つのノードに集中しているか、複数ノードで同時に起きているかを比較します。

```bash
kubectl get pods -A -o wide \
  --field-selector spec.nodeName=<ノード名>
kubectl get events -A --field-selector reason=FailedMount \
  --sort-by=.lastTimestamp
kubectl describe node <ノード名>
```

### 原因7：FailedMountは一度出たが、再試行で既に成功している

Eventsは、現在値だけを置き換える一覧ではありません。失敗した試行が記録された後、kubeletが再試行して成功しても、古い `FailedMount` はしばらく残ります。

次の3点を同時に確認します。

```bash
kubectl get pod <Pod名> -n <名前空間>
kubectl describe pod <Pod名> -n <名前空間>
kubectl events -n <名前空間> --for pod/<Pod名>
```

Podが `Running` かつ `Ready` で、`FailedMount` の最終時刻が古く、その後に `SuccessfulMountVolume`、`Pulled`、`Created`、`Started` が並んでいるなら、過去の失敗だけを見て[修正](/glossary/修正/)する必要はありません。

反対に、現在も `ContainerCreating` で、`FailedMount` の `Last Seen` が更新され続け、回数が増えているなら未解決です。

監視でも、`FailedMount` が1回出た事実だけを障害条件にすると、一時的な再試行を恒久障害として通知します。Podが一定時間 `Waiting` のままか、直近の失敗が繰り返されているか、Readyになったかを合わせて判定します。

### 原因8：FailedMountではなく、別の準備処理で止まっている

`ContainerCreating` でも `FailedMount` がない場合は、最新のWarning[イベント](/glossary/イベント/)を読みます。

```text
ErrImagePull / ImagePullBackOff
  → イメージ名、タグ、レジストリ認証、通信を確認する

FailedCreatePodSandBox
  → CNI、コンテナ実行基盤、Podの通信環境を確認する

CreateContainerConfigError
  → 環境変数が参照するSecretやConfigMap、コンテナ設定を確認する

FailedCreatePodContainer
  → コンテナ実行基盤が返した具体的な文を確認する
```

Secretが原因でも、ボリュームとして参照した場合は `FailedMount`、[環境変数](/glossary/環境変数/)として参照した場合は `CreateContainerConfigError` になることがあります。同じ対象名でも、Pod定義のどこから使っているかで失敗段階が変わります。

## 補足：似ているが別のもの

`Pending` はPodのphaseです。ノードへ未配置の場合と、配置済みだが[コンテナ](/glossary/コンテナ/)準備中の場合を含みます。`ContainerCreating` は、その中で `kubectl` が[コンテナ](/glossary/コンテナ/)の待機理由を表示したものです。

`ImagePullBackOff` は、[コンテナイメージ](/glossary/コンテナイメージ/)の取得に失敗し、再試行まで待っている状態です。ボリュームの `FailedMount` とは別の準備処理です。

`CreateContainerConfigError` は、[コンテナ](/glossary/コンテナ/)を作る設定を完成できない状態です。SecretやConfigMapが関係していても、volumeではなく `env` や `envFrom` から参照している場合はこちらになることがあります。

`FailedAttachVolume` は、[ストレージ](/glossary/ストレージ/)をノードへ接続する段階の失敗です。`FailedMount` は、そのボリュームをノード上で利用可能にする段階の失敗、または接続待ち全体の結果として出ます。両方がある場合は、時系列で先に出た具体的な接続失敗を優先します。

`CrashLoopBackOff` は、[コンテナ](/glossary/コンテナ/)が少なくとも一度は開始し、終了を繰り返している状態です。こちらではアプリケーションログと終了[コード](/glossary/コード/)が主な調査対象になります。`ContainerCreating` は開始前なので、通常のアプリケーションログがないこと自体は異常ではありません。

`MountVolume.SetUp succeeded` または `SuccessfulMountVolume` があっても、[コンテナ](/glossary/コンテナ/)開始が保証されたわけではありません。マウント後のPod通信環境、[イメージ](/glossary/イメージ/)取得、[コンテナ](/glossary/コンテナ/)作成で別の失敗が起きる可能性があります。最新[イベント](/glossary/イベント/)を最後まで読みます。

## 切り分けの順序

1. `kubectl get pod -o wide` で現在の状態、配置先ノード、経過時間を確認する。
2. `PodScheduled` がFalseなら、マウントではなく `FailedScheduling` を先に調べる。
3. `kubectl describe pod` とEventsを時系列で確認し、最新のWarningを読む。
4. `FailedMount` があれば、末尾の対象ボリューム名と具体的な失敗文を取り出す。
5. Podの `spec.volumes` で、対象がSecret、ConfigMap、PVC、CSIのどれかを確定する。
6. SecretやConfigMapなら、同じ名前空間の対象名と[キー](/glossary/キー/)を確認する。
7. PVCなら、PVCの状態からPV、StorageClass、CSIドライバーまでたどる。
8. `FailedAttachVolume` が先にあるなら、接続先ノード、VolumeAttachment、アクセスモード、場所の制約を確認する。
9. CSIの `rpc error` や `mount failed` は、`desc` と `Output` の末尾を読み、失敗ノードのCSI[ログ](/glossary/ログ/)と照合する。
10. Podの現在状態、[イベント](/glossary/イベント/)の最終時刻、回数を比べ、古い失敗記録か現在も続く失敗かを分ける。
11. `FailedMount` がなければ、[イメージ](/glossary/イメージ/)、Podの通信環境、[コンテナ](/glossary/コンテナ/)実行基盤など別の準備処理へ進む。
12. Pod削除やノード再起動は、証拠を[保存](/glossary/保存/)し、原因の範囲を絞った後に行う。

## 確認コマンド集

```bash
# 1. 現在の状態と配置先ノードを確認する
kubectl get pod <Pod名> -n <名前空間> -o wide

# 2. phase、ノード、コンテナの待機理由を確認する
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{.status.phase}{"\t"}{.spec.nodeName}{"\n"}{range .status.containerStatuses[*]}{.name}{"\t"}{.state.waiting.reason}{"\t"}{.state.waiting.message}{"\n"}{end}'

# 3. Podの現在状態とEventsをまとめて確認する
kubectl describe pod <Pod名> -n <名前空間>

# 4. 対象Podのイベントだけを時系列で確認する
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp

# 5. ボリューム名と参照先を対応させる
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .spec.volumes[*]}{.name}{"\tPVC="}{.persistentVolumeClaim.claimName}{"\tSecret="}{.secret.secretName}{"\tConfigMap="}{.configMap.name}{"\n"}{end}'

# 6. PVCの状態とEventsを確認する
kubectl get pvc -n <名前空間>
kubectl describe pvc <PVC名> -n <名前空間>

# 7. 結び付いたPVとStorageClassを確認する
kubectl get pv <PV名> -o yaml
kubectl get storageclass <StorageClass名> -o yaml

# 8. 失敗ノードに登録されたCSIドライバーを確認する
kubectl get csinode <ノード名> -o yaml
kubectl get csidriver

# 9. ノード上のCSI node Podを探す
kubectl get pods -A -o wide --field-selector spec.nodeName=<ノード名>

# 10. 接続処理を確認する
kubectl get volumeattachment
kubectl describe volumeattachment <VolumeAttachment名>

# 11. FailedMountがどのPodとノードに集中しているか確認する
kubectl get events -A --field-selector reason=FailedMount \
  --sort-by=.lastTimestamp

# 12. 調査前の状態を保存する
kubectl get pod <Pod名> -n <名前空間> -o yaml > pod-containercreating.yaml
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp > pod-events.txt
```

## Editor's Note

`ContainerCreating` と `FailedMount` が分かりにくい理由は、**現在の要約と過去の試行記録が同じ画面に並ぶ**ことにあります。この境界は、[Kubernetes](/glossary/kubernetes/)の公式課題でも繰り返し問題になっています。

2017年の報告（[FailedMount event can be misleading](https://github.com/kubernetes/kubernetes/issues/42867)）では、ボリュームのマウントが最終的には成功したのに、Eventsには `FailedMount` だけが残り、現在も失敗中なのか分からないと指摘されました。報告者は、成功したことを示す[イベント](/glossary/イベント/)が必要だと求めています。

この課題に対して、同年に [SuccessfulMountVolumeを追加する変更](https://github.com/kubernetes/kubernetes/pull/43852) が取り込まれました。変更の説明にも、最初のマウントは失敗しても、複数回の再試行後に成功し得るため、失敗だけが見えると判断を誤ると書かれています。

しかし、問題の構造はそれだけでは消えませんでした。2021年の報告（[False Positive: FailedMount events generated even when the pod comes up fine](https://github.com/kubernetes/kubernetes/issues/99475)）では、ServiceAccount用のボリュームで `failed to sync secret cache` が一時的に出た後、Podは正常に起動しました。報告者は、`FailedMount` だけで監視すると誤検知になるため、[イベント](/glossary/イベント/)を出す前に再試行してほしいと述べています。

さらに2022年の報告（[Inconsistent POD status reporting with kubectl get && describe](https://github.com/kubernetes/kubernetes/issues/109451)）では、同じPodが `kubectl get` では `ContainerCreating`、`kubectl describe` の `Status` では `Pending` と表示されました。報告内でも、前者は表示用の要約、後者はPodのphaseで、同じ項目を見ていないことが指摘されています。

3件が示しているのは、文言の正誤より、**どの時点の何を表す情報かを分ける必要がある**ということです。`ContainerCreating` は現在の待機理由をまとめた表示です。`Pending` はPodのphaseです。`FailedMount` は失敗した試行の[イベント](/glossary/イベント/)です。どれか1つだけでは、現在も障害が続いているかを判断できません。

だから、`ContainerCreating` を見たら状態名を検索して終わらず、最新[イベント](/glossary/イベント/)へ進みます。`FailedMount` を見たら、その存在だけで警報を確定せず、末尾の具体的な理由、最終時刻、回数、現在のReady状態を確認します。情報の種類と時刻をそろえることが、この組み合わせを正しく読むための中心です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
