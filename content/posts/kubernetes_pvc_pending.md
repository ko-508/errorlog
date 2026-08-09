---
title: "Kubernetes の PVC が Pending：原因と解決策"
date: 2026-08-07
description: "PVC の Pending は原因の名前ではなく、割り当てがまだ済んでいないという事実だけを表します。この記事が扱うのは原因の一覧ではなく、理由がどこに書いてあるかの読み方です。制御プログラムは未結合の要求を3つの経路に振り分けており、その振り分け先が Events の Reason にそのまま出ます。Reason を1語読むだけで、調査範囲がほぼ確定します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_pvc_pending.png"]
errorCode: "Pending"
lastmod: 2026-08-07
service: "Kubernetes"
error_type: "Pending"
components: ["PersistentVolume Controller", "Scheduler"]
related_services: ["kube-controller-manager", "kube-scheduler", "CSI"]
trend_incident: false
---

## 冒頭まとめ

PVC（PersistentVolumeClaim、[ストレージ](/glossary/ストレージ/)の割り当てを求める[オブジェクト](/glossary/オブジェクト/)）が Pending のままになったとき、まず[容量](/glossary/容量/)や[設定ファイル](/glossary/設定ファイル/)を読み返す人が多くいます。順序としては後回しでかまいません。先に読むべきなのは `kubectl describe pvc` の Events に出る Reason の1語です。

理由は実装にあります。[Kubernetes](/glossary/kubernetes/) の制御側は、未結合の要求を1か所で3つの経路に振り分けています。結合を遅らせる設定で誰も使っていない場合、[クラス](/glossary/クラス/)名が指定されていて動的な作成に進む場合、そのどちらでもない場合です。この3分岐がそのまま Reason になるため、Reason を見れば自分がどの経路にいるかが確定します。

分かれ方は5通りです。`WaitForFirstConsumer` と `WaitForPodScheduled` は待機、`ExternalProvisioning` と `ProvisioningFailed` は動的な作成、`FailedBinding` は既存の領域との突き合わせで、それぞれ直す場所が違います。

最も見落とされるのが2番目です。`WaitForPodScheduled` が出ているなら、待たせているのは PVC ではありません。それを使う Pod が配置できずに止まっています。PVC の定義を読み直しても原因は出てきません。

`WaitForFirstConsumer` も異常ではありません。公式ドキュメントは、この設定が Pod ができるまで結合と作成を意図的に遅らせるものだと説明しています。Pending の表示だけを見て設定を書き換えると、かえって配置できない Pod を作ることになります。

## エラーの概要

一覧では、状態が Pending のまま止まり、割り当て先の欄が空になります。

```text
NAME       STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
data-pvc   Pending                                      standard       6m41s
```

この Pending は、実装では要求の段階を表す3つの値のうちの1つです。`Pending`（まだ結合されていない）、`Bound`（結合済み）、`Lost`（結合していた領域が失われた）の3つが定義されています。つまり Pending 自体は失敗ではなく、結合がまだ済んでいないという事実だけを示します。

理由は Events に出ます。表示例は次のようになります。

```text
Events:
  Type    Reason                Age                From                         Message
  ----    ------                ----               ----                         -------
  Normal  WaitForFirstConsumer  20s (x6 over 87s)  persistentvolume-controller  waiting for first consumer to be created before binding
```

出所は `persistentvolume-controller` です。この[コード](/glossary/コード/)は未結合の要求を3つに振り分けます。第一に、結合を遅らせる設定で、まだ配置の判断が渡ってきていない場合。第二に、[クラス](/glossary/クラス/)名が空でない場合。第三に、そのどちらでもない場合です。1番目からは `WaitForFirstConsumer` または `WaitForPodScheduled`、2番目からは `ExternalProvisioning`・`ProvisioningFailed`・`ProvisioningSucceeded`、3番目からは `FailedBinding` が出ます。

3番目の文言は固定です。

```text
no persistent volumes available for this claim and no storage class is set
```

この文が出ているなら、動的な作成は一切試みられていません。既存の領域との突き合わせだけが行われ、条件に合うものが無かったという意味です。

## まず最初に：Reason を1語だけ見る

推測する前に、Reason を取り出します。

