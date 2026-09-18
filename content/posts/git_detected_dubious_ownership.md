---
title: "Gitのdubious ownershipエラーの原因と解決策"
date: 2026-09-18
draft: true
description: "Gitでfatal: detected dubious ownership in repository atと表示されるのは、リポジトリの所有者とGitを実行している利用者が一致しないためです。信頼できるリポジトリならsafe.directoryへ登録できますが、所有者の設定を直した方がよい場合もあります。Windows、Linux、コンテナでの確認方法と安全な対処を説明します。"
tags: ["Git"]
images: ["og/posts/git_detected_dubious_ownership.png"]
errorCode: "fatal: detected dubious ownership in repository at"
urgency: "medium"
service: "Git"
error_type: "fatal: detected dubious ownership in repository at"
components: ["safe.directory", "repository ownership"]
related_services: ["Docker", "GitHub Actions"]
trend_incident: false
---

## 冒頭まとめ

`fatal: detected dubious ownership in repository at`は、Gitがリポジトリの所有者を確認し、現在Gitを実行している利用者と一致しないと判断したときに発生します。これはファイルを読み書きできないという意味ではなく、所有者の異なるリポジトリを信頼しないための安全機能です。

自分だけが使うフォルダなら、まず所有者を確認し、誤って別の利用者や管理者の所有になっている場合は所有者を直します。共有リポジトリやコンテナのように、所有者が異なる状態を意図している場合は、信頼できるパスだけを`safe.directory`へ登録してください。

```bash
git config --global --add safe.directory "<repository-path>"
```

この設定は原因となった所有者の違いを解消するものではありません。指定したリポジトリを例外として信頼する設定です。内容を確認していないリポジトリや、外部から書き換えられるフォルダは登録しないでください。

## エラーの概要

表示されるエラーは次の形式です。

```text
fatal: detected dubious ownership in repository at '<path>'
To add an exception for this directory, call:

    git config --global --add safe.directory <path>
```

Gitは通常、Gitを実行している利用者が所有するリポジトリだけを信頼します。所有者が異なる場合、リポジトリ内の設定やフックを読み込む前に処理を止めます。[Gitの公式文書](https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory)では、所有者が異なっていても信頼するディレクトリを`safe.directory`で個別に登録できると説明されています。

このエラーはWindowsだけでなく、Linux、macOS、Dockerなどのコンテナ、CIでも発生します。特に、ファイルを作成した利用者とGitを実行する利用者が異なる環境で起こりやすくなります。

## まず所有者と設定を確認する

先に`safe.directory`を追加するのではなく、誰がリポジトリを所有しているかを確認します。

LinuxやmacOSでは、次のコマンドでフォルダの所有者IDと現在の利用者IDを比較できます。

```bash
ls -ldn "<repository-path>"
id -u
```

WindowsのPowerShellでは、次のコマンドでフォルダの所有者と現在の利用者を確認できます。

```powershell
(Get-Acl "C:\path\to\repository").Owner
whoami /user
```

すでに登録されている`safe.directory`と、その設定が書かれている場所は次のコマンドで確認できます。

```bash
git config --show-origin --get-all safe.directory
```

何も表示されない場合は、`safe.directory`が登録されていません。

## 信頼できるリポジトリだけを登録する

共有フォルダやコンテナのマウント先など、所有者が異なる状態を意図している場合は、対象のリポジトリを個別に登録します。エラーメッセージに表示されたパスを確認し、絶対パスで指定してください。

```bash
git config --global --add safe.directory "<repository-path>"
```

Windowsでは、次のようにスラッシュを使ったパスも指定できます。

```powershell
git config --global --add safe.directory "C:/work/example"
```

設定を残さず、そのコマンドだけ実行したい場合は`-c`を使います。

```bash
git -c safe.directory="<repository-path>" status
```

`safe.directory`は複数の値を持てる設定です。別のリポジトリで同じエラーが発生した場合、そのリポジトリも個別に登録する必要があります。

## `.git/config`に書いても解決しない理由

次のコマンドでリポジトリ内の設定へ追加しても、このエラーは解消しません。

```bash
# この設定では解消しない
git config --local --add safe.directory "<repository-path>"
```

`safe.directory`が有効なのは、system、global、コマンド行の設定だけです。Gitではこの3つを、利用者または管理者が管理する保護された設定として扱います。リポジトリ内の`.git/config`に書かれた値は無視されます。

