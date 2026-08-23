---
title: "Kubernetes FailedCreatePodSandbox：原因と解決策"
date: 2026-08-05
description: "Kubernetes の FailedCreatePodSandbox は、kubelet が Pod sandbox を作成できない状態です。CNI、runtime、ノード状態から切り分けます。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_failedcreatepodsandbox.png"]
errorCode: "FailedCreatePodSandbox"
urgency: "medium"
service: "Kubernetes"
error_type: "FailedCreatePodSandbox"
components: []
related_services: []
---

## 冒頭まとめ

`FailedCreatePodSandbox` は、kubelet が Pod の sandbox（[ネットワーク](/glossary/ネットワーク/)名前空間や pause [コンテナ](/glossary/コンテナ/)といった、[コンテナ](/glossary/コンテナ/)起動前の土台）を作成できなかったときに記録される警告[イベント](/glossary/イベント/)です。Pod は `ContainerCreating` のまま止まり、kubelet は[リトライ](/glossary/リトライ/)を繰り返します。

原因はほぼ次の3方向に分かれます。

1. CNI プラグインまたは CNI 設定の不整合で、Pod の[ネットワーク](/glossary/ネットワーク/)設定（IP 割り当てを含む）に失敗している
2. container runtime が sandbox image（pause image）を取得・起動できず、sandbox [コンテナ](/glossary/コンテナ/)を作れない
3. ノード側の状態（ディスク、iptables/sysctl、カーネルモジュール、runtime プロセス）が壊れている

調査の出発点は「[イベント](/glossary/イベント/)本文の `desc =` 以降に書かれた、container runtime から返った実メッセージ」です。ここに `cni` / `network` / `image` / `no space left on device` のどの語が出ているかで、上の1〜3のどれを追うべきかがほぼ決まります。次に「1ノードだけの問題か、クラスタ全体か」を確認すると、ノード修復かクラスタ設定修正かの判断が付きます。

## エラーの概要

### これは HTTP ステータスではなく kubelet のイベント理由です

`FailedCreatePodSandbox` はエラーコードではなく、kubelet が Pod に対して発行する Event の `reason` です。`kubectl describe pod` の Events 欄や `kubectl get events` に現れます。

実際にクラスタ上で出力される文字列は **`FailedCreatePodSandBox`（`Box` の B が大文字）** です。[ログ](/glossary/ログ/)や[イベント](/glossary/イベント/)を検索するときは大文字小文字を区別しない検索（`grep -i`）を使うと取りこぼしが減ります。

### sandbox とは何か

[Kubernetes](/glossary/kubernetes/) の Pod は、内部の[コンテナ](/glossary/コンテナ/)が[ネットワーク](/glossary/ネットワーク/)名前空間などを共有する単位です。CRI（Container Runtime Interface）では、この共有される土台を「Pod sandbox」と呼びます。kubelet が Pod を起動する流れは、おおむね次の順序です。

1. kubelet が CRI の `RunPodSandbox` を container runtime に要求する
2. container runtime が sandbox image をもとに sandbox [コンテナ](/glossary/コンテナ/)（一般に pause [コンテナ](/glossary/コンテナ/)）を作り、名前空間を用意する
3. container runtime が CNI プラグインを呼び出し、Pod に[ネットワーク](/glossary/ネットワーク/)（[IP アドレス](/glossary/ip-アドレス/)やルート）を設定する
4. 成功後、init [コンテナ](/glossary/コンテナ/)とアプリコンテナの[イメージ](/glossary/イメージ/)取得・作成に進む

`FailedCreatePodSandBox` は、この1〜3のどこかで失敗した場合に出ます。**アプリコンテナの[イメージ](/glossary/イメージ/)や[コマンド](/glossary/コマンド/)はまだ関係しません。** ここを押さえると、Deployment の[マニフェスト](/glossary/マニフェスト/)ばかり見直して時間を失う事故を避けられます。

### 近い事象との違い

