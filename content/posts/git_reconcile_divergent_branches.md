---
title: "Gitの分岐した履歴のpull対処法"
date: 2026-10-11
slug: git_reconcile_divergent_branches
draft: false
description: "fatal: Need to specify how to reconcile divergent branches.は、git pullが分岐した履歴の取り込み方を決められず停止したときのエラーです。マージ・リベース・早送りのみの違い、設定の確認、競合時の続行と中止を説明します。"
tags: ["Git", "GitHub"]
images: ["og/posts/git_reconcile_divergent_branches.png"]
errorCode: "Need to specify how to reconcile divergent branches"
service: "Git"
error_type: "divergent_branches"
components: ["git pull"]
related_services: ["GitHub"]
trend_incident: false
---

## 冒頭まとめ

`git pull`で次のエラーが出た場合、取得した履歴を現在のブランチへどう取り込むかが指定されていません。

```text
fatal: Need to specify how to reconcile divergent branches.
```

典型的には、ローカルとリモートの両方に、それぞれ独自のコミットがあります。コミットは変更を記録した単位です。マージで両方の履歴を結合するか、リベースでローカルのコミットを取り込み先の上に作り直すかを決めます。

既存のコミットをそのまま残して結合するなら、今回の操作だけマージを指定できます。

```bash
git pull --no-rebase --ff origin main
```

`origin`と`main`は例です。実際の接続先と取り込むブランチに置き換えてください。共同開発では、プロジェクトで決めている方法に合わせます。

## エラーは取り込み方を決める段階で出る