これは、信頼できないリポジトリ自身が`safe.directory`を書き換え、安全確認を無効にするのを防ぐためです。[Gitの設定範囲に関する公式文書](https://git-scm.com/docs/git-config#Documentation/git-config.txt-Protectedconfiguration)にも、保護された設定はsystem、global、commandの3範囲だと記載されています。

## 所有者の設定を直す

自分だけが使うリポジトリなのに所有者が別の利用者になっている場合は、例外を増やすより所有者を直した方が再発を防げます。

Linuxでは、対象が自分の管理するリポジトリであることを確認してから、所有者を現在の利用者へ変更します。

```bash
sudo chown -R "$(id -u):$(id -g)" "<repository-path>"
```

`-R`は配下のファイルにも変更を適用します。共有リポジトリやシステム管理者が用意したフォルダでは、管理方針を確認せずに実行しないでください。

Windowsでは、フォルダのプロパティにある「セキュリティ」の詳細設定から所有者を変更できます。コマンドで変更する場合は、管理者として開いたPowerShellまたはコマンドプロンプトで次を実行します。

```powershell
takeown /f "C:\path\to\repository" /r
```

`takeown`は所有者を変更するコマンドです。`/r`を付けると配下にも適用されます。[Microsoftの公式文書](https://learn.microsoft.com/windows-server/administration/windows-commands/takeown)では、`/a`を付けない場合は現在ログオンしている利用者が所有者になると説明されています。会社や学校の端末では、権限管理に影響するため管理者へ確認してください。

## コンテナやCIで発生する場合

Dockerなどでホストのフォルダをマウントすると、ホスト側でファイルを作った利用者IDと、コンテナ内でGitを実行する利用者IDが異なる場合があります。

```bash
ls -ldn "<repository-path>"
id -u
```

2つのIDが異なる場合は、コンテナをホストと同じ利用者IDで動かす、マウント先の所有者を実行利用者に合わせる、信頼できる作業ディレクトリだけを`safe.directory`へ登録する、という順で対処を検討します。

CIで実行のたびに環境が作り直される場合は、処理の開始時に対象の作業ディレクトリを登録します。固定パスだからという理由だけで、すべてのリポジトリを許可する設定へ広げないでください。

## `sudo`で実行した場合

LinuxなどでGitがrootとして動いている場合、Gitは`SUDO_UID`も確認します。これは、通常の利用者が`sudo`を使ってインストール処理を実行する場面に対応するためです。[Git本体の実装](https://github.com/git/git/blob/master/git-compat-util.h)と[公式文書](https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory)の両方で確認できます。

`sudo -i`や`su -`など、元の利用者を示す情報が引き継がれない実行方法では、同じフォルダでも所有者が一致しないと判断されることがあります。Gitをrootで動かす必要があるかを先に確認し、通常の利用者で実行できる処理なら`sudo`を外してください。

## 広い範囲を許可するときの注意点

現在のGit公式文書では、パスの末尾に`/*`を付けると、そのディレクトリ配下にあるリポジトリをまとめて登録できます。

```bash
git config --global --add safe.directory "/srv/git/*"
```

この形式は、[Git 2.46.0のリリースノート](https://github.com/git/git/blob/master/Documentation/RelNotes/2.46.0.adoc)で追加が案内されています。古いGitでは利用できない可能性があるため、先に版を確認してください。

```bash
git --version
```

次の設定は、所有者の確認をすべてのリポジトリで無効にします。

```bash
git config --global --add safe.directory "*"
```

信頼できない場所に置かれたリポジトリも対象になるため、通常の解決方法としては推奨できません。個別のパスを登録するか、所有者の設定を直してください。

## 似ているが別のエラー

`fatal: not a git repository`は、現在の場所からGitリポジトリを見つけられない場合のエラーです。所有者の確認で止まっているわけではありません。

`Permission denied`は、ファイルやディレクトリを読み書きする権限がない場合に発生します。`detected dubious ownership`は、読み書きできる場合でも所有者が異なれば発生します。

`cannot use bare repository ... safe.bareRepository`は、ベアリポジトリを使える条件に関する別の安全機能です。`safe.directory`ではなく`safe.bareRepository`の設定を確認します。

## 確認コマンド集

```bash
# Gitの版を確認する
git --version

# 登録済みのsafe.directoryと設定元を確認する
git config --show-origin --get-all safe.directory

# 信頼できるリポジトリを1件登録する
git config --global --add safe.directory "<repository-path>"

# 設定を残さずに1回だけ実行する
git -c safe.directory="<repository-path>" status

# POSIX系OSでフォルダの所有者IDを確認する
ls -ldn "<repository-path>"

# POSIX系OSで現在の利用者IDを確認する
id -u
```

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報はGitおよび各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