```bash
kubectl describe pvc <要求名> -n <区画名> | sed -n '/^Events:/,$p'
```

出てきた語で、そこから先の調べ方が決まります。`WaitForFirstConsumer` なら原因1、`WaitForPodScheduled` なら原因2、`ExternalProvisioning` なら原因3、`ProvisioningFailed` なら原因4、`FailedBinding` なら原因5です。

Events が空のこともあります。[イベント](/glossary/イベント/)は既定で一定時間後に消えるため、時間の経った要求には何も残りません。その場合は、指定している[クラス](/glossary/クラス/)の結合の設定を先に確認します。

```bash
kubectl get sc <クラス名> -o jsonpath='{.volumeBindingMode}{"\n"}{.provisioner}{"\n"}'
```

`WaitForFirstConsumer` が返れば待機の系統、`Immediate` が返れば作成か突き合わせの系統です。

## よくある原因と解決手順

### 原因1：結合を遅らせる設定で、使う相手がまだいない

`WaitForFirstConsumer` は、公式ドキュメントに書かれたとおりの動きです。この設定は、PVC を使う Pod ができるまで結合と作成を遅らせます。目的は、置ける場所が限られる[ストレージ](/glossary/ストレージ/)で、Pod の配置条件を知らないまま先に割り当ててしまい、結果として置き場所の無い Pod ができることを防ぐことにあります。

この Reason が出ている間は何も壊れていません。PVC を使う Pod を作れば先へ進みます。Pod を作っても変わらないなら、Reason は原因2の語に変わっているはずです。

**Before（待機を異常と判断して設定を書き換える）：**

```yaml
volumeBindingMode: Immediate
```

**After（設定は変えず、要求を使う相手を作る）：**

```yaml
spec:
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: data-pvc
```

`Immediate` に変えると、配置の条件を無視して先に割り当てが決まります。置ける場所が限られる構成では、その割り当てのせいで Pod が配置できなくなります。

### 原因2：使う Pod のほうが配置できずに止まっている

`WaitForPodScheduled` が出ている場合、要求を使う Pod は既に存在します。制御側はその Pod を見つけたうえで、配置が決まるのを待っています。文言には対象の名前が入ります。

```text
  Normal  WaitForPodScheduled  5s  persistentvolume-controller  waiting for pod pod-0 to be scheduled
```

複数の Pod が同じ要求を参照している場合は、名前が並びます。この Reason が出ているなら、調べる先は Pod です。

**Before（PVC の定義を読み直す）：**

```bash
kubectl describe pvc data-pvc -n app
```

**After（止まっている Pod の理由を読む）：**

```bash
kubectl describe pod pod-0 -n app | sed -n '/^Events:/,$p'
```

Pod 側には配置できない理由が出ます。[ストレージ](/glossary/ストレージ/)に関する理由は実装に定義されていて、条件に合う領域が見つからない（`node(s) didn't find available persistent volumes to bind`）、領域が指定する置き場所の条件に合わない（`node(s) didn't match PersistentVolume's node affinity`）、空き[容量](/glossary/容量/)が足りない（`node(s) did not have enough free storage`）、結合先の領域が存在しない（`node(s) unavailable due to one or more pvc(s) bound to non-existent pv(s)`）の4つがあります。資源不足や条件不一致といった[ストレージ](/glossary/ストレージ/)と無関係な理由で止まっていることも珍しくありません。

### 原因3：作成を担う仕組みが動いていない、または名前が違う

`ExternalProvisioning` が出続ける場合です。文言は次の形で、名前の部分に指定した作成担当が入ります。

```text
Waiting for a volume to be created either by the external provisioner 'ebs.csi.aws.com' or manually by the system administrator.
If volume creation is delayed, please verify that the provisioner is running and correctly registered.
```

ここに注意点があります。制御側は、名前が `kubernetes.io/` で始まらない場合、それを外部の担当とみなして[エラー](/glossary/エラー/)を出しません。つまり名前を打ち間違えても、存在しない担当を待ち続けるだけで、失敗の記録は残りません。この Reason が繰り返し出ているのに何も起きないなら、疑うのは名前の綴りと、担当する[コンテナ](/glossary/コンテナ/)が動いているかどうかです。

**Before（名前を確かめずに待つ）：**

