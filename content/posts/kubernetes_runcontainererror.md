---
title: "Kubernetes RunContainerError：原因と解決策"
date: 2026-08-05
description: "RunContainerError はPod sandbox作成後、container runtimeがコンテナ起動へ進めない状態です。まずreason、message、Events、ノード偏りを分けて確認します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_runcontainererror.png"]
errorCode: "RunContainerError"
urgency: "medium"
service: "Kubernetes"
error_type: "RunContainerError"
components: ["kubelet", "container runtime", "runc", "cgroup"]
related_services: ["kubectl", "containerd", "CRI-O", "crictl"]
trend_incident: false
---

## 冒頭まとめ

`RunContainerError` は、[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)ではなく、Pod内の[コンテナ](/glossary/コンテナ/)状態に出る `waiting.reason` です。Podはノードに割り当てられ、Pod sandboxも作られた後、kubeletがcontainer runtimeへ[コンテナ](/glossary/コンテナ/)起動を依頼した段階で失敗しています。

```text
State:          Waiting
  Reason:       RunContainerError
  Message:      <container runtime が返した実メッセージ>
```

ここで重要なのは、`RunContainerError` という文字だけでは原因が決まらないことです。原因は隣にある `Message`、直近のEvents、そして同じノード上の他Podの状態から切り分けます。

まず次の4つを分けてください。

1. 表示されているreasonが本当に `RunContainerError` なのか。
2. messageがワークロード設定の問題を示しているのか。
3. volume、[権限](/glossary/権限/)、[セキュリティ](/glossary/セキュリティ/)設定など、Pod定義とノード条件の組み合わせで失敗しているのか。
4. containerd、CRI-O、runc、cgroup、ディスクなど、ノード側runtimeの問題なのか。

`kubectl logs` が空でも不思議ではありません。プロセスがまだ開始できていないため、アプリケーションログへ到達しないことがあります。最初に読むべきなのは、アプリログではなく `kubectl describe pod` のState、Message、Eventsです。

## エラーの概要

[Kubernetes](/glossary/kubernetes/)のPod起動は、ざっくり次の段階に分けられます。

```text
Scheduling
  ↓
Image pull
  ↓
Pod sandbox 作成
  ↓
Container 作成
  ↓
Container 起動
  ↓
Application 実行
```

`RunContainerError` は、このうち **Container作成または起動** の近辺で止まっている状態です。kubeletの実装では、`RunContainerError` は[コンテナ](/glossary/コンテナ/)起動時の失敗を表す[エラー](/glossary/エラー/)として定義されています（[sync_result.go](https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/container/sync_result.go)）。

したがって、`RunContainerError` を見た時点で、少なくとも次の切り分けが必要です。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{"\t"}{.state.waiting.reason}{"\t"}{.state.waiting.message}{"\n"}{end}'
```

init[コンテナ](/glossary/コンテナ/)で止まっている場合は、見る場所が変わります。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.initContainerStatuses[*]}{.name}{"\t"}{.state.waiting.reason}{"\t"}{.state.waiting.message}{"\n"}{end}'
```

似ている表示との境界も先に確定してください。

| 表示 | 失敗している段階 | 本記事の対象 |
| --- | --- | --- |
| `RunContainerError` | sandbox作成後、runtimeが[コンテナ](/glossary/コンテナ/)を起動できない | 対象 |
| `CreateContainerConfigError` | kubeletが[コンテナ](/glossary/コンテナ/)設定を解決できない | 対象外 |
| `FailedCreatePodSandbox` | sandbox作成、CNI、pause container付近 | 対象外 |
| `ImagePullBackOff` / `ErrImagePull` | [イメージ](/glossary/イメージ/)取得 | 対象外 |
| `CrashLoopBackOff` | 起動後にプロセスが終了し再起動を繰り返す | 対象外 |

[Kubernetes](/glossary/kubernetes/)公式のPod[デバッグ](/glossary/デバッグ/)手順でも、まずPodを確認し、`kubectl describe` で状態と最近のEventsを見る流れが示されています（[Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)）。

## まず最初に：reason・message・Events・ノード偏りを分ける

