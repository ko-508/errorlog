---
title: "Kubernetes の NodeNotReady：原因と解決策"
date: 2026-08-03
description: "NotReady には Ready が False の場合と Unknown の場合があり、調べる場所が正反対です。False はノード自身の申告、Unknown は制御側が連絡を受け取れていない状態を指します。既定では50秒で Unknown になり、その5分後に Pod の退去が始まります。まず条件の値から読みます。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_nodenotready.png"]
errorCode: "NodeNotReady"
lastmod: 2026-08-03
service: "Kubernetes"
error_type: "NodeNotReady"
components: ["kubelet", "Node", "kube-controller-manager"]
related_services: ["kubectl", "containerd"]
trend_incident: false
---

## 冒頭まとめ

`kubectl get nodes` に `NotReady` と表示されたとき、**まず確認すべきは条件の値**です。[Kubernetes](/glossary/kubernetes/) の `Ready` 条件は3つの値を取り、表示は同じでも意味が違います。

公式の定義はこうです。`True` はノードが健全で Pod を受け入れられる状態、`False` は健全ではなく受け入れていない状態、そして `Unknown` は**ノード制御役が既定50秒の猶予の間にノードから連絡を受け取れなかった**状態です。

この違いが調査の方向を決めます。`False` は**ノード自身が「準備できていない」と申告している**ので、ノードの中を調べます。`Unknown` は**申告そのものが届いていない**ので、ノードと制御側の間を調べます。ノードが正常に動いていても `Unknown` にはなり得ます。

時間の流れも押さえておくと役に立ちます。ノード制御役は5秒ごとに状態を確認し、連絡が途絶えて50秒で `Unknown` にします。そこから**既定で5分待って**、Pod の退去を始めます。この5分は、`node.kubernetes.io/not-ready` と `node.kubernetes.io/unreachable` に対して自動的に付与される猶予（`tolerationSeconds=300`）によるものです。

つまり、**NotReady になってもすぐ Pod は動かない**。逆に、5分を過ぎると一斉に動き始めます。

## エラーの概要

一覧では状態として現れます。

```text
NAME       STATUS     ROLES    AGE   VERSION
node-01    Ready      <none>   30d   v1.32.1
node-02    NotReady   <none>   30d   v1.32.1
```

詳細を見ると、条件と最終連絡時刻が入ります。ここが判断材料です。

```text
Conditions:
  Type             Status    LastHeartbeatTime      Reason              Message
  ----             ------    -----------------      ------              -------
  MemoryPressure   Unknown   Mon, 03 Aug ... 12:01  NodeStatusUnknown   Kubelet stopped posting node status.
  DiskPressure     Unknown   Mon, 03 Aug ... 12:01  NodeStatusUnknown   Kubelet stopped posting node status.
  Ready            Unknown   Mon, 03 Aug ... 12:01  NodeStatusUnknown   Kubelet stopped posting node status.
```

**すべての条件が同時に `Unknown` になっていれば、連絡が途絶えた形**です。最終連絡時刻を見れば、いつ止まったかが分かります。

一方、`False` の場合は理由と文言が具体的になります。

```text
  Ready   False   Mon, 03 Aug ... 12:05   KubeletNotReady
    container runtime network not ready: NetworkReady=false reason:NetworkPluginNotReady
```

**この文言に原因が書かれています**。ネットワークの仕組みが準備できていない、実行環境が応答しない、といった内容が入ります。

なお、混同されやすい表示があります。`Ready,SchedulingDisabled` は NotReady ではありません。公式にも、これは API 上の条件ではなく、ノードが割り当て不可に設定されている状態だと明記されています。**意図的に閉じた状態であって、異常ではありません**。

## まず最初に：False か Unknown かを判別する

第一に、条件の値を確認します。`False` と `Unknown` で調べる先が正反対です。

第二に、最終連絡時刻を見ます。止まった時刻が分かれば、その時点で何が起きたかを追えます。

第三に、`False` であれば理由と文言を読みます。原因がそこに書かれています。

第四に、経過時間を確認します。5分を超えていれば、Pod の退去が始まっています。

## よくある原因と解決手順

### 原因1：kubelet が停止している（Unknown）

最も多い形です。ノード上の常駐処理が止まれば、連絡も止まります。すべての条件が `Unknown` になり、文言は「ノード状態の送信が止まった」という趣旨になります。