| 事象 | 失敗している段階 | 主な調査先 |
| --- | --- | --- |
| `FailedCreatePodSandBox` | sandbox 作成（名前空間・CNI・pause） | ノードの kubelet / runtime / CNI |
| `ErrImagePull` / `ImagePullBackOff` | アプリコンテナの[イメージ](/glossary/イメージ/)取得 | [レジストリ](/glossary/レジストリ/)疎通、`imagePullSecrets` |
| `CreateContainerConfigError` | sandbox 後の[コンテナ](/glossary/コンテナ/)設定 | 参照している ConfigMap / Secret |
| `CreateContainerError` | sandbox 後の[コンテナ](/glossary/コンテナ/)作成 | runtime、マウント、リソース設定 |
| `FailedScheduling`（Pending） | ノードへの割り当て前 | スケジューラ、リソース、taint |
| `FailedMount` | ボリュームのマウント | CSI [ドライバ](/glossary/ドライバ/)、PV/PVC |
| `CrashLoopBackOff` | [コンテナ](/glossary/コンテナ/)起動後 | [アプリケーション](/glossary/アプリケーション/)の[ログ](/glossary/ログ/) |

この記事が扱うのは1行目、つまり「sandbox が作れない」段階に限定します。sandbox 作成後に発生する `CreateContainerError` 系や、アプリイメージの pull 失敗は範囲外です。[イベント](/glossary/イベント/)の `reason` を先に確定させてから読み進めてください。

## エラーメッセージの読み方

[イベント](/glossary/イベント/)は典型的に次の構造で出力されます（`<...>` は[環境](/glossary/環境/)ごとに変わる部分です）。

```text
Warning  FailedCreatePodSandBox  <経過時間>  kubelet  Failed to create pod sandbox: rpc error: code = <gRPC コード> desc = <container runtime が返した実メッセージ>
```

読み方は3層に分けて考えます。

1. **`Failed to create pod sandbox`**：失敗した段階。sandbox 作成であることの確認。
2. **`rpc error: code = ... desc = ...`**：kubelet から container runtime への CRI（[gRPC](/glossary/grpc/)）呼び出しが失敗したという枠。`code` は [gRPC](/glossary/grpc/) のステータスで、原因の特定にはあまり使えません。
3. **`desc =` 以降**：container runtime が返した実メッセージ。**ここが唯一の手がかりです。**

`desc` 以降に含まれる語から、追うべき方向を判断します。

| メッセージに含まれる語の傾向 | 疑う対象 | この記事の該当箇所 |
| --- | --- | --- |
| `cni`、`plugin`、`network for sandbox`、IPAM やアドレス枯渇を示す表現 | CNI プラグイン・CNI 設定・IP 管理 | 原因1 |
| `cni config uninitialized`、`NetworkPluginNotReady` | CNI 設定がランタイムに読み込まれていない | 原因1 |
| sandbox image や pull、[認証](/glossary/認証/)、名前解決に関する表現 | pause image の取得 | 原因2 |
| runtime のソケット、cgroup、runtime 起動に関する表現 | container runtime 本体 | 原因2 |
| `no space left on device`、inode や[ファイル](/glossary/ファイル/)作成の失敗 | ノードのディスク・資源 | 原因3 |

なお、同じ Pod で同種の[イベント](/glossary/イベント/)が大量に出ると、kubelet は「類似[イベント](/glossary/イベント/)をまとめた」形（発生回数付き）で1行に集約して出力します。回数と経過時間が大きい場合は、恒久的な設定不備である可能性が高くなります。

[イベント](/glossary/イベント/)自体は [API](/glossary/api/) [サーバー](/glossary/サーバー/)の設定に従って一定時間で[削除](/glossary/削除/)されるため、古い障害を後追いする場合は[イベント](/glossary/イベント/)ではなくノードの[ログ](/glossary/ログ/)（後述）を確認してください。

## 原因と解決策

### 解決策の早見表