第一に、reasonを確定します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{"\t"}{.state.waiting.reason}{"\n"}{end}'
```

ここが `RunContainerError` でなければ、この記事の手順をそのまま当てはめません。表示されたreasonが示す段階へ戻ってください。

第二に、messageをそのまま[保存](/glossary/保存/)します。

```bash
kubectl describe pod <Pod名> -n <名前空間>
```

`RunContainerError` は段階名です。実際の原因は `Message:` にあります。実行[ファイル](/glossary/ファイル/)がない、[権限](/glossary/権限/)が拒否された、マウントできない、cgroupを作れない、runtimeが応答できない、といった語を探します。

第三に、Eventsで前段階の失敗が混ざっていないかを確認します。

```bash
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp
```

`FailedCreatePodSandbox` が繰り返し出ているなら、主戦場はsandbox作成側です。CNI、pause image、container runtimeのsandbox設定を優先し、`RunContainerError` の記事から離れます。

第四に、ノード偏りを見ます。

```bash
kubectl get pod <Pod名> -n <名前空間> -o wide
kubectl get pods -A -o wide --field-selector spec.nodeName=<ノード名>
```

同じワークロードが別ノードでは動くなら、ノード側runtimeやノード状態を疑います。どのノードでも同じmessageで失敗するなら、Pod定義や[イメージ](/glossary/イメージ/)内の実行設定を疑います。

## よくある原因と解決手順

### 原因1：command、args、workingDir、実行権限が不正

`command`、`args`、`workingDir`、実行[ファイル](/glossary/ファイル/)の[パス](/glossary/パス/)、実行権限、`runAsUser` などが噛み合っていないと、runtimeはプロセスを開始できません。[イメージ](/glossary/イメージ/)取得までは成功しているため、`kubectl logs` は空のままになりがちです。

**Before（entrypointを上書きしている）：**

```yaml
spec:
  containers:
    - name: app
      image: <your-image>
      command: ["/opt/app/bin/start"]
      workingDir: /opt/app
      securityContext:
        runAsUser: 1000
```

**After（まず[イメージ](/glossary/イメージ/)既定で起動を確認する）：**

```yaml
spec:
  containers:
    - name: app
      image: <your-image>
```

修正後は、同じimageでPodが起動するかを確認します。

```bash
kubectl apply -f <manifest.yaml>
kubectl get pod <Pod名> -n <名前空間> -w
```

これで起動するなら、外した項目を1つずつ戻します。`command` だけ、`workingDir` だけ、`securityContext` だけ、という順に戻すと、どの設定がruntimeを止めているかが分かります。

### 原因2：volumeMount、Secret、ConfigMap、hostPath、権限が合っていない

ボリュームの実体や[権限](/glossary/権限/)がPod定義と合っていない場合、runtimeが[コンテナ](/glossary/コンテナ/)を作れず `RunContainerError` になることがあります。特に `hostPath`、[ファイル](/glossary/ファイル/)としてマウントするSecret/ConfigMap、読み書き[権限](/glossary/権限/)、SELinuxやAppArmorの拒否はmessage側に出ます。

**Before（hostPathとsecurityContextを同時に疑う必要がある）：**

```yaml
spec:
  containers:
    - name: app
      image: <your-image>
      volumeMounts:
        - name: app-data
          mountPath: /var/lib/app
      securityContext:
        runAsUser: 1000
  volumes:
    - name: app-data
      hostPath:
        path: /var/lib/app
        type: Directory
```

**After（まずmountなしで起動段階を確認する）：**

```yaml
spec:
  containers:
    - name: app
      image: <your-image>
```

設定を棚卸しします。

```bash
kubectl get pod <Pod名> -n <名前空間> -o yaml \
  | grep -A 60 -E 'volumeMounts:|volumes:|securityContext:'
