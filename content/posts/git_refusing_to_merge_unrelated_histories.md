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

`git pull`や`git merge`で次の[エラー](/glossary/エラー/)が出る場合、[Git](/glossary/git/)は結合する二つの履歴に共通の祖先となる[コミット](/glossary/コミット/)を見つけられていません。[コミット](/glossary/コミット/)は、変更内容を記録した単位です。

```text
fatal: refusing to merge unrelated histories
```

[通信](/glossary/通信/)をやり直すだけでは解消しません。接続先と対象[ブランチ](/glossary/ブランチ/)を確認し、独立した二つの履歴を本当に結合したい場合だけ、`--allow-unrelated-histories`を指定します。

```bash
git fetch origin
git merge --allow-unrelated-histories origin/main
```

`origin`と`main`は例です。実際の接続先と[ブランチ](/glossary/ブランチ/)名に置き換えてください。このオプションは履歴の結合を許可するだけで、[ファイル](/glossary/ファイル/)の競合を自動で解消するものではありません。

## エラーが出る条件とGitの版

[Gitのmerge公式文書](https://git-scm.com/docs/git-merge#Documentation/git-merge.txt---allow-unrelated-histories)は、共通の祖先がない履歴の結合を既定で拒否すると説明しています。独立して始まった[プロジェクト](/glossary/プロジェクト/)の履歴を結合するための例外が、`--allow-unrelated-histories`です。

この拒否は[Git 2.9のリリースノート](https://github.com/git/git/blob/v2.9.0/Documentation/RelNotes/2.9.0.txt)に記録されています。それ以前の既定動作は、共通の祖先がない履歴の結合も許可するものでした。別に作られた履歴が意図せず既存[プロジェクト](/glossary/プロジェクト/)へ混ざることを防ぐため、動作が変更されました。

`git pull`でも、取得した履歴を[マージ](/glossary/マージ/)で取り込む場合にこの判定が働きます。`pull`には履歴を組み直すrebase方式もあり、今回のオプションは[マージ](/glossary/マージ/)方式で使うものです。

[ファイル](/glossary/ファイル/)の内容が同じでも、別々に作った最初の[コミット](/glossary/コミット/)が同じ履歴になるとは限りません。判断対象は[ファイル](/glossary/ファイル/)の一致ではなく、[コミット](/glossary/コミット/)間の親子関係です。

## 接続先と共通の祖先を確認する

最初に、別の[プロジェクト](/glossary/プロジェクト/)を接続先に指定していないかを確認します。

```bash
git status
git remote -v
git branch --show-current
git fetch origin
git log --oneline --graph --decorate --all
git merge-base HEAD origin/main
```

`git fetch`はリモートの履歴を取得します。この段階では作業中の[ブランチ](/glossary/ブランチ/)へ[マージ](/glossary/マージ/)しません。取得後の`origin/main`と、現在の[コミット](/glossary/コミット/)を表す`HEAD`を比べます。

[merge-baseの公式文書](https://git-scm.com/docs/git-merge-base)によると、この[コマンド](/glossary/コマンド/)は二つの[コミット](/glossary/コミット/)の共通祖先を探します。この記事の[Git](/glossary/git/) 2.51.1による確認では、独立した履歴に対して標準出力は空、終了[コード](/glossary/コード/)は1でした。

ただし、出力がないだけで判断しないでください。[ブランチ](/glossary/ブランチ/)名が誤っているなどの[エラー](/glossary/エラー/)が表示された場合は、先にその問題を直します。

履歴を途中までしか取得していない浅い[リポジトリ](/glossary/リポジトリ/)では、祖先をたどる情報が不足する場合もあります。

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

[GitHub](/glossary/github/)でREADME付きの[リポジトリ](/glossary/リポジトリ/)を作り、手元でも別に`git init`して[コミット](/glossary/コミット/)すると、それぞれ独立した最初の[コミット](/glossary/コミット/)ができます。そこへ接続先を追加しても、過去の履歴の親子関係は変わりません。

[GitHub DesktopのIssue #1484](https://github.com/desktop/desktop/issues/1484)には、[GitHub](/glossary/github/)側とローカル側をそれぞれREADME付きで[初期化](/glossary/初期化/)し、Pullで同じ[エラー](/glossary/エラー/)になった報告があります。これは2017年の報告であり、現在のDesktop全般の不具合を示すものではありません。

この記事では、外部へ接続せず、二つのローカルリポジトリを別々に[初期化](/glossary/初期化/)して確認しました。各[リポジトリ](/glossary/リポジトリ/)に異なる内容のREADMEを[コミット](/glossary/コミット/)し、一方をもう一方の接続先として取得すると、通常の[マージ](/glossary/マージ/)は次の結果になりました。

```text
fatal: refusing to merge unrelated histories
```

同じことは、別の[リポジトリ](/glossary/リポジトリ/)を誤って接続した場合や、履歴を独立したものとして作り直した場合にも、共通祖先が見つからなければ起こり得ます。[エラー](/glossary/エラー/)だけから、どの操作が原因だったかまでは断定できません。

## 両方の履歴を残して結合する

結合する対象が正しく、両方の[コミット](/glossary/コミット/)履歴を残したい場合は、変更を[保存](/glossary/保存/)してから[マージ](/glossary/マージ/)します。未[コミット](/glossary/コミット/)の変更がある場合は、内容を確認して[コミット](/glossary/コミット/)するか、一時保管しておきます。

現在の[コミット](/glossary/コミット/)を残すための[ブランチ](/glossary/ブランチ/)も作れます。次の名前が既に存在する場合は、別の名前にしてください。この[ブランチ](/glossary/ブランチ/)は未[コミット](/glossary/コミット/)の変更を[保存](/glossary/保存/)するものではありません。

```bash
git branch backup-before-history-merge
git fetch origin
git merge --allow-unrelated-histories origin/main
```

`pull`で取得と[マージ](/glossary/マージ/)をまとめて行うなら、[マージ](/glossary/マージ/)方式を明示します。

```bash
git pull --no-rebase --allow-unrelated-histories origin main
```

二つの[コマンド](/glossary/コマンド/)例は代替の手順です。両方を続けて実行する必要はありません。

公式文書は、この許可を常時有効にする設定変数は存在せず、追加もしないと説明しています。接続先の誤りを見逃さないためにも、必要な結合に限って指定します。

## 許可後にREADMEが競合した場合

同じ名前の[ファイル](/glossary/ファイル/)を両方で作っていると、履歴の結合を許可しても競合することがあります。今回の[Git](/glossary/git/) 2.51.1による確認では、READMEの内容が異なっていたため、次の表示になりました。

```text
CONFLICT (add/add): Merge conflict in README.md
Automatic merge failed; fix conflicts and then commit the result.
```

この時点では、無関係な履歴の拒否は通過しています。次に直すのは[ファイル](/glossary/ファイル/)内容の競合です。

```bash
git status
```

競合した[ファイル](/glossary/ファイル/)を開き、残す内容へ編集します。`<<<<<<<`、`=======`、`>>>>>>>`という競合の印も取り除きます。READMEだけが競合していた場合は、次で解消結果を記録できます。

```bash
git add README.md
git commit
```

ほかの[ファイル](/glossary/ファイル/)にも競合があれば、それぞれ解消して追加してください。今回の確認では、この操作後に二つの親[コミット](/glossary/コミット/)を持つマージコミットが作られました。

進行中の[マージ](/glossary/マージ/)を中止する場合は、次を使います。

```bash
git merge --abort
```

[mergeの公式文書](https://git-scm.com/docs/git-merge)は、開始前から未[コミット](/glossary/コミット/)の変更がある場合、元の状態を完全に[復元](/glossary/復元/)できない場合があると注意しています。変更の[保存](/glossary/保存/)は、[マージ](/glossary/マージ/)を始める前に行ってください。

## 結合しない場合と近いエラーの違い

ローカルの[コミット](/glossary/コミット/)履歴を残す必要がなく、[ファイル](/glossary/ファイル/)だけリモートの[プロジェクト](/glossary/プロジェクト/)へ追加したい場合は、別の[ディレクトリ](/glossary/ディレクトリ/)へcloneし、必要な[ファイル](/glossary/ファイル/)を移す方法があります。

```bash
git clone <repository-url> project-copy
```

元の[ディレクトリ](/glossary/ディレクトリ/)は残します。新しいclone先へ必要な[ファイル](/glossary/ファイル/)をコピーし、差分を確認して[コミット](/glossary/コミット/)してください。元の`.git`[ディレクトリ](/glossary/ディレクトリ/)はコピーしません。この方法では、ローカル側の過去の[コミット](/glossary/コミット/)履歴は引き継がれません。

`local changes would be overwritten by merge`は、手元の未[コミット](/glossary/コミット/)の変更が上書きされるという別の拒否です。変更を一時保管しても、今回の共通祖先の問題そのものは解消しません。

`failed to push some refs`はpushの失敗をまとめた表示で、原因はその前の説明を読む必要があります。今回の[エラー](/glossary/エラー/)を消すために強制pushすると、リモート側の履歴を置き換える可能性があります。二つの履歴を残す目的には使いません。

## 解決手順のまとめ

まず接続先と[ブランチ](/glossary/ブランチ/)を確認し、履歴を取得して`git merge-base`で共通祖先を調べます。浅い履歴なら、必要な履歴を取得してから判断します。

独立した二つの履歴を残して結合する場合だけ、`--allow-unrelated-histories`を付けて[マージ](/glossary/マージ/)します。許可後に[ファイル](/glossary/ファイル/)の競合が出た場合は、内容を解消して[コミット](/glossary/コミット/)します。

[ファイル](/glossary/ファイル/)だけを移したい場合は、別の場所にcloneし、元の[リポジトリ](/glossary/リポジトリ/)を残したまま必要な[ファイル](/glossary/ファイル/)を追加できます。接続先の誤り、履歴の結合、[ファイル](/glossary/ファイル/)の競合を分けて確認してください。

確認に使った[環境](/glossary/環境/)は[Git](/glossary/git/) 2.51.1です。通常[マージ](/glossary/マージ/)の拒否、共通祖先なしのmerge-base、許可後のREADME競合、解消後のマージコミットをローカルで確認しました。[GitHub](/glossary/github/)へのpushや、古い[Git](/glossary/git/)各版での実行確認は行っていません。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
