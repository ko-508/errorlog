---
title: "Readiness probe失敗：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "Readiness probe failed は、Podを再起動するエラーではありません。コンテナを動かしたままPodをReady=Falseにし、該当Serviceの通常転送先から外します。Pod IPへの直接通信や既存接続まで遮断する機能ではないため、Ready条件とEndpointSliceを確認します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_readiness_probe_failed.png"]
errorCode: "Readiness probe failed"
lastmod: 2026-08-05T00:00:00+09:00
service: "Kubernetes"
error_type: "ReadinessProbeFailed"
components: ["kubelet", "EndpointSlice", "Service"]
related_services: ["Pod", "kube-proxy", "Ingress"]
trend_incident: false
---

## 冒頭まとめ

`Readiness probe failed` は、kubeletが「この[コンテナ](/glossary/コンテナ/)は現在、利用者からの要求を受ける準備ができていない」と判定した記録です。

```text
Warning  Unhealthy  kubelet  Readiness probe failed:
Get "http://10.244.1.18:8080/readyz":
context deadline exceeded
```

失敗が `failureThreshold` の回数だけ連続すると、kubeletは[コンテナ](/glossary/コンテナ/)を終了せず、Podの `Ready` conditionを `False` にします。該当Podを選択するServiceでは、EndpointSliceの通常転送対象から外れます。

```text
Readiness probeが失敗
  ↓ failureThreshold回連続
コンテナはRunningのまま
  ↓
Container Ready=False
  ↓
Pod Ready=False
  ↓
該当Serviceの通常転送先から外れる
  ↓ probeが再び成功
同じPodがReady=Trueへ戻り、転送先へ復帰する
```

したがって、readiness失敗だけでは `RESTARTS` は増えません。`kubectl get pod` では次のように、`STATUS` は `Running` のまま、`READY` が `0/1` になることがあります。

```text
NAME    READY   STATUS    RESTARTS   AGE
app-0   0/1     Running   0          12m
```

同じprobe失敗でも、[`livenessProbe`](/posts/kubernetes_liveness_probe_failed/)とは結果が反対です。

```text
Readiness probe failed
  → 動かしたままServiceの通常転送先から外す

Liveness probe failed
  → 対象コンテナを終了し、restartPolicyに従って再起動する
```

ただし、readinessはPodのnetworkを切断する機能ではありません。[Kubernetes公式のprobe資料](https://kubernetes.io/docs/concepts/workloads/pods/probes/#readiness-probe)が変更すると説明しているのは、PodのReady状態と、該当ServiceのEndpointSliceです。

この仕組みから、次の点を分ける必要があります。

```text
ServiceのClusterIP、NodePort、LoadBalancerなどからの通常転送
  → ReadyでないPodを転送先から外す

Pod IPへの直接接続、kubectl port-forward、独自に管理したEndpointSlice
  → readinessだけでは遮断されない

すでに確立済みの接続
  → readiness失敗だけで切断される保証はない
```

また、EndpointSliceと各Nodeの転送規則は制御処理で更新されるため、失敗した瞬間にクラスタ内のすべての[通信](/glossary/通信/)が同時停止するわけではありません。外部Load Balancer、Ingress、service meshには、それぞれ反映時間と動作があります。

最初に確認するのは、Podだけではなく次の3点です。

```text
probeがなぜ失敗したか
PodのReady conditionがどうなったか
該当ServiceのEndpointSliceでreadyがどうなったか
```

## エラーの概要

readiness probeは、[コンテナ](/glossary/コンテナ/)が現在、要求を受けてよいかを定期的に判定します。[HTTP](/glossary/http/)、TCP、exec、[gRPC](/glossary/grpc/)の方式はlivenessと共通ですが、失敗後の処理が違います。

```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
  successThreshold: 2
```

この例では、2回連続で失敗するとUnreadyになり、失敗後は2回連続で成功してからReadyへ戻ります。`successThreshold` を2以上にできる点は、1固定のlivenessと異なります。

省略時の値は、現在の[Kubernetes公式設定資料](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#configure-probes)で次のように定義されています。

| 項目 | 既定値 | 意味 |
|---|---:|---|
| `initialDelaySeconds` | 0秒 | [コンテナ](/glossary/コンテナ/)開始後、最初のprobeまで待つ時間 |
| `periodSeconds` | 10秒 | probeの基本間隔 |
| `timeoutSeconds` | 1秒 | 1回のprobeを失敗とする時間 |
| `successThreshold` | 1回 | 失敗後にReadyへ戻す連続成功数 |
| `failureThreshold` | 3回 | Unreadyとする連続失敗数 |

[コンテナ](/glossary/コンテナ/)がUnreadyの間、readiness probeは復帰を早く検出するため、設定した `periodSeconds` 以外の時点にも実行されることがあります。したがって、常に正確な固定間隔だと仮定してprobe回数を監視しないでください。

PodのReadyは、1つのreadiness probeだけで決まるとは限りません。

```text
各コンテナのready状態
  ↓ すべて成功
ContainersReady=True
  ↓ readinessGatesもすべて成功
Pod Ready=True
```

複数[コンテナ](/glossary/コンテナ/)のうち1つでもReadyでなければ、Pod全体のReadyはFalseになります。また、`readinessGates` を使っている場合は、すべてのprobeが成功しても独自conditionがFalseまたは未設定ならPodはReadyになりません。

PodがReadyになると、EndpointSlice controllerは該当Service向けのendpointへ状態を反映します。[EndpointSliceの公式資料](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/#conditions)では、`ready`、`serving`、`terminating` のconditionが定義されています。通常の実行中Podでは、PodのReadyがService endpointの `ready` と `serving` に対応します。

各Nodeのkube-proxy、または代替のService実装は、ServiceとEndpointSliceを監視し、Serviceの仮想IPへ来た[通信](/glossary/通信/)の転送先を更新します。[Serviceの仮想IPとproxyの公式資料](https://kubernetes.io/docs/reference/networking/virtual-ips/)にも、この監視と[同期](/glossary/同期/)の制御処理が説明されています。

## まず最初に：Pod、condition、EndpointSliceを同じ時刻で見る

第一に、Podの表示を確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> -o wide
kubectl describe pod <Pod名> -n <名前空間>
```

[イベント](/glossary/イベント/)末尾の具体的な理由を読みます。

```text
Readiness probe failed: dial tcp ... connect: connection refused
Readiness probe failed: context deadline exceeded
Readiness probe failed: HTTP probe failed with statuscode: 503
```

第二に、Pod conditionと[コンテナ](/glossary/コンテナ/)ごとのready状態を確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" ready="}{.ready}{" restarts="}{.restartCount}{"\n"}{end}{range .status.conditions[*]}{.type}{"="}{.status}{" reason="}{.reason}{"\n"}{end}'
```

`ContainersReady=False` なのか、独自のreadiness gateで `Ready=False` なのかを分けます。

第三に、Podを選ぶServiceを特定します。

```bash
kubectl get service -n <名前空間> --show-labels
kubectl get pod <Pod名> -n <名前空間> --show-labels
```

ServiceのselectorとPodのlabelが一致しなければ、probeが成功してもそのServiceの転送先には入りません。

第四に、EndpointSliceを確認します。

```bash
kubectl get endpointslice -n <名前空間> \
  -l kubernetes.io/service-name=<Service名> -o yaml
```

対象Pod IPを探し、`conditions.ready` を確認します。

```yaml
endpoints:
  - addresses:
      - 10.244.1.18
    conditions:
      ready: false
      serving: false
      terminating: false
```

古い `Endpoints` [API](/glossary/api/)ではなく、現在のService転送の基礎であるEndpointSliceを優先して確認します。`kubectl describe service` の要約だけで判定しません。

最後に、Pod IPへ直接接続して、アプリ自体の応答とService経由の応答を分けます。

```bash
kubectl port-forward -n <名前空間> pod/<Pod名> 18080:8080
```

別端末から次を実行します。

```bash
curl -i http://127.0.0.1:18080/readyz
```

port-forwardが成功するのにService経由で対象Podへ届かないのは、readinessが意図どおり転送先から外した結果であり得ます。

## よくある原因と解決手順

### 原因1：pathまたはportが実際のendpointと違う

```text
Readiness probe failed: Get "http://10.244.1.18:8081/readyz":
dial tcp 10.244.1.18:8081: connect: connection refused
```

`connection refused` なら、対象IPのportで待ち受けていません。アプリの待受port、probeの `port`、名前付きportを照合します。

**Before（アプリは8080、probeは8081）：**

```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: 8081
```

**After：**

```yaml
ports:
  - name: http
    containerPort: 8080

readinessProbe:
  httpGet:
    path: /readyz
    port: http
```

[HTTP](/glossary/http/) 404ならportへの接続は成功しています。`/readyz` のpath、base path、アプリのroute登録を確認します。[HTTP](/glossary/http/) 401または403なら、[認証](/glossary/認証/)が必要なendpointをprobeしていないか確認します。

### 原因2：アプリがlocalhostだけで待ち受けている

[HTTP](/glossary/http/)とTCPのprobeは、Node側のkubeletからPod IPへ接続します。[コンテナ](/glossary/コンテナ/)内の次の接続だけで成功しても不十分です。

```bash
curl http://127.0.0.1:8080/readyz
```

待受状態を確認します。

```bash
kubectl exec -n <名前空間> <Pod名> -c <コンテナ名> -- \
  sh -c 'ss -lnt || netstat -lnt'
```

`127.0.0.1:8080` だけなら、Pod IPから到達できるアドレスへ変更します。

```text
0.0.0.0:8080
```

実際の利用者がPod network経由で接続するアプリなら、readinessも同じ到達性を確認する必要があります。

### 原因3：起動処理が終わる前にreadinessを確認している

readiness probeがあるPodは、最初の成功までServiceの転送先へ入りません。これは起動中の要求を防ぐ正しい動作です。

一方、起動に数分かかることが正常なのに、[イベント](/glossary/イベント/)を障害として監視しているなら、監視条件を見直します。起動完了前のreadiness失敗は、必ずしもアプリ異常ではありません。

起動処理と起動後の一時的な準備不足を分けたい場合は、startup probeを追加します。

```yaml
startupProbe:
  httpGet:
    path: /startupz
    port: http
  periodSeconds: 5
  failureThreshold: 60

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 5
  failureThreshold: 2
```

startup probeが成功するまでreadinessとlivenessは開始されません。起動中の `Readiness probe failed` [イベント](/glossary/イベント/)を減らせますが、その間もPodはReadyになりません。

### 原因4：timeoutSecondsが短く、高負荷時だけ失敗する

既定の時間切れは1秒です。

```text
Readiness probe failed: context deadline exceeded
```

probe endpointの応答時間、CPU制限、GC、Node負荷を確認します。

```bash
kubectl top pod <Pod名> -n <名前空間> --containers
kubectl describe pod <Pod名> -n <名前空間>
```

readiness endpoint自体がDBへの重い問い合わせや大きな応答生成を行っているなら、軽量化します。正常時の遅延分布を測定し、必要な場合だけ時間切れを調整します。

```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: http
  timeoutSeconds: 3
  periodSeconds: 5
  failureThreshold: 2
```

timeoutを延ばすとUnreadyの検出も遅くなるため、値を大きくするだけで解決しません。

### 原因5：一時的な外部依存障害を正しく検出している

アプリが外部DBなしでは正しい応答を返せないなら、その依存先の停止でreadinessを失敗させる設計は合理的です。[コンテナ](/glossary/コンテナ/)を再起動せず、誤った応答を返すPodをServiceから外せます。

```text
DB接続不可
  ↓
/readyz が503
  ↓
Pod Ready=False
  ↓
Serviceの通常転送先から外れる
```

ただし、全Podが同じDBを必須条件にすると、DB障害時に全endpointがUnreadyとなり、Serviceの転送先が0になります。アプリがcacheやread-onlyで縮退できるなら、どの依存先をreadiness必須条件にするかを見直します。

再起動で直らない外部依存障害をlivenessにも入れると、全Pod再起動を重ねるため分離します。

```text
liveness: プロセス自身が処理を進められるか
readiness: 現在、要求を正しく処理できるか
```

### 原因6：failureThresholdとsuccessThresholdが敏感すぎる

1回の短い遅延で転送先から外したくない場合は、`failureThreshold` を調整します。復帰直後の揺れを抑えるなら `successThreshold` を2以上にできます。

```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 2
```

この値では、失敗判定まで最低でも複数回のprobeが必要になります。数を増やすほど、一時的な失敗には強くなりますが、本当に要求を処理できないPodを転送先に残す時間も長くなります。

### 原因7：複数コンテナの別コンテナがUnreadyになっている

main containerの `/readyz` が成功していても、sidecarなど別の[コンテナ](/glossary/コンテナ/)がReadyでなければPod全体はReadyになりません。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" ready="}{.ready}{" state="}{.state}{"\n"}{end}'
```

各[コンテナ](/glossary/コンテナ/)の `ready` を確認し、[イベント](/glossary/イベント/)に表示されたcontainer名とprobe設定を対応させます。Serviceがmain containerだけへ送る構成でも、Pod単位のReadyがFalseなら通常転送先から外れます。

### 原因8：readinessGateがFalseまたは未設定になっている

Pod仕様に `readinessGates` がある場合、probeが成功しても独自conditionがTrueになるまでPodはReadyになりません。

```yaml
spec:
  readinessGates:
    - conditionType: example.com/feature-ready
```

conditionを確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.conditions[*]}{.type}{"="}{.status}{" reason="}{.reason}{" message="}{.message}{"\n"}{end}'
```

`Readiness probe failed` が過去[イベント](/glossary/イベント/)に残っていても、現在のReady=FalseがreadinessGateによる場合があります。[イベント](/glossary/イベント/)の最終時刻と現在conditionを分けます。

### 原因9：ServiceがpublishNotReadyAddressesを有効にしている

Serviceに次の設定があると、EndpointSliceを利用する処理はPodのReadyを無視する扱いになります。

```yaml
spec:
  publishNotReadyAddresses: true
```

[Service APIの公式資料](https://kubernetes.io/docs/reference/kubernetes-api/core/service-v1/#ServiceSpec)では、[Kubernetes](/glossary/kubernetes/)が生成するEndpointsとEndpointSliceで、すべてのendpointをreadyとして扱う設定と説明されています。主な用途は、StatefulSetのpeer discoveryなどです。

```bash
kubectl get service <Service名> -n <名前空間> \
  -o jsonpath='{.spec.publishNotReadyAddresses}{"\n"}'
```

この設定では、readiness probeが失敗してもService経由の[通信](/glossary/通信/)が続き得ます。利用者要求を止める目的のServiceで必要な設定かを確認します。

### 原因10：ServiceのselectorまたはEndpointSliceの管理主体が違う

readinessが成功しているのにServiceへ入らない場合、ServiceのselectorとPod labelを確認します。

```bash
kubectl get service <Service名> -n <名前空間> -o yaml
kubectl get pod <Pod名> -n <名前空間> --show-labels
```

selectorなしのServiceや、独自controllerが管理するEndpointSliceでは、Pod readinessが自動反映されない場合があります。EndpointSliceの次のlabelを確認します。

```yaml
metadata:
  labels:
    endpointslice.kubernetes.io/managed-by: endpointslice-controller.k8s.io
```

独自管理なら、そのcontrollerがPod Readyをどう扱うかを確認します。[Kubernetes](/glossary/kubernetes/)標準のreadinessだけで外れると仮定しません。

## 補足：似ているが別のもの

### Liveness probe failed

liveness失敗が閾値へ達すると、対象[コンテナ](/glossary/コンテナ/)を終了し、restartPolicyに従って再起動します。`RESTARTS` が増え、同じ失敗が続けばCrashLoopBackOffになり得ます。readinessの修正と混同しないでください。

### Startup probe failed

startup probeが成功するまでreadinessとlivenessを開始しません。起動に時間がかかる[コンテナ](/glossary/コンテナ/)を保護します。startup失敗が閾値へ達すると、readinessとは違って[コンテナ](/glossary/コンテナ/)終了と再起動の対象になります。

### Serviceのselector不一致

Podが `1/1 Running` かつ `Ready=True` でも、Serviceのselectorとlabelが一致しなければEndpointSliceへ入りません。Pod readinessではなくServiceの選択条件を直します。

### NetworkPolicy

readinessはServiceの転送先を制御する状態です。NetworkPolicyはPod間通信を許可または拒否する規則です。Pod IPへの直接接続も拒否されるなら、readinessだけでなくNetworkPolicy、CNI、firewallを確認します。

### terminating Pod

Podが削除されると、readiness probeとは別にEndpointSliceの `terminating` がTrueとなり、通常は `ready` がFalseになります。終了処理中の[通信](/glossary/通信/)には `serving` conditionも使われます。削除中の動作をreadiness失敗だけで説明しません。

### Ingressや外部Load Balancerのhealth check

Ingress controllerや外部Load Balancerが独自のhealth checkとbackend管理を持つ場合、EndpointSlice変更の反映時刻と挙動は実装ごとに違います。Pod Ready=Falseだけで、外部からの全経路が同時に止まったと断定しません。

## 切り分けの順序

1. `kubectl describe pod` で `Readiness probe failed` の末尾と最終時刻を確認する。
2. 各containerのready、Podの `ContainersReady` と `Ready` conditionを確認する。
3. 作成済みPodからpath、port、scheme、timeout、thresholdを確認する。
4. Podを選択するServiceと、そのselectorを確認する。
5. EndpointSliceで対象Pod IPの `ready`、`serving`、`terminating` を確認する。
6. `connection refused` なら待受portとアドレス、404ならpath、timeoutなら処理時間と資源を確認する。
7. 起動中だけ失敗するならstartup probeを追加する。
8. 外部依存を必須条件にする範囲と、全PodがUnreadyになる場合の縮退動作を確認する。
9. `readinessGates` と `publishNotReadyAddresses` の有無を確認する。
10. Pod IPへの直接通信、Service、Ingressを分け、どの経路で転送が止まったかを確認する。

## 確認コマンド集

PodのReady状態と[イベント](/glossary/イベント/)を確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> -o wide
kubectl describe pod <Pod名> -n <名前空間>
```

[コンテナ](/glossary/コンテナ/)とPod conditionをまとめて確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" ready="}{.ready}{" restarts="}{.restartCount}{"\n"}{end}{range .status.conditions[*]}{.type}{"="}{.status}{" reason="}{.reason}{"\n"}{end}'
```

readiness設定だけを確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .spec.containers[*]}{.name}{"\n"}{.readinessProbe}{"\n"}{end}'
```

ServiceとEndpointSliceを確認します。

```bash
kubectl get service <Service名> -n <名前空間> -o yaml

kubectl get endpointslice -n <名前空間> \
  -l kubernetes.io/service-name=<Service名> -o yaml
```

対象Podの[イベント](/glossary/イベント/)を時刻順に確認します。

```bash
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp
```

Podへ直接port-forwardして、Serviceを通さず確認します。

```bash
kubectl port-forward -n <名前空間> pod/<Pod名> 18080:8080
curl -i http://127.0.0.1:18080/readyz
```

資源使用量を確認します。Metrics Serverなどが必要です。

```bash
kubectl top pod <Pod名> -n <名前空間> --containers
```

rollout中のReady数を確認します。

```bash
kubectl rollout status deployment/<Deployment名> -n <名前空間>
kubectl get deployment/<Deployment名> -n <名前空間>
kubectl get pods -n <名前空間> -l <label-key>=<label-value> -w
```

## Editor's Note

`Readiness probe failed` を「Podへの[通信](/glossary/通信/)が遮断された」とまとめると、実際の変更範囲を広く見積もりすぎます。readinessが直接変更するのは、containerとPodのReady状態です。そこからEndpointSlice controller、kube-proxyや代替実装、IngressやLoad Balancerへ状態が伝わり、Service経由の通常転送先が更新されます。

2024年の[Kubernetes](/glossary/kubernetes/)の課題（[`kubectl describe service` shows endpoints that are not ready](https://github.com/kubernetes/kubernetes/issues/126922)）では、readinessが失敗して `kubectl get endpoints` では転送先が空なのに、`kubectl describe service` の要約にはUnreadyなPod IPが表示される不整合が報告されました。修正は[Pull Request #126932](https://github.com/kubernetes/kubernetes/pull/126932)で取り込まれています。

この事例は、Pod IPが画面に見えることと、実際の転送対象であることが同じではないと示します。現在の切り分けでは、Serviceの要約だけでなくEndpointSliceの `conditions.ready` を確認する必要があります。

一方、2024年の[AWS](/glossary/aws/) Load Balancer Controllerの課題（[Potential thundering herd caused by readiness probes](https://github.com/kubernetes-sigs/aws-load-balancer-controller/issues/3711)）では、全Podのreadinessが失敗するとcontrollerがALBの対象から外し、少数のPodがReadyへ戻った瞬間に要求が集中して再びUnreadyになる循環が報告されました。[コンテナ](/glossary/コンテナ/)は生存していても、外部転送先の管理によって全体障害を増幅し得る例です。

readinessは再起動を起こさないため、livenessより安全とは限りません。全Podが同じ外部依存を確認し、その依存先の障害で同時にUnreadyになると、Serviceから利用可能な転送先が消えます。復帰時の `successThreshold` が1なら、最初に成功した少数のPodへ負荷が集中することもあります。

だから、readiness endpointが答えるべき問いは「すべての依存先が完全に正常か」ではありません。**このPodへ今、新しい要求を送ると、利用者へ意味のある応答を返せるか**です。そして失敗時の結果は通信遮断ではなく、Serviceの通常転送先からの除外です。直接通信、既存接続、独自EndpointSlice、`publishNotReadyAddresses` は別に確認します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
