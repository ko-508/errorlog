---
title: "GitLabの503：原因と切り分け方"
date: 2026-10-27
draft: false
description: "GitLabのAPIやGit操作で503が返ったとき、応答本文とRetry-Afterを確認し、Gitalyの資源不足、保守モード、正常性確認の失敗を切り分けます。"
tags: ["GitLab"]
images: ["og/posts/gitlab_503.png"]
errorCode: "503"
urgency: "high"
service: "GitLab"
error_type: "503"
components: ["Gitaly", "Workhorse", "GitLab API"]
related_services: ["Git", "Redis", "PostgreSQL"]
trend_incident: false
---

## 冒頭まとめ

GitLab の [API](/glossary/api/) や [Git](/glossary/git/) 操作で `503 Service Unavailable` が返ったら、まず応答の本文と `Retry-After` [ヘッダー](/glossary/ヘッダー/)を確認してください。503 だけでは、原因を一つに決められません。

Gitaly の資源不足を示す本文なら、同時に実行されている[処理](/glossary/処理/)や待ち行列が手がかりになります。一方、応答の大きさが上限を超えたことを示す本文なら、待つだけでは解消しない問題です。保守モード中の書き込みも 503 になる場合があります。

## エラーの概要

[API](/glossary/api/) から返る応答の一例です。Gitaly は、GitLab で [Git](/glossary/git/) [リポジトリ](/glossary/リポジトリ/)へのアクセスを扱う部品です。

```text
HTTP/1.1 503 Service Unavailable

{"message":"Upstream Gitaly has been exhausted. Try again later"}
```

