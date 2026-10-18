---
title: "Gitリポジトリが見つからない時の対処法"
date: 2026-10-14
slug: git_not_a_git_repository
draft: false
description: "fatal: not a git repositoryが出たら、現在の場所とclone先を確認します。新規initと既存履歴の復旧を区別し、ZIP取得、.gitファイル、GIT_DIR、探索範囲の設定も確認します。"
tags: ["Git"]
images: ["og/posts/git_not_a_git_repository.png"]
errorCode: "not a git repository"
service: "Git"
error_type: "repository_not_found_local"
components: ["repository discovery"]
related_services: ["GitHub"]
trend_incident: false
---

## 冒頭まとめ

`git status`や`git add`で次の[エラー](/glossary/エラー/)が出たら、まず[コマンド](/glossary/コマンド/)を実行している場所を確認します。

```text
fatal: not a git repository (or any of the parent directories): .git
```

[Git](/glossary/git/)が、その場所から利用できる[リポジトリ](/glossary/リポジトリ/)を見つけられていません。cloneでできた[ディレクトリ](/glossary/ディレクトリ/)へ移動せず、その親で操作している場合もあります。

```bash
cd repo
git status
```

`repo`は実際の保存先に置き換えます。既存の[リポジトリ](/glossary/リポジトリ/)を使うつもりなら、[エラー](/glossary/エラー/)を消すためにその場で`git init`するのではなく、正しい場所を確認してください。

## Gitは現在の場所から親へ探す