| 原因 | 主な確認 | 主な対処 |
| --- | --- | --- |
| CNI 設定・プラグインの不整合 | CNI アドオンの Pod 状態、CNI 設定[ディレクトリ](/glossary/ディレクトリ/)とバイナリ、ノードの `NetworkUnavailable` | アドオンの公式手順どおりに再適用、ノード上の CNI 設定・バイナリの整合を回復 |
| [IP アドレス](/glossary/ip-アドレス/)の枯渇・IPAM の不整合 | アドオン側の IPAM 状態、Pod CIDR 設定の一致 | 不要な Pod や滞留 sandbox の整理、CIDR 設計の見直し |
| pause image を取得できない | ランタイム設定上の sandbox image 名、[レジストリ](/glossary/レジストリ/)疎通、[認証](/glossary/認証/) | ランタイム設定の[修正](/glossary/修正/)、[プライベートレジストリ](/glossary/プライベートレジストリ/)へのミラー設定 |
| container runtime の異常 | `systemctl status`、runtime の[ログ](/glossary/ログ/)、`crictl info` | runtime の復旧、設定不整合（cgroup [ドライバ](/glossary/ドライバ/)等）の[修正](/glossary/修正/) |
| ノードのディスク・inode 枯渇 | `df -h` / `df -i`、ノードの `DiskPressure` | 不要[イメージ](/glossary/イメージ/)・[ログ](/glossary/ログ/)の[削除](/glossary/削除/)、容量拡張 |
| [ネットワーク](/glossary/ネットワーク/)前提条件の欠落 | カーネルモジュールと sysctl、iptables の[バックエンド](/glossary/バックエンド/) | 公式ドキュメントの前提条件どおりに設定 |

### 原因1：CNI プラグインまたは CNI 設定の不整合

sandbox の[ネットワーク](/glossary/ネットワーク/)設定は container runtime が CNI プラグインを呼び出して行います。ここが成立しないと、pause [コンテナ](/glossary/コンテナ/)まで作れていても sandbox 作成全体が失敗として扱われます。よくあるパターンは次のとおりです。

