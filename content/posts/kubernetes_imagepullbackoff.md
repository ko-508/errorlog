---
title: "Kubernetes の ImagePullBackOff エラー：原因と解決策"
date: 2026-07-29
description: "ImagePullBackOff は取得に失敗した理由の名前ではなく、次の取得まで待たせている状態の名前です。kubelet は取得に関する状態名を5つ定義しており、どれが出ているかで原因の範囲がほぼ決まります。待ち時間は10秒から倍々に増えて上限300秒。そして、この状態は何度失敗しても諦めません。"
tags: ["Kubernetes"]
errorCode: "ImagePullBackOff"
lastmod: 2026-07-29
service: "Kubernetes"
error_type: "ImagePullBackOff"
components: ["kubelet", "Pod"]
related_services: ["Container Registry", "kubelet"]
trend_incident: false
---

## 冒頭まとめ

ImagePullBackOff は、[イメージ](/glossary/イメージ/)の取得に失敗した理由の名前ではありません。失敗したあと、次に取得を試みるまで待たせている状態の名前です。理由は別の名前で表されます。

kubelet のソースには、取得に関する状態名が5つ定義されています。待たせている状態、一般的な取得の失敗、[イメージ](/glossary/イメージ/)を調べられない場合、手元に無いのに取得しない方針になっている場合、そして名前を解釈できない場合です。この5つのどれが出ているかで、原因の範囲がほぼ決まります。最初に見るべきはここです。

待ち時間の決まり方は、[コンテナ](/glossary/コンテナ/)の再起動と同じ形です。初回は10秒で倍々に増え、上限は300秒です。値は同じですが、記録は別に管理されています。

そして、この状態には決定的な性質が1つあります。諦めません。何度失敗しても、対象は待機中の扱いのまま残り続け、割り当てられた資源を確保し続けます。失敗を重ねたら異常として扱う、という仕組みが標準では用意されていません。人が気付いて手を入れるまで、そのままです。

最後に、取得の方針の既定値も押さえておきます。ソースの規則は単純で、[タグ](/glossary/タグ/)が `latest` なら毎回取得し、それ以外なら手元にあるものを使います。[タグ](/glossary/タグ/)を書かない場合は[タグ](/glossary/タグ/)を `latest` とみなす処理が入るため、結果として毎回取得になります。一方、ダイジェストで指定した場合は[タグ](/glossary/タグ/)が空のままなので、手元にあるものを使う方針になります。

## エラーの概要

一覧では待機中の理由として表示されます。再起動の回数は増えません。[コンテナ](/glossary/コンテナ/)が一度も起動していないためです。

```text
NAME                    READY   STATUS             RESTARTS   AGE
my-app-6c4d8f9b5-2xq7w  0/1     ImagePullBackOff   0          4m12s
```

詳細を見ると、最初の失敗と、その後の待機が別々に記録されています。

```text
Events:
  Type     Reason     Age                  From     Message
  ----     ------     ----                 ----     -------
  Normal   Pulling    4m (x4 over 5m)      kubelet  Pulling image "example/my-app:1.0"
  Warning  Failed     3m (x4 over 5m)      kubelet  Failed to pull image "example/my-app:1.0": ...
  Warning  Failed     3m (x4 over 5m)      kubelet  Error: ErrImagePull
  Normal   BackOff    30s (x12 over 4m)    kubelet  Back-off pulling image "example/my-app:1.0"
  Warning  Failed     30s (x12 over 4m)    kubelet  Error: ImagePullBackOff
```

読むべきは、上から2行目の末尾です。ここに、取得を担う仕組みが返した文言がそのまま入ります。名前が見つからない、資格が無い、回数の上限に達した、といった内容が、その置き場の言葉で書かれています。ImagePullBackOff という表示だけを見ていても、この文言には辿り着きません。

## まず最初に：5つの状態名のどれかを見る

第一に、表示されている状態名を確認します。`InvalidImageName` なら名前の書式そのものが解釈できていないので、置き場に問い合わせる前の段階です。`ErrImageNeverPull` なら取得しない方針なのに手元に無い状態で、置き場とは無関係です。この2つは、原因が手元の記述に限定されます。

第二に、`ErrImagePull` または `ImagePullBackOff` であれば、置き場との[通信](/glossary/通信/)は行われています。この場合、失敗の詳細は前述の文言に入っています。

第三に、その文言を取り出します。ここから先の切り分けは、すべてこの文言に依存します。

```bash
kubectl describe pod <ポッド名> | grep -A3 "Failed to pull image"
```