```bash
# ノード上で確認する
systemctl status kubelet
journalctl -u kubelet --since "10 minutes ago" | tail -50
```

停止していれば起動します。繰り返し落ちる場合は、記録に原因が残っています。設定[ファイル](/glossary/ファイル/)の誤り、証明書の期限切れ、資源の枯渇などが典型です。

### 原因2：制御側との通信が届いていない（Unknown）

ノードは動いているのに `Unknown` になる形です。ノードに入って確認すると、常駐処理は正常に動いています。

この場合、疑うのは経路です。ノードから API への到達性、名前解決、証明書の有効期限を確認します。

```bash
# ノード上から制御側への到達を確認する
curl -sk https://<APIサーバー>:6443/healthz
# 証明書の期限を確認する
sudo openssl x509 -in /var/lib/kubelet/pki/kubelet-client-current.pem -noout -dates
```

重要な注意があります。公式文書には、ノードが到達不能な場合、削除の決定を kubelet に伝えられないため、**削除予定の Pod が分断されたノード上で動き続けることがある**と明記されています。制御側から見て消えたはずの Pod が、実際には動き続けている可能性を念頭に置いてください。

### 原因3：ネットワークの仕組みが準備できていない（False）

新しいノードを追加した直後や、ネットワーク機能を入れ替えた直後に起こります。実装では、実行環境のネットワークが準備できていない場合に状態が設定され、文言に `NetworkReady=false` が含まれます。

この状態のノードは Pod を受け入れません。**ノード自体は生きているので、連絡は届いています**。したがって条件は `False` になります。

```bash
# ネットワーク機能の Pod が動いているかを確認する
kubectl get pods -n kube-system -o wide | grep <ノード名>
# 設定ファイルが配置されているかを確認する（ノード上）
ls -l /etc/cni/net.d/
```

設定[ファイル](/glossary/ファイル/)が置かれていない、あるいは対応する Pod が起動していない場合、その配布を担う仕組みの側を調べます。

### 原因4：実行環境の応答が遅れている（False で断続的に切り替わる）

`Ready` と `NotReady` を行き来する形です。記録には `PLEG is not healthy` という文言が現れます。

実装を確認すると、[コンテナ](/glossary/コンテナ/)の一覧を定期的に取得する処理があり、**前回の取得から3分を超えると不健全と判定**されます。文言には、最後に動作した時刻からの経過と閾値が入ります。

```text
PLEG is not healthy: pleg was last seen active 3m2.xxx s ago; threshold is 3m0s
```

原因は、実行環境からの応答が遅いことです。[コンテナ](/glossary/コンテナ/)数が多い、ディスクが遅い、資源が逼迫している、といった状況で起こります。

```bash
# 実行環境の応答時間を測る（ノード上）
time sudo crictl ps -a > /dev/null
# ノードの負荷を確認する
uptime; iostat -x 1 3
```

対処はノード上の[コンテナ](/glossary/コンテナ/)数を減らすか、ディスクや資源を増やすことです。**この形は「治った」ように見えても再発します**。閾値ぎりぎりで動いているためです。

### 原因5：資源の枯渇

ディスクやメモリが尽きた場合です。まず圧迫の条件が立ち、Pod の退避が始まります（[Kubernetes の Evicted の記事](/posts/kubernetes_evicted/)）。それでも改善しなければ、常駐処理自体が動けなくなり `NotReady` に至ります。

```bash
kubectl get nodes -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,DISK:.status.conditions[?(@.type=="DiskPressure")].status,MEM:.status.conditions[?(@.type=="MemoryPressure")].status'
```

圧迫の条件が先に立っている場合、根本原因はそちらです。ノードの復旧だけを試みても、また同じ状態になります。

### 原因6：退去が始まらない、あるいは一斉に始まる

対処というより、挙動の理解です。公式には退去の速度制限が定義されています。既定では毎秒0.1ノード、つまり**10秒に1ノードずつ**です。

さらに、区画ごとの健全性による調整があります。不健全なノードの割合が既定0.55以上になった場合、退去の速度は下げられます。そして**ノード数が50以下の小規模な構成では、退去そのものが停止します**。

この設計を知らないと、「ノードが落ちたのに Pod が移らない」という状況で原因を探し回ることになります。小規模な構成で複数ノードが同時に落ちた場合、**それは仕様どおりの停止**です。制御側が壊れたわけではありません。

## 補足：似ているが別のもの

`Ready,SchedulingDisabled` は異常ではありません。前述のとおり、割り当てを止めた状態です。解除すれば元に戻ります。

