---
title: "Kubernetes Init:CrashLoopBackOff：原因と解決策"
date: 2026-08-05
draft: false
description: "init container が失敗して再起動待ちに入り、通常コンテナの起動へ進めない状態。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_init_crashloopbackoff.png"]
errorCode: "Init:CrashLoopBackOff"
urgency: "medium"
service: "Kubernetes"
error_type: "Init:CrashLoopBackOff"
components: ["kubelet", "init container", "Pod lifecycle"]
related_services: ["kubectl"]
---

## 冒頭まとめ

`Init:CrashLoopBackOff` は、Pod の init container が失敗して終了し、kubelet による再起動が繰り返されて[バックオフ](/glossary/バックオフ/)待ちに入っている状態を示します。[Kubernetes 公式ドキュメント](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/)では、init container は必ず完了まで実行され、次の init container が始まる前に成功して終了する必要があり、init container が失敗した場合は kubelet が成功するまでその init container を繰り返し再起動すると説明されています。つまりこの[エラー](/glossary/エラー/)が出ている間、通常（アプリ）[コンテナ](/glossary/コンテナ/)は一度も起動していません。

調査の出発点は次の 2 つです。

1. `kubectl describe pod <pod-name>` と `status.initContainerStatuses` で、どの init container が止まっているかを特定する。
2. `kubectl logs <pod-name> -c <init-container> --previous` で、直前に終了した[インスタンス](/glossary/インスタンス/)の終了理由を確認する。

本体[コンテナ](/glossary/コンテナ/)の `CrashLoopBackOff` と混同すると調査対象がずれます。`Init:` の接頭辞が付いている間は、修正対象は init container 側です。

## エラーの概要

`Init:CrashLoopBackOff` は Pod の `STATUS` 列に表示される文字列で、Pod の[初期化](/glossary/初期化/)フェーズで失敗が繰り返されていることを表します。

公式ドキュメントで確認できる init container の性質は次のとおりです。

- init container は通常の[コンテナ](/glossary/コンテナ/)とほぼ同じですが、[常に完了まで実行される](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/)点が異なります。各 init container は、次の init container が起動する前に成功して完了しなければなりません。
- init container が失敗した場合、kubelet はそれが成功するまで繰り返し再起動します。ただし Pod の `restartPolicy` が `Never` で、起動中に init container が失敗した場合は、[Kubernetes](/glossary/kubernetes/) は Pod 全体を失敗として扱います。
- Pod の `STATUS` は[初期化](/glossary/初期化/)の進み方を示します。[Debug Init Containers](https://kubernetes.io/docs/tasks/debug/debug-application/debug-init-containers/) では、たとえば `Init:1/2` は 2 つある init container のうち 1 つが成功して完了したことを示すと説明されています。

近い表示との違いを整理します。

| 表示 | 意味の範囲 | 修正対象 |
| --- | --- | --- |
| `Init:N/M` | [初期化](/glossary/初期化/)が進行中。M 個のうち N 個の init container が完了 | 進行が止まっているなら該当 init container |
| `Init:Error` | init container が失敗して終了した状態の表示 | init container |
| `Init:CrashLoopBackOff` | init container の失敗と再起動が繰り返され、[バックオフ](/glossary/バックオフ/)待ちに入っている状態 | init container |
| `CrashLoopBackOff`（`Init:` なし） | 通常[コンテナ](/glossary/コンテナ/)の起動後クラッシュと再起動の繰り返し | アプリコンテナ |
| `PodInitializing` | init container はすべて完了し、通常[コンテナ](/glossary/コンテナ/)の起動処理に入っている | init container 側の問題は解消済み |

`Init:CrashLoopBackOff` は「アプリが動いていない」ことの原因ではなく、「アプリが起動する前段で止まっている」ことの表示です。[Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) にあるとおり、Pod は Pending フェーズから始まり、主要[コンテナ](/glossary/コンテナ/)のいずれかが正常に起動すると Running へ移ります。[初期化](/glossary/初期化/)が完了しない Pod は Running へ進めません。

## まず最初に見るべき切り分け軸

原因を推測する前に、次の 5 点を観察します。ここで観察した内容と、後述の原因が対応します。

| 観察するもの | 確認方法 | 判断の方向 |
| --- | --- | --- |
| どの init container で止まっているか | `kubectl get pod <pod-name>` の `Init:N/M`、`kubectl describe pod` の Init Containers セクション | 複数ある場合は N 番目の次の init container が対象 |
| 終了[コード](/glossary/コード/)と Reason | `kubectl describe pod <pod-name>` の該当 init container の State / Last State（Exit Code、Reason） | `OOMKilled` ならリソース側、それ以外は処理内容側 |
| [ログ](/glossary/ログ/)が出ているか | `kubectl logs <pod-name> -c <init-container> --previous` | 出ている＝[プロセス](/glossary/プロセス/)は起動した。出ていない＝起動前に失敗した可能性 |
| Pod の[イベント](/glossary/イベント/) | `kubectl describe pod <pod-name>` の Events | マウント失敗、[イメージ](/glossary/イメージ/)取得失敗などはここに出ます |
| 再起動回数の増え方 | `kubectl get pod <pod-name> -w` の RESTARTS | 増え続けるなら失敗は継続中。止まっているなら別状態へ遷移した可能性 |

init container の状態は[プログラム](/glossary/プログラム/)からも読めます。Debug Init Containers では、Pod の `status.initContainerStatuses` [フィールド](/glossary/フィールド/)を読むことで init container の状態を取得できると案内されています。

```bash
kubectl get pod <pod-name> -o jsonpath='{range .status.initContainerStatuses[*]}{.name}{"\t"}{.ready}{"\t"}{.restartCount}{"\n"}{end}'
```

より詳細な状態（`waiting` / `terminated` の理由）を含めて見る場合は、[フィールド](/glossary/フィールド/)全体を出力します。

```bash
kubectl get pod <pod-name> -o jsonpath='{.status.initContainerStatuses}' | jq .
```

`jq` が使えない[環境](/glossary/環境/)では `kubectl get pod <pod-name> -o yaml` の `status.initContainerStatuses` を直接確認してください。

## よくある原因と解決手順

### 原因1：init container のコマンドや引数が失敗している

もっとも多いのは、init container が実行する[コマンド](/glossary/コマンド/)自体が失敗して非ゼロで終了しているケースです。init container は完了まで実行されて成功する必要があるため、[スクリプト](/glossary/スクリプト/)の 1 行が失敗しただけでも Pod は前に進めません。

確認：

```bash
kubectl logs <pod-name> -c <init-container> --previous
kubectl describe pod <pod-name>
```

[ログ](/glossary/ログ/)に実行時の[エラーメッセージ](/glossary/エラーメッセージ/)が出ている場合は、[コマンド](/glossary/コマンド/)の内容が原因です。[ログ](/glossary/ログ/)がまったく出ない場合は、[コマンド](/glossary/コマンド/)が実行される前（実行[ファイル](/glossary/ファイル/)が存在しない、[イメージ](/glossary/イメージ/)内に[シェル](/glossary/シェル/)がない、`command` の指定形式が違うなど）で失敗している可能性があります。実際に何が指定されているかは spec 側で確認します。

```bash
kubectl get pod <pod-name> -o jsonpath='{range .spec.initContainers[*]}{.name}{"\n"}  command: {.command}{"\n"}  args: {.args}{"\n"}{end}'
```

対処：

- [ログ](/glossary/ログ/)に出た[エラー](/glossary/エラー/)をそのまま解消します。[パス](/glossary/パス/)、[引数](/glossary/引数/)、[環境変数](/glossary/環境変数/)の有無を spec の記述と突き合わせます。
- 同じ[イメージ](/glossary/イメージ/)と[コマンド](/glossary/コマンド/)を、Pod と同じ namespace の一時 Pod で単体実行して再現させます。

```bash
kubectl run tmp-init-check -n <namespace> --rm -it \
  --image=<your-init-image> --restart=Never -- sh
```

解決確認：修正後の Pod で `STATUS` が `Init:N/M` を進み、`PodInitializing` を経て `Running` になり、`RESTARTS` が増えないことを確認します。

### 原因2：init container が参照する Secret、ConfigMap、volume、権限が不正

init container は通常[コンテナ](/glossary/コンテナ/)とは別に `env`、`envFrom`、`volumeMounts`、ServiceAccount 経由の[権限](/glossary/権限/)を使います。本体[コンテナ](/glossary/コンテナ/)側の定義が正しくても、init container 側の参照が欠けていれば init container だけが失敗します。

確認：

```bash
# Events にマウント関連の失敗が出ていないか
kubectl describe pod <pod-name>

# 参照先が存在するか
kubectl get configmap <configmap-name> -n <namespace>
kubectl get secret <secret-name> -n <namespace>

# init container 側の参照定義を抽出
kubectl get pod <pod-name> -o jsonpath='{range .spec.initContainers[*]}{.name}{"\n"}  mounts: {.volumeMounts}{"\n"}  envFrom: {.envFrom}{"\n"}{end}'
```

[API](/glossary/api/) を呼ぶ init container であれば、その Pod の ServiceAccount で操作が許可されているかを確認します。

```bash
kubectl auth can-i get secrets \
  --as=system:serviceaccount:<namespace>:<serviceaccount-name> \
  -n <namespace>
```

対処：

- 参照している Secret / ConfigMap を、Pod と同じ namespace に用意します。名前の綴りと[キー](/glossary/キー/)名も突き合わせます。
- volume を書き込み先として使う init container では、マウント先の[パス](/glossary/パス/)と書き込み[権限](/glossary/権限/)（`securityContext` の設定内容）が本体[コンテナ](/glossary/コンテナ/)と一致しているかを確認します。
- 権限不足であれば、必要な操作に絞った Role / RoleBinding を付与します。広い[権限](/glossary/権限/)をまとめて付与する方法は取りません。

秘密情報を扱う際は、[マニフェスト](/glossary/マニフェスト/)や[コマンド](/glossary/コマンド/)履歴に実値を残さないでください。記事中の値と同様に `<your-xxx>` 形式のプレースホルダーで管理し、実値は Secret 側に置きます。

解決確認：`kubectl describe pod <pod-name>` の Events にマウント失敗や参照[エラー](/glossary/エラー/)が再出力されないこと、該当 init container の `state` が `terminated` の正常完了に変わることを確認します。

### 原因3：待機先サービスや依存処理が完了せず終了している

依存する Service や[データベース](/glossary/データベース/)の起動を待つ init container は、待機に失敗すると非ゼロ終了し、再起動を繰り返します。待機処理に[タイムアウト](/glossary/タイムアウト/)がある実装では、依存先が遅いだけでも `Init:CrashLoopBackOff` になります。

確認：

```bash
# 依存先 Service と Endpoints が存在し、対象 Pod が紐付いているか
kubectl get svc <service-name> -n <namespace>
kubectl get endpoints <service-name> -n <namespace>

# 依存先 Pod 自体が起動しているか
kubectl get pod -n <namespace> -o wide
```

init container はすでに終了しているため、その中に `kubectl exec` で入って確認することはできません。名前解決や到達性は、同じ namespace の一時 Pod から確認します。

```bash
kubectl run tmp-net-check -n <namespace> --rm -it \
  --image=<your-debug-image> --restart=Never -- sh
```

対処：

- 依存先 Service の名前、namespace、[ポート](/glossary/ポート/)が init container の待機対象と一致しているかを合わせます。
- Endpoints が空の場合は、依存先 Pod 側の問題です。調査対象をそちらへ移します。
- 依存先の起動に時間がかかる構成では、待機処理の[タイムアウト](/glossary/タイムアウト/)と[リトライ](/glossary/リトライ/)間隔を実態に合わせます。待機を単に[削除](/glossary/削除/)すると、[初期化](/glossary/初期化/)されていない状態で本体[コンテナ](/glossary/コンテナ/)が起動します。

解決確認：init container の[ログ](/glossary/ログ/)に待機完了に相当する出力が出て、`STATUS` が次の段階へ進むことを確認します。

### 原因4：init container のリソース不足や OOM により終了している

init container にもリソース要求と上限が個別に効きます。本体[コンテナ](/glossary/コンテナ/)に十分な上限を与えていても、init container の上限が小さければ init container だけが停止します。

確認：

```bash
kubectl describe pod <pod-name>
```

該当 init container の Last State に表示される Reason と Exit Code を確認します。Reason が `OOMKilled` であれば、[メモリ](/glossary/メモリ/)上限に達して終了しています。[設定値](/glossary/設定値/)そのものは spec 側で確認します。

```bash
kubectl get pod <pod-name> -o jsonpath='{range .spec.initContainers[*]}{.name}{"\t"}{.resources}{"\n"}{end}'
```

ノード側の空き[容量](/glossary/容量/)が疑わしい場合は、ノードの割り当て状況も確認します。

```bash
kubectl describe node <node-name>
```

対処：

- `OOMKilled` の場合は、init container の `resources.limits.memory` を実際の使用量に合わせて見直します。処理内容（大きな[アーカイブ](/glossary/アーカイブ/)の展開、大量データのコピーなど）を軽くする方向も検討します。
- ノードに空きがない場合は、`Init:CrashLoopBackOff` ではなくスケジューリング側の事象が併発している可能性があります。Events を先に確認してください。

解決確認：再[デプロイ](/glossary/デプロイ/)後に Last State の `OOMKilled` が出なくなり、init container が完了することを確認します。

## 補足：似ているが別のもの

- **`CrashLoopBackOff`（`Init:` なし）**：通常[コンテナ](/glossary/コンテナ/)が起動後にクラッシュして再起動を繰り返している状態です。init container が成功するまで通常[コンテナ](/glossary/コンテナ/)は起動しないため、`Init:CrashLoopBackOff` の原因調査に本体[コンテナ](/glossary/コンテナ/)の[ログ](/glossary/ログ/)や設定を持ち込むと切り分けがずれます。両者は別々に[修正](/glossary/修正/)してください。
- **`Init:Error`**：init container が失敗して終了した状態の表示です。`Init:CrashLoopBackOff` は、その失敗と再起動が繰り返されて[バックオフ](/glossary/バックオフ/)待ちになった状態を指します。`restartPolicy` が `Never` の場合は、公式ドキュメントの説明どおり Pod 全体が失敗として扱われるため、繰り返し再起動による[バックオフ](/glossary/バックオフ/)表示にはなりません。
- **`FailedCreatePodSandbox`**：kubelet が Pod sandbox の作成に失敗した段階の[イベント](/glossary/イベント/)で、アプリコンテナ起動前の問題です（[Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)）。init container の[コマンド](/glossary/コマンド/)やマウント内容ではなく、[ネットワークプラグイン（CNI）とネットワーク設定](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)を優先して確認します。あわせて、[container runtime](https://kubernetes.io/docs/setup/production-environment/container-runtimes/) と pause / sandbox image の設定（containerd の場合は [CRI プラグインの設定](https://github.com/containerd/containerd/blob/main/docs/cri/config.md)）も切り分けの対象になります。
- **サイドカーコンテナ**：公式ドキュメントでは、サイドカーコンテナは主アプリケーションコンテナより先に起動して動作を継続する[コンテナ](/glossary/コンテナ/)と説明されており、Pod の初期化中に完了まで実行される init container とは別の扱いです。長時間動き続ける処理を init container として書くと、完了しないまま[初期化](/glossary/初期化/)が止まります。自分の Pod がどちらの想定かは、[Init Containers](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/) の該当節で確認してください。

## 危険な対応を行う前の確認

再起動が続く状況では手早く止めたくなりますが、次の対応は原因を隠したまま本番稼働させる結果になり得ます。主たる解決策として選ばないでください。

- **init container を[削除](/glossary/削除/)・コメントアウトして起動させる**：[初期化](/glossary/初期化/)が完了しないまま本体[コンテナ](/glossary/コンテナ/)が動きます。マイグレーション、設定生成、証明書配置などを担う init container では、データ不整合や不完全な設定での稼働につながります。[削除](/glossary/削除/)する場合は、その初期化処理が本当に不要であることを確認してからにします。
- **失敗する[コマンド](/glossary/コマンド/)の末尾に `|| true` を付けて成功扱いにする**：終了[コード](/glossary/コード/)だけが変わり、[初期化](/glossary/初期化/)の失敗は残ります。原因が特定できるまでは使いません。
- **権限不足を広い[権限](/glossary/権限/)で解消する**：ServiceAccount に過剰な[権限](/glossary/権限/)を与えると、失敗の原因は消えても影響範囲が広がります。`kubectl auth can-i` で不足している操作を特定し、その操作だけを許可します。
- **Pod を強制削除して証跡を消す**：`kubectl describe pod` の出力、`--previous` 付きの[ログ](/glossary/ログ/)、Events は再起動や[削除](/glossary/削除/)で失われます。対処に着手する前に[保存](/glossary/保存/)してください。
- **リソース上限を外して回避する**：`OOMKilled` の場合でも、上限を撤去するとノード全体の安定性に影響します。実測に基づいて上限値を調整します。

いずれの変更も、まず開発・検証環境の Pod で再現と確認を行ってから本番へ適用してください。

## 切り分けの順序

1. `kubectl get pod <pod-name>` で `STATUS` を確認し、`Init:` 付きであることと `Init:N/M` の進み具合を見ます。
2. `kubectl describe pod <pod-name>` の Init Containers セクションで、止まっている init container の名前、State / Last State、Exit Code、Reason、Restart Count を記録します。
3. 同じ出力の Events で、マウント失敗、[イメージ](/glossary/イメージ/)取得失敗、スケジューリング関連のメッセージがないかを確認します。
4. `kubectl logs <pod-name> -c <init-container> --previous` で直前の終了時の出力を確認します。[ログ](/glossary/ログ/)が空なら、[コマンド](/glossary/コマンド/)実行前の失敗を疑って手順 3 に戻ります。
5. Reason が `OOMKilled` なら原因 4、参照[エラー](/glossary/エラー/)やマウント失敗なら原因 2、待機処理の出力で止まっているなら原因 3、それ以外のアプリケーションエラーなら原因 1 へ進みます。
6. [修正](/glossary/修正/)を適用し、`STATUS` が `PodInitializing` を経て `Running` になること、`RESTARTS` が増えないことを確認します。
7. ここまでで原因が特定できない場合は、init container の spec（`command`、`args`、`env`、`volumeMounts`、`resources`）を最小構成まで削って再現の有無を切り分けます。

## 確認コマンド集

```bash
# 1. Pod の状態と初期化の進み具合
kubectl get pod <pod-name> -n <namespace>
kubectl get pod <pod-name> -n <namespace> -w

# 2. init container の状態、Exit Code、Reason、Events
kubectl describe pod <pod-name> -n <namespace>

# 3. init container の状態を構造化して取得
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{range .status.initContainerStatuses[*]}{.name}{"\t"}{.ready}{"\t"}{.restartCount}{"\n"}{end}'
kubectl get pod <pod-name> -n <namespace> -o yaml

# 4. ログ（現在のインスタンスと直前のインスタンス）
kubectl logs <pod-name> -n <namespace> -c <init-container>
kubectl logs <pod-name> -n <namespace> -c <init-container> --previous

# 5. init container の spec を確認
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{range .spec.initContainers[*]}{.name}{"\n"}  command: {.command}{"\n"}  args: {.args}{"\n"}  resources: {.resources}{"\n"}  mounts: {.volumeMounts}{"\n"}{end}'

# 6. 参照先リソースの存在確認
kubectl get configmap,secret -n <namespace>
kubectl get svc,endpoints -n <namespace>

# 7. 権限の確認
kubectl auth can-i <verb> <resource> \
  --as=system:serviceaccount:<namespace>:<serviceaccount-name> -n <namespace>

# 8. Pod に紐づくイベントを時系列で確認
kubectl get events -n <namespace> \
  --field-selector involvedObject.name=<pod-name> --sort-by=.lastTimestamp

# 9. 依存先への到達性を一時 Pod から確認
kubectl run tmp-net-check -n <namespace> --rm -it \
  --image=<your-debug-image> --restart=Never -- sh

# 10. ノード側のリソース状況
kubectl describe node <node-name>
```

各[コマンド](/glossary/コマンド/)のオプションは [Kubernetes](/glossary/kubernetes/) の[バージョン](/glossary/バージョン/)によって差があります。手元の[環境](/glossary/環境/)で使える形式は `kubectl <subcommand> --help` と公式リファレンスで確認してください。init container の状態確認と[デバッグ](/glossary/デバッグ/)の流れは [Debug Init Containers](https://kubernetes.io/docs/tasks/debug/debug-application/debug-init-containers/)、init container の実行順序と失敗時の挙動は [Init Containers](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/)、Pod のフェーズ遷移は [Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) が一次情報です。

## Editor's Note

init container は「アプリコンテナの前に実行され、完了してから次へ進むもの」として扱うのが切り分けの軸です。[Kubernetes](/glossary/kubernetes/) 公式ドキュメントは、現在のサイドカーコンテナを「主アプリケーションコンテナより先に起動し、実行を継続する[コンテナ](/glossary/コンテナ/)」と説明し、完了まで実行される init container と分けて説明しています。[初期化](/glossary/初期化/)のために一度だけ完了すべき処理なのか、Pod の生存中ずっと動く補助処理なのかを分けておくと、`Init:CrashLoopBackOff` を `CrashLoopBackOff` やサイドカーの停止と混同しにくくなります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