- **クラスタ構築直後にネットワークアドオンを適用していない**：kubeadm などで構築した直後は CNI 設定が存在せず、kubelet は「ネットワークプラグインが未初期化」であることを示すメッセージとともに Pod を起動できません。ノードの Ready 条件のメッセージにも `NetworkPluginNotReady` 相当の記述が出ます。この症状は公式[リポジトリ](/glossary/リポジトリ/)の Issue でも繰り返し報告されています（[kubernetes/kubernetes#48798](https://github.com/kubernetes/kubernetes/issues/48798)、[kubernetes/kubeadm#1031](https://github.com/kubernetes/kubeadm/issues/1031)）。
- **アドオンの DaemonSet が該当ノードで動いていない**：ノード追加直後、taint、[イメージ](/glossary/イメージ/)取得失敗などでアドオンの Pod が起動せず、そのノードだけ CNI 設定が配置されないケースです。
- **CNI [設定ファイル](/glossary/設定ファイル/)が壊れている・複数あって意図しないものが選ばれている**：設定[ディレクトリ](/glossary/ディレクトリ/)内の[ファイル](/glossary/ファイル/)は名前順で評価されるため、旧アドオンの設定が残っていると意図しないプラグインが使われます。アドオンを入れ替えた際に起きやすい失敗です。
- **CNI プラグインのバイナリが無い、実行できない**：ノードの初期化方法を変えた、[イメージ](/glossary/イメージ/)を作り直した、ディスクを入れ替えたといった変更の直後に起きます。
- **[IP アドレス](/glossary/ip-アドレス/)の枯渇や IPAM 情報の不整合**：ノードに割り当てられた Pod 用アドレス範囲を使い切ると、新しい sandbox に IP を割り当てられません。[削除](/glossary/削除/)しきれなかった sandbox が IP を保持し続けている場合もあります。

**対処の流れ**

```bash
# 1. ネットワークアドオンが該当ノードで動いているか
kubectl get pods -A -o wide | grep -i -E 'cni|calico|cilium|flannel|weave|antrea'

# 2. ノード側の条件を確認（NetworkUnavailable / Ready の message）
kubectl describe node <your-node-name> | sed -n '/Conditions:/,/Addresses:/p'

# 3. ノードにログインし、ランタイムが認識している CNI 設定を確認
sudo crictl info | grep -i -A20 cni
```

CNI 設定[ディレクトリ](/glossary/ディレクトリ/)やバイナリディレクトリの場所は container runtime の設定で決まります。既定値を推測せず、`crictl info` の出力やランタイムの[設定ファイル](/glossary/設定ファイル/)で実際の[パス](/glossary/パス/)を確認してください。

修復手順（[設定ファイル](/glossary/設定ファイル/)の内容、Pod CIDR の指定方法、必要な [RBAC](/glossary/rbac/) など）はアドオンごとに大きく異なります。使用しているアドオンの公式ドキュメントに従ってください。Pod CIDR は kubeadm 側の指定とアドオン側の設定が一致している必要があるため、両方を照合します。

### 原因2：pause image または container runtime が sandbox コンテナを作れない

container runtime は sandbox [コンテナ](/glossary/コンテナ/)を起動するために sandbox image（pause image）を必要とします。この取得や起動に失敗すると、CNI が正常でも sandbox は作れません。

- **エアギャップ[環境](/glossary/環境/)・制限された[ネットワーク](/glossary/ネットワーク/)で pause image を取得できない**：ノードから公開[レジストリ](/glossary/レジストリ/)へ到達できない、[プロキシ](/glossary/プロキシ/)設定が runtime に反映されていない、[DNS](/glossary/dns/) が引けない、といった状況です。
- **ランタイム設定の sandbox image 指定が誤っている**：存在しない[タグ](/glossary/タグ/)、到達できないミラー、アーキテクチャの異なる[イメージ](/glossary/イメージ/)を指定している場合です。
- **[プライベートレジストリ](/glossary/プライベートレジストリ/)の[認証](/glossary/認証/)**：sandbox image の取得は container runtime 自身の設定と認証情報で行われるため、Pod の `imagePullSecrets` を追加しても解決しない場合があります。ランタイム側の[レジストリ](/glossary/レジストリ/)認証設定を公式ドキュメントで確認してください。
- **container runtime 本体の異常**：プロセスが停止している、CRI ソケットが応答しない、設定変更後に再起動していない、cgroup [ドライバ](/glossary/ドライバ/)の設定が kubelet と食い違っている、といった状態です。

**確認方法**

```bash
# ランタイムの稼働状況とログ
sudo systemctl status containerd   # CRI-O の場合は crio
sudo journalctl -u containerd --since "15 min ago" --no-pager | grep -i -E 'sandbox|image|cni'

# ランタイムが保持しているイメージ一覧（pause を確認）
sudo crictl images | grep -i pause
```

設定されている sandbox image 名は、推測せずランタイムの実効設定から読み取ります。containerd と CRI-O では設定[キー](/glossary/キー/)名が異なり、containerd はメジャーバージョンによっても書き方が変わるため、実効設定のダンプ出力を確認するのが確実です。

```bash
# containerd：実効設定から sandbox / pause 関連の項目を探す
sudo containerd config dump | grep -i -E 'sandbox|pause|pinned'

# 取得可否そのものを試す（<your-sandbox-image> は上で確認した値）
sudo crictl pull <your-sandbox-image>
```

`crictl pull` が失敗するなら、原因は[レジストリ](/glossary/レジストリ/)疎通か[認証](/glossary/認証/)か[設定値](/glossary/設定値/)です。成功するのに sandbox が作れないなら、CNI（原因1）かノード状態（原因3）を疑います。cgroup [ドライバ](/glossary/ドライバ/)やランタイムの前提設定については、[Kubernetes](/glossary/kubernetes/) 公式ドキュメントの「Container Runtimes」に記載された手順を基準にしてください。

### 原因3：ノード側の状態（ディスク・iptables・sysctl・カーネル）

kubelet と container runtime はノードの [OS](/glossary/os/) 機能に強く依存します。ノード側が壊れていると、[マニフェスト](/glossary/マニフェスト/)が正しくても sandbox は作れません。

- **ディスクや inode の枯渇**：`no space left on device` を含むメッセージで sandbox 作成が失敗する事例は、[クラウド](/glossary/クラウド/)提供元のトラブルシューティング文書でも紹介されています（例：[Tencent Cloud TKE のドキュメント](https://www.tencentcloud.com/document/product/457/35761)）。ランタイムのデータディレクトリ、`/var/log`、`/var/lib/kubelet` を個別に確認します。
- **[ネットワーク](/glossary/ネットワーク/)前提条件の欠落**：ノードで必要なカーネルモジュールや sysctl（IP 転送やブリッジ関連の設定）が有効でないと、Pod [ネットワーク](/glossary/ネットワーク/)の設定に失敗します。必要な項目は [Kubernetes](/glossary/kubernetes/) 公式ドキュメントの「Container Runtimes」に前提条件として明記されているので、その一覧と実機の状態を照合してください。
- **iptables/nftables の不整合**：ホストの `iptables` がどの[バックエンド](/glossary/バックエンド/)（legacy / nft）で動いているかが、CNI やサービスプロキシの想定と食い違うと、ルール適用が失敗したり無効化されたりします。ノード再作成やディストリビューション更新の後に起きやすい問題です。
- **プロセス・ファイルディスクリプタ・PID の上限**：ノードが高負荷のときに sandbox 作成だけが失敗することがあります。カーネルログ（`dmesg`）に該当メッセージが出ていないか確認します。
- **RuntimeClass の指定**：Pod が指定した `runtimeClassName` に対応する handler がノードの runtime 側に設定されていないと、Pod は起動できません。特定の Pod だけが失敗する場合は、この可能性を確認してください（設定名や必要な runtime 側の定義は公式の RuntimeClass ドキュメントを参照）。

**確認[コマンド](/glossary/コマンド/)**

```bash
# 容量と inode
df -h /var/lib/kubelet /var/log
df -h $(sudo crictl info | grep -i -m1 root | awk -F'"' '{print $4}') 2>/dev/null
df -i /var

# ネットワーク前提の状態（公式ドキュメントの前提条件と照合する）
lsmod | grep -E 'br_netfilter|overlay'
sysctl net.ipv4.ip_forward net.bridge.bridge-nf-call-iptables

# iptables のバックエンド
iptables -V

# カーネル側のエラー
sudo dmesg -T | tail -50
```

不要[イメージ](/glossary/イメージ/)の整理など、[削除](/glossary/削除/)を伴う対処を行うときは、先に対象ノードを `kubectl cordon`（必要に応じて `kubectl drain`）して影響範囲を限定してください。`iptables -F` の実行やランタイムのデータディレクトリの[削除](/glossary/削除/)は、クラスタ全体の通信断や復旧困難な状態を招く可能性があるため、主たる解決策としては採りません。

## 確認・切り分け手順

上から順に実施すると、原因が3方向のどれかに収束します。

### 手順1：イベント全文を取得する

```bash
kubectl describe pod <your-pod-name> -n <your-namespace>

# 名前空間内のイベントを時系列で見る
kubectl get events -n <your-namespace> --sort-by=.lastTimestamp

# 該当イベントだけを全名前空間から抽出する
kubectl get events -A --field-selector type=Warning,reason=FailedCreatePodSandBox
```

`desc =` 以降を必ず全文で記録します。ここが後続すべての判断材料になります。

### 手順2：影響範囲を切り分ける

```bash
# 止まっている Pod がどのノードに偏っているか
kubectl get pods -A -o wide | grep -E 'ContainerCreating|Init:'

# ノードの状態
kubectl get nodes -o wide
kubectl describe node <your-node-name>
```

- **特定ノードに集中**：そのノードの runtime・CNI・資源（原因2、原因3）を追います。
- **クラスタ全体**：ネットワークアドオン、クラスタ共通設定、[レジストリ](/glossary/レジストリ/)疎通（原因1、原因2）を追います。
- **特定 Pod だけ**：`hostNetwork`、`hostPort` の競合、`runtimeClassName`、Pod 単位の設定を確認します。

### 手順3：ノードの kubelet ログを読む

```bash
sudo journalctl -u kubelet --since "30 min ago" --no-pager | grep -i -E 'sandbox|cni|network'
```

[イベント](/glossary/イベント/)は要約されているため、失敗の直前後に出ている[ログ](/glossary/ログ/)行を見ると、どのコンポーネントが返した[エラー](/glossary/エラー/)かが明確になります。

### 手順4：container runtime 側を確認する

```bash
sudo journalctl -u containerd --since "30 min ago" --no-pager | grep -i -E 'sandbox|cni|image'
sudo crictl info
sudo crictl pods
```

`crictl info` の出力にはランタイムの状態（`RuntimeReady` / `NetworkReady` に相当する条件）と CNI 設定の読み込み状況が含まれます。`NetworkReady` が false なら原因1、ランタイム自体が応答しないなら原因2に進みます。`crictl` の使い方は [Kubernetes](/glossary/kubernetes/) 公式ドキュメントの「Debugging [Kubernetes](/glossary/kubernetes/) nodes with crictl」に説明があります。

### 手順5：仮説を1つずつ検証する

- CNI を疑うなら：アドオン Pod の状態と[ログ](/glossary/ログ/)、ノード上の CNI 設定・バイナリの存在を確認
- pause image を疑うなら：`crictl pull <your-sandbox-image>` を実行
- ノード状態を疑うなら：`df -h` / `df -i` / `sysctl` / `lsmod` / `dmesg`

### 手順6：解決を確認する

対処後、対象 Pod を作り直して観測します。

```bash
kubectl delete pod <your-pod-name> -n <your-namespace>
kubectl get pod -n <your-namespace> -w
```

期待される状態は、`ContainerCreating` を経て `Running` に到達し、`kubectl describe pod` の Events に新しい `FailedCreatePodSandBox` が出ないことです。Pod に IP が割り当てられていることも合わせて確認します。

```bash
kubectl get pod <your-pod-name> -n <your-namespace> -o wide
```

ノードを cordon していた場合は、復旧確認後に `kubectl uncordon <your-node-name>` で戻します。

## それでも解決しない場合

次の情報をまとめると、原因の再検討や外部への問い合わせが進みます。

```bash
# 1. イベント（desc 全文を含む）
kubectl describe pod <your-pod-name> -n <your-namespace> > pod-describe.txt

# 2. ノードの状態
kubectl get nodes -o wide > nodes.txt
kubectl describe node <your-node-name> > node-describe.txt

# 3. kubelet と runtime のログ
sudo journalctl -u kubelet --since "1 hour ago" --no-pager > kubelet.log
sudo journalctl -u containerd --since "1 hour ago" --no-pager > runtime.log

# 4. ランタイムと CNI の状態
sudo crictl info > crictl-info.txt
sudo crictl pods > crictl-pods.txt

# 5. ノード資源
df -h > df.txt; df -i > df-inode.txt
```

問い合わせ先の選び方は次のとおりです。

- **CNI 由来のメッセージが出ている**：使用しているネットワークアドオンの公式[リポジトリ](/glossary/リポジトリ/)・ドキュメント
- **container runtime 由来のメッセージが出ている**：containerd や CRI-O の公式[リポジトリ](/glossary/リポジトリ/)・ドキュメント
- **kubelet や CRI の挙動そのものに疑問がある**：kubernetes/kubernetes の Issue を検索し、同種の報告があるか確認する
- **マネージドサービス（[クラウド](/glossary/クラウド/)提供の [Kubernetes](/glossary/kubernetes/)）を利用している**：ノードイメージや[ネットワーク](/glossary/ネットワーク/)実装が提供元固有のため、提供元のサポート窓口が最短

報告時は、クラスタの構築方法（kubeadm、マネージドサービス、ディストリビューション）、使用しているネットワークアドオン、container runtime の種類、直前に行った変更（ノード追加、アップグレード、設定変更）を添えると切り分けが早くなります。[ログ](/glossary/ログ/)を共有する際は、[トークン](/glossary/トークン/)や認証情報が含まれていないかを確認し、必要に応じて `<your-token>` のような形に置き換えてください。

## Editor's Note

この[エラー](/glossary/エラー/)はアプリコンテナの失敗ではなく、kubelet が sandbox を作る前段で止まる点が重要です。[Kubernetes](/glossary/kubernetes/) の Pod [デバッグ](/glossary/デバッグ/)手順は[イベント](/glossary/イベント/)確認を起点にしており（[公式ドキュメント](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)）、[ネットワーク](/glossary/ネットワーク/)実装は CNI プラグインが担うため（[Network Plugins](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)）、現場では `desc =` 以降の文言から CNI か runtime かを先に分けるのが有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
