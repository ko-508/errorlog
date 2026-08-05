---
title: "Kubernetes RunContainerError：原因と解決策"
date: 2026-08-05
description: "Kubernetes の RunContainerError は、Pod sandbox 作成後に container runtime がコンテナ起動へ進めない状態です。message とノード状態から切り分けます。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_runcontainererror.png"]
errorCode: "RunContainerError"
urgency: "medium"
service: "Kubernetes"
error_type: "RunContainerError"
components: []
related_services: []
---

## 冒頭まとめ

`RunContainerError` は、HTTP のステータスコードではなく、Pod のコンテナ状態（`state.waiting.reason`）に現れる文字列です。kubelet の実装では、
ランタイムが Pod のコンテナの起動に失敗したときに返るエラーとして `RunContainerError` が定義されています
（[pkg/kubelet/container/sync_result.go](https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/container/sync_result.go)）。つまり Pod のスケジュールとイメージの取得は済み、Pod sandbox も用意された後、コンテナランタイム（containerd、CRI-O など）がコンテナを作成・起動する段階で止まっている状態です。

調査の出発点は 3 つだけです。

1. `kubectl describe pod` で reason が本当に `RunContainerError` か確認し、その隣にある message を読む（実際の失敗理由はここに現れます）。
2. message がワークロード設定（`command`、`args`、`workingDir`、`securityContext`、`volumeMounts` など）に起因するのか、ノード上の条件に起因するのかを判定する。
3. 同じ Pod が別ノードでも失敗するかを見て、ノード固有かワークロード固有かを切り分ける。

この記事は「sandbox は作成済みで、コンテナの起動に失敗している段階」に限定して扱います。`FailedCreatePodSandbox` のようにアプリコンテナの起動前で止まっている場合は、後述の境界表のとおり別の切り分けが必要です。

## エラーの概要

Kubernetes の Pod は、スケジュール、イメージ取得、Pod sandbox 作成、コンテナ作成、コンテナ起動という段階を踏みます。kubelet は失敗した段階ごとに別のエラー文字列を持っており、`RunContainerError` はそのうち「コンテナの起動に失敗した」段階に対応します（
同じファイル内に `KillContainerError` や `CreatePodSandboxError` など、段階の異なるエラーが並んで定義されています
）。

したがって `RunContainerError` が出ているとき、次のことは基本的に成立しています。

- Pod はノードにスケジュールされている（Pending で止まってはいない）。
- コンテナランタイムが起動処理まで到達している（sandbox の作成前で止まってはいない）。
- アプリケーションのプロセスはまだ動いていない（起動後に落ちる問題とは別）。

似た表示との境界を、先に確定させてください。

| 表示 | どの段階の失敗か | この記事の対象 |
| --- | --- | --- |
| `RunContainerError`（コンテナの `waiting.reason`） | sandbox 作成後、ランタイムがコンテナを起動できない | 対象 |
| `FailedCreatePodSandbox`（Pod の Events） | Pod sandbox の作成に失敗。アプリコンテナの起動前の問題 | 対象外（[Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/) の手順で Events から確認し、[CNI プラグイン](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)とネットワーク設定、[コンテナランタイム](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)や sandbox 用イメージの設定を優先して確認します） |
| `CrashLoopBackOff` | コンテナの起動には成功したが、終了と再起動を繰り返している | 対象外（アプリケーションの終了理由と終了コードを追う） |
| `RunContainerError` 以外の reason（`CreateContainerConfigError` など） | kubelet が別の段階で失敗している | 対象外。表示された reason 文字列をそのまま確認し、その段階の調査に切り替える |

Pod が動かないときに reason を読み違えると、調査対象のレイヤーごと間違えます。まず `kubectl describe pods <your-pod>` でコンテナの状態と直近のイベントを確認するのが、公式ドキュメントでも示されている最初の一手です（[Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)）。

## エラーメッセージの読み方

`RunContainerError` 自体は「どの段階で失敗したか」しか伝えません。原因を特定する情報は、隣に置かれる message 側にあります。

```bash
kubectl describe pod <your-pod> -n <your-namespace>
```

出力のうち、注目するのはコンテナの State の並びです（表示位置の模式図。実際の文言は環境やランタイムによって異なります）。

```text
State:          Waiting
  Reason:       RunContainerError
  Message:      <コンテナランタイムが返したメッセージ>
Last State:     ...
Ready:          False
Restart Count:  ...
Events:
  ...
```

message を機械的に取り出したい場合は、次のように参照します。

```bash
# アプリコンテナの reason と message
kubectl get pod <your-pod> -n <your-namespace> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" | "}{.state.waiting.reason}{" | "}{.state.waiting.message}{"\n"}{end}'

# init コンテナ側で止まっている場合
kubectl get pod <your-pod> -n <your-namespace> \
  -o jsonpath='{range .status.initContainerStatuses[*]}{.name}{" | "}{.state.waiting.reason}{" | "}{.state.waiting.message}{"\n"}{end}'
```

