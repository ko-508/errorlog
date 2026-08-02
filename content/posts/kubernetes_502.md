---
title: "Kubernetes の 502 エラー：原因と解決策"
date: 2026-07-29
description: "Kubernetes の 502 は、API サーバーではなく Ingress の制御役が返している場合がほとんどです。転送先には届いているのに正しい応答が得られなかった状態で、原因は接続の拒否、応答の見出しが大きすぎる、途中で切られたの3系統に整理できます。転送先が1つも無い場合は 502 ではなく 503 になり、この違いが切り分けの起点になります。"
tags: ["Kubernetes"]
errorCode: "502"
lastmod: 2026-07-29
service: "Kubernetes"
error_type: "502"
components: ["Ingress", "Service"]
related_services: ["ingress-nginx", "kube-apiserver", "Endpoints"]
trend_incident: false
---

## 冒頭まとめ

[Kubernetes](/glossary/kubernetes/) で 502 Bad Gateway を見る場面は、利用者向けの[通信](/glossary/通信/)を取り次ぐ Ingress の制御役に集中します。`kubectl` の操作で 502 が出ることは、通常ありません。[API](/glossary/api/) [サーバー](/glossary/サーバー/)が時間切れで打ち切る場合は 504 になり、応答できる相手が居ない場合は 503 になるためです。したがって 502 を見たら、まず[コンテナ](/glossary/コンテナ/)への通信経路の話だと考えて構いません。

502 の意味は、取り次いだ側が転送先から正しい応答を得られなかった、ということです。ここで重要なのは、転送先そのものは選べているという点です。選べていなければ、そもそも転送する相手が居ないので別の[エラー](/glossary/エラー/)になります。多くの制御役は、対象の転送先が1つも無い場合に 503 を返します。

したがって切り分けの第一歩は、502 と 503 のどちらが出ているかを見ることです。503 なら、転送先の一覧が空です。準備完了の判定が通っていないか、選択の条件が合っていないかのどちらかです。502 なら、一覧には相手が居るのに、その相手との[通信](/glossary/通信/)が成立していません。

502 の原因は、制御役の土台になっている[ソフトウェア](/glossary/ソフトウェア/)の作りから、3系統に整理できます。接続そのものを拒否された場合、応答の見出し部分が大きすぎて扱えなかった場合、そして応答を渡し終える前に切られた場合です。[ログ](/glossary/ログ/)の文言でこの3つは区別できます。

## エラーの概要

制御役の[ログ](/glossary/ログ/)には、要求ごとの記録と、失敗の理由が残ります。接続を拒否された場合の記録は次の形です。

```text
connect() failed (111: Connection refused) while connecting to upstream,
client: 10.1.0.5, server: example.com, request: "GET /api HTTP/1.1",
upstream: "http://10.2.3.4:8080/api"
```

応答の見出し部分が大きすぎる場合は、別の文言になります。

```text
upstream sent too big header while reading response header from upstream,
client: 10.1.0.5, server: example.com, request: "GET /api HTTP/1.1"
```

このとき記録に残る転送先の番号を確認してください。ここに出ている番号が、自分が意図した[コンテナ](/glossary/コンテナ/)の番号と違っていれば、原因は設定の食い違いです。

## まず最初に：502と503を区別し、転送先の一覧を見る

第一に、返っているのが 502 か 503 かを確認します。503 なら転送先が空なので、以下の原因の話ではありません。

第二に、転送先の一覧を直接確認します。ここに何が並んでいるかで、次に見る場所が決まります。

```bash
kubectl get endpointslices -n example -l kubernetes.io/service-name=my-service
kubectl describe service my-service -n example
```

一覧に並んでいる番号が、[コンテナ](/glossary/コンテナ/)が実際に待ち受けている番号と一致しているかを確かめます。ここがずれていると、接続の拒否として現れます。

第三に、制御役の[ログ](/glossary/ログ/)から、失敗の文言を取り出します。3系統のどれに当たるかで、対処が決まります。

