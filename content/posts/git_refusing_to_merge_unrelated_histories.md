---
title: "Gitの無関係な履歴のマージ拒否対処法"
date: 2026-10-10
slug: git_refusing_to_merge_unrelated_histories
draft: false
description: "fatal: refusing to merge unrelated historiesは、共通の祖先が見つからない履歴の結合をGitが拒否したときのエラーです。接続先と履歴を確認し、意図した結合だけを許可する手順、READMEの競合、cloneからやり直す場合の違いを説明します。"
tags: ["Git", "GitHub"]
images: ["og/posts/git_refusing_to_merge_unrelated_histories.png"]
errorCode: "fatal: refusing to merge unrelated histories"
service: "Git"
error_type: "unrelated_histories"
components: ["git merge", "git pull"]
related_services: ["GitHub"]
trend_incident: false
---

## 冒頭まとめ

`git pull`や`git merge`で次のエラーが出る場合、Gitは結合する二つの履歴に共通の祖先となるコミットを見つけられていません。コミットは、変更内容を記録した単位です。

```text
fatal: refusing to merge unrelated histories
```

通信をやり直すだけでは解消しません。接続先と対象ブランチを確認し、独立した二つの履歴を本当に結合したい場合だけ、`--allow-unrelated-histories`を指定します。

```bash
git fetch origin
git merge --allow-unrelated-histories origin/main
```

`origin`と`main`は例です。実際の接続先とブランチ名に置き換えてください。このオプションは履歴の結合を許可するだけで、ファイルの競合を自動で解消するものではありません。

## エラーが出る条件とGitの版

