---
title: "Kubernetes の ErrImagePull：原因と解決策"
date: 2026-08-07
description: "この記事が扱うのは取得失敗の原因一覧ではなく、ErrImagePull と ImagePullBackOff がどう違うのかです。2つは原因の違いではなく、同じ失敗を時間軸の別の地点から呼んだ名前です。しかも ErrImagePull は分類できなかった残り全部を指す名前なので、原因はメッセージ本文にしかありません。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_errimagepull.png"]
errorCode: "ErrImagePull"
lastmod: 2026-08-07
service: "Kubernetes"
error_type: "ErrImagePull"
components: ["kubelet", "CRI"]
related_services: ["Container Registry", "containerd"]
trend_incident: false
---

## 冒頭まとめ

同じ Pod を見ているのに、表示が `ErrImagePull` になったり `ImagePullBackOff` になったりする。この入れ替わりを原因の変化だと受け取ると、調べる方向を誤ります。

2つは原因の違いではありません。同じ失敗を、時間軸の別の地点から呼んだ名前です。kubelet は取得を求められると、まず待機の途中かどうかを確かめます。待機中なら取得を行わず `ImagePullBackOff` を返します。待機が明けていれば実際に取得を試み、失敗したときに `ErrImagePull` を返します。つまり前者は次の試行を待っている時間帯、後者は試して失敗した瞬間です。

したがって、どちらが表示されているかは原因を何も語りません。実際、この入れ替わりは利用者にとって分かりにくいと開発側も認めており、待機中の表示に前回の失敗理由を残す変更が v1.32 で入りました。

もう1つ、名前そのものの意味も押さえてください。`ErrImagePull` は取得失敗の総称ではありません。実装は[レジストリ](/glossary/レジストリ/)に届かない場合と署名の検証に失敗した場合を先に切り分け、そのどちらでもない残り全部を `ErrImagePull` にしています。分類できなかった、という意味の名前です。

だから原因は名前ではなくメッセージ本文にあります。実際に取得を試みた瞬間に出る警告の[イベント](/glossary/イベント/)だけが、[コンテナ](/glossary/コンテナ/)の実行基盤が返した文言をそのまま載せています。ここを取り逃がすと、手がかりが無くなります。

## エラーの概要

`kubectl describe pod` の[イベント](/glossary/イベント/)は、失敗が続くと次の並びになります。

```text
Normal   Pulling  2m    kubelet  Pulling image "example.com/app:v1"
Warning  Failed   2m    kubelet  Failed to pull image "example.com/app:v1": rpc error: code = NotFound desc = ...
Warning  Failed   2m    kubelet  Error: ErrImagePull
Normal   BackOff  95s   kubelet  Back-off pulling image "example.com/app:v1"
Warning  Failed   95s   kubelet  Error: ImagePullBackOff
```

`Failed` という理由が2行出ますが、意味が違います。1行目は実際に取得を試みて返ってきた文言で、原因はここにしかありません。2行目は状態の名前を告げているだけです。この違いは実装の作りから来ています。取得の失敗は `Failed to pull image %q: %v` の形で記録され、状態の名前は別の箇所から `Error: %v` の形で記録されます。

待機の[イベント](/glossary/イベント/)は理由が `BackOff` で、種別は警告ではなく通常です。並びの中で警告が付いている行だけを追えば、読むべき場所が絞れます。

待ち時間の決まり方も実装で決まっています。[イメージ](/glossary/イメージ/)の取得には専用の[バックオフ](/glossary/バックオフ/)が用意されており、初回は10秒、上限は300秒です。[コンテナ](/glossary/コンテナ/)の再起動とは別に管理されています。

回数を数えるときも、この区別が効きます。理由が `Pulling` の[イベント](/glossary/イベント/)は、実際に取得を始めた回数です。理由が `BackOff` の[イベント](/glossary/イベント/)は、待機のまま見送った回数にすぎません。両方を合わせて数えると、実際の試行回数を大きく見誤ります。

待機の記録は Pod と[イメージ](/glossary/イメージ/)の組を鍵にして持たれます。同じ Pod の中で複数の[コンテナ](/glossary/コンテナ/)が同じ[イメージ](/glossary/イメージ/)を指していれば、待機は共有されます。

Pod の状態にも同じ情報が入ります。待機の理由と本文が `status.containerStatuses[*].state.waiting` に置かれ、理由には状態の名前、本文には詳細が入ります。

## まず最初に：警告の行から本文を取り出す

推測の前に、詳細を載せた行だけを取り出します。

```bash
kubectl describe pod <対象> -n <区画名> | grep -A2 "Failed to pull image"
```

[イベント](/glossary/イベント/)が消えている場合は、Pod の状態から取ります。v1.32 以降なら、待機中でも前回の理由が本文の末尾に連結されています。

```bash
kubectl get pod <対象> -n <区画名> \
  -o jsonpath='{.status.containerStatuses[*].state.waiting.message}{"\n"}'
```

取り出した本文の中身で、次に見る場所が決まります。名前が見つからない、認証が通らない、回数の上限に当たっている、といった区別はすべてこの文言に書かれています。原因ごとの対処は別記事にまとめてあります（[Kubernetes の ImagePullBackOff の記事](/posts/kubernetes_imagepullbackoff/)）。

## よくある原因と解決手順

### 原因1：一覧の表示だけを見て、入れ替わりに気づいていない

`kubectl get pod` の状態欄は、同じ失敗が続いていても表示が入れ替わります。取得を試みた直後は取得の失敗を表す名前、待機に入ると `ImagePullBackOff` です。開発側もこの点を、利用者にとって分かりにくい挙動だと述べています。

対処は、一覧ではなく[イベント](/glossary/イベント/)か状態の本文を見ることです。表示が変わっても、本文の内容は変わりません。

**Before（状態欄の変化を追う）：**

```bash
watch kubectl get pod -n app
```

**After（本文を直接取り出す）：**

```bash
kubectl get pod -n app \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[*].state.waiting.message}{"\n"}{end}'
```

### 原因2：待機中の表示に理由が入らない版を使っている

v1.31 以前では、待機中の本文は `Back-off pulling image "..."` だけでした。詳細は取得を試みた瞬間の[イベント](/glossary/イベント/)にしか無く、[イベント](/glossary/イベント/)が消えると追えなくなります。

v1.32 で入った変更により、前回の失敗理由が本文の末尾に連結されるようになりました。実装では、`imageManager` が `sync.Map` の `prevPullErrMsg` に前回の理由を保存します。取得に失敗した時点で Pod UID とイメージから作った `backOffKey` に理由を `Store` し、待機中は同じキーで `Load` して本文へ付け足します。控えた内容は、次に実際の取得を始める直前に `Delete` されます。

**Before（待機中の本文だけを見て諦める）：**

```text
Back-off pulling image "example.com/app:v1"
```

**After（v1.32 以降では理由が続く）：**

```text
Back-off pulling image "example.com/app:v1": ErrImagePull: rpc error: code = NotFound desc = ...
```

古い版を使っていて[イベント](/glossary/イベント/)も消えている場合は、Pod を作り直して最初の取得をやり直させるのが確実です。作り直した直後の警告に、必要な文言が出ます。

### 原因3：イベントが期限切れで消えている

[イベント](/glossary/イベント/)は永久には残りません。保持時間の既定値は1時間です。夜間に始まった失敗を翌朝に調べると、詳細を載せた行が消えている、という状況が起きます。

待機は上限の300秒で繰り返されるため、状態の表示だけは残り続けます。表示があるのに詳細が無い、という食い違いはここから来ます。

**Before（時間が経ってから describe する）：**

```bash
kubectl describe pod <対象> -n app
```

**After（消えない場所から取る）：**

```bash
kubectl get pod <対象> -n app -o yaml | grep -A3 "waiting:"
kubectl get events -n app --field-selector reason=Failed --sort-by=.lastTimestamp
```

### 原因4：ErrImagePull ではなく、より具体的な名前が出ている

実装は、実行基盤が返したエラーの先頭を見て2つを切り分けます。`RegistryUnavailable` で始まれば[レジストリ](/glossary/レジストリ/)に届いていないという意味の名前になり、本文も「[レジストリ](/glossary/レジストリ/)に到達できないため取得に失敗した」という文に書き換えられます。`SignatureValidationFailed` で始まれば署名の検証に失敗したという名前になります。

どちらでもない残り全部が `ErrImagePull` です。したがって、状態欄に `ErrImagePull` 以外の名前が出ているなら、その時点で範囲がかなり絞れています。逆に `ErrImagePull` が出ているときは、名前から得られる情報はありません。

なお取得そのものに入る前に弾かれる場合は、また別の名前になります。名前を解釈できない場合、[イメージ](/glossary/イメージ/)を調べられない場合、取得しない方針なのに手元に無い場合の3つで、いずれも[レジストリ](/glossary/レジストリ/)との[通信](/glossary/通信/)は行われていません。

**Before（すべてを取得失敗として一括で扱う）：**

```bash
kubectl get pod -n app | grep -E "ErrImagePull|ImagePullBackOff"
```

**After（状態の名前を正確に取り出す）：**

```bash
kubectl get pod -n app \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[*].state.waiting.reason}{"\n"}{end}'
```

### 原因5：直したのに反映されないように見えている

[レジストリ](/glossary/レジストリ/)側や資格情報を直したのに状態が変わらない、という場合です。多くは失敗ではなく待機です。待ち時間は失敗のたびに倍に伸び、上限の300秒に達します。直した直後に見ても、次の試行までは最大で5分待つことになります。

待機の記録は Pod と[イメージ](/glossary/イメージ/)の組ごとに持たれます。したがって Pod を作り直せば記録は引き継がれず、すぐに取得が試みられます。急ぐ場合はこちらが確実です。

**Before（直したあと同じ Pod を見続ける）：**

```bash
kubectl get pod <対象> -n app -w
```

**After（待機の記録ごと作り直す）：**

```bash
kubectl delete pod <対象> -n app
```

管理下の Pod なら削除すれば作り直されます。単体で作った Pod の場合は、削除後に自分で作り直してください。

## 補足：似ているが別のもの

原因ごとの対処は別記事にまとめてあります。名前や[タグ](/glossary/タグ/)が存在しない場合、非公開の置き場に資格情報が渡っていない場合、取得回数の上限、土台の種類の不一致などです（[Kubernetes の ImagePullBackOff の記事](/posts/kubernetes_imagepullbackoff/)）。

`CreateContainerConfigError` は取得より後の段階です。[イメージ](/glossary/イメージ/)は手に入っており、[コンテナ](/glossary/コンテナ/)の設定を組み立てる時点で止まっています（[Kubernetes の CreateContainerConfigError の記事](/posts/kubernetes_createcontainerconfigerror/)）。

`CrashLoopBackOff` は起動した後の話です。名前に `BackOff` が付くため混同されますが、待機の記録は別に管理されており、値が同じでも別物です（[Kubernetes の CrashLoopBackOff の記事](/posts/kubernetes_crashloopbackoff/)）。

Pod が `Pending` のまま止まっている場合は、そもそも取得の段階に入っていません（[Kubernetes の Pending の記事](/posts/kubernetes_pending/)）。

## 切り分けの順序

1. `kubectl get pod` の表示は入れ替わるものとして扱い、それだけで判断しない。
2. `kubectl describe pod` の[イベント](/glossary/イベント/)から、警告が付いている行だけを拾う。
3. `Failed to pull image` で始まる行を探す。原因はこの行の本文にある。
4. その行が無ければ、Pod の状態の待機の本文を見る。v1.32 以降なら理由が連結されている。
5. どちらも無ければ[イベント](/glossary/イベント/)が期限切れの可能性を疑う。既定の保持時間は1時間。
6. 状態の名前を正確に読む。`ErrImagePull` 以外なら、その時点で範囲が絞れている。
7. 本文の内容に応じて、名前・資格情報・回数の上限・土台の種類のどれかへ進む。
8. 直したあとは、待機が最大300秒続くことを踏まえる。急ぐなら Pod を作り直す。

## 確認コマンド集

```bash
# 1. 詳細を載せた行だけを取り出す（最初に行う）
kubectl describe pod <対象> -n <区画名> | grep -A2 "Failed to pull image"

# 2. 状態の名前と本文を、消えない場所から取る
kubectl get pod <対象> -n <区画名> \
  -o jsonpath='{.status.containerStatuses[*].state.waiting.reason}{"\t"}{.status.containerStatuses[*].state.waiting.message}{"\n"}'

# 3. 区画内でこの状態にあるものをまとめて拾う
kubectl get pod -n <区画名> \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[*].state.waiting.reason}{"\n"}{end}'

# 4. 取得の失敗イベントだけを時系列で見る
kubectl get events -n <区画名> --field-selector reason=Failed --sort-by=.lastTimestamp

# 5. 待機のイベントを見て、繰り返しの回数と間隔を把握する
kubectl get events -n <区画名> --field-selector reason=BackOff --sort-by=.lastTimestamp

# 6. 指定されているイメージと取得の方針を確認する
kubectl get pod <対象> -n <区画名> \
  -o jsonpath='{range .spec.containers[*]}{.image}{"\t"}{.imagePullPolicy}{"\n"}{end}'

# 7. 実際に取得を試みた回数を数える（待機の回数とは別物）
kubectl get events -n <区画名> --field-selector reason=Pulling --sort-by=.lastTimestamp

# 8. 待機の記録ごと作り直して、すぐに再取得させる
kubectl delete pod <対象> -n <区画名>
```

## Editor's Note

表示が入れ替わることを問題として扱った記録が、[kubernetes/kubernetes の Pull Request #127918](https://github.com/kubernetes/kubernetes/pull/127918) に残っています。2024年10月8日に出され、取り込み済みです。変更は v1.32 に入りました。

提案者が冒頭で述べているのは、この記事の主題そのものです。[コンテナ](/glossary/コンテナ/)の待機理由が `ImagePullBackOff` と実際の取得エラーの間で入れ替わり、`kubectl` のような利用者にとって体験が悪い、という指摘です。

説明には `kubectl get pods` の出力が2通り並べてあります。片方は状態欄が `SignatureValidationFailed`、もう片方は `ImagePullBackOff`。同じ Pod で、取得がどの段階にあるかによってどちらかが出る、と書かれています。原因は1つも変わっていないのに、見える名前だけが変わるわけです。

変更の中身は、待機中の本文に前回の失敗理由を残すことでした。提案には変更後の状態が[コード](/glossary/コード/)で示されており、待機の理由は `ImagePullBackOff` のまま、本文が `Back-off pulling image "...": SignatureValidationFailed: ...` という連結された形になっています。名前は状態を、本文は原因を表す、という役割の分離がここで明確になりました。

この経緯を踏まえると、2つの名前の読み方が定まります。`ErrImagePull` と `ImagePullBackOff` は、原因を区別するための名前ではありません。取得を試みたか、次の試行を待っているかという段階の名前です。原因はどちらの段階でも同じ場所、つまり本文にあります。名前を見比べる時間があるなら、本文を1行取り出すほうが早く進みます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