読み方のポイントは次の 3 点です。

- message はコンテナランタイム側から伝わってきた文言です。実行ファイルが見つからない、権限が拒否された、マウントできなかった、といったランタイム層の語彙で書かれます。推測せず、文言をそのまま調査の起点にしてください。
- `kubectl logs` は当てになりません。プロセスがまだ開始できていないため、アプリケーションのログが空になるのが普通です。ログが空であること自体は追加の情報になりません。
- Events に `FailedCreatePodSandbox` が先行していないか確認します。先行していれば、失敗の主戦場は sandbox 側であり、この記事の対象外です。

message の文言は Kubernetes ではなくランタイム（containerd、CRI-O、runc など）が生成するため、意味を確定させたいときは、使っているランタイムの公式ドキュメントやリポジトリで同じ文言を確認するのが確実です。

## 原因と解決策

### 原因 1：コンテナの実行設定が不正で、プロセスを開始できない

`command`、`args`、`workingDir`、実行ファイルのパスや実行権限、`securityContext` の実行ユーザー指定などが噛み合っていないと、ランタイムはコンテナ作成・起動の段階で失敗します。イメージ内に存在しないパスを `command` に指定した、`workingDir` がイメージ内に無い、非 root 実行を指定したがファイルの権限が合っていない、といったパターンが典型です。

対処は、マニフェストの上書き設定を外して、イメージ本来の設定で起動するかを確かめる方向で進めます。

```yaml
# Before：イメージの entrypoint を上書きしている
spec:
  containers:
    - name: app
      image: <your-image>
      command: ["/opt/app/bin/start"]
      workingDir: /opt/app
      securityContext:
        runAsUser: 1000
```

```yaml
# After：上書きを外し、まずイメージ既定の設定で起動を確認する
spec:
  containers:
    - name: app
      image: <your-image>
```

これで起動するなら、外した項目を 1 つずつ戻して、どの設定で再発するかを特定します。イメージ内の実際のパスや実行権限は、同じイメージをローカルのコンテナランタイムで起動して確認するか、`kubectl debug` などでイメージの中身を確認して突き合わせます。

### 原因 2：マウントやノード上の制約でコンテナを作成・起動できない

`volumeMounts`、Secret、ConfigMap、`hostPath` の指定と、ノード上の実体・権限が合っていない場合も、この段階で失敗します。SELinux、AppArmor、seccomp といったノード側のセキュリティ機構が、指定されたマウントや実行を拒否している場合も同様です。

切り分けは、ボリュームとセキュリティ設定を落とした最小構成から積み上げるのが最短です。

```bash
# 現在の Pod がどのボリュームとセキュリティ設定を持っているか棚卸しする
kubectl get pod <your-pod> -n <your-namespace> -o yaml \
  | grep -A 40 -E 'volumeMounts:|volumes:|securityContext:'
```

最小構成（ボリューム無し、追加のセキュリティ設定無し、同じイメージ、同じノード）で起動するなら、原因はマニフェスト側の設定にあります。最小構成でも失敗するなら、原因 3 のノード側を疑います。

なお、`privileged: true` の付与や SELinux・AppArmor の無効化は、原因を確定させるための一時的な検証としては使えますが、恒久的な解決策にはしないでください。保護機構を外す変更は、そのノード上の他のワークロードの隔離まで弱めます。恒久策としては、必要な権限やラベル、ボリュームのパーミッションを個別に見直します。

### 原因 3：ノード側のコンテナランタイムやリソースの状態が不整合

containerd や CRI-O、runc、cgroup、ディスク容量、展開済みイメージレイヤなど、ノード側の状態が壊れていても、コンテナの作成・起動は失敗します。この場合、同じマニフェストが他のノードでは問題なく動く、あるいは同じノード上の別の Pod も同時に失敗する、といった形で症状が出ます。

判定に使う情報は次の 2 つです。

```bash
# 1. 問題の Pod が乗っているノードを特定する
kubectl get pod <your-pod> -n <your-namespace> -o wide

# 2. そのノード上の他の Pod も失敗していないか確認する
kubectl get pods -A -o wide --field-selector spec.nodeName=<your-node>
```

同じノードに偏って失敗しているなら、ノード側を調べます。systemd で管理されているノードでは、kubelet とコンテナランタイムのログ、サービスの状態、ディスクの空き容量を順に確認します。

```bash
# ノードにログインして実行
sudo journalctl -u kubelet --since "30 min ago" --no-pager
sudo systemctl status containerd    # CRI-O の場合は crio
sudo journalctl -u containerd --since "30 min ago" --no-pager
df -h
```