[Gitのmerge公式文書](https://git-scm.com/docs/git-merge#Documentation/git-merge.txt---allow-unrelated-histories)は、共通の祖先がない履歴の結合を既定で拒否すると説明しています。独立して始まったプロジェクトの履歴を結合するための例外が、`--allow-unrelated-histories`です。

この拒否は[Git 2.9のリリースノート](https://github.com/git/git/blob/v2.9.0/Documentation/RelNotes/2.9.0.txt)に記録されています。それ以前の既定動作は、共通の祖先がない履歴の結合も許可するものでした。別に作られた履歴が意図せず既存プロジェクトへ混ざることを防ぐため、動作が変更されました。

`git pull`でも、取得した履歴をマージで取り込む場合にこの判定が働きます。`pull`には履歴を組み直すrebase方式もあり、今回のオプションはマージ方式で使うものです。

ファイルの内容が同じでも、別々に作った最初のコミットが同じ履歴になるとは限りません。判断対象はファイルの一致ではなく、コミット間の親子関係です。

## 接続先と共通の祖先を確認する

最初に、別のプロジェクトを接続先に指定していないかを確認します。

```bash
git status
git remote -v
git branch --show-current
git fetch origin
git log --oneline --graph --decorate --all
git merge-base HEAD origin/main
```

`git fetch`はリモートの履歴を取得します。この段階では作業中のブランチへマージしません。取得後の`origin/main`と、現在のコミットを表す`HEAD`を比べます。

[merge-baseの公式文書](https://git-scm.com/docs/git-merge-base)によると、このコマンドは二つのコミットの共通祖先を探します。この記事のGit 2.51.1による確認では、独立した履歴に対して標準出力は空、終了コードは1でした。

ただし、出力がないだけで判断しないでください。ブランチ名が誤っているなどのエラーが表示された場合は、先にその問題を直します。

履歴を途中までしか取得していない浅いリポジトリでは、祖先をたどる情報が不足する場合もあります。

```bash
git rev-parse --is-shallow-repository
```

`true`なら、接続先を確認したうえで履歴全体を取得し、再確認します。

```bash
git fetch --unshallow origin
git merge-base HEAD origin/main
```

浅い履歴の取得方法は[fetchの公式文書](https://git-scm.com/docs/git-fetch)に説明されています。共通の祖先が見つからない理由を確認する前に、結合の許可へ進まないようにします。

## 別々の初期化で二つの履歴ができる

GitHubでREADME付きのリポジトリを作り、手元でも別に`git init`してコミットすると、それぞれ独立した最初のコミットができます。そこへ接続先を追加しても、過去の履歴の親子関係は変わりません。

[GitHub DesktopのIssue #1484](https://github.com/desktop/desktop/issues/1484)には、GitHub側とローカル側をそれぞれREADME付きで初期化し、Pullで同じエラーになった報告があります。これは2017年の報告であり、現在のDesktop全般の不具合を示すものではありません。

この記事では、外部へ接続せず、二つのローカルリポジトリを別々に初期化して確認しました。各リポジトリに異なる内容のREADMEをコミットし、一方をもう一方の接続先として取得すると、通常のマージは次の結果になりました。

```text
fatal: refusing to merge unrelated histories
```

同じことは、別のリポジトリを誤って接続した場合や、履歴を独立したものとして作り直した場合にも、共通祖先が見つからなければ起こり得ます。エラーだけから、どの操作が原因だったかまでは断定できません。

## 両方の履歴を残して結合する

結合する対象が正しく、両方のコミット履歴を残したい場合は、変更を保存してからマージします。未コミットの変更がある場合は、内容を確認してコミットするか、一時保管しておきます。

現在のコミットを残すためのブランチも作れます。次の名前が既に存在する場合は、別の名前にしてください。このブランチは未コミットの変更を保存するものではありません。

```bash
git branch backup-before-history-merge
git fetch origin
git merge --allow-unrelated-histories origin/main
```

`pull`で取得とマージをまとめて行うなら、マージ方式を明示します。

```bash
git pull --no-rebase --allow-unrelated-histories origin main
```

二つのコマンド例は代替の手順です。両方を続けて実行する必要はありません。

公式文書は、この許可を常時有効にする設定変数は存在せず、追加もしないと説明しています。接続先の誤りを見逃さないためにも、必要な結合に限って指定します。

## 許可後にREADMEが競合した場合

同じ名前のファイルを両方で作っていると、履歴の結合を許可しても競合することがあります。今回のGit 2.51.1による確認では、READMEの内容が異なっていたため、次の表示になりました。

```text
CONFLICT (add/add): Merge conflict in README.md
Automatic merge failed; fix conflicts and then commit the result.
```

この時点では、無関係な履歴の拒否は通過しています。次に直すのはファイル内容の競合です。

```bash
git status
```

競合したファイルを開き、残す内容へ編集します。`<<<<<<<`、`=======`、`>>>>>>>`という競合の印も取り除きます。READMEだけが競合していた場合は、次で解消結果を記録できます。

```bash
git add README.md
git commit
```

ほかのファイルにも競合があれば、それぞれ解消して追加してください。今回の確認では、この操作後に二つの親コミットを持つマージコミットが作られました。

進行中のマージを中止する場合は、次を使います。

```bash
git merge --abort
```

[mergeの公式文書](https://git-scm.com/docs/git-merge)は、開始前から未コミットの変更がある場合、元の状態を完全に復元できない場合があると注意しています。変更の保存は、マージを始める前に行ってください。

## 結合しない場合と近いエラーの違い

ローカルのコミット履歴を残す必要がなく、ファイルだけリモートのプロジェクトへ追加したい場合は、別のディレクトリへcloneし、必要なファイルを移す方法があります。

```bash
git clone <repository-url> project-copy
```

元のディレクトリは残します。新しいclone先へ必要なファイルをコピーし、差分を確認してコミットしてください。元の`.git`ディレクトリはコピーしません。この方法では、ローカル側の過去のコミット履歴は引き継がれません。

`local changes would be overwritten by merge`は、手元の未コミットの変更が上書きされるという別の拒否です。変更を一時保管しても、今回の共通祖先の問題そのものは解消しません。

`failed to push some refs`はpushの失敗をまとめた表示で、原因はその前の説明を読む必要があります。今回のエラーを消すために強制pushすると、リモート側の履歴を置き換える可能性があります。二つの履歴を残す目的には使いません。

## 解決手順のまとめ

まず接続先とブランチを確認し、履歴を取得して`git merge-base`で共通祖先を調べます。浅い履歴なら、必要な履歴を取得してから判断します。

独立した二つの履歴を残して結合する場合だけ、`--allow-unrelated-histories`を付けてマージします。許可後にファイルの競合が出た場合は、内容を解消してコミットします。

ファイルだけを移したい場合は、別の場所にcloneし、元のリポジトリを残したまま必要なファイルを追加できます。接続先の誤り、履歴の結合、ファイルの競合を分けて確認してください。

確認に使った環境はGit 2.51.1です。通常マージの拒否、共通祖先なしのmerge-base、許可後のREADME競合、解消後のマージコミットをローカルで確認しました。GitHubへのpushや、古いGit各版での実行確認は行っていません。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