Pod が割り当て先を得られない場合は `Pending` です（[Kubernetes の Pending の記事](/posts/kubernetes_pending/)）。ノードが `NotReady` であれば割り当て先の候補から外れるため、結果として `Pending` が増えます。**原因はノード側**です。

資源の圧迫による Pod の退避は `Evicted` です（[Kubernetes の Evicted の記事](/posts/kubernetes_evicted/)）。こちらはノードが生きたまま起こります。

利用者が API を通じて要求する退避は、また別の系統です（[Kubernetes の 429 の記事](/posts/kubernetes_429/)）。

## 切り分けの順序

1. 条件の値を読む。`False` はノードの中、`Unknown` はノードと制御側の間。
2. 最終連絡時刻を見る。いつ止まったかが分かる。
3. すべての条件が `Unknown` なら、連絡が途絶えた形。常駐処理と経路を確認する。
4. `False` なら理由と文言を読む。原因はそこに書かれている。
5. `Ready` と `NotReady` を行き来するなら、実行環境の応答遅延を疑う。閾値は3分。
6. 圧迫の条件が先に立っていないかを確認する。立っていれば根本原因はそちら。
7. 5分を超えたかを確認する。超えていれば Pod の退去が始まっている。
8. Pod が移らないなら、小規模構成での退去停止の条件に当たっていないかを確認する。

## 確認コマンド集

```bash
# 1. 全ノードの条件を一覧で見る
kubectl get nodes -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,REASON:.status.conditions[?(@.type=="Ready")].reason,MSG:.status.conditions[?(@.type=="Ready")].message'

# 2. 最終連絡時刻を確認する
kubectl get node <ノード名> -o jsonpath='{range .status.conditions[?(@.type=="Ready")]}{.status}{"\t"}{.lastHeartbeatTime}{"\t"}{.reason}{"\n"}{end}'

# 3. ノードの詳細から条件とイベントを読む
kubectl describe node <ノード名> | sed -n '/Conditions:/,/Addresses:/p'

# 4. 付与された taint を確認する（退去の判断材料）
kubectl get node <ノード名> -o jsonpath='{.spec.taints}{"\n"}'

# 5. 連絡の記録（Lease）を確認する
kubectl get lease -n kube-node-lease <ノード名> -o yaml | grep renewTime

# 6. ノード上で常駐処理の状態と記録を見る
systemctl status kubelet
journalctl -u kubelet --since "30 minutes ago" | grep -iE "PLEG|not ready|network"

# 7. 実行環境の応答を確認する（ノード上）
sudo crictl info | head -20
time sudo crictl ps -a > /dev/null

# 8. そのノードに残っている Pod を確認する
kubectl get pods -A -o wide --field-selector spec.nodeName=<ノード名>
```

## Editor's Note

`NotReady` の中でも、**行き来を繰り返す**形は原因の特定が難しくなります。落ちた瞬間には調査できず、調べたときには復帰しているためです。

その典型を長期間にわたって記録した報告があります（[Node flapping between Ready/NotReady with PLEG issues](https://github.com/kubernetes/kubernetes/issues/45419)）。2017年5月に登録され、題名のとおり、ノードが `Ready` と `NotReady` を行き来する現象を扱っています。共通して現れていたのが、あの文言です。**最後に動作したのが3分と少し前、閾値は3分**。

この数字の並びが、問題の性質を物語っています。実装上、[コンテナ](/glossary/コンテナ/)の一覧を取得する処理が3分以内に一巡しなければ不健全と判定されます。つまり、**わずかに超えただけで `NotReady` になる**。そして次の巡回が間に合えば `Ready` に戻ります。原因が消えたわけではなく、閾値の境界で揺れているだけです。

報告に集まった状況も一貫していました。[コンテナ](/glossary/コンテナ/)の数が多いノード、ディスクの遅いノード、負荷の高いノード。いずれも一覧の取得に時間がかかる条件です。

ここから得られる教訓は2つあります。1つは、**行き来する `NotReady` は「たまたま」ではない**こと。閾値のすぐ外側で常時動いている状態です。もう1つは、復帰したから解決したとは限らないことです。文言に出る経過時間が閾値に近ければ、次も落ちます。

`NotReady` を見たら、まず条件の値を読む。`False` か `Unknown` か。それだけで、ノードの中を見るのか、ノードの外を見るのかが決まります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*