```bash
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=200 \
  | grep -E "connect\(\) failed|too big header|closed connection"
```

## よくある原因と解決手順

### 原因1：転送先の番号が実際と違う

最も多い形です。定義した番号と、[コンテナ](/glossary/コンテナ/)が実際に待ち受けている番号が食い違っていると、接続を拒否されます。準備完了の判定が別の番号を見ている場合、判定は通るのに[通信](/glossary/通信/)は失敗する、という状態にもなります。

**Before（定義と実態がずれている）：**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 8080   # コンテナは 3000 で待ち受けている
```

**After（実態に合わせる）：**

```yaml
    - port: 80
      targetPort: 3000
```

実際に待ち受けている番号は、[コンテナ](/glossary/コンテナ/)の中から確認できます。

```bash
kubectl exec -n example deploy/my-app -- sh -c "netstat -tnl 2>/dev/null || ss -tnl"
```

制御役を通さずに、直接届くかどうかも確かめてください。ここで失敗するなら、原因は制御役ではありません。

```bash
kubectl run tmp --rm -it --image=curlimages/curl --restart=Never -- \
  curl -sS -o /dev/null -w "status:%{http_code}\n" http://my-service.example.svc.cluster.local/
```

### 原因2：応答の見出し部分が大きすぎる

`too big header` の文言が出る場合です。[認証](/glossary/認証/)の情報を大きな見出しに載せる構成で起きやすく、利用者によって成功したり失敗したりするのが特徴です。情報の量が人によって違うためです。

制御役には、この大きさを調整する指定が用意されています。個別の設定として書けます。

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-ingress
  annotations:
    nginx.ingress.kubernetes.io/proxy-buffer-size: "8k"
spec:
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-service
                port:
                  number: 80
```

全体に適用したい場合は、制御役の設定にまとめて指定します。値は、実際の見出しの大きさを見て決めてください。むやみに大きくすると、接続あたりの使用量が増えます。

### 原因3：応答を渡し終える前に切られている

[コンテナ](/glossary/コンテナ/)側が、応答の途中で接続を閉じた場合です。処理に時間がかかって[コンテナ](/glossary/コンテナ/)側の待ち時間が先に尽きた、[コンテナ](/glossary/コンテナ/)が終了処理に入った、資源の上限に達して落ちた、といった状況が候補になります。

まず、該当の時刻に[コンテナ](/glossary/コンテナ/)が再起動していないかを確認します。

```bash
kubectl get pods -n example -o wide
kubectl describe pod -n example <ポッド名> | grep -A5 "Last State"
```

再起動の回数が増えていれば、原因は[通信](/glossary/通信/)ではなく[コンテナ](/glossary/コンテナ/)側です。資源の上限に達して終了させられている場合、終了の理由にその旨が残ります。

更新の最中にだけ出る場合は、終了処理と[通信](/glossary/通信/)の切り離しの順序が問題です。終了の合図を受けてから実際に止まるまでの猶予を確保し、その間に転送先の一覧から外れるようにします。

### 原因4：準備完了の判定と実態が合っていない

判定が通っているのに実際には応答できない、という状態です。判定先の[パス](/glossary/パス/)が、実際の処理と無関係な場所を指している場合に起きます。

```bash
kubectl get pod -n example <ポッド名> \
  -o jsonpath='{.spec.containers[*].readinessProbe}' | python3 -m json.tool
```

判定は、実際に処理を担う部分まで到達する[パス](/glossary/パス/)に向けてください。静的な[ファイル](/glossary/ファイル/)を返すだけの[パス](/glossary/パス/)では、背後の準備が整っていなくても通ってしまいます。

## 補足：似ているが別のもの

転送先が1つも無い場合は 503 です。準備完了の判定が通っていないか、選択の条件が[コンテナ](/glossary/コンテナ/)の名札と一致していない場合にこうなります（[Kubernetes の 503 の記事](/posts/kubernetes_503/)）。502 との違いは、相手が居るかどうかです。

