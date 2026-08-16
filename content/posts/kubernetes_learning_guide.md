---
title: "Kubernetesを学ぶ：6段階ロードマップ"
date: 2026-08-09
description: "Kubernetesを個別マニフェストの写経で終わらせず、Pod、Deployment、Service、設定とデータ、スケジューリング、トラブルシューティングまで順序立てて学ぶためのロードマップを解説します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_learning_guide.png"]
errorCode: ""
lastmod: 2026-08-09
service: "Kubernetes"
error_type: "learning guide"
components: ["Control Plane", "kubelet"]
related_services: []
trend_incident: false
---

> この記事にはアフィリエイト広告が含まれています。

## 冒頭まとめ

[Kubernetes](/glossary/kubernetes/)の[エラー](/glossary/エラー/)を検索して1件ずつ直しているのに、翌日は別の[エラー](/glossary/エラー/)で止まる。この繰り返しから抜けるには、覚える順序を変える必要があります。

[Kubernetes](/glossary/kubernetes/)の[エラー](/glossary/エラー/)の多くは、4つの境界のどこかで起きています。宣言した状態と実際の状態の境界、コントロールプレーンとノードの境界、Podの内と外の境界、そしてPodの寿命とデータの寿命の境界です。[エラー](/glossary/エラー/)文や[イベント](/glossary/イベント/)はこの境界のどれで止まったかを示していますが、境界の存在を知らないと文言が読めません。

[Docker](/glossary/docker/)との最大の違いはここにあります。[Docker](/glossary/docker/)では実行した命令がそのまま結果になりますが、[Kubernetes](/glossary/kubernetes/)では「こうあってほしい」という宣言を出し、それを実現しようとする過程が延々と続きます。したがって[エラー](/glossary/エラー/)は、失敗した瞬間ではなく、実現できないまま繰り返している状態として現れます。

学ぶ順序は、Podと[コンテナ](/glossary/コンテナ/)、Deploymentと宣言、Serviceと[ネットワーク](/glossary/ネットワーク/)、設定とデータ、スケジューリングとリソース、[ログ](/glossary/ログ/)とトラブルシューティングの6段階です。各段階には「次へ進む目安」を置きました。飛ばした段階は、後の段階の[エラー](/glossary/エラー/)として別の顔で現れます。

## 個別に直すだけでは理解しにくい理由

検索で見つかる対処は、多くの場合その[環境](/glossary/環境/)で有効だった手順です。なぜ有効だったかは書かれていないことがあります。

たとえば、Podが起動しないときに `kubectl delete pod` を実行したら直った、という手順があります。Deploymentの管理下にあるPodは削除すると作り直されるので、一時的な不具合であれば確かに解消します。しかし原因が[マニフェスト](/glossary/マニフェスト/)の側にあれば、作り直されたPodも同じ理由で止まります。Podが誰に管理されているかを知らないと、この区別ができません。

同じことが[ネットワーク](/glossary/ネットワーク/)でも起きます。Serviceの `port` と `targetPort` を同じ値に揃えたら繋がった、という手順は、どちらがService側でどちらが[コンテナ](/glossary/コンテナ/)側かを知らなければ再現できません。

[エラー](/glossary/エラー/)文と[イベント](/glossary/イベント/)も同じです。[Kubernetes](/glossary/kubernetes/)の表示は、どの部品が判断したのかを示しています。スケジューラが置き場所を決められないのか、kubeletが[イメージ](/glossary/イメージ/)を取得できないのか、[コンテナ](/glossary/コンテナ/)の中のプロセスが落ちているのかで、直す場所が変わります。この区別は、次に説明する全体像を知っていれば読み取れます。

## 最初に理解するべきKubernetesの全体像

先に部品の関係を押さえます。ここを飛ばすと、後のすべての段階で判断がぶれます。

