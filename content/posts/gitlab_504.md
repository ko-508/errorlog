---
title: "GitLabの504：原因と切り分け方"
date: 2026-10-29
draft: false
description: "GitLabで504が返るとき、失敗した操作と応答元から原因を切り分けます。大きなclone、アップロード、依存関係プロキシで確認する場所を説明します。"
tags: ["GitLab"]
images: ["og/posts/gitlab_504.png"]
errorCode: "504"
urgency: "high"
service: "GitLab"
error_type: "504"
components: ["Workhorse", "Gitaly", "load balancer"]
related_services: ["Git", "AWS ALB", "object storage"]
trend_incident: false
---

## 冒頭まとめ

GitLab への要求で `504 Gateway Timeout` が返ったら、まず失敗した操作と、504 を返した部品を確認してください。大きな[リポジトリ](/glossary/リポジトリ/)の `git clone` なら、GitLab の手前にある負荷分散装置や中継[サーバー](/glossary/サーバー/)の待ち時間が手がかりになります。一方、[ファイル](/glossary/ファイル/)の[アップロード](/glossary/アップロード/)や依存関係[プロキシ](/glossary/プロキシ/)では、GitLab の Workhorse 自身が 504 を返す[処理](/glossary/処理/)もあります。

Workhorse は、GitLab の手前で要求を受ける中継の部品です。504 が出たという理由だけで、GitLab 本体の処理時間の上限を上げても、原因に[対応](/glossary/対応/)した変更になるとは限りません。

## エラーの概要