```bash
kubectl get pvc data-pvc -n app
```

**After（指定名と、動いている担当を突き合わせる）：**

```bash
kubectl get sc <クラス名> -o jsonpath='{.provisioner}{"\n"}'
kubectl get csidrivers
```

`csidrivers` の一覧に無い名前を指定していれば、それが原因です。一覧にあるのに進まない場合は、担当する[コンテナ](/glossary/コンテナ/)の記録を確認します。

### 原因4：作成を試みて失敗している

`ProvisioningFailed` は、担当が動いたうえで失敗した場合です。Warning として記録され、文言に理由がそのまま入ります。指定した[クラス](/glossary/クラス/)が存在しない場合もここに入り、`storageclass.storage.k8s.io "xxx" not found` の形で出ます。

内容は担当ごとに違います。多いのは、[権限](/glossary/権限/)が足りない、指定した[容量](/glossary/容量/)が下限や上限から外れている、指定した置き場所に空きが無い、の3系統です。

**Before（存在しない[クラス](/glossary/クラス/)を指定している）：**

```yaml
spec:
  storageClassName: gp3-encrypted
```

**After（実在する[クラス](/glossary/クラス/)名に合わせる）：**

```bash
kubectl get sc
```

一覧に出た名前へ書き換えます。ただし PVC の `storageClassName` は作成後に変更できないため、書き換えるには作り直しが必要です。

### 原因5：既存の領域と条件が合っていない

`FailedBinding` は、動的な作成を行わずに既存の PV（PersistentVolume、実際の保管領域を表す[オブジェクト](/glossary/オブジェクト/)）を探した結果です。突き合わせの規則は実装に書かれており、順に適用されます。

まず、別の要求と結び付いている領域は除外されます。次に、[容量](/glossary/容量/)が要求未満のものが除外されます。ここは誤解されやすい点で、[容量](/glossary/容量/)は一致している必要がありません。要求以上であれば成立し、残ったもののうち最も小さいものが選ばれます。続いて利用の形式が違うもの、削除待ちのもの、状態が `Available` でないもの、指定した条件にラベルが合わないもの、[クラス](/glossary/クラス/)名が一致しないものが除外されます。

見落としが多いのは状態の条件です。保持の方針で解放された領域は `Released` になり、元の要求への参照が残ります。この2点により突き合わせの対象から外れるため、一覧に見えていても新しい要求には使われません。公式ドキュメントも、解放された領域は前の利用者のデータが残っているため他の要求には使えない、と明記しています。

**Before（解放済みの領域が使われることを期待する）：**

```bash
kubectl get pv
# -> STATUS が Released のまま
```

**After（参照を外して再び選ばれる状態に戻す）：**

```bash
kubectl patch pv <領域名> -p '{"spec":{"claimRef": null}}'
```

中身が残ったままの領域を再び使う操作なので、前の利用者のデータが残っている点を承知したうえで行ってください。

もう1つ、[クラス](/glossary/クラス/)名の扱いにも規則があります。空文字を明示した要求は「[クラス](/glossary/クラス/)無し」を求めるものとして扱われ、同じく[クラス](/glossary/クラス/)無しの領域としか結合しません。未指定は別扱いで、既定の[クラス](/glossary/クラス/)があればそれが使われます。既定が無い時期に未指定で作った要求は、作り直す必要がありません。後から既定を用意すれば、制御側が未指定の要求を見つけて設定します。この遡及の動きは v1.28 で安定版になりました。ただし空文字を明示した要求は対象外です。

## 補足：似ているが別のもの

Pod が Pending の場合は別の[コード](/glossary/コード/)が担当します。要求が結合されていないことが Pod の停止として現れているだけのこともあり、その場合は本記事の系統に戻ってきます（[Kubernetes の Pending の記事](/posts/kubernetes_pending/)）。

Pod 側に `pod has unbound immediate PersistentVolumeClaims` が出る場合は、結合の設定が `Immediate` で、まだ結合が終わっていないという意味です。この文言が出ている間は、配置の判断そのものが行われません。

要求の状態が `Lost` の場合は Pending とは違います。一度は結合していた領域が失われた状態で、データが残っていないことを示します。