[Gitの公式文書](https://git-scm.com/docs/git#Documentation/git.txt-GITDISCOVERYACROSSFILESYSTEM)は、現在の[ディレクトリ](/glossary/ディレクトリ/)に[リポジトリ](/glossary/リポジトリ/)がなければ、親をたどって探すと説明しています。既定ではファイルシステムの境界を越えません。[環境変数](/glossary/環境変数/)によって探索先が指定・制限されている場合もあります。

通常の作業[ディレクトリ](/glossary/ディレクトリ/)では、`.git`に履歴や[設定](/glossary/設定/)の管理情報があります。ただし、[Git](/glossary/git/)が探すのは子[ディレクトリ](/glossary/ディレクトリ/)ではありません。`Downloads/repo`が[リポジトリ](/glossary/リポジトリ/)でも、`Downloads`から`git status`を実行して、その中の`repo`を自動で選ぶわけではありません。

反対に、[リポジトリ](/glossary/リポジトリ/)の下にある`repo/src`からは、通常は親の管理情報を見つけられます。必ず一番上で実行しなければならない、という意味でもありません。

この[エラー](/glossary/エラー/)は、[Git](/glossary/git/)の[インストール](/glossary/インストール/)失敗や通信障害を直接示すものではありません。少なくとも、表示された[Git](/glossary/git/)の[コマンド](/glossary/コマンド/)は起動しています。

## 現在の場所とclone先を確認する

macOS・[Linux](/glossary/linux/)・[Git](/glossary/git/) Bashでは、次で現在の場所と隠し[ファイル](/glossary/ファイル/)を確認できます。

```bash
pwd
ls -a
```

Windowsの[コマンドプロンプト](/glossary/コマンドプロンプト/)では次を使います。

```bat
cd
dir /a
```

[リポジトリ](/glossary/リポジトリ/)と思われる場所へ移動し、[Git](/glossary/git/)自身に確認させます。

```bash
git rev-parse --is-inside-work-tree
git rev-parse --show-toplevel
```

[rev-parseの公式文書](https://git-scm.com/docs/git-rev-parse)によると、最初の指定は作業[ディレクトリ](/glossary/ディレクトリ/)内なら`true`を表示し、後の指定は作業[ディレクトリ](/glossary/ディレクトリ/)の最上位を表示します。今回の[Git](/glossary/git/) 2.51.1による確認では、[リポジトリ](/glossary/リポジトリ/)外の最初の[コマンド](/glossary/コマンド/)は、冒頭の[エラー](/glossary/エラー/)で終了[コード](/glossary/コード/)128となりました。

[cloneの公式文書](https://git-scm.com/docs/git-clone)は、新しい[ディレクトリ](/glossary/ディレクトリ/)に[リポジトリ](/glossary/リポジトリ/)を複製する操作を説明しています。保存先の名前を明示すると、移動先も分かりやすくなります。

```bash
git clone <repository-url> repo
cd repo
git status
```

`<repository-url>`は実際の[URL](/glossary/url/)へ置き換えます。cloneが失敗していた場合は、その出力を先に確認してください。

場所を移動せずに指定する方法もあります。

```bash
git -C repo status
```

`-C`は、指定した場所で[Git](/glossary/git/)を実行するための指定です。エディターや自動処理から呼んでいる場合も、実際の作業場所がどこになっているかを確認します。

[GitHub DesktopのIssue #11413](https://github.com/desktop/desktop/issues/11413)には、指定した親[ディレクトリ](/glossary/ディレクトリ/)ではなく、その下の[リポジトリ](/glossary/リポジトリ/)名の[ディレクトリ](/glossary/ディレクトリ/)に`.git`が作られたという報告があります。今回の[CLI](/glossary/cli/)の全文と同じ表示の報告ではありませんが、保存先の思い違いを確認する関連事例です。

## 新規管理とZIPからの取得を区別する

自分の[ファイル](/glossary/ファイル/)を新しく[Git](/glossary/git/)で管理し始めたい場合は、対象[ディレクトリ](/glossary/ディレクトリ/)で[初期化](/glossary/初期化/)します。

```bash
cd my-project
git init
git status
```

[initの公式文書](https://git-scm.com/docs/git-init)は、空の[リポジトリ](/glossary/リポジトリ/)を作る、または既存の[リポジトリ](/glossary/リポジトリ/)を再初期化する操作と説明しています。新規初期化だけでは、ほかの場所にあった過去の履歴やリモート[設定](/glossary/設定/)が戻るわけではありません。

[GitHub](/glossary/github/)のDownload [ZIP](/glossary/zip/)で取得したものも、cloneとは異なります。[GitHubのアーカイブ公式説明](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives)では、[ZIP](/glossary/zip/)などの[アーカイブ](/glossary/アーカイブ/)は[ファイル](/glossary/ファイル/)のスナップショットで、[リポジトリ](/glossary/リポジトリ/)の履歴を含まないと説明しています。

元の履歴と接続して作業したいなら、別の新しい場所へcloneします。[ZIP](/glossary/zip/)側や元の作業[ディレクトリ](/glossary/ディレクトリ/)に変更がある場合は、それを残したまま、必要な[ファイル](/glossary/ファイル/)をclone先へ移し、差分を確認してください。`.git`を上書きするコピーは行いません。

## .gitがあっても認識されない場合

空の`.git`[ディレクトリ](/glossary/ディレクトリ/)を作るだけでは、[リポジトリ](/glossary/リポジトリ/)にはなりません。今回の確認でも、空の`.git`だけがある場所の`git status`は同じ[エラー](/glossary/エラー/)になりました。

[Git 2.51.1の探索実装](https://github.com/git/git/blob/v2.51.1/setup.c)には、HEADの書式、[オブジェクト](/glossary/オブジェクト/)の保存先、参照情報を確認する処理があります。ただし、それらが必ず同じ`.git`の直下に全部あるとは限りません。

[リポジトリ構成の公式文書](https://git-scm.com/docs/gitrepository-layout)によると、`.git`は[ディレクトリ](/glossary/ディレクトリ/)ではなく、実際の管理情報の場所を示す[ファイル](/glossary/ファイル/)の場合もあります。worktreeやsubmoduleで使われる構成です。今回作成したworktreeでは、`.git`が[ファイル](/glossary/ファイル/)でも`git status`は成功しました。

したがって、`.git`が[ファイル](/glossary/ファイル/)だから壊れていると判断して[削除](/glossary/削除/)しないでください。参照先へアクセスできるか、元の[リポジトリ](/glossary/リポジトリ/)を移動していないかを確認します。

以前は正常だったのに管理情報がなくなっている場合は、作業[ファイル](/glossary/ファイル/)と残っている管理情報を先に保全します。リモートから別の場所へcloneすれば、そのリモートにある履歴は取得できますが、未pushの[コミット](/glossary/コミット/)まで戻るとは限りません。それらは[バックアップ](/glossary/バックアップ/)や元の管理情報からの[復旧](/glossary/復旧/)が必要です。

## 環境変数と探索範囲を確認する

正しい場所なのに見つからない場合は、[Git](/glossary/git/)の探索に関係する[環境変数](/glossary/環境変数/)を確認します。Windowsの[コマンドプロンプト](/glossary/コマンドプロンプト/)なら、次で該当する[変数](/glossary/変数/)を表示できます。

```bat
set GIT_
```

macOS・[Linux](/glossary/linux/)・[Git](/glossary/git/) Bashでは、必要な値だけを表示できます。

```bash
printf '%s\n' "$GIT_DIR" "$GIT_WORK_TREE" "$GIT_CEILING_DIRECTORIES" "$GIT_DISCOVERY_ACROSS_FILESYSTEM"
```

[Gitの環境変数の公式説明](https://git-scm.com/docs/git)に、それぞれの用途があります。

| [変数](/glossary/変数/) | 確認する内容 |
|---|---|
| `GIT_DIR` | 通常の探索先ではなく、指定した管理情報の場所を使っていないか |
| `GIT_WORK_TREE` | 作業[ディレクトリ](/glossary/ディレクトリ/)の場所を別に指定していないか |
| `GIT_CEILING_DIRECTORIES` | 親へたどる範囲を制限していないか |
| `GIT_DISCOVERY_ACROSS_FILESYSTEM` | ファイルシステムの境界を越える探索を許可するか |

意図せず残った値か、道具が必要として[設定](/glossary/設定/)した値かを確認します。全変数をまとめて[削除](/glossary/削除/)するのではなく、誤っている指定だけを[修正](/glossary/修正/)してください。

`GIT_CEILING_DIRECTORIES`は、指定した親[ディレクトリ](/glossary/ディレクトリ/)へ上がる探索を制限します。現在の[ディレクトリ](/glossary/ディレクトリ/)自体や、明示した`GIT_DIR`を除外する指定ではありません。今回も、子[ディレクトリ](/glossary/ディレクトリ/)から親の[リポジトリ](/glossary/リポジトリ/)へ到達する探索を制限すると、同じ拒否を再現できました。

## 似たエラーの文言で確認先を分ける

`GIT_DIR`に存在しない場所を指定した確認では、次の別の文言になりました。

```text
fatal: not a git repository: '/path/to/missing'
```

この場合は、現在の場所だけでなく、明示された管理情報の[パス](/glossary/パス/)を確認します。

次の文言なら、探索がファイルシステムの境界で停止しています。

```text
fatal: not a git repository (or any parent up to mount point ...)
Stopping at filesystem boundary (GIT_DISCOVERY_ACROSS_FILESYSTEM not set).
```

公式文書には、`GIT_DISCOVERY_ACROSS_FILESYSTEM`を有効にすると境界を越えて探索する説明があります。ただし、別のマウント先にある[リポジトリ](/glossary/リポジトリ/)を使いたいなら、まずその実際の場所へ移動するか、`git -C`で明示します。探索範囲を広げれば管理情報が[復元](/glossary/復元/)されるわけではありません。

`detected dubious ownership`は、見つかった[リポジトリ](/glossary/リポジトリ/)の所有者に関する拒否です。今回の[エラー](/glossary/エラー/)への一般的な対処として、`safe.directory`を追加する必要はありません。

[GitHub](/glossary/github/)の`Repository not found`は、リモートの[URL](/glossary/url/)や[アクセス権](/glossary/アクセス権/)に関係する別の問題です。今回の`git status`の最小例は外部通信なしで発生しています。

## 解決手順のまとめ

現在の場所とclone先を確認し、[リポジトリ](/glossary/リポジトリ/)へ移動するか`git -C`で指定します。認識できたら、`git rev-parse --show-toplevel`で対象が意図した場所か確認してください。

新しく管理を始める場合だけ`git init`を使います。[ZIP](/glossary/zip/)取得や管理情報の欠損から既存の履歴を使いたい場合は、元の変更を残し、cloneや[バックアップ](/glossary/バックアップ/)からの[復旧](/glossary/復旧/)を検討します。

この記事では[Linux](/glossary/linux/)上の[Git](/glossary/git/) 2.51.1で、[リポジトリ](/glossary/リポジトリ/)外、clone後の親[ディレクトリ](/glossary/ディレクトリ/)、子[ディレクトリ](/glossary/ディレクトリ/)からの探索、空の`.git`、不正な`GIT_DIR`、探索範囲の制限、正常なworktreeの`.git`[ファイル](/glossary/ファイル/)を確認しました。Windowsでの[コマンド](/glossary/コマンド/)実行と、実際のマウント境界での再現は未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