ノード上のランタイムやコンテナを直接検査したい場合は、CRI 互換ランタイム用のコマンドラインツール `crictl` が使えます。Kubernetes の公式ドキュメントでは、
「ノード上のコンテナランタイムとアプリケーションを検査・デバッグできる」
ツールとして案内されています（[Debugging Kubernetes nodes with crictl](https://kubernetes.io/docs/tasks/debug/debug-cluster/crictl/)）。使えるサブコマンドと構文は環境のバージョンによって差があるため、`crictl --help` と公式ページで確認してから実行してください。

ランタイム側の設定を疑う場合、containerd では設定ファイルの既定パスが `/etc/containerd/config.toml` で、CRI 用の設定は `[plugins."io.containerd.grpc.v1.cri"]` セクションにまとまっています（[containerd CRI Plugin Config Guide](https://github.com/containerd/containerd/blob/main/docs/cri/config.md)）。個別の設定キーは版によって変わるため、値を書き換える前に必ず使用中の版のドキュメントで確認してください。ランタイムそのものの導入・構成については [Container Runtimes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/) が起点になります。

## 確認・切り分け手順

上から順に実行すると、原因のレイヤーが 1 つずつ確定します。

1. **reason を確定する**

```bash
kubectl get pod <your-pod> -n <your-namespace> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" | "}{.state.waiting.reason}{"\n"}{end}'
```

reason が `RunContainerError` でなければ、この記事の手順は当てはめません。表示された reason に対応する段階の調査に切り替えます。

2. **message とイベントを読む**

```bash
kubectl describe pod <your-pod> -n <your-namespace>
kubectl get events -n <your-namespace> --sort-by=.lastTimestamp
```

`FailedCreatePodSandbox` が先行していないかをここで確認します。

3. **ワークロード設定かノードかを分ける**

同じイメージで、`command`、`args`、`workingDir`、`securityContext`、`volumeMounts` を外した最小構成の Pod を、同じノードに置いて起動します。

- 最小構成が起動する場合：マニフェスト側（原因 1、原因 2）。外した項目を 1 つずつ戻して再現条件を特定します。
- 最小構成も失敗する場合：ノード側（原因 3）。

4. **ノード固有かどうかを見る**

問題の Pod を別のノードで起動し、結果を比べます。片方のノードだけで失敗するなら、そのノードのランタイム状態を調べます。

5. **ノード側のログと状態を確認する**

kubelet とコンテナランタイムのログ、サービスの稼働状態、ディスク容量、`crictl` によるランタイムの応答を確認します（コマンドは原因 3 のとおり）。

6. **修正後に解決を確認する**

```bash
kubectl get pod <your-pod> -n <your-namespace> -w
# Deployment 経由の場合
kubectl rollout status deployment/<your-deployment> -n <your-namespace>
```

期待する状態は、コンテナが Running かつ Ready になり、`waiting.reason` が消え、`Restart Count` が増え続けないことです。Running には入るが再起動を繰り返す場合、問題は起動段階から起動後の段階へ移っており、`RunContainerError` の調査は完了しています。

## それでも解決しない場合

ここまでで原因が確定しない場合は、次の情報をそろえてから相談・報告に進んでください。推測を足さず、観測した文言をそのまま残すことが重要です。

- `kubectl describe pod <your-pod> -n <your-namespace>` の全文（reason と message を含む）
- `kubectl get pod <your-pod> -n <your-namespace> -o yaml` の内容（Secret の値などの秘密情報は `<your-secret>` のように置き換える）
- 失敗しているノード名と、そのノード上の他 Pod の状態
- ノードの kubelet ログとコンテナランタイムのログの該当時刻部分
- 使用しているコンテナランタイムの種類と版、Kubernetes の版
- 最小構成での再現結果（起動したか、失敗したか）

進め方の指針として、次の公式ドキュメントを参照してください。

- [Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)：Pod の状態と Events を起点にした切り分け手順。
なおこのページはアプリケーション側のデバッグを対象としており、クラスター自体のデバッグは別ページに案内されています
。
- [Debugging Kubernetes nodes with crictl](https://kubernetes.io/docs/tasks/debug/debug-cluster/crictl/)：ノード上のランタイムとコンテナを直接検査する方法。
- [Container Runtimes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/)：ノードのランタイム構成の前提条件。
- [containerd CRI Plugin Config Guide](https://github.com/containerd/containerd/blob/main/docs/cri/config.md)：containerd を使う場合の CRI 設定の確認先。
- [pkg/kubelet/container/sync_result.go](https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/container/sync_result.go)：`RunContainerError` を含む kubelet のエラー定義。段階の対応関係を確かめたいときの一次情報です。

message の文言が特定のランタイムに固有だと分かった場合は、そのランタイムのリポジトリの Issue を、実際の文言で検索するのが有効です。Kubernetes 側の不具合が疑われる場合は、上記のログと再現手順をそろえて kubernetes/kubernetes の Issue を確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