この本文は、GitLab の[Gitaly エラー処理の実装](https://github.com/gitlabhq/gitlabhq/blob/master/lib/gitlab/git/wraps_gitaly_errors.rb)にある文言の一つです。503 の本文は原因や応答を返した部品によって異なり、[JSON](/glossary/json/) とは限りません。[Git](/glossary/git/) [コマンド](/glossary/コマンド/)やブラウザーでも、同じ本文がそのまま表示されるとは限りません。

## まず最初に：応答と障害情報を確認する

[API](/glossary/api/) で失敗した場合は、状態[コード](/glossary/コード/)と本文に加えて、`Retry-After` があるか確認します。以下は読み取り要求の例です。[URL](/glossary/url/) と[プロジェクト](/glossary/プロジェクト/) [ID](/glossary/id/) は実際の接続先に置き換えてください。

```bash
curl -i --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.example.com/api/v4/projects/1/repository/commits"
```

`GITLAB_TOKEN` は事前に[設定](/glossary/設定/)したアクセストークンです。応答や[コマンド](/glossary/コマンド/)の記録を共有する際は、[トークン](/glossary/トークン/)などの秘密情報を含めないでください。

`Retry-After` があれば、指定された待ち時間を守って再試行します。書き込み要求で失敗した場合は、重複した変更を避けるため、再実行する前に対象の状態も確認してください。

GitLab.com を利用している場合は、[GitLab の稼働状況ページ](https://status.gitlab.com/)でも[障害](/glossary/障害/)や保守の情報を確認できます。自分で運用する GitLab の場合は、その[環境](/glossary/環境/)の管理者に確認してください。

## よくある原因と解決手順

### Gitaly の資源不足

`Upstream Gitaly has been exhausted` と表示された場合は、Gitaly に関わる[処理](/glossary/処理/)が資源不足として扱われています。GitLab の実装では、詳細な制限[エラー](/glossary/エラー/)や `RESOURCE_EXHAUSTED` を、この文言を含む[エラー](/glossary/エラー/)へ変換する経路があります。本文だけで同時実行数が原因だと断定せず、管理者は Gitaly の[ログ](/glossary/ログ/)や監視情報も確認してください。

[公式資料](https://docs.gitlab.com/administration/gitaly/concurrency_limiting/)では、[リポジトリ](/glossary/リポジトリ/)ごとの同時実行数や、待ち行列の長さ・待ち時間を制限できると説明されています。制限に達すると要求が拒否される場合があります。再試行が案内されている場合も、短い間隔で繰り返さず、指定された待ち時間や管理者の案内に従ってください。

### Gitaly の応答が大きすぎる

`The response from Gitaly is too large to load` に続き、`This is a size limit, not a temporary error` と表示される場合は、大きさの上限を超えた応答が原因です。GitLab の実装には、一時的な負荷ではなく設定上の上限として扱うコメントがあります。

この文言が出ている場合は、待つだけで解消するとは限りません。管理者に対象の[リポジトリ](/glossary/リポジトリ/)や操作、応答を伝え、要求の分割や対象範囲の見直しが可能か確認してください。分割方法は操作によって異なります。

### 保守モード中の書き込み

[API](/glossary/api/) の本文に `GitLab Maintenance: system is in maintenance mode` とあれば、保守モードが手がかりです。[GitLab の公式資料](https://docs.gitlab.com/ja-jp/administration/maintenance_mode/)によると、保守モード中は多くの [JSON](/glossary/json/) の書き込み要求が 503 で拒否されます。`git clone` や `git pull` は可能ですが、`git push` は拒否されます。

この保守モードは、Self-Managed の Premium または Ultimate で利用できる機能です。利用者は保守の終了を待ち、管理者は作業の状況を確認してください。

### 前段の部品による負荷制御

Gitaly や保守モードの文言が見えない場合もあります。例えば GitLab の [Webservice chart の資料](https://docs.gitlab.com/charts/charts/gitlab/webservice/)には、Workhorse が Puma の待機中の要求数に応じて 503 を返す[設定](/glossary/設定/)が記載されています。この[設定](/glossary/設定/)は既定では無効です。

503 の本文だけで応答元を決められない場合は、構成に応じて GitLab の前段にある部品や中継先の[ログ](/glossary/ログ/)も確認します。

## 補足：似ているが別のもの

[GitLab の 429](/posts/gitlab_429/) は、要求の回数などに設けられた制限で拒否される場合の状態[コード](/glossary/コード/)です。Gitaly の同時実行制限は、一定期間の要求回数だけでなく、同時に動く[処理](/glossary/処理/)や待ち行列を扱います。

[GitLab の 502](/posts/gitlab_502/) は、中継する側がその先から不正な応答を受け取るなどした場合の状態[コード](/glossary/コード/)です。502 と 503 のいずれも、状態[コード](/glossary/コード/)だけで故障箇所を確定することはできません。

## 切り分けの順序

最初に失敗した操作と時刻を控え、応答本文と `Retry-After` を確認します。GitLab.com なら稼働状況ページを確認し、自分で運用している場合は管理者へ状況を伝えます。

Gitaly の資源不足を示す場合は、一時的な集中と制限の状況を調べます。応答サイズの上限を示す場合は、対象の操作や[リポジトリ](/glossary/リポジトリ/)を調べます。保守モードの文言がある場合は、保守状況を確認します。

どの文言にも当てはまらない場合は、応答を返した部品を[ログ](/glossary/ログ/)や構成から調べます。[メンテナンス](/glossary/メンテナンス/)時以外の書き込み要求では、再試行前に[処理](/glossary/処理/)が実行済みかも確認してください。

## 確認コマンド集

Self-Managed の管理者は、GitLab が要求を受け付けられるか、依存する部品も含めて確認できます。接続先のアドレスは実際の[環境](/glossary/環境/)に置き換えてください。

```bash
curl -i "https://gitlab.example.com/-/readiness?all=1"
curl -i "https://gitlab.example.com/-/liveness"
```

[正常性確認の公式資料](https://docs.gitlab.com/ja-jp/administration/monitoring/health_check/)によると、`readiness?all=1` は[データベース](/glossary/データベース/)、Redis、Gitaly などの状態も確認します。`liveness` はアプリケーションサーバーの稼働を確認します。どちらも確認が失敗すると 503 を返します。利用できる接続元は[環境](/glossary/環境/)の[設定](/glossary/設定/)によって異なります。

[Linux](/glossary/linux/) [パッケージ](/glossary/パッケージ/)版では、管理者は次の[コマンド](/glossary/コマンド/)で稼働状況と Gitaly の[ログ](/glossary/ログ/)を確認できます。

```bash
sudo gitlab-ctl status
sudo gitlab-ctl tail gitaly
```

導入方法が異なる場合は、その[環境](/glossary/環境/)に合った監視・[ログ](/glossary/ログ/)確認の方法を使ってください。掲載[コマンド](/glossary/コマンド/)の実行結果は[環境](/glossary/環境/)によって異なります。

## Editor's Note

503 は再試行が役立つ場合がありますが、応答サイズの上限のように、時間を置くだけでは解決しない経路もあります。また、正常性確認の 503 は、その確認自体が失敗したことを示します。一般の [API](/glossary/api/) 要求で受け取った 503 と区別して、失敗した [URL](/glossary/url/) と本文を確認することが大切です。

実装に関する説明は、確認時点の [GitLab の Gitaly エラー処理](https://github.com/gitlabhq/gitlabhq/blob/master/lib/gitlab/git/wraps_gitaly_errors.rb)と [API の例外処理](https://github.com/gitlabhq/gitlabhq/blob/master/lib/api/api.rb)に基づきます。実際の文言や動作は利用している GitLab の版や構成で異なることがあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