## よくある原因と解決手順

### 原因1：名前やタグが存在しない

最も多い形です。文言には、指定された対象が見つからない旨が入ります。書き間違いのほか、[タグ](/glossary/タグ/)を消したあとに古い記述が残っている場合もあります。

まず、手元から同じ名前で取得できるかを確かめます。

```bash
docker pull example/my-app:1.0
```

ここで失敗するなら、原因は [Kubernetes](/glossary/kubernetes/) 側ではありません。存在する[タグ](/glossary/タグ/)の一覧を置き場で確認してください。

**Before（存在しない[タグ](/glossary/タグ/)を指定している）：**

```yaml
containers:
  - name: my-app
    image: example/my-app:1.0.0
```

**After（実在する[タグ](/glossary/タグ/)を指定する）：**

```yaml
containers:
  - name: my-app
    image: example/my-app:1.0
```

なお、名前の書式自体が壊れている場合は、状態名が `InvalidImageName` になります。大文字を含む、記号の位置がおかしいといった場合です。この状態名が出ていたら、置き場を調べる必要はありません。記述だけを見てください。

### 原因2：非公開の置き場に資格情報が渡っていない

文言に、資格が無い、あるいは取得の許可が無い、という内容が入ります。公開されていない対象を指しているのに、資格情報を渡していない状態です。

**Before（資格情報を渡していない）：**

```yaml
spec:
  containers:
    - name: my-app
      image: registry.example.com/my-app:1.0
```

**After（資格情報を渡す）：**

```bash
kubectl create secret docker-registry my-registry-secret \
  --docker-server=registry.example.com \
  --docker-username=<利用者名> \
  --docker-password=<パスワード>
```

```yaml
spec:
  imagePullSecrets:
    - name: my-registry-secret
  containers:
    - name: my-app
      image: registry.example.com/my-app:1.0
```

設定したのに変わらない場合は、置き場所を確認してください。この秘密情報は、対象と同じ区画に置く必要があります。別の区画にあるものは参照できません。

```bash
kubectl get secret my-registry-secret -n <区画名>
```

また、実行の主体に既定で紐づける方法もあります。多数の対象がある場合は、そちらのほうが漏れが起きにくくなります。

### 原因3：取得の回数の上限に当たっている

文言に、要求が多すぎる旨が入ります。公開の置き場には、一定時間あたりの取得回数に上限があるためです。同じ場所から多数の対象を同時に起動したときや、毎回取得する方針になっているときに当たりやすくなります。

この形の特徴は、時間を置くと通ることです。恒久的な対処は3つあります。資格情報を設定して上限を引き上げる、控えの置き場を用意する、そして毎回取得しない方針にすることです。

```yaml
containers:
  - name: my-app
    image: example/my-app:1.0
    imagePullPolicy: IfNotPresent
```

前述のとおり、[タグ](/glossary/タグ/)を書かないと毎回取得になります。上限に当たりやすい[環境](/glossary/環境/)では、[タグ](/glossary/タグ/)を明示するだけでも回数が減ります。制限そのものの詳しい仕組みは、置き場側の記事も参照してください（[Docker の 429 の記事](/posts/docker_429/)）。

### 原因4：土台の種類が合っていない

文言に、対応する構成が見つからない旨が入ります。取得しようとしている対象が、実行する機器の種類に対応していない状態です。

複数の種類に対応した対象であれば起きませんが、片方の種類でしか作られていない対象を、別の種類の機器で動かそうとすると失敗します。

まず、機器の種類を確認します。

```bash
kubectl get nodes -o custom-columns='NAME:.metadata.name,ARCH:.status.nodeInfo.architecture'
```

対象がどの種類に対応しているかは、置き場側で確認できます。対応していない場合、対象を作り直すか、対応する機器に配置を限定するかのどちらかになります。

```yaml
spec:
  nodeSelector:
    kubernetes.io/arch: amd64
```

### 原因5：取得しない方針なのに手元に無い

状態名が `ErrImageNeverPull` の場合です。取得を行わない方針にしているのに、実行する機器の手元に対象が存在しません。

この方針は、あらかじめ各機器に配っておく運用を前提としています。配布が済んでいない機器に配置されると、この状態になります。

対処は2つです。配布を確実にするか、方針を変えて取得を許すかです。一部の機器にしか無い場合は、配置先を限定する方法もあります。この状態名が出ている限り、置き場や資格情報を調べても意味がありません。取得を試みてすらいないためです。

## 補足：似ているが別のもの