[GitLab の Geo の公式資料](https://docs.gitlab.com/administration/geo/replication/troubleshooting/synchronization_verification/#exit-status-128-caused-by-http-504-from-a-load-balancer)には、大きな[リポジトリ](/glossary/リポジトリ/)の複製に失敗したときの例として、次の表示が載っています。

```text
error: RPC failed; HTTP 504 curl 22 The requested URL returned error: 504
fatal: expected 'packfile'
```

Geo は、GitLab のデータを複数の拠点に複製する機能です。この例では、手前の負荷分散装置や中継[サーバー](/glossary/サーバー/)が接続を終了する状況が説明されています。`packfile` は [Git](/glossary/git/) が転送するデータをまとめたものです。

[API](/glossary/api/) や Web 画面では表示が異なる場合があります。504 という番号や画面の見た目だけでは、どこが時間切れになったかは確定できません。

## まず最初に：操作と応答元を確認する

失敗した時刻、[URL](/glossary/url/)、操作の種類、失敗までのおおよその時間を控えます。[API](/glossary/api/) の場合は、応答の[ヘッダー](/glossary/ヘッダー/)と本文も確認してください。次の[コマンド](/glossary/コマンド/)は読み取り要求の例です。

```bash
curl -i "https://gitlab.example.com/api/v4/projects/1"
```

[URL](/glossary/url/) と[プロジェクト](/glossary/プロジェクト/) [ID](/glossary/id/) は実際の接続先へ置き換えます。非公開[プロジェクト](/glossary/プロジェクト/)などでは[認証](/glossary/認証/)が必要です。この要求が成功しても、大きな clone や[アップロード](/glossary/アップロード/)の経路まで正常だとは判断できません。

Self-Managed の管理者は、同じ時刻の負荷分散装置、中継[サーバー](/glossary/サーバー/)、Workhorse の[ログ](/glossary/ログ/)を照合します。本文や[ヘッダー](/glossary/ヘッダー/)は応答元を調べる手がかりですが、それだけで確定せず、実際に 504 を記録した部品を確認してください。

## よくある原因と解決手順

### 大きな clone の途中で負荷分散装置が時間切れになる

GitLab の Geo の資料は、Gitaly が転送用の packfile を準備している間にデータが流れず、手前の負荷分散装置が接続を終了する例を挙げています。Gitaly は [Git](/glossary/git/) [リポジトリ](/glossary/リポジトリ/)へのアクセスを扱う部品です。

[AWS](/glossary/aws/) の Application Load Balancer（ALB）では、データの送受信がない接続を閉じる待ち時間が、既定で60秒です。[AWS の公式資料](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-load-balancer-attributes.html#connection-idle-timeout)でも、この値と変更方法を確認できます。

管理者は、負荷分散装置の[ログ](/glossary/ログ/)に時間切れが記録されているか、現在の待ち時間が[処理](/glossary/処理/)に見合っているかを確認します。ALB なら対象の負荷分散装置の[属性](/glossary/属性/)にある `Connection idle timeout` を見直します。これは要求全体の実行時間ではなく、データが流れない時間の制限です。

### アップロードの処理が期限を超える

[Workhorse のアップロード処理](https://github.com/gitlabhq/gitlabhq/blob/master/workhorse/internal/upload/uploads.go)には、`context.DeadlineExceeded` を受けたときに、504 と本文 `deadline exceeded` を返す経路があります。

[アップロード](/glossary/アップロード/)中にこの本文が出た場合は、管理者が Workhorse の[ログ](/glossary/ログ/)と保存先の状態を確認します。[アップロード設定を組み立てる実装](https://github.com/gitlabhq/gitlabhq/blob/master/workhorse/internal/upload/destination/upload_opts.go)では、Rails から渡された保存先の[タイムアウト](/glossary/タイムアウト/)値を期限に使用しています。

ただし、`deadline exceeded` は他の[ソフトウェア](/glossary/ソフトウェア/)でも使われる文言です。本文だけで Workhorse と断定せず、失敗した操作と[ログ](/glossary/ログ/)を合わせて判断してください。

### 依存関係プロキシの取得先が時間切れになる

依存関係[プロキシ](/glossary/プロキシ/)は、外部の配布元から取得したデータを中継する機能です。[確認した Workhorse の実装](https://github.com/gitlabhq/gitlabhq/blob/master/workhorse/internal/dependencyproxy/dependencyproxy.go)では、取得先への接続と応答[ヘッダー](/glossary/ヘッダー/)を待つ時間に、それぞれ10秒の値を使い、取得時の時間切れを 504 にする経路があります。

この経路で失敗している場合は、外部の取得先の応答や GitLab からの通信経路を確認します。この10秒は[ダウンロード](/glossary/ダウンロード/)全体の制限とは異なります。また、利用中の GitLab の版によって実装が異なる可能性があるため、変更する[設定](/glossary/設定/)は実際の版と[ログ](/glossary/ログ/)を基に確認してください。

## 補足：似ているが別のもの

[GitLab の 502](/posts/gitlab_502/) と 504 は、どちらも中継する部品が関わる場合があります。[Workhorse の実装](https://github.com/gitlabhq/gitlabhq/blob/master/workhorse/internal/badgateway/roundtripper.go)では、Rails への転送時に応答を受け取れなかった[エラー](/glossary/エラー/)を 502 にし、通常は `GitLab is not responding` という本文を返す経路があります。

これは、Rails が関わる[遅延](/glossary/遅延/)では絶対に 504 が出ないという意味ではありません。さらに手前の負荷分散装置が先に時間切れになれば、利用者が見る応答は別になります。

[GitLab の 503](/posts/gitlab_503/) は、Gitaly の資源不足や保守モードなどでも返ります。番号だけで原因を決めず、本文と失敗した操作を確認する点は共通です。

## 切り分けの順序

大きな clone だけで失敗するなら、まず負荷分散装置や中継[サーバー](/glossary/サーバー/)の待ち時間と[ログ](/glossary/ログ/)を確認します。[ファイル](/glossary/ファイル/)の[アップロード](/glossary/アップロード/)なら Workhorse と保存先、依存関係[プロキシ](/glossary/プロキシ/)なら外部の取得先への[通信](/glossary/通信/)を調べます。

時間切れを記録した部品が分かったら、その制限と、実際に時間がかかっている[処理](/glossary/処理/)を確認してください。手前の待ち時間が短い問題と、保存先や取得先が応答しない問題では、変更する場所が異なります。

原因が分からない段階で複数の待ち時間をまとめて変更すると、どの変更が効いたか判断しにくくなります。変更後は、最初に失敗した操作と同じ条件で結果を確認します。

## 確認コマンド集

[Git](/glossary/git/) の [HTTP](/glossary/http/) [通信](/glossary/通信/)を詳しく確認する場合は、[Git](/glossary/git/) の追跡出力を利用できます。以下は macOS、[Linux](/glossary/linux/)、[Git](/glossary/git/) Bash 向けの例です。

```bash
GIT_TRACE_CURL=1 GIT_TRACE_CURL_NO_DATA=1 GIT_TRACE_REDACT=1 \
  git clone https://gitlab.example.com/group/project.git
```

[Git の公式資料](https://git-scm.com/docs/git#Documentation/git.txt-GIT_TRACE_CURL)によると、`GIT_TRACE_CURL` は [HTTP](/glossary/http/) [通信](/glossary/通信/)の追跡を有効にし、`GIT_TRACE_CURL_NO_DATA` は本文の出力を省きます。`GIT_TRACE_REDACT` を有効にすると、Authorization [ヘッダー](/glossary/ヘッダー/)などの対象情報が伏せられます。ただし、[URL](/glossary/url/) や独自の[ヘッダー](/glossary/ヘッダー/)などに秘密情報が残る可能性があるため、出力を共有する前に確認してください。

通信経路を調べる[コマンド](/glossary/コマンド/)であり、待ち時間を変更するものではありません。対象の[環境](/glossary/環境/)へアクセスできる利用者または管理者が実行してください。

## Editor's Note

504 は時間切れの結果ですが、延ばすべき時間が一つに決まっているわけではありません。GitLab の手前の待ち時間、Workhorse の[アップロード](/glossary/アップロード/)期限、外部の取得先を待つ時間は、それぞれ別の場所にあります。

本記事で取り上げた負荷分散装置の例は GitLab の Geo の公式資料、Workhorse の動作は確認時点の GitLab の公開ミラーの実装に基づきます。利用中の構成や版による違いを確認し、応答元を特定してから対処してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