```

同じノードで最小構成が起動するなら、原因はPod定義側です。mountを戻した瞬間に再発するなら、ノード上の[パス](/glossary/パス/)、[権限](/glossary/権限/)、ラベル、[ファイル](/glossary/ファイル/)/[ディレクトリ](/glossary/ディレクトリ/)の型を確認します。

### 原因3：containerd、CRI-O、runc、cgroup、ディスクなどノード側runtimeが壊れている

同じPodが特定ノードでだけ失敗する場合は、ノード側のcontainer runtimeを見ます。containerd、CRI-O、runc、cgroup、ディスク[容量](/glossary/容量/)、展開済みimage layerの不整合が原因になることがあります。

**Before（ノード偏りを見ずにPod定義だけ直そうとしている）：**

```bash
kubectl describe pod <Pod名> -n <名前空間>
# Pod定義だけを繰り返し編集する
```

**After（失敗ノードを先に確定する）：**

```bash
kubectl get pod <Pod名> -n <名前空間> -o wide
kubectl get pods -A -o wide --field-selector spec.nodeName=<ノード名>
```

ノードに入れる場合は、kubeletとruntimeの[ログ](/glossary/ログ/)を確認します。

```bash
sudo journalctl -u kubelet --since "30 min ago" --no-pager
sudo systemctl status containerd
sudo journalctl -u containerd --since "30 min ago" --no-pager
df -h
```

CRI互換runtimeの状態を直接見る場合は `crictl` が使えます。[Kubernetes](/glossary/kubernetes/)公式ドキュメントは、ノード上のcontainer runtimeと[アプリケーション](/glossary/アプリケーション/)を検査・[デバッグ](/glossary/デバッグ/)するための[ツール](/glossary/ツール/)として `crictl` を案内しています（[Debugging Kubernetes nodes with crictl](https://kubernetes.io/docs/tasks/debug/debug-cluster/crictl/)）。

containerdのCRI設定を疑う場合、containerd側ではCRI pluginの設定が `plugins."io.containerd.grpc.v1.cri"` セクションにまとまります（[containerd CRI Plugin Config Guide](https://github.com/containerd/containerd/blob/main/docs/cri/config.md)）。ただし設定[キー](/glossary/キー/)は版によって変わるため、実行中の版のドキュメントと現在の `config.toml` を突き合わせてください。

## 補足：似ているが別のもの

`CreateContainerConfigError` は、SecretやConfigMapの参照、[環境変数](/glossary/環境変数/)、設定解決など、container runtimeへ起動を依頼する前の段階で止まる表示です。`RunContainerError` と同じ「[コンテナ](/glossary/コンテナ/)が動かない」見た目でも、調査対象はPod定義の解決側です。

`FailedCreatePodSandbox` は、Pod sandbox、CNI、pause container付近の失敗です。アプリコンテナの起動以前で止まっています。Eventsにこのreasonが出ているなら、CNI pluginやcontainer runtimeのsandbox設定を先に見ます。

`CrashLoopBackOff` は、[コンテナ](/glossary/コンテナ/)の起動には成功した後、[アプリケーション](/glossary/アプリケーション/)が終了して再起動を繰り返している状態です。この場合は `kubectl logs --previous` や終了[コード](/glossary/コード/)が主な手がかりです。

`ImagePullBackOff` と `ErrImagePull` は、image取得の失敗です。[認証](/glossary/認証/)、[タグ](/glossary/タグ/)、registry到達性を確認します。`RunContainerError` はimage取得後の段階です。

`OOMKilled` は、起動後に[メモリ](/glossary/メモリ/)制限などでプロセスが終了した結果です。`RunContainerError` はプロセス開始前または開始時点で止まるため、調査する時間軸が違います。

## 危険な対応を行う前の確認

`RunContainerError` でよくある危険な対応は、原因を確定しないまま[権限](/glossary/権限/)や保護機構を広げることです。

次の対応は、原因切り分けの一時検証に限定してください。

```yaml
securityContext:
  privileged: true
```

```yaml
securityContext:
  runAsUser: 0
```

```yaml
securityContext:
  seLinuxOptions: null
