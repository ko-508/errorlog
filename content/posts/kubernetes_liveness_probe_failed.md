---
title: "Liveness probe失敗：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "Liveness probe failed は、アプリが応答できないとkubeletが判断した記録です。失敗がfailureThresholdへ達すると対象コンテナが終了し、restartPolicyに従って同じPod内で再起動します。再起動回数を増やす前に、失敗理由とprobeの判定条件を確認します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_liveness_probe_failed.png"]
errorCode: "Liveness probe failed"
lastmod: 2026-08-05T00:00:00+09:00
service: "Kubernetes"
error_type: "LivenessProbeFailed"
components: ["kubelet", "Container", "Probe"]
related_services: ["Pod", "startupProbe", "readinessProbe"]
trend_incident: false
---

## 冒頭まとめ

`Liveness probe failed` は、kubeletが対象[コンテナ](/glossary/コンテナ/)の生存確認に失敗した記録です。

```text
Warning  Unhealthy  kubelet  Liveness probe failed:
Get "http://10.244.1.17:8080/healthz":
dial tcp 10.244.1.17:8080: connect: connection refused
```

失敗が `failureThreshold` の回数だけ連続すると、kubeletは**失敗した[コンテナ](/glossary/コンテナ/)を終了**させます。その後の再起動は `restartPolicy` に従います。[Pod lifecycleの公式資料](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-level-container-restart-policy)では、Pod単位の値は `Always`、`OnFailure`、`Never` で、既定値は `Always` と定義されています。そのため、Deploymentなど一般的なPodでは同じPod内で[コンテナ](/glossary/コンテナ/)が再起動します。

```text
Liveness probeが失敗
  ↓ failureThreshold回連続
kubeletが対象コンテナを終了
  ↓ restartPolicyがAlwaysまたはOnFailure
同じPod、同じNodeでコンテナを再起動
  ↓
失敗が続けば再起動待ちが長くなり、CrashLoopBackOffになり得る
```

ここで、Podが[削除](/glossary/削除/)されて新しいPodへ置き換わるわけではありません。Pod名とUIDは同じまま、[コンテナ](/glossary/コンテナ/)の `restartCount` が増えます。複数[コンテナ](/glossary/コンテナ/)のPodなら、probeに失敗した[コンテナ](/glossary/コンテナ/)が対象です。