[コンテナ](/glossary/コンテナ/)が起動したあとに落ちている場合は、別の状態になります。取得は成功しているので、調べる対象も別です（[Kubernetes の CrashLoopBackOff の記事](/posts/kubernetes_crashloopbackoff/)）。待ち時間の値は同じですが、記録は独立しています。

配置そのものができていない場合は、[コンテナ](/glossary/コンテナ/)の状態以前の問題です。取得の失敗ではないので、状態名も違います。

利用者向けの[通信](/glossary/通信/)が失敗している場合は、状態[コード](/glossary/コード/)として現れます。転送先が1つも無ければ 503 です（[Kubernetes の 503 の記事](/posts/kubernetes_503/)）。取得に失敗し続けている対象は、準備完了と判定されないため転送先に入りません。

置き場側が返す状態[コード](/glossary/コード/)を直接調べたい場合は、置き場の記事を参照してください。取得の失敗は、置き場から見れば 404 や 401、429 として記録されています。

## 切り分けの順序

1. 状態名を確認する。`InvalidImageName` と `ErrImageNeverPull` なら、置き場を調べる必要はない。
2. `ErrImagePull` または `ImagePullBackOff` なら、詳細の文言を取り出す。ここから先はすべてこの文言に依存する。
3. 手元から同じ名前で取得できるかを試す。失敗するなら [Kubernetes](/glossary/kubernetes/) 側の問題ではない。
4. 資格の不足を示す文言なら、秘密情報の有無と、それが対象と同じ区画にあるかを確認する。
5. 要求が多すぎる旨なら、時間を置いて再確認する。恒久策は資格情報の設定か方針の変更。
6. 対応する構成が無い旨なら、機器の種類と対象の対応を突き合わせる。
7. 直したあとは、待ち時間を飛ばすために対象を作り直す。最大で5分待つ仕組みになっている。

## 確認コマンド集

```bash
# 1. 状態名と詳細の文言をまとめて取り出す
kubectl describe pod <ポッド名> | sed -n '/Events:/,$p'

# 2. 状態名だけを取り出す
kubectl get pod <ポッド名> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{"  "}{.state.waiting.reason}{"  "}{.state.waiting.message}{"\n"}{end}'

# 3. 手元から同じ名前で取得できるかを試す
docker pull <対象の名前>

# 4. 資格情報の有無と置き場所を確認する
kubectl get secret -n <区画名> | grep docker
kubectl get pod <ポッド名> -o jsonpath='{.spec.imagePullSecrets}'

# 5. 機器の種類を確認する
kubectl get nodes -o custom-columns='NAME:.metadata.name,ARCH:.status.nodeInfo.architecture'

# 6. 取得の方針を確認する（書いていない場合の既定値に注意）
kubectl get pod <ポッド名> \
  -o jsonpath='{range .spec.containers[*]}{.name}{"  "}{.image}{"  "}{.imagePullPolicy}{"\n"}{end}'

# 7. 直したあと、待ち時間を飛ばして確かめる
kubectl delete pod <ポッド名>
```

## Editor's Note

この状態のいちばん厄介な性質は、失敗し続けても何も起きないことです。本体に登録された要望が、その問題をそのまま述べています（[A mechanism to fail a Pod that is stuck due to an invalid Image](https://github.com/kubernetes/kubernetes/issues/122300)）。

2023年12月の投稿で、求められているのは、取得の失敗が一定回数を超えたときに対象を失敗の状態へ移す仕組みです。現状では待機中の扱いのまま留まり続ける、と書かれています。

投稿者が挙げている状況が具体的です。順番待ちの仕組みを通して処理を投入する[環境](/glossary/環境/)では、投入から実際に動き出すまでに数時間から数日かかることがあります。その場合、名前を書き間違えていたとしても、投入した本人が気付くのは手遅れになってからです。さらに、これらの対象は資源を確保したまま残るため、他の待機中の処理が始められなくなります。そして、管理する側の仕組みは、対象が実際に失敗の状態で終了して初めて後処理を行うため、待機中のままでは何もできません。

つまり、この状態は静かに資源を握り続けます。落ちて再起動を繰り返す状態は、回数が増えるので目に付きます。取得に失敗し続ける状態は、回数が増えません。一覧を眺めていても、変化が無いように見えます。

だからこそ、監視の対象に入れておく価値があります。待機中の理由が一定時間以上変わらない対象を検出する、という単純な仕組みで足ります。標準では誰も気付いてくれない、という前提で組んでください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*