```

`privileged: true`、root実行、SELinux/AppArmor/seccompの無効化、hostPathの広範囲な付与は、Podの隔離を弱めます。動いたから恒久対応にするのではなく、どの[権限](/glossary/権限/)・ラベル・mount・実行ユーザーが必要だったのかを狭く戻します。

ノード側でruntimeを再起動する場合も、影響範囲を確認してください。

```bash
kubectl get pods -A -o wide --field-selector spec.nodeName=<ノード名>
kubectl cordon <ノード名>
```

本番ノードでcontainer runtimeを再起動すると、そのノード上のPodに影響します。まず対象ノードのPod、PodDisruptionBudget、冗長性を確認し、必要ならcordonやdrainの計画を立てます。

imageやレイヤを[削除](/glossary/削除/)する場合も、対象を限定します。

```bash
# 実行前に対象ノードと対象imageを確認する
crictl images
```

不要だからといって広範囲にimageやcontainer stateを消すと、他のPodの再起動や復旧に影響します。messageとruntime[ログ](/glossary/ログ/)で対象を絞ってから実行してください。

## 切り分けの順序

1. `containerStatuses` と `initContainerStatuses` のreasonを確認し、`RunContainerError` であることを確定する。
2. `kubectl describe pod` で `Message` をそのまま[保存](/glossary/保存/)する。
3. Eventsを時系列で確認し、`FailedCreatePodSandbox` やimage pull系の前段階[エラー](/glossary/エラー/)が主因でないか確認する。
4. `kubectl logs` が空でも、プロセス開始前なら異常ではないと判断する。
5. `command`、`args`、`workingDir`、`securityContext` を外した最小構成で同じimageを起動する。
6. volumeMount、Secret、ConfigMap、hostPathを1つずつ戻し、どの設定で再発するか確認する。
7. 同じPodを別ノードで動かし、ノード固有かワークロード固有かを分ける。
8. ノード固有なら kubelet、containerd/CRI-O、runc、cgroup、ディスク[容量](/glossary/容量/)を確認する。
9. 権限緩和やruntime再起動を行う前に、影響範囲と戻し方を決める。
10. 修正後は `waiting.reason` が消え、Podが `Running` かつ `Ready` になることを確認する。

## 確認コマンド集

```bash
# 1. Pod内の各コンテナのreason/messageを確認する
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{"\t"}{.state.waiting.reason}{"\t"}{.state.waiting.message}{"\n"}{end}'

# 2. initコンテナ側も確認する
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.initContainerStatuses[*]}{.name}{"\t"}{.state.waiting.reason}{"\t"}{.state.waiting.message}{"\n"}{end}'

# 3. describeでState、Message、Eventsをまとめて確認する
kubectl describe pod <Pod名> -n <名前空間>

# 4. Eventsを時系列で見る
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp

# 5. Pod定義を保存する
kubectl get pod <Pod名> -n <名前空間> -o yaml > pod-runcontainererror.yaml

# 6. 対象ノードを確認する
kubectl get pod <Pod名> -n <名前空間> -o wide

# 7. 同じノード上のPodを確認する
kubectl get pods -A -o wide --field-selector spec.nodeName=<ノード名>

# 8. ノード側でkubeletログを見る
sudo journalctl -u kubelet --since "30 min ago" --no-pager

# 9. containerdを使っている場合の状態とログ
sudo systemctl status containerd
sudo journalctl -u containerd --since "30 min ago" --no-pager

# 10. ディスク容量を確認する
df -h

# 11. CRI経由でruntime状態を見る
crictl ps -a
crictl pods
crictl images
```

## Editor's Note

`RunContainerError` が扱いにくい理由は、[Kubernetes](/glossary/kubernetes/)の表示が「runtimeが起動できなかった」という段階名で止まり、原因の本文はruntime由来のmessageに移ることです。[Kubernetes](/glossary/kubernetes/)の公式[デバッグ](/glossary/デバッグ/)手順はPodの状態とEventsを見るところから始めますが、`RunContainerError` ではそこからさらにcontainer runtime側の語彙へ降りる必要があります。

kubeletのソースにも、`RunContainerError` は `CreatePodSandboxError` や `KillContainerError` など段階の異なる[エラー](/glossary/エラー/)と並んで定義されています（[sync_result.go](https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/container/sync_result.go)）。つまり、この文字列は「[Kubernetes](/glossary/kubernetes/)全体が失敗した」という大ざっぱな印ではなく、Pod起動のどの境界で止まったかを示す印です。

一方で、ノード上の実態を見るには[Kubernetes](/glossary/kubernetes/) [API](/glossary/api/)だけでは足りないことがあります。[Kubernetes](/glossary/kubernetes/)公式の [`crictl` デバッグ手順](https://kubernetes.io/docs/tasks/debug/debug-cluster/crictl/)は、ノード上のcontainer runtimeと[コンテナ](/glossary/コンテナ/)を直接調べる方法を案内しています。`RunContainerError` では、Pod定義の[修正](/glossary/修正/)だけでなく、runtime[ログ](/glossary/ログ/)やCRIの状態確認まで含めて初めて原因が見えることがあります。

だから、`RunContainerError` を見たら、まず `Message` を読み、次にPod定義かノードかを分けてください。[権限](/glossary/権限/)を広げる、runtimeを再起動する、image stateを消す、といった操作は、原因の層が分かってから行う最後の手段です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