公式ドキュメントによれば、[Kubernetes](/glossary/kubernetes/)クラスターはコントロールプレーンと1つ以上のワーカーノードで構成されます。コントロールプレーン側には、[Kubernetes](/glossary/kubernetes/)の[HTTP](/glossary/http/) [API](/glossary/api/)を公開する中核[サーバー](/glossary/サーバー/)である kube-apiserver、[API](/glossary/api/)[サーバー](/glossary/サーバー/)の全データを保持するキーバリューストアの etcd、まだノードに割り当てられていないPodを探して適切なノードへ割り当てる kube-scheduler、[API](/glossary/api/)の振る舞いを実装するコントローラーを動かす kube-controller-manager があります。ノード側には、Podとその[コンテナ](/glossary/コンテナ/)が動いていることを保証する kubelet、Serviceを実装する[ネットワーク](/glossary/ネットワーク/)規則を維持する kube-proxy、[コンテナ](/glossary/コンテナ/)の実行を担うコンテナランタイムがあります（[Cluster Architecture](https://kubernetes.io/docs/concepts/overview/components/)）。

この構造から、[エラー](/glossary/エラー/)の読み分けが決まります。`kubectl` は[API](/glossary/api/)[サーバー](/glossary/サーバー/)へ要求を送るだけの道具です。[マニフェスト](/glossary/マニフェスト/)を適用した時点で成功と表示されても、それは「宣言が受け付けられた」という意味であり、動き出したという意味ではありません。実際に動くかどうかは、その後にスケジューラとkubeletが決めます。

したがって[Kubernetes](/glossary/kubernetes/)の調査は、常に2段構えになります。宣言は正しく登録されたか。そしてその宣言を実現しようとした過程のどこで止まったか。前者は `kubectl get` で、後者は `kubectl describe` の[イベント](/glossary/イベント/)欄で確認します。

まずは手元の[環境](/glossary/環境/)が動いているかを確認してください。

```bash
kubectl cluster-info
kubectl get nodes
```

ノードが `Ready` でなければ、この先のPodはどれも起動しません。この時点で次へ進んでも、以降の[コマンド](/glossary/コマンド/)はすべて同じ理由で止まります。

## 学習ステップ1：Podとコンテナ

**何を理解する段階か**：Podが何の単位なのか、そして[コンテナ](/glossary/コンテナ/)とどう違うのかです。

**なぜ[エラー](/glossary/エラー/)解決に必要か**：[Kubernetes](/glossary/kubernetes/)の[エラー](/glossary/エラー/)の大半はPod単位で現れます。Podの状態欄と[コンテナ](/glossary/コンテナ/)の状態欄が別々にあることを知らないと、どちらの情報を読んでいるのか分からなくなります。

**最低限覚える概念**：公式ドキュメントによれば、Podは[Kubernetes](/glossary/kubernetes/)で作成・管理できる最小の[デプロイ](/glossary/デプロイ/)単位で、1つ以上の[コンテナ](/glossary/コンテナ/)のグループです。[ストレージ](/glossary/ストレージ/)と[ネットワーク](/glossary/ネットワーク/)の資源を共有し、[コンテナ](/glossary/コンテナ/)をどう動かすかの仕様を持ちます。Podの中身は常に同じ場所に配置され、同時にスケジュールされ、共有された文脈で動きます（[Pods](https://kubernetes.io/docs/concepts/workloads/pods/)）。

つまりPodは、複数の[コンテナ](/glossary/コンテナ/)をまとめて1台の論理的なホストのように扱う入れ物です。同じPodの中の[コンテナ](/glossary/コンテナ/)は同じ[ネットワーク](/glossary/ネットワーク/)名前空間を共有するため、互いに `localhost` で[通信](/glossary/通信/)できます。別のPodには届きません。

**実際に試す[コマンド](/glossary/コマンド/)**：

```bash
# Pod を一覧する
kubectl get pods

# 状態とノードと再起動回数まで表示する
kubectl get pods -o wide

# Pod の詳細とイベントを確認する（最も重要）
kubectl describe pod <Pod名>

# Pod 内のコンテナでコマンドを実行する
kubectl exec -it <Pod名> -- sh

# 複数コンテナがある場合はコンテナを指定する
kubectl exec -it <Pod名> -c <コンテナ名> -- sh
```

`kubectl describe` の出力は上半分が宣言された内容、下半分の Events が実現しようとした過程です。[エラー](/glossary/エラー/)の理由はほぼ常に下半分にあります。

**次の段階へ進む目安**：`kubectl describe pod` の出力を、宣言部分と[イベント](/glossary/イベント/)部分に分けて読めることです。

**関連して発生しやすい[エラー](/glossary/エラー/)**：`ImagePullBackOff` と `ErrImagePull` は[イメージ](/glossary/イメージ/)を取得できていない状態です。`CrashLoopBackOff` は起動した後に[コンテナ](/glossary/コンテナ/)が落ちて再起動を繰り返している状態を指します。前者はまだ起動していない、後者は一度は起動している、という違いがあります。

## 学習ステップ2：Deploymentと宣言的な管理

**何を理解する段階か**：Podを直接作るのではなく、あるべき状態を宣言して任せる仕組みです。

**なぜ[エラー](/glossary/エラー/)解決に必要か**：Podが消えても勝手に作り直される、更新したのに古いPodが残っている、といった現象は、この層を知らないと理解できません。

**最低限覚える概念**：公式ドキュメントによれば、DeploymentはPodとReplicaSetに対する宣言的な更新を提供します。Deploymentに望ましい状態を記述すると、Deploymentコントローラーが実際の状態を望ましい状態へ、制御された速度で変更します（[Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)）。

関係は3層です。DeploymentがReplicaSetを作り、ReplicaSetがPodを作ります。Podを手で削除しても、ReplicaSetが数を保とうとして作り直します。同じページには、Deploymentが所有するReplicaSetを直接操作しないように、という注意も書かれています。

この層があるため、[マニフェスト](/glossary/マニフェスト/)を直さずにPodだけを消しても意味がありません。直す対象は常に宣言の側です。

**実際に試す[コマンド](/glossary/コマンド/)**：

```bash
# 宣言を適用する
kubectl apply -f deployment.yaml

# Deployment と、その配下の状態を確認する
kubectl get deployments
kubectl get replicasets
kubectl get pods --show-labels

# 更新の進行状況を確認する
kubectl rollout status deployment/<Deployment名>

# 更新の履歴を確認し、必要なら1つ前へ戻す
kubectl rollout history deployment/<Deployment名>
kubectl rollout undo deployment/<Deployment名>
```

`kubectl get deployments` の READY 欄は、望ましい数に対して実際に準備できた数を示します。ここが揃わないまま止まっているなら、原因はPod側にあります。

**次の段階へ進む目安**：Podを1つ削除したときに何が起きるかを、実行前に説明できることです。

**関連して発生しやすい[エラー](/glossary/エラー/)**：更新が進まない場合、新しいReplicaSetのPodが起動できていないことがほとんどです。`kubectl rollout status` が止まったら、`kubectl get pods` で新しいPodの状態を確認してください。

## 学習ステップ3：Serviceとネットワーク

**何を理解する段階か**：Podは入れ替わるものであり、その前に固定の入口を置く仕組みです。そして3種類の[ポート](/glossary/ポート/)の区別です。

**なぜ[エラー](/glossary/エラー/)解決に必要か**：「繋がらない」という症状は、この段階の理解不足で起きるものが最も多くなります。

**最低限覚える概念**：

第一に、[コンテナ](/glossary/コンテナ/)が待ち受けている[ポート](/glossary/ポート/)です。Podの中のプロセスが実際に開いている番号です。

第二に、Serviceの `port` と `targetPort` です。公式ドキュメントによれば、Serviceは任意の[受信](/glossary/受信/) `port` を `targetPort` へ対応付けられます。既定では利便性のため、`targetPort` は `port` と同じ値に設定されます（[Service](https://kubernetes.io/docs/concepts/services-networking/service/)）。`port` がServiceの入口、`targetPort` がPod側の受け口です。同じページには、Podの[ポート](/glossary/ポート/)に名前を付けて `targetPort` からその名前で参照できることも記載されています。

第三に、クラスターの外からの入口です。Serviceの `type` は既定で `ClusterIP` であり、この場合はクラスターの内側からしか到達できません。外へ出すには別の型やIngressといった仕組みが要ります。

そして名前解決です。公式ドキュメントによれば、Podの `/etc/resolv.conf` はkubeletが設定し、`search` には `<namespace>.svc.cluster.local`、`svc.cluster.local`、`cluster.local` が並びます。この展開により、`test` 名前空間のPodは `data.prod` でも `data.prod.svc.cluster.local` でも解決できます（[DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)）。

ここが `localhost` の話と繋がります。同じPodの中の[コンテナ](/glossary/コンテナ/)同士は `localhost` で[通信](/glossary/通信/)できますが、別のPodのサービスへ `localhost` と書いても届きません。Service名を書きます。名前空間が違えば `<Service名>.<名前空間>` と書きます。

**実際に試す[コマンド](/glossary/コマンド/)**：

```bash
# Service を一覧する（TYPE と PORT(S) を見る）
kubectl get services

# Service の詳細と、実際に紐づいている宛先を確認する
kubectl describe service <Service名>
kubectl get endpointslices -l kubernetes.io/service-name=<Service名>

# クラスター内から名前解決と疎通を試す
kubectl run tmp --rm -it --image=busybox:1.36 --restart=Never -- sh
# （コンテナ内で）
# nslookup <Service名>
# wget -qO- http://<Service名>:<port>

# 一時的に手元へ転送して確認する
kubectl port-forward service/<Service名> 8080:80
```

`kubectl describe service` の Endpoints 欄が空であれば、セレクターに一致するPodがありません。ラベルの綴り違いが原因のことが多くあります。

**次の段階へ進む目安**：Pod内の[アプリケーション](/glossary/アプリケーション/)が書く接続先と、手元のブラウザに入力する接続先が違う理由を説明できることです。

**関連して発生しやすい[エラー](/glossary/エラー/)**：クラスター内で `could not translate host name` のような名前解決の失敗が出る場合、接続先にService名ではなく `localhost` を書いている可能性があります。到達はするが応答しない場合は `targetPort` の指定を確認してください。

## 学習ステップ4：設定とデータの分離

**何を理解する段階か**：Podが消えても残すべきものと、Podと一緒に消えてよいものの違いです。

**なぜ[エラー](/glossary/エラー/)解決に必要か**：この区別を知らないまま「作り直せば直る」を続けると、いずれデータを失います。

**最低限覚える概念**：公式ドキュメントによれば、一時的なボリュームの寿命は特定のPodに紐づきますが、永続的なボリュームは個々のPodの寿命を超えて存在します。Podが存在しなくなると[Kubernetes](/glossary/kubernetes/)は一時的なボリュームを破棄しますが、永続的なボリュームは破棄しません。なお、どの種類のボリュームでも、[コンテナ](/glossary/コンテナ/)の再起動をまたいでデータは保持されます（[Volumes](https://kubernetes.io/docs/concepts/storage/volumes/)）。

つまり境界は2段あります。[コンテナ](/glossary/コンテナ/)の再起動をまたぐかどうかと、Podの消滅をまたぐかどうかです。前者はボリュームを使えば保たれ、後者は永続的なボリュームでなければ保たれません。

設定については、ConfigMapとSecretで本体から切り離します。ここで重要な注意が公式に書かれています。[Kubernetes](/glossary/kubernetes/)のSecretは既定で[API](/glossary/api/)[サーバー](/glossary/サーバー/)の背後にあるデータストア（etcd）に[暗号化](/glossary/暗号化/)されずに[保存](/glossary/保存/)されます。[API](/glossary/api/)にアクセスできる者は誰でもSecretを取得または変更でき、etcdにアクセスできる者も同様です。さらに、ある名前空間でPodを作る[権限](/glossary/権限/)を持つ者は、その[権限](/glossary/権限/)を使って同じ名前空間の任意のSecretを読めます（[Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)）。

Secretの値がbase64で表示されるのは符号化であって[暗号化](/glossary/暗号化/)ではありません。同じページは、安全に使うために保存時の[暗号化](/glossary/暗号化/)を有効にするなどの手順を取るよう促しています。

**実際に試す[コマンド](/glossary/コマンド/)**：

```bash
# 永続領域の要求と、実際の領域を確認する
kubectl get persistentvolumeclaims
kubectl get persistentvolumes

# 要求が結び付かない理由を確認する
kubectl describe pvc <PVC名>

# 設定を一覧する
kubectl get configmaps
kubectl get secrets

# Pod がどのボリュームをどこへマウントしているかを確認する
kubectl get pod <Pod名> -o jsonpath='{range .spec.containers[*]}{.name}{"\t"}{.volumeMounts}{"\n"}{end}'
```

`kubectl delete pvc` は永続領域の要求を削除する操作です。回収方針によっては実データも削除されます。実行前に、その要求がどの領域に結び付いているかを `kubectl describe pvc` で確認してください。同様に、名前空間ごと削除する操作は中の永続領域の要求も巻き込みます。

**次の段階へ進む目安**：Podを削除して作り直したときに、どのデータが残りどのデータが消えるかを、実際に手を動かして確認できることです。

**関連して発生しやすい[エラー](/glossary/エラー/)**：`PVCがPending` のまま進まない状態は、条件に合う領域が用意されていないか、最初の利用者を待っている状態です。`CreateContainerConfigError` は、参照しているConfigMapやSecretが存在しない場合に出ます。

## 学習ステップ5：スケジューリングとリソース

**何を理解する段階か**：Podがどのノードに置かれるかの決まり方と、リソース指定の意味です。

**なぜ[エラー](/glossary/エラー/)解決に必要か**：Podが起動しない原因には、置き場所が決まらない場合と、置かれた後に落ちる場合があります。この2つは対処がまったく違います。

**最低限覚える概念**：公式ドキュメントによれば、Podを作るとスケジューラが実行先のノードを選びます。各ノードには資源の種類ごとに最大容量があり、スケジューラは資源の種類ごとに、割り当て済み[コンテナ](/glossary/コンテナ/)の[リクエスト](/glossary/リクエスト/)の合計がノードの[容量](/glossary/容量/)を下回るようにします。実際の使用量が低くても、[容量](/glossary/容量/)の確認に失敗すればスケジューラはそのノードへの配置を拒みます（[Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)）。

`requests` と `limits` の違いも同じページに書かれています。ノードに十分な余裕があれば、[コンテナ](/glossary/コンテナ/)は `request` を超えて資源を使うことが可能であり、許されてもいます。一方 `limits` は別の話で、CPUと[メモリ](/glossary/メモリ/)のどちらの上限もkubeletとコンテナランタイムによって適用されます。

つまり `requests` は置き場所を決めるための申告、`limits` は動き始めた後の上限です。前者が大きすぎればPodは置かれず、後者が小さすぎればPodは置かれた後に止められます。

**実際に試す[コマンド](/glossary/コマンド/)**：

```bash
# Pod が置かれていない理由を確認する（Events を読む）
kubectl describe pod <Pod名>

# ノードの容量と、割り当て済みの量を確認する
kubectl describe node <ノード名>

# 実際の使用量を確認する（メトリクスサーバーが必要）
kubectl top nodes
kubectl top pods

# 指定されている requests と limits を取り出す
kubectl get pod <Pod名> -o jsonpath='{range .spec.containers[*]}{.name}{"\t"}{.resources}{"\n"}{end}'
```

`kubectl describe node` の Allocated resources 欄は、実際の使用量ではなく申告値の合計です。使用量に余裕があるのに新しいPodが置かれない場合は、ここを見てください。

**次の段階へ進む目安**：Podが `Pending` のときに、原因が資源不足なのか、条件不一致なのか、永続領域の待ちなのかを、[イベント](/glossary/イベント/)から判断できることです。

**関連して発生しやすい[エラー](/glossary/エラー/)**：`Pending` は置き場所が決まっていない状態です。`OOMKilled` は[メモリ](/glossary/メモリ/)の上限に達して止められた状態で、こちらは置かれた後の話になります。`Evicted` はノード側の余裕が失われて追い出された状態を指します。

## 学習ステップ6：ログ確認とトラブルシューティング

**何を理解する段階か**：[エラー](/glossary/エラー/)が出たときに、どの順番で何を見るかです。

**なぜ[エラー](/glossary/エラー/)解決に必要か**：ここまでの5段階は、この順序を実行するための前提知識です。順序が決まっていれば、初めて見る[エラー](/glossary/エラー/)でも調べる範囲を絞れます。

**確認の順序**：

第一に、実行した[コマンド](/glossary/コマンド/)と[マニフェスト](/glossary/マニフェスト/)そのものを確認します。名前空間の指定漏れ、適用した[ファイル](/glossary/ファイル/)の取り違え、インデントの誤りは、この時点で見つかります。

```bash
kubectl config get-contexts
kubectl get pods -A | head
```

第二に、表示された内容を全文読みます。`kubectl` が返す拒否の理由と、リソースの状態は別物です。適用が成功していれば、次に見るのはリソース側です。

第三に、対象リソースの状態を確認します。実行中なのか、待機中なのか、そもそも作られていないのかで、次に見る場所が変わります。

```bash
kubectl get pods -o wide
kubectl get deployments,replicasets
```

第四に、[イベント](/glossary/イベント/)を読みます。[Kubernetes](/glossary/kubernetes/)では、失敗の理由の大半がここに集まります。

```bash
kubectl describe pod <Pod名>
kubectl get events --sort-by=.lastTimestamp
```

[イベント](/glossary/イベント/)は既定で一定時間後に消えます。時間が経ってから調べる場合、詳細が残っていないことがあります。

第五に、[ログ](/glossary/ログ/)を読みます。[コンテナ](/glossary/コンテナ/)の中のプロセスが出力した内容です。

```bash
# 直近の100行を表示する
kubectl logs --tail 100 <Pod名>

# 再起動している場合、1つ前のコンテナのログを見る
kubectl logs --previous <Pod名>

# 複数コンテナがある場合は指定する
kubectl logs <Pod名> -c <コンテナ名>
```

`--previous` は `CrashLoopBackOff` の調査で必須です。現在の[コンテナ](/glossary/コンテナ/)はまだ何も出力していないことが多く、落ちた理由は1つ前の[ログ](/glossary/ログ/)に残っています。

第六に、[ネットワーク](/glossary/ネットワーク/)、永続領域、そしてノードとコントロールプレーンの状態を確認します。

```bash
kubectl get services,endpointslices
kubectl get pvc,pv
kubectl get nodes -o wide
kubectl get pods -n kube-system
```

ノードが `Ready` でない場合、個別のPodをいくら調べても解決しません。

**次の段階へ進む目安**：初めて見る[エラー](/glossary/エラー/)に対して、この6段階のどこから調べるかを即座に決められることです。

**避けるべき対処**：原因を確認しないまま `kubectl delete` を繰り返す、ServiceAccountに強い[権限](/glossary/権限/)を与えて通す、リソース制限を外して回避する、`--force --grace-period=0` を常用する、といった手順は、症状を消しても原因を残します。特に[権限](/glossary/権限/)の付与と削除の強行は、後から戻せない影響を残すことがあります。

## 独学と動画講座の使い分け

ここまでの6段階は、公式ドキュメントと手元のクラスターだけでも進められます。実際、この記事で参照した仕様はすべて公式ドキュメントに書かれています。

独学が向いているのは、目的が明確な場合です。特定の[エラー](/glossary/エラー/)を直す、特定のリソースの仕様を確認する、といった作業は、公式ドキュメントを直接読むのが最短です。

一方で、[Kubernetes](/glossary/kubernetes/)は独学の負担が[Docker](/glossary/docker/)より大きくなります。部品の数が多く、しかも部品どうしの関係を知らないと個々の説明が頭に入りません。どこから読むかを決める段階で止まりやすい構造です。加えて、手を動かすにはクラスターが要ります。

動画講座は、この順序と[環境](/glossary/環境/)の用意がまとめて示されている点が違います。途中で詰まって止まる回数を減らせます。反面、自分に必要な部分だけを選んで進めるのは難しくなります。

どちらが適しているかは、いま何に時間を取られているかで決まります。仕様が分からなくて止まっているなら公式ドキュメント、何から手を付けるか決められなくて止まっているなら講座、という切り分けが実際的です。

## 学習後に自力で確認できるようにしたいこと

到達点を具体的に置いておきます。以下を自分の[環境](/glossary/環境/)で確認できるようになっていれば、この記事の範囲は終わりです。

`kubectl apply` が成功した表示と、実際に動き出したことが別だと説明できる。`kubectl describe pod` の出力を、宣言部分と[イベント](/glossary/イベント/)部分に分けて読める。Podを1つ削除したときに何が起きるかを、実行前に言える。Serviceの `port` と `targetPort` がどちらを指すかを説明でき、Pod内から書く接続先と手元から入力する接続先の違いを説明できる。Podを削除したときに消えるデータと残るデータを、実際に試して確認できる。`Pending` と `CrashLoopBackOff` と `OOMKilled` が、それぞれ処理のどの段階の話かを区別できる。初めて見る[エラー](/glossary/エラー/)に対して、[コマンド](/glossary/コマンド/)、表示内容、リソースの状態、[イベント](/glossary/イベント/)、[ログ](/glossary/ログ/)、[ネットワーク](/glossary/ネットワーク/)とノードの順で調べられる。

これらは暗記ではなく、手を動かして確認する操作です。読んだだけでは身に付かない部分なので、手元のクラスターで1つずつ試してください。

## まとめ

[Kubernetes](/glossary/kubernetes/)の[エラー](/glossary/エラー/)が繰り返し起きるのは、[マニフェスト](/glossary/マニフェスト/)の書き方を知らないからではなく、境界を知らないからです。宣言と実際、コントロールプレーンとノード、Podの内と外、そして消えるデータと残るデータ。この4つの境界を押さえると、[イベント](/glossary/イベント/)の読み方が変わります。

学ぶ順序は、Podと[コンテナ](/glossary/コンテナ/)、Deploymentと宣言、Serviceと[ネットワーク](/glossary/ネットワーク/)、設定とデータ、スケジューリングとリソース、トラブルシューティングです。それぞれに「次へ進む目安」を置いたのは、飛ばした段階が後から別の顔で現れるからです。

公式ドキュメントは仕様の確認先として最も確実です。一方で、学ぶ順序や検証用のクラスターを自分で用意する負担が大きいと感じる場合は、順序と演習がまとまった教材を使う選択肢もあります。

[Kubernetesを体系的に学べるUdemy講座を確認する（PR）](https://trk.udemy.com/QYWqz3)

内容や価格、対象範囲はリンク先のページで確認してください。自分がいまどの段階で止まっているかを踏まえて、必要な範囲が含まれているかを見るのが選び方の基準になります。

## 参考資料

- [Cluster Architecture](https://kubernetes.io/docs/concepts/overview/components/)
- [Pods](https://kubernetes.io/docs/concepts/workloads/pods/)
- [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Service](https://kubernetes.io/docs/concepts/services-networking/service/)
- [DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
- [Volumes](https://kubernetes.io/docs/concepts/storage/volumes/)
- [Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)や講座の内容、価格、提供条件は予告なく変更されることがあります。最新の情報は[Kubernetes](/glossary/kubernetes/)公式ドキュメントおよびリンク先の講座ページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*