[Git 2.51のpull公式文書](https://git-scm.com/docs/git-pull/2.51.0)は、ローカルがリモートより遅れているだけなら早送りし、履歴が分岐していればマージかリベースを指定する必要があると説明しています。早送りは、新しいコミットを作らず、ブランチの先端を既存のコミットへ進める更新です。

[Git 2.51.1のpull実装](https://github.com/git/git/blob/v2.51.1/builtin/pull.c)では、早送りできず、現在の履歴が既に取り込み先を含んでいるわけでもない場合に、分岐と判定します。取り込み方が未指定なら、マージやリベースを始める前に終了します。

したがって、このエラーだけでファイルの競合が起きたとは判断できません。ただし、`pull`の前半にあるfetchは既に実行されています。現在のコミットが変わらなくても、`origin/main`などのリモート追跡情報は更新されている場合があります。

この記事ではGit 2.51.1を使い、共通のコミットからローカルとリモートを別々に進めて確認しました。方式未指定のpullは終了コード128となり、現在のコミットは変わらず、上記のエラーと`hint:`付きの案内が表示されました。

## 接続先・分岐・設定を確認する

取り込む対象と現在の状態を確認します。

```bash
git status
git remote -v
git branch -vv
git fetch origin
git log --oneline --graph --decorate --all
git rev-list --left-right --count HEAD...origin/main
```

最後のコマンドは、二つの履歴のうち片側だけに存在するコミット数を表示します。`HEAD`側が左、`origin/main`側が右です。今回の再現では`1 1`となり、両側に独自のコミットがありました。接続先やブランチ名のエラーが出た場合は、先にその指定を直します。

次に、設定値と、その設定がどのファイルから来ているかを確認します。

```bash
git config --show-origin --get pull.rebase
git config --show-origin --get pull.ff
git branch --show-current
```

現在のブランチが`main`なら、ブランチ専用の設定も確認します。

```bash
git config --show-origin --get branch.main.rebase
```

該当する設定がなければ、`git config --get`は値を表示しません。ブランチ専用のrebase設定は`pull.rebase`より先に参照されます。全体の設定だけを変更しても、ブランチ専用の指定が残っている場合があります。

## マージ・リベース・早送りのみの違い

案内にある三つの方法は、同じ結果になる設定ではありません。

| 方法 | 分岐した履歴への動作 | 今回だけ指定する例 |
|---|---|---|
| マージ | 既存の両側のコミットを残し、結合するコミットを作る | `git pull --no-rebase --ff origin main` |
| リベース | ローカル側のコミットを取り込み先の上に作り直す | `git pull --rebase origin main` |
| 早送りのみ | 先端を進めるだけで取り込める場合に限って更新する | `git pull --ff-only origin main` |

マージの例に付けた`--ff`は、早送りできればそれを使い、できなければ通常のマージを許可する指定です。既存の`pull.ff=only`がある環境でも、今回のマージを明示できます。`--ff-only`とは異なります。

リベースではコミットが作り直されるため、識別するIDが変わります。[Gitのrebase公式文書](https://git-scm.com/docs/git-rebase)には、他の人が既に利用している履歴を書き換えた場合の問題が説明されています。共有済みのコミットを含む場合は、チームの運用を確認します。

早送りのみは、分岐の解消方法ではありません。今回の再現でも、分岐した状態で指定すると次のエラーになりました。

```text
fatal: Not possible to fast-forward, aborting.
```

同じ再現用リポジトリで、マージとリベースはそれぞれ成功しました。今回は異なるファイルを変更したため、競合はありませんでした。実際の変更内容によっては、どちらでも競合が起こります。

## 既定の方法はリポジトリ単位で設定する

毎回同じ方式を使う運用なら、このリポジトリに設定できます。次の例は互いに別の方針であり、まとめて実行するものではありません。

マージを使う方針なら、次を設定します。

```bash
git config --local pull.rebase false
```

リベースを使う方針なら、次を設定します。

```bash
git config --local pull.rebase true
```

分岐した場合は自動で取り込まず止める方針なら、次を設定します。

```bash
git config --local pull.ff only
```

[Gitの設定公式文書](https://git-scm.com/docs/git-config/2.51.0)には、`pull.rebase`、`pull.ff`、ブランチ専用の`branch.<名前>.rebase`が説明されています。これらは別の設定なので、例えば`pull.rebase=false`を入れても、既存の`pull.ff=only`が自動で消えるわけではありません。

`--global`を使うと、そのユーザーのほかのリポジトリにも既定値が適用されます。今回の一件を直すために、全リポジトリの方針まで変更する必要はありません。まずコマンドの引数で今回だけ指定するか、対象リポジトリに設定します。

## 取り込みを始めた後に競合した場合

方式を指定して進めた後、同じ箇所の変更などが競合することがあります。これは方式未指定による停止とは別の段階です。

マージ中なら、競合したファイルを編集して内容を決め、解消したファイルを追加して続行します。

```bash
git status
git add <resolved-file>
git merge --continue
```

リベース中なら、同様に解消したファイルを追加し、リベースを続行します。

```bash
git status
git add <resolved-file>
git rebase --continue
```

`<resolved-file>`は解消したファイル名に置き換えます。取り込みを中止する場合は、進行中の操作に対応するコマンドだけを使います。

```bash
# マージ中の場合
git merge --abort

# リベース中の場合
git rebase --abort
```

今回の方式未指定エラーで止まっただけなら、マージやリベースは始まっていないため、この中止操作は不要です。

操作前に未コミットの変更がある場合は、内容を確認してコミットするか一時保管します。[mergeの公式文書](https://git-scm.com/docs/git-merge)は、開始前の未コミット変更を中止時に完全に復元できない場合があると注意しています。中止コマンドを使えばどんな状態でも安全に戻せる、とは考えないでください。

## 無関係な履歴の拒否や同期画面との違い

今回のエラーが出たからといって、共通の祖先があるとは限りません。今回のGit 2.51.1による確認では、別々に初期化した履歴でも、方式未指定なら先に同じエラーが表示されました。マージ方式を指定した後で、次のエラーになりました。

```text
fatal: refusing to merge unrelated histories
```

これは、共通の祖先が見つからない履歴の結合をマージが拒否したという別の条件です。今回のエラーへの一般的な対処として、`--allow-unrelated-histories`を付ける必要はありません。接続先と履歴を確認し、独立した履歴を意図的に結合する場合だけ検討します。

`local changes would be overwritten by merge`は、未コミットの変更が上書きされる場合の拒否です。変更を一時保管しても、コミット済みの分岐をどう取り込むかは別に決める必要があります。

[VS CodeのIssue #198210](https://github.com/microsoft/vscode/issues/198210)には、手元とリモートをそれぞれ更新し、同期ボタンから実行された`git pull --tags origin main`が今回のエラーで停止した報告があります。画面上の同期操作でも、内部のGitコマンドと設定を確認する必要があることを示す実例です。すべてのVS Code環境で同じ挙動になるという意味ではありません。

## 解決手順のまとめ

接続先と取り込むブランチを確認し、ローカルと取得先の履歴、`pull.rebase`、`pull.ff`、ブランチ専用のrebase設定を調べます。

両方の既存コミットを残す方針ならマージ、ローカルのコミットを取り込み先の上に作り直す方針ならリベースを選びます。早送りのみは、分岐した履歴を自動でまとめず止める方針です。案内の三つの設定を一括で実行しないでください。

この記事はGit 2.51.1で、方式未指定の停止、マージ・リベースの成功、早送りのみの拒否、無関係な履歴での表示順序をローカルで確認しました。fatal表示が導入された最初のGitの版は特定していません。開発中のmasterの説明を、すべてのGitの既定動作として扱うことも避けています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
