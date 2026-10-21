---
title: "Gitのpathspec不一致エラー対処法"
date: 2026-10-21
slug: git_pathspec_did_not_match
draft: false
description: "git checkoutでpathspec did not matchが出たら、ブランチ名とリモート追跡ブランチを確認します。fetch後の切り替え、single-branchで取得対象が限られる場合、ファイルを指定した場合を分けて説明します。"
tags: ["Git"]
images: ["og/posts/git_pathspec_did_not_match.png"]
errorCode: "pathspec did not match"
service: "Git"
error_type: "pathspec did not match"
components: ["git checkout", "git fetch"]
related_services: ["GitHub"]
trend_incident: false
---

## 冒頭まとめ

ブランチを切り替えようとして、次のエラーが出ることがあります。

```text
error: pathspec 'feature/login' did not match any file(s) known to git
```

`feature/login` は、指定した名前の例です。ブランチへ切り替えるつもりでも、エラーにはファイルという言葉が出ます。

まずブランチ名と接続先を確認し、リモートの状態を取得してから切り替えます。`git checkout -b feature/login` だけで新しく作ると、相手が作ったブランチではなく、現在のコミットから作ってしまうため、先に切り替え元を確認してください。

## ブランチ指定なのにファイルのエラーになる理由

`git checkout` は、ブランチへの切り替えと、ファイルを戻す操作の両方を担当します。[公式文書の名前の解釈](https://git-scm.com/docs/git-checkout#_argument_disambiguation)にも、この2つの用途が説明されています。

指定した名前がコミットやブランチとして見つからず、リモート追跡ブランチからの自動作成もできなければ、ファイルの指定として処理される場合があります。そのファイルにも一致しないと、本件の文言になります。

pathspecは、Gitに渡すファイルやディレクトリなどの対象指定です。エラー文だけでは、ブランチを指定したかったのか、ファイルを指定したかったのかまでは分かりません。最初に実行したコマンドの目的を確認します。

## 名前とリモート追跡ブランチを確認する

ブランチを切り替えたい場合は、まず次を実行します。

```bash
git status
git remote -v
git branch -a
```

`git branch -a` でローカルのブランチと、`remotes/origin/feature/login` などのリモート追跡ブランチを確認します。後者は、リモートの状態を手元に記録したものです。GitHubの画面をその場で問い合わせた一覧ではありません。

名前の綴りと、大文字・小文字を含む正確な表記も確認してください。別のリポジトリや、同僚の個人用リポジトリを見ていないかは、`git remote -v` のURLと照合します。

未コミットの変更がある場合は、その内容も確認します。名前の問題が解消した後、変更の上書きを防ぐために切り替えが止まることもあります。その場合は、本件とは別の停止理由です。

## fetchしてから既存ブランチに切り替える

接続先がoriginなら、次でリモートの状態を取得します。origin以外なら実際の名前に置き換えてください。

```bash
git fetch origin
git branch -r
```

[git fetchの公式文書](https://git-scm.com/docs/git-fetch#_configured_remote_tracking_branches)では、引数で取得するブランチを指定しない場合、リモートのfetch設定に従って取得し、リモート追跡ブランチを更新します。

`origin/feature/login` が確認できたら、次で切り替えます。

```bash
git switch feature/login
```

[git switchの説明](https://git-scm.com/docs/git-switch)では、ローカルに名前が無くても、条件に合うリモート追跡ブランチがあれば、ローカルブランチを作成して追跡する動作があります。これは、リモートに直接移動して作業する操作ではありません。

同じ名前が複数のリモートにある場合や、取得元を明示したい場合は、ローカルに同名のブランチがまだ無いことを確認して次を使います。

```bash
git switch -c feature/login --track origin/feature/login
```

checkoutを使う場合の同等の指定は、次です。

```bash
git checkout -b feature/login --track origin/feature/login
```

2つは代替のコマンドです。続けて両方を実行する必要はありません。既にローカルブランチがある場合は、新規作成ではなく `git switch feature/login` を使います。

## fetch後も見えないなら取得範囲を調べる

fetchが成功しても、すべてのブランチが取得されるとは限りません。[git cloneの説明](https://git-scm.com/docs/git-clone#Documentation/git-clone.txt---single-branch)では、`--single-branch` で複製すると、その後のfetchも対象ブランチだけを更新します。`--depth` も、`--no-single-branch` を併用しなければ、単一ブランチの取得を伴います。

設定を確認します。

```bash
git config --get-all remote.origin.fetch
```

たとえば次はmainだけを取得する設定です。

```text
+refs/heads/main:refs/remotes/origin/main
```

リモートに目的のブランチが公開されているかは、[git ls-remote](https://git-scm.com/docs/git-ls-remote)でも確認できます。

```bash
git ls-remote --branches origin refs/heads/feature/login
```

このコマンドはリモートと通信します。通信に成功して目的の名前が表示されたのに、ローカルの取得対象から外れている場合は、次のように追加できます。

```bash
git remote set-branches --add origin feature/login
git fetch origin
git branch -r
```

[git remoteの公式説明](https://git-scm.com/docs/git-remote)では、`set-branches --add` は現在の取得対象を置き換えずに追加します。設定を変更する操作なので、対象が制限されていることを確認してから使ってください。取得後に `origin/feature/login` を確認し、前の節の明示的な作成・切り替えを行います。

通信や認証が失敗している場合は、そのエラーを先に解決します。取得対象を増やしても、存在しない名前やアクセスできないブランチは取得できません。

## 自動作成の設定とswitchの役割を確認する

[checkoutの公式説明](https://git-scm.com/docs/git-checkout#Documentation/git-checkout.txt---guess)では、`--no-guess` を指定するとリモート追跡ブランチからの自動作成を行いません。既定の動作は `checkout.guess` で変更できます。

```bash
git config --get checkout.guess
```

設定が見つからず何も表示されない場合もあります。`false` なら自動作成を期待せず、取得元を明示した指定を使う方法があります。設定を一律に変更する必要はありません。

ブランチ操作には `git switch` を使うと、ファイルを戻す操作と区別できます。ただし、switchに変えただけで未取得のブランチが使えるようになるわけではありません。

LinuxのGit 2.51.1で、リモートに追加されたブランチをまだfetchしていない状態を再現しました。checkoutは本件のエラーになり、switchは次で停止しました。

```text
fatal: invalid reference: feature/login
```

同じ検証で、通常の複製はfetch後に自動作成と切り替えが成功しました。`--no-guess` では自動作成が行われず、`--single-branch` の複製では取得対象の追加とfetch後に、追跡ブランチの作成・切り替えが成功しました。Windowsでの再現は未検証です。

## ファイルを戻したい場合はパスと記録を確認する

ファイルを指定した場合も同じ文言が出ます。Git 2.51.1では、存在しないファイルへの `git checkout -- missing.txt` でも、本件を確認しました。

ファイルを戻したい場合は、[git ls-files](https://git-scm.com/docs/git-ls-files)で、インデックスに記録されているパスを確認します。

```bash
git ls-files -- path/to/file.txt
```

現在の場所からのパスが正しいか、対象のブランチにそのファイルがあるかを確認してください。`--` はブランチではなくファイルの指定として区切るものです。存在しないファイルを作成したり、過去の全履歴から自動で探したりする指定ではありません。

`git checkout -- ファイル名` は、対象の作業中の内容を戻す操作にもなるため、名前を確かめるためだけに実行しないでください。

リポジトリ自体が見つからない[not a git repository](/posts/git_not_a_git_repository/)や、接続先へのアクセスに失敗する[Repository not found](/posts/github_repository_not_found/)とは、確認する対象が異なります。

## 解決手順のまとめ

ブランチへの切り替えなら、名前とリモートのURLを確認し、fetchしてからリモート追跡ブランチの一覧を見ます。取得元が確認できたら、switchで切り替えるか、取得元を明示してローカルブランチを作ります。

fetch後も見えなければ、リモート側の存在と取得範囲を確認します。ファイルを戻す目的なら、ブランチの取得ではなく、パスとGitに記録されたファイルを確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
