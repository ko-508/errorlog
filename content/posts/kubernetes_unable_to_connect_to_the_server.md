---
title: "kubectl接続エラーの原因と対処法"
date: 2026-09-27
draft: false
description: "kubectlのUnable to connect to the serverは、APIサーバーへ接続できないときに表示されます。kubeconfig、connection refused、名前解決、タイムアウト、TLSエラーを順番に切り分ける方法を解説します。"
tags: ["Kubernetes"]
images: ["og/posts/kubernetes_unable_to_connect_to_the_server.png"]
errorCode: "Unable to connect to the server"
urgency: "high"
service: "Kubernetes"
error_type: "unable_to_connect_to_the_server"
components: ["kubectl", "kubeconfig", "kube-apiserver"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

`kubectl get pods`などを実行したとき、次の[エラー](/glossary/エラー/)が出ることがあります。

```text
Unable to connect to the server: dial tcp: lookup api.example.com: no such host
```

```text
The connection to the server 127.0.0.1:6443 was refused - did you specify the right host or port?
```

どちらもkubectlから[Kubernetes](/glossary/kubernetes/) [API](/glossary/api/)[サーバー](/glossary/サーバー/)へ接続できていません。ただし、直す場所は後半の文言によって異なります。

| 後半の文言 | 最初に疑う場所 |
|---|---|
| `connection refused` | [API](/glossary/api/)[サーバー](/glossary/サーバー/)の停止、ホスト、[ポート](/glossary/ポート/) |
| `no such host` | [DNS](/glossary/dns/)、VPN、kubeconfig内のホスト名 |
| `i/o timeout`、`TLS handshake timeout` | 経路、VPN、[ファイアウォール](/glossary/ファイアウォール/)、負荷 |
| `x509:`、`tls:` | CA[証明書](/glossary/証明書/)、接続先名、[証明書](/glossary/証明書/)の期限 |
| `no configuration has been provided` | kubeconfigの有無と読み込み元 |

最初に、kubectlが選んでいるcontextと[API](/glossary/api/)[サーバー](/glossary/サーバー/)の[URL](/glossary/url/)を確認してください。

```bash
kubectl config current-context
kubectl config view --minify
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}{"\n"}'
```

想定外のクラスターが表示された場合は、[ネットワーク](/glossary/ネットワーク/)を調べる前にkubeconfigの読み込み元を直します。

## Unable to connect to the serverとは

kubectlは、kubeconfigから[API](/glossary/api/)[サーバー](/glossary/サーバー/)の場所、接続に使う認証情報、現在のcontextを読み取ります。その情報を使って接続を試み、名前解決、TCP接続、[TLS](/glossary/tls/)接続などの段階で失敗すると、`Unable to connect to the server`が表示されます。

kubectlの実装では、接続時の[エラー](/glossary/エラー/)が`connection refused`を含む場合だけ、次の専用メッセージへ変換します。

```text
The connection to the server <host>:<port> was refused - did you specify the right host or port?
```

それ以外の接続[エラー](/glossary/エラー/)は、元の原因を後ろに付けた次の形式になります。

```text
Unable to connect to the server: <接続に失敗した理由>
```

したがって、`Unable to connect to the server`だけを見ても原因は決まりません。コロン以降にある`no such host`、`timeout`、`tls`などを省略せずに確認することが重要です。

なお、これはPodやDeploymentの[エラー](/glossary/エラー/)ではありません。kubectlが[API](/glossary/api/)[サーバー](/glossary/サーバー/)へ到達する前後で止まっているため、`kubectl logs`やPodの再起動では解決できません。

## kubeconfigとcontextを確認する

kubectlが接続に使う情報はkubeconfigにあります。まず、利用できるcontextと現在選ばれているcontextを確認します。

```bash
kubectl config get-contexts
kubectl config current-context
kubectl config view --minify
```

`--minify`を付けると、現在のcontextに関係するclusterとuserへ表示を絞れます。`server:`に書かれた[URL](/glossary/url/)が、接続したいクラスターの[API](/glossary/api/)[サーバー](/glossary/サーバー/)か確認してください。

kubeconfigの読み込み規則は次の順序です。

1. `--kubeconfig`を指定した場合は、その1[ファイル](/glossary/ファイル/)だけを使う
2. `KUBECONFIG`[環境変数](/glossary/環境変数/)がある場合は、列挙された[ファイル](/glossary/ファイル/)を[マージ](/glossary/マージ/)する
3. どちらもない場合は、通常`$HOME/.kube/config`を使う

この規則は[Kubeconfigファイルを使用したクラスターアクセスの構成](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/)に記載されています。

[Linux](/glossary/linux/)またはmacOSでは、[環境変数](/glossary/環境変数/)を次のように確認できます。

```bash
printf '%s\n' "$KUBECONFIG"
ls -l "$HOME/.kube/config"
```

Windows PowerShellでは次を使います。

```powershell
$Env:KUBECONFIG
Test-Path "$HOME\.kube\config"
```

`KUBECONFIG`には複数の[ファイル](/glossary/ファイル/)を指定できます。区切りは[Linux](/glossary/linux/)とmacOSではコロン、Windowsではセミコロンです。複数[ファイル](/glossary/ファイル/)に同名のclusterやuserがあると、[マージ](/glossary/マージ/)結果が想定と異なることがあります。

確認のために特定の[ファイル](/glossary/ファイル/)だけを使う場合は、`--kubeconfig`を明示します。

```bash
kubectl --kubeconfig=/path/to/config config view --minify
kubectl --kubeconfig=/path/to/config get nodes
```

この指定で接続できるなら、クラスターではなく、通常実行時に読み込まれているkubeconfigやcontextが原因です。

`error: no configuration has been provided`や`cluster has no server defined`が出る場合は、TCP接続より前に[設定](/glossary/設定/)の読み込みで止まっています。クラスター管理者または利用している[クラウド](/glossary/クラウド/)・ローカルクラスターの公式手順から、kubeconfigを取得し直してください。入手元が不明なkubeconfigは、[認証](/glossary/認証/)プラグインなどを通じて[コード](/glossary/コード/)を実行する可能性があるため使用しないでください。

## connection refusedの対処

次の文言は、指定されたホストと[ポート](/glossary/ポート/)へのTCP接続が拒否された場合に表示されます。

```text
The connection to the server <host>:<port> was refused - did you specify the right host or port?
```

名前解決や経路が完全に失敗した場合とは異なり、接続先から拒否が返っています。主な原因は、[API](/glossary/api/)[サーバー](/glossary/サーバー/)が停止している、kubeconfigの[ポート](/glossary/ポート/)が古い、クラスターを作り直したのに以前の接続先を参照している、といったものです。

まず、現在の接続先を取り出します。

```bash
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}{"\n"}'
```

`localhost:8080`や、削除済みクラスターの[IPアドレス](/glossary/ipアドレス/)が出る場合は、正しいkubeconfigを取得し直します。minikubeなどのローカルクラスターを使っている場合は、クラスター自体が起動しているかも確認してください。

管理対象のクラスターなら、control planeや[API](/glossary/api/)[サーバー](/glossary/サーバー/)前段の[ロードバランサー](/glossary/ロードバランサー/)が正常かを管理画面や監視から確認します。利用者側から接続できないという理由だけで、control planeを再起動しないでください。VPN、接続元制限、誤ったcontextでも同じように利用不能になるためです。

## no such host・timeoutの対処

次の文言は、kubeconfigに書かれたホスト名を[DNS](/glossary/dns/)で解決できない場合に出ます。

```text
Unable to connect to the server: dial tcp: lookup api.example.com: no such host
```

[API](/glossary/api/)[サーバー](/glossary/サーバー/)の[URL](/glossary/url/)を確認し、そのホスト名が現在の[環境](/glossary/環境/)から解決できるか調べます。

```bash
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}{"\n"}'
nslookup api.example.com
```

社内[DNS](/glossary/dns/)やプライベート[DNS](/glossary/dns/)でのみ解決できるホストなら、VPNへ接続してから再確認します。クラスターを再作成したあとに古いホスト名が残っている場合は、[DNS設定](/glossary/dns設定/)を手作業で書き換えるのではなく、正しいkubeconfigを取得し直してください。

`i/o timeout`や`TLS handshake timeout`の場合は、接続先へ応答が返る前に制限時間を超えています。VPN、[ファイアウォール](/glossary/ファイアウォール/)、[プロキシ](/glossary/プロキシ/)、[API](/glossary/api/)[サーバー](/glossary/サーバー/)前段の[ロードバランサー](/glossary/ロードバランサー/)を確認します。

到達性だけを確認したい場合は、kubeconfigに表示された[URL](/glossary/url/)を使い、短い接続時間で試します。

```bash
curl --connect-timeout 5 https://api.example.com:6443/readyz
```

認証情報を付けていないため、`401 Unauthorized`や`403 Forbidden`が返る場合があります。ただし、その応答が返るなら[DNS](/glossary/dns/)、TCP、[TLS](/glossary/tls/)の接続は少なくとも成立しています。

自己署名証明書などでcurlの検証だけが失敗する場合、経路の確認に限って`-k`を使う方法もあります。

```bash
curl -k --connect-timeout 5 https://api.example.com:6443/readyz
```

`-k`は[サーバー](/glossary/サーバー/)[証明書](/glossary/証明書/)の検証を無効にします。中間者攻撃を検出できなくなるため、恒久的な[設定](/glossary/設定/)や通常の[API](/glossary/api/)操作には使用しないでください。kubectl側の[TLS](/glossary/tls/)検証を無効にする解決策でもありません。

## TLSエラーの対処

`Unable to connect to the server:`の後ろに`x509:`や`tls:`がある場合は、[API](/glossary/api/)[サーバー](/glossary/サーバー/)には接続を試みていますが、[証明書](/glossary/証明書/)の検証または[TLS](/glossary/tls/)ハンドシェイクに失敗しています。

よくある原因は次のとおりです。

- クラスターを再作成したため、kubeconfig内のCAが古い
- [証明書](/glossary/証明書/)の有効期限が切れている
- kubeconfigの接続先名と[証明書](/glossary/証明書/)の対象名が一致しない
- 途中の[プロキシ](/glossary/プロキシ/)が別の[証明書](/glossary/証明書/)を返している

kubeconfig内の接続先と証明書設定を確認します。

```bash
kubectl config view --minify
```

`certificate-authority`または`certificate-authority-data`と、`server`の組み合わせが同じクラスターから取得されたものか確認してください。クラスターを作り直した場合は、古いCAだけを残して接続先を手作業で変えるのではなく、kubeconfig一式を再取得します。

`insecure-skip-tls-verify: true`を恒久的に[設定](/glossary/設定/)すると、kubectlが接続先の正当性を確認できなくなります。原因調査を省略するための対処としては使わないでください。

[証明書](/glossary/証明書/)が正しく、その後に`Unauthorized`や`Forbidden`へ変わった場合は、接続自体は成立しています。次に[トークン](/glossary/トークン/)、[クライアント](/glossary/クライアント/)[証明書](/glossary/証明書/)、exec[認証](/glossary/認証/)プラグイン、[RBAC](/glossary/rbac/)を調べます。

## 似たエラーとの違い

`error: You must be logged in to the server (Unauthorized)`は、[API](/glossary/api/)[サーバー](/glossary/サーバー/)へ到達したあとに[認証](/glossary/認証/)で拒否された[エラー](/glossary/エラー/)です。kubeconfigの接続先ではなく、認証情報の期限や[ログイン](/glossary/ログイン/)状態を確認します。

`Error from server (Forbidden)`は[認証](/glossary/認証/)された利用者に操作権限がない状態です。接続障害ではなく、[RBAC](/glossary/rbac/)などの認可設定を確認します。

`Error from server (NotFound)`や`the server could not find the requested resource`は、[API](/glossary/api/)[サーバー](/glossary/サーバー/)から応答を受け取っています。リソース名、namespace、[API](/glossary/api/)の種類や[バージョン](/glossary/バージョン/)が調査対象です。

`error: no configuration has been provided`は、接続を試す前にkubeconfigを読み込めなかった[エラー](/glossary/エラー/)です。`Unable to connect to the server`とは発生段階が異なります。

Podの`Pending`、`CrashLoopBackOff`、`ImagePullBackOff`は、[API](/glossary/api/)[サーバー](/glossary/サーバー/)へ接続したあとに確認できるワークロード側の状態です。kubectl自体が接続できない今回の[エラー](/glossary/エラー/)とは分けて考えます。

## 解決手順のまとめ

最初に`kubectl config current-context`と`kubectl config view --minify`を実行し、kubectlが選んでいるクラスター、利用者、[API](/glossary/api/)[サーバー](/glossary/サーバー/)の[URL](/glossary/url/)を確認します。

[設定](/glossary/設定/)が違う場合は、`--kubeconfig`、`KUBECONFIG`、`$HOME/.kube/config`の読み込み規則を確認してください。新しい端末、[コンテナ](/glossary/コンテナ/)、CIでは、kubeconfigや[認証](/glossary/認証/)プラグインを渡していないことがあります。

接続先が正しければ、後半の文言に従って切り分けます。`connection refused`は[API](/glossary/api/)[サーバー](/glossary/サーバー/)と[ポート](/glossary/ポート/)、`no such host`は[DNS](/glossary/dns/)とVPN、`timeout`は経路と[ファイアウォール](/glossary/ファイアウォール/)、`x509`や`tls`は[証明書](/glossary/証明書/)と接続先名を確認します。

`curl -k`や`insecure-skip-tls-verify`で警告を消すことを解決策にしないでください。[TLS](/glossary/tls/)検証を外して到達性を確認した場合も、最終的には正しいCAとkubeconfigでkubectlが接続できる状態へ戻す必要があります。

免責事項：本記事の内容は一般的な[Kubernetes](/glossary/kubernetes/)[環境](/glossary/環境/)を前提としています。kubeconfigには認証情報や外部[コマンド](/glossary/コマンド/)の[設定](/glossary/設定/)が含まれる場合があります。共有、公開、編集を行う前に内容を確認し、[TLS](/glossary/tls/)検証や[アクセス制御](/glossary/アクセス制御/)を無効化しないでください。