[API](/glossary/api/) [サーバー](/glossary/サーバー/)が時間切れで打ち切った場合は 504 で、文言も定型のものが付きます（[Kubernetes の 504 の記事](/posts/kubernetes_504/)）。`kubectl` の操作で 502 が出た場合は、クラスタの前段に別の中継役が挟まっていることを疑ってください。

処理そのものが失敗した場合は 500、対象が見つからない場合は 404、[権限](/glossary/権限/)が足りない場合は 403 です（[Kubernetes の 500 の記事](/posts/kubernetes_500/)、[404 の記事](/posts/kubernetes_404/)、[403 の記事](/posts/kubernetes_403/)）。

制御役の土台になっている[ソフトウェア](/glossary/ソフトウェア/)そのものの挙動は、別記事で扱っています（[Nginx の 502 の記事](/posts/nginx_502/)）。文言の意味を細かく追う場合はそちらも参照してください。

## 切り分けの順序

1. 502 か 503 かを確認する。503 なら転送先が空なので、別の調査になる。
2. 転送先の一覧を直接見る。並んでいる番号が、実際に待ち受けている番号と一致するかを確かめる。
3. 制御役の[ログ](/glossary/ログ/)から失敗の文言を取り出し、3系統のどれかに振り分ける。
4. 接続の拒否なら、定義した番号と実態の食い違いを疑う。
5. 見出しが大きすぎる場合は、大きさの指定を調整する。利用者によって成否が分かれるのが特徴。
6. 途中で切られている場合は、[コンテナ](/glossary/コンテナ/)の再起動と終了処理の順序を確認する。
7. 制御役を通さずに直接届くかを確かめる。直接なら成功するなら、原因は制御役側の設定にある。

## 確認コマンド集

```bash
# 1. 転送先の一覧を確認する（空なら 503 の話）
kubectl get endpointslices -n example -l kubernetes.io/service-name=my-service

# 2. サービスの定義と実際の番号を突き合わせる
kubectl describe service my-service -n example
kubectl exec -n example deploy/my-app -- sh -c "netstat -tnl 2>/dev/null || ss -tnl"

# 3. 制御役のログから失敗の文言を取り出す
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=200 \
  | grep -E "connect\(\) failed|too big header|closed connection"

# 4. 制御役を通さずに直接届くかを確かめる
kubectl run tmp --rm -it --image=curlimages/curl --restart=Never -- \
  curl -sS -o /dev/null -w "status:%{http_code}\n" http://my-service.example.svc.cluster.local/

# 5. コンテナの再起動と終了理由を確認する
kubectl get pods -n example
kubectl describe pod -n example <ポッド名> | grep -A5 "Last State"

# 6. 準備完了の判定の設定を確認する
kubectl get pod -n example <ポッド名> \
  -o jsonpath='{.spec.containers[*].readinessProbe}' | python3 -m json.tool
```

## Editor's Note

502 と 503 の区別は、単なる分類の話ではありません。この2つは、調べるべき対象がまったく違います。503 は「相手が居ない」ので、見るのは準備完了の判定と名札の条件です。502 は「相手は居るが通じない」ので、見るのは番号と応答の中身です。同じ画面の裏で、まったく別の作業が待っています。

そして厄介なのは、この2つが入れ替わることです。準備完了の判定が通った直後は 503 から 502 に変わり、[コンテナ](/glossary/コンテナ/)が落ちれば 502 から 503 に戻ります。更新の最中に両方が混ざって出るのは、そのためです。一方だけを見て原因を決めると、もう一方の時間帯を取りこぼします。

もう1つ、原因2の見出しの大きさは、切り分けを誤りやすい形です。すべての利用者で失敗するなら設定を疑いますが、この形では一部の利用者だけが失敗します。「特定の人だけ動かない」という報告が来たとき、[権限](/glossary/権限/)の問題を疑うのが自然です。しかし実際には、その人の[認証](/glossary/認証/)の情報が他より少しだけ大きい、というだけのことがあります。[ログ](/glossary/ログ/)の文言を見れば一目で分かるので、推測の前に文言を確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*