[Kubernetes公式のprobe資料](https://kubernetes.io/docs/concepts/workloads/pods/probes/#liveness-probe)は、liveness probeを、停止しているように見えないまま処理が進まなくなった[コンテナ](/glossary/コンテナ/)を再起動する仕組みとして説明しています。一時的な高負荷、外部[データベース](/glossary/データベース/)の停止、起動の遅さを検出するためのものではありません。

同じ接続失敗でも、readiness probeとは結果が違います。

```text
Liveness probe failed
  → 対象コンテナを終了し、再起動対象にする

Readiness probe failed
  → コンテナは動かしたまま、PodをServiceの通常転送先から外す
```

一時的に要求を受けられないだけなら、[`readinessProbe`](/posts/kubernetes_readiness_probe_failed/)でServiceから外します。起動に時間がかかるなら `startupProbe` で、livenessの開始を待たせます。再起動しなければ回復できない状態だけを `livenessProbe` で判定します。

最初に確認するのは再起動回数ではなく、[イベント](/glossary/イベント/)末尾の失敗理由です。

```text
connect: connection refused
  → 指定したportで待ち受けていない

context deadline exceeded / timeout
  → timeout内に応答できない

HTTP probe failed with statuscode: 500
  → endpointが失敗用statusを返した

command timed out / exit code != 0
  → exec probeのcommandが失敗した
```

## エラーの概要

probeは、kubeletが[コンテナ](/glossary/コンテナ/)へ定期的に行う診断です。[HTTP](/glossary/http/)、TCP、exec、[gRPC](/glossary/grpc/)の4方式があります。

| 方式 | 成功条件の中心 |
|---|---|
| `httpGet` | [HTTP](/glossary/http/) statusが200以上400未満 |
| `tcpSocket` | 指定したportへTCP接続できる |
| `exec` | [コンテナ](/glossary/コンテナ/)内で実行したcommandが終了[コード](/glossary/コード/)0を返す |
| `grpc` | [gRPC](/glossary/grpc/) Health Checking Protocolが成功を返す |

[HTTP](/glossary/http/) probeの代表例は次のとおりです。

```yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
```

この例では、[コンテナ](/glossary/コンテナ/)開始後10秒待ってから、10秒ごとに `/livez` を確認します。1回の確認は2秒で時間切れとなり、3回連続で失敗するとliveness全体が失敗です。

各値を省略したときの既定値は、現在の[Kubernetes公式設定資料](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#configure-probes)で次のように定義されています。

| 項目 | 既定値 | 意味 |
|---|---:|---|
| `initialDelaySeconds` | 0秒 | [コンテナ](/glossary/コンテナ/)開始後、最初のprobeまで待つ時間 |
| `periodSeconds` | 10秒 | probeの基本間隔 |
| `timeoutSeconds` | 1秒 | 1回のprobeを失敗とする時間 |
| `successThreshold` | 1回 | 失敗後に成功と戻すための連続成功数。livenessは1固定 |
| `failureThreshold` | 3回 | 全体を失敗とする連続失敗数 |

ただし、再起動までの時間を単純に次だけで断定しないでください。

```text
initialDelaySeconds + periodSeconds × failureThreshold
```

probeの実行時間、最初の実行時刻、kubeletの処理、[コンテナ](/glossary/コンテナ/)の終了猶予、再起動の待ち時間が加わります。概算には使えても、正確な再起動時刻の式ではありません。

失敗が閾値へ達すると、kubeletは[コンテナ](/glossary/コンテナ/)を終了させます。liveness probeには、Pod全体の `terminationGracePeriodSeconds` を上書きするprobe単位の値も指定できます。

```yaml
spec:
  terminationGracePeriodSeconds: 30
  containers:
    - name: app
      image: example/app:1.0
      livenessProbe:
        httpGet:
          path: /livez
          port: 8080
        terminationGracePeriodSeconds: 5
```

probe単位の `terminationGracePeriodSeconds` は[Kubernetes](/glossary/kubernetes/) v1.28で安定機能になっています。readiness probeには指定できません。短くしすぎると、アプリの終了処理が完了する前に強制停止されます。

## まず最初に：イベント、直前ログ、現在の設定をそろえる

第一に、Podの[イベント](/glossary/イベント/)を確認します。

```bash
kubectl describe pod <Pod名> -n <名前空間>
```

次の2行を探します。

```text
Warning  Unhealthy  kubelet  Liveness probe failed: ...
Normal   Killing    kubelet  Container app failed liveness probe, will be restarted
```

`Unhealthy` が1回あるだけでは、必ず再起動したとは限りません。`failureThreshold` へ達する前に成功すれば連続失敗は途切れます。`Killing`、`restartCount`、`lastState`を合わせて確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" restartCount="}{.restartCount}{" lastReason="}{.lastState.terminated.reason}{" lastExitCode="}{.lastState.terminated.exitCode}{"\n"}{end}'
```

第二に、再起動前のコンテナログを取得します。

```bash
kubectl logs <Pod名> -n <名前空間> \
  -c <コンテナ名> --previous --timestamps
```

現在の[ログ](/glossary/ログ/)だけを見ると、再起動後の正常な起動しか残っていない場合があります。`--previous` は直前に終了した[コンテナ](/glossary/コンテナ/)の[ログ](/glossary/ログ/)を取る指定です。

第三に、現在適用されているprobe設定を確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> -o yaml
```

DeploymentやHelm valuesだけでなく、作成済みPodの値を見ます。chartの既定値、mutating admission、環境別overrideによって、想定と実値が違う場合があります。

第四に、probeと同じ経路を確認します。[HTTP](/glossary/http/)とTCP probeはkubeletがNode側からPod IPへ接続します。[コンテナ](/glossary/コンテナ/)内の `localhost` で成功しても、Pod IPのportで待ち受けていなければprobeは失敗します。

```bash
kubectl get pod <Pod名> -n <名前空間> -o wide
kubectl exec -n <名前空間> <Pod名> -c <コンテナ名> -- \
  sh -c 'ss -lnt || netstat -lnt'
```

probe用[URL](/glossary/url/)をService名へ置き換えて確認すると、実際のprobeと別経路になります。[イベント](/glossary/イベント/)に表示されたPod IP、path、port、schemeを基準にします。

## よくある原因と解決手順

### 原因1：pathまたはportが実際の待受先と違う

代表的な原因です。

```text
Liveness probe failed: Get "http://10.244.1.17:8080/healthz":
dial tcp 10.244.1.17:8080: connect: connection refused
```

`connection refused` は、接続先IPまでは到達したものの、そのportで接続を受け付けていない状態です。アプリの待受port、containerPort、probeの `port` を照合します。

**Before（アプリは8080、probeは8081）：**

```yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8081
```

**After：**

```yaml
ports:
  - name: http
    containerPort: 8080

livenessProbe:
  httpGet:
    path: /livez
    port: http
```

名前付きportを使うと、port番号の変更時にprobeだけ古く残る事故を減らせます。[gRPC](/glossary/grpc/) probeの `port` には名前を使えないため、数値で指定します。

[HTTP](/glossary/http/) statusが404なら、portには到達しています。path、アプリのbase path、reverse proxyを通さない直接接続でそのpathが存在するかを確認します。

### 原因2：アプリがlocalhostだけで待ち受けている

アプリが次だけで待ち受けている場合、[コンテナ](/glossary/コンテナ/)内からは成功しても、NodeからPod IPへ送る[HTTP](/glossary/http/)・TCP probeは失敗します。

```text
127.0.0.1:8080
```

待受先をPod IPから到達できるアドレスへ変更します。

```text
0.0.0.0:8080
```

アプリの設定名は言語やWeb[サーバー](/glossary/サーバー/)ごとに違います。起動[ログ](/glossary/ログ/)と次の結果で、実際の待受アドレスを確認します。

```bash
kubectl exec -n <名前空間> <Pod名> -c <コンテナ名> -- \
  sh -c 'ss -lnt || netstat -lnt'
```

[コンテナ](/glossary/コンテナ/)内だけで確認する必要があるなら `exec` probeも選択肢ですが、単に設定ミスを隠すために変更しないでください。実際の利用者がPod[ネットワーク](/glossary/ネットワーク/)経由で接続するなら、その経路で成功する必要があります。

### 原因3：起動完了前にliveness probeが始まる

起動時のmigration、cache作成、JIT、設定取得などに時間がかかると、正常な初期化中でもlivenessが失敗します。再起動すると[初期化](/glossary/初期化/)が最初からやり直され、永遠にReadyにならないことがあります。

`initialDelaySeconds` を極端に増やすより、`startupProbe` を使います。

```yaml
startupProbe:
  httpGet:
    path: /startupz
    port: http
  periodSeconds: 5
  failureThreshold: 60

livenessProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 10
  failureThreshold: 3
```

startup probeが一度成功するまで、livenessとreadinessは実行されません。この例では、最大約300秒の起動期間を許します。値は実測した最悪時の起動時間を基に決めます。

### 原因4：timeoutSecondsが実際の応答時間より短い

probeの既定の時間切れは1秒です。通常は速いendpointでも、CPU制限、GC、Node高負荷、disk待ちによって一時的に超えることがあります。

```text
Liveness probe failed: Get "http://10.244.1.17:8080/livez":
context deadline exceeded
```

まずprobe endpointの処理時間と資源使用量を確認します。

```bash
kubectl top pod <Pod名> -n <名前空間> --containers
kubectl describe pod <Pod名> -n <名前空間>
```

endpointがDB問い合わせや大きな計算をしているなら、単純で軽い判定へ変更します。正常時でも1秒を超え得ることが確認できた場合は、実測に基づいて `timeoutSeconds` と `failureThreshold` を調整します。

```yaml
livenessProbe:
  httpGet:
    path: /livez
    port: http
  timeoutSeconds: 3
  periodSeconds: 10
  failureThreshold: 3
```

timeoutを延ばすだけでは、CPU不足や停止状態の原因は直りません。

### 原因5：一時的な外部依存障害をlivenessへ含めている

liveness endpointがDB、cache、外部[API](/glossary/api/)、[DNS](/glossary/dns/)などを必須条件にすると、共有依存先の停止で全Podが同時に再起動します。

```text
外部DBが遅延
  ↓
全Podのlivenessが失敗
  ↓
全Podが再起動
  ↓
再接続と初期化が集中し、DB負荷がさらに増える
```

再起動しても直らない条件は、livenessへ入れません。

```text
/livez
  → プロセス自身が処理を進められるか

/readyz
  → 現在、利用者の要求を正しく処理できるか
```

外部依存が利用者要求に必須ならreadinessで判定し、Serviceから一時的に外します。ただし、共有依存先の障害で全PodをUnreadyにするとServiceの転送先が0になるため、依存関係と縮退動作を含めて設計します。

### 原因6：認証が必要なendpointを指定している

probeは通常の利用者[ログイン](/glossary/ログイン/)を行いません。

```text
Liveness probe failed: HTTP probe failed with statuscode: 401
```

probe専用の最小endpointを用意し、Nodeからの確認に必要な条件だけを返します。

```yaml
livenessProbe:
  httpGet:
    path: /livez
    port: http
```

機密情報や内部状態を本文へ含めず、成功時は小さな応答を返します。固定tokenをPod定義の `httpHeaders` へ直接書くと、Podを読める主体から見えるため避けます。[認証](/glossary/認証/)が必須なら、Secretを利用した `exec` probeなど、資格情報を平文でPod仕様へ置かない方法を検討します。

### 原因7：HTTPのschemeまたはHost条件が違う

アプリが[HTTPS](/glossary/https/)だけで待ち受けているのに、probeが既定の[HTTP](/glossary/http/)を使うと失敗します。

```yaml
livenessProbe:
  httpGet:
    scheme: HTTPS
    path: /livez
    port: 8443
```

virtual hostで `Host` headerが必要なら、接続先の `host` を変えるのではなく、headerを指定します。

```yaml
livenessProbe:
  httpGet:
    path: /livez
    port: http
    httpHeaders:
      - name: Host
        value: app.internal.example
```

[HTTP](/glossary/http/) probeの接続先は既定でPod IPです。Service名やIngressの公開[URL](/glossary/url/)をprobe先にすると、Pod自身以外の[DNS](/glossary/dns/)、Service、proxyまでliveness条件へ含めることになります。

### 原因8：exec probeのcommandがコンテナにない、または終了しない

```yaml
livenessProbe:
  exec:
    command:
      - curl
      - -f
      - http://127.0.0.1:8080/livez
```

distrolessや最小[イメージ](/glossary/イメージ/)には `curl`、`sh`、`cat` がない場合があります。commandが存在しなければアプリが正常でもprobeは失敗します。

```bash
kubectl exec -n <名前空間> <Pod名> -c <コンテナ名> -- \
  curl -f http://127.0.0.1:8080/livez
```

上の確認自体が `executable file not found` なら、[イメージ](/glossary/イメージ/)にあるcommandへ変更するか、組み込みの `httpGet`、`tcpSocket`、`grpc` を使います。exec commandが子処理を残す、標準入出力を閉じない、時間内に終わらない場合も失敗の原因になります。

### 原因9：livenessとreadinessを同じ厳しい条件にしている

同じpathを使うこと自体は禁止されていません。ただし、同じ閾値と条件では、一時的な過負荷に対してServiceから外れるのと再起動がほぼ同時に起きます。

公式資料は、同じ軽量endpointを使う場合でも、liveness側の `failureThreshold` を高くし、先にreadinessで転送先から外れる時間を作る構成を例示しています。

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: http
  periodSeconds: 5
  failureThreshold: 1

livenessProbe:
  httpGet:
    path: /healthz
    port: http
  periodSeconds: 10
  failureThreshold: 6
```

より明確にするなら、判定目的も分けます。

```text
readiness: 一時的に要求を受けてよいか
liveness: 再起動しなければ回復できないか
```

## 補足：似ているが別のもの

### Readiness probe failed

readiness失敗では[コンテナ](/glossary/コンテナ/)を終了しません。Podの `Ready` conditionをFalseにし、該当Serviceの通常転送先から外します。`RESTARTS` が増えているなら、liveness、アプリ自身の終了、OOMKilledなど別の理由を確認します。

### Startup probe failed

startup probeが設定されている間、livenessとreadinessは開始されません。startup失敗が閾値へ達すると[コンテナ](/glossary/コンテナ/)を終了し、restartPolicyの対象になります。起動中のliveness再起動を防ぐ目的で使います。

### OOMKilled

[メモリ](/glossary/メモリ/)上限超過で[コンテナ](/glossary/コンテナ/)が終了した状態です。liveness endpointが応答できなかった時刻と近くても、終了理由が `OOMKilled` なら[メモリ](/glossary/メモリ/)不足を調べます。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" "}{.lastState.terminated.reason}{"\n"}{end}'
```

### CrashLoopBackOff

短時間の終了と再起動が続き、kubeletが次の再起動まで待っている状態です。livenessが原因になることもありますが、アプリの終了、設定不足、command失敗などでも起きます。`Liveness probe failed` と `Killing` の[イベント](/glossary/イベント/)を確認して原因を結びます。

### Podの再作成

liveness失敗は通常、同じPod内の[コンテナ](/glossary/コンテナ/)再起動です。Deploymentが新しいPodを作るのは、Pod[削除](/glossary/削除/)、rollout、Node障害、replica不足など別の制御です。Pod UIDが変わっているなら、livenessだけで説明しません。

## 切り分けの順序

1. `kubectl describe pod` で `Liveness probe failed` の末尾を確認する。
2. `Killing` [イベント](/glossary/イベント/)と `restartCount` を確認し、閾値到達後の再起動かを確定する。
3. `kubectl logs --previous` で終了直前のアプリログを取得する。
4. 作成済みPodからpath、port、scheme、timeout、各thresholdを確認する。
5. `connection refused` なら待受portとアドレス、404ならpath、401・403なら認証条件を確認する。
6. timeoutならprobe処理時間、CPU、memory、Node負荷を確認する。
7. 起動中だけ失敗するなら `startupProbe` を追加する。
8. 外部依存の一時障害をliveness条件から外し、必要ならreadinessへ分離する。
9. `restartPolicy` と終了猶予を確認する。
10. 修正後、[イベント](/glossary/イベント/)の最終時刻、`restartCount`、Ready状態を継続して確認する。

## 確認コマンド集

Podの状態と再起動回数を確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> -o wide
kubectl describe pod <Pod名> -n <名前空間>
```

終了理由を[コンテナ](/glossary/コンテナ/)ごとに確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" restartCount="}{.restartCount}{" lastReason="}{.lastState.terminated.reason}{" lastExitCode="}{.lastState.terminated.exitCode}{"\n"}{end}'
```

直前と現在の[ログ](/glossary/ログ/)を取得します。

```bash
kubectl logs <Pod名> -n <名前空間> -c <コンテナ名> \
  --previous --timestamps > liveness-previous.log

kubectl logs <Pod名> -n <名前空間> -c <コンテナ名> \
  --timestamps > liveness-current.log
```

probe設定だけを確認します。

```bash
kubectl get pod <Pod名> -n <名前空間> \
  -o jsonpath='{range .spec.containers[*]}{.name}{"\n"}{.livenessProbe}{"\n"}{end}'
```

対象Podの[イベント](/glossary/イベント/)を時刻順に取得します。

```bash
kubectl get events -n <名前空間> \
  --field-selector involvedObject.name=<Pod名> \
  --sort-by=.lastTimestamp
```

資源使用量を確認します。Metrics Serverなどが必要です。

```bash
kubectl top pod <Pod名> -n <名前空間> --containers
```

Deploymentのrollout後に、新しいPodの状態を確認します。

```bash
kubectl rollout status deployment/<Deployment名> -n <名前空間>
kubectl get pods -n <名前空間> -l <label-key>=<label-value> -w
```

## Editor's Note

`Liveness probe failed` を「アプリが壊れた証拠」と読むと、probe側の誤りを見落とします。[Kubernetes](/glossary/kubernetes/)が確定したのは、設定された方法が設定された時間内に成功しなかったことです。その失敗が、再起動でしか直らない状態かどうかは、probe設計者が決めています。

2018年の[Kubernetes](/glossary/kubernetes/)の課題（[Liveness/Readiness probes are failing with connection refused](https://github.com/kubernetes/kubernetes/issues/62594)）では、同じDeploymentのprobeが断続的に `connection refused` となり、一部のPodが多くの再起動を繰り返して `CrashLoopBackOff` になった状況が報告されました。[ログ](/glossary/ログ/)にはlivenessとreadinessの両方の失敗がありましたが、[コンテナ](/glossary/コンテナ/)を再起動させるのはliveness側です。

同じ `connection refused` でも、readinessだけなら対象PodをServiceの通常転送先から外し、[コンテナ](/glossary/コンテナ/)を動かしたまま次のprobeを待ちます。livenessなら、閾値到達後に[コンテナ](/glossary/コンテナ/)を終了します。**失敗文ではなく、どのprobe欄に書いたかが結果を決める**例です。

2019年の課題（[Give the proper reason for killing pods](https://github.com/kubernetes/kubernetes/issues/81723)）では、[コンテナ](/glossary/コンテナ/)が終了した理由として広い `Killing` だけが表示され、liveness、memory、別の理由を区別しにくいことが指摘されました。現在も、終了[コード](/glossary/コード/)だけでlivenessを確定するのは危険です。[イベント](/glossary/イベント/)の `Liveness probe failed` と `Container ... failed liveness probe, will be restarted`、container status、直前[ログ](/glossary/ログ/)を時刻で結びます。

[Kubernetes](/glossary/kubernetes/)公式は、誤ったlivenessが高負荷時に[コンテナ](/glossary/コンテナ/)を再起動し、残ったPodへ負荷を集中させ、連鎖的な失敗を起こし得ると警告しています。再起動は回復手段ですが、負荷、外部依存、遅い起動に対しては障害を増幅する処理にもなります。

だから、liveness endpointが答えるべき問いは「今、完全に正常か」ではありません。**この[プロセス](/glossary/プロセス/)は、再起動しなければ回復できない状態か**です。一時的に要求を受けられない状態はreadinessへ、まだ起動中の状態はstartupへ分けます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