区画ごとの上限に当たっている場合は、そもそも要求を作れません。作成の時点で拒否されるため、Pending にはならず[コマンド](/glossary/コマンド/)が失敗します。

[容量](/glossary/容量/)の変更で止まっている場合も別です。結合済みの要求を大きくする操作は拡張として扱われ、[クラス](/glossary/クラス/)側で許可されている必要があります。縮小はできません。

## 切り分けの順序

1. `kubectl describe pvc` の Events から Reason を取り出す。ここで系統が決まる。
2. `WaitForFirstConsumer` なら、要求を使う Pod があるかを確認する。無ければ作る。
3. `WaitForPodScheduled` なら、PVC の調査を止めて Pod 側の記録を読む。
4. `ExternalProvisioning` が繰り返し出ているなら、指定名と動いている担当の一覧を突き合わせる。
5. `ProvisioningFailed` なら、Warning の文言をそのまま読む。理由は文言に含まれている。
6. `FailedBinding` なら、既存の領域を一覧し、[容量](/glossary/容量/)・利用の形式・[クラス](/glossary/クラス/)名・状態の4点を順に照らす。
7. Events が空なら、指定している[クラス](/glossary/クラス/)の結合の設定と作成担当の名前を確認する。
8. それでも決まらない場合は、制御側の記録を要求名で絞り込む。

## 確認コマンド集

```bash
# 1. 状態と結合先を一覧で確認する（VOLUME 欄が空なら未結合）
kubectl get pvc -n <区画名>

# 2. Events から Reason を取り出す（最初に行う）
kubectl describe pvc <要求名> -n <区画名> | sed -n '/^Events:/,$p'

# 3. 指定しているクラスの結合の設定と作成担当を確認する
kubectl get sc <クラス名> -o jsonpath='{.volumeBindingMode}{"\n"}{.provisioner}{"\n"}'

# 4. 既定として印が付いているクラスを探す
kubectl get sc -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.annotations.storageclass\.kubernetes\.io/is-default-class}{"\n"}{end}'

# 5. 動いている作成担当の一覧を出す（3 の名前と突き合わせる）
kubectl get csidrivers

# 6. 既存の領域を、突き合わせに使う4項目だけ抜き出して並べる
kubectl get pv -o custom-columns='NAME:.metadata.name,CAP:.spec.capacity.storage,MODE:.spec.volumeMode,CLASS:.spec.storageClassName,STATUS:.status.phase'

# 7. 要求を参照している Pod を探す（WaitForPodScheduled のとき）
kubectl get pod -n <区画名> -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes[*].persistentVolumeClaim.claimName}{"\n"}{end}'

# 8. 制御側の記録を要求名で絞り込む
kubectl logs -n kube-system -l component=kube-controller-manager --tail=200 | grep <要求名>
```

## Editor's Note

Reason の1語が決め手になるという読み方は、後から補われたものです。その経緯が [kubernetes/kubernetes の Issue #88229](https://github.com/kubernetes/kubernetes/issues/88229) に残っています。2020年2月17日に開かれ、既に閉じられています。

報告の内容はこうです。結合を遅らせる設定を使っていて、PVC が結合されない。Pod 側には条件に合う領域が見つからないという明確な記録が出ているのに、PVC 側には「最初の利用者ができるのを待っている」という文言しか出ない。しかし Pod は既に存在している。実際の理由は、指定した[クラス](/glossary/クラス/)が動的な作成を行わない設定で、条件に合う既存の領域も無かったことでした。

報告者が求めたのは、Pod 側と同じ内容を PVC 側にも出すことです。この報告を受けて出された変更（[Pull Request #91455](https://github.com/kubernetes/kubernetes/pull/91455)）が、`WaitForPodScheduled` を追加しました。要求を参照する Pod が見つかった場合には、待機の文言を「その Pod の配置を待っている」に切り替えるという内容です。変更の説明には、対象が1つの場合と2つの場合の表示例が並べて示されています。

つまり `WaitForFirstConsumer` と `WaitForPodScheduled` の違いは、あとから意図的に作られた区別です。前者は使う相手がまだいない状態、後者は相手はいるが配置が決まらない状態を指します。この2語を見分けるだけで、PVC を調べるべきか Pod を調べるべきかが決まります。Pending という表示そのものには、その情報が入っていません。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*