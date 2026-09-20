---
title: "Gitのdubious ownershipエラーの原因と解決策"
date: 2026-09-18
draft: false
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

`fatal: detected dubious ownership in repository at`は、[Git](/glossary/git/)が[リポジトリ](/glossary/リポジトリ/)の所有者を確認し、現在[Git](/glossary/git/)を実行している利用者と一致しないと判断したときに発生します。これは[ファイル](/glossary/ファイル/)を読み書きできないという意味ではなく、所有者の異なる[リポジトリ](/glossary/リポジトリ/)を信頼しないための安全機能です。

自分だけが使う[フォルダ](/glossary/フォルダ/)なら、まず所有者を確認し、誤って別の利用者や管理者の所有になっている場合は所有者を直します。共有[リポジトリ](/glossary/リポジトリ/)や[コンテナ](/glossary/コンテナ/)のように、所有者が異なる状態を意図している場合は、信頼できる[パス](/glossary/パス/)だけを`safe.directory`へ登録してください。

```bash
git config --global --add safe.directory "<repository-path>"
```

この[設定](/glossary/設定/)は原因となった所有者の違いを解消するものではありません。指定した[リポジトリ](/glossary/リポジトリ/)を例外として信頼する[設定](/glossary/設定/)です。内容を確認していない[リポジトリ](/glossary/リポジトリ/)や、外部から書き換えられる[フォルダ](/glossary/フォルダ/)は登録しないでください。

## エラーの概要

表示される[エラー](/glossary/エラー/)は次の形式です。

```text
fatal: detected dubious ownership in repository at '<path>'
To add an exception for this directory, call:

    git config --global --add safe.directory <path>
```

[Git](/glossary/git/)は通常、[Git](/glossary/git/)を実行している利用者が所有する[リポジトリ](/glossary/リポジトリ/)だけを信頼します。所有者が異なる場合、[リポジトリ](/glossary/リポジトリ/)内の[設定](/glossary/設定/)やフックを読み込む前に処理を止めます。[Gitの公式文書](https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory)では、所有者が異なっていても信頼する[ディレクトリ](/glossary/ディレクトリ/)を`safe.directory`で個別に登録できると説明されています。

この[エラー](/glossary/エラー/)はWindowsだけでなく、[Linux](/glossary/linux/)、macOS、[Docker](/glossary/docker/)などの[コンテナ](/glossary/コンテナ/)、CIでも発生します。特に、[ファイル](/glossary/ファイル/)を作成した利用者と[Git](/glossary/git/)を実行する利用者が異なる[環境](/glossary/環境/)で起こりやすくなります。

## まず所有者と設定を確認する

先に`safe.directory`を追加するのではなく、誰が[リポジトリ](/glossary/リポジトリ/)を所有しているかを確認します。

[Linux](/glossary/linux/)やmacOSでは、次の[コマンド](/glossary/コマンド/)で[フォルダ](/glossary/フォルダ/)の所有者[ID](/glossary/id/)と現在の利用者[ID](/glossary/id/)を比較できます。

```bash
ls -ldn "<repository-path>"
id -u
```

WindowsのPowerShellでは、次の[コマンド](/glossary/コマンド/)で[フォルダ](/glossary/フォルダ/)の所有者と現在の利用者を確認できます。

```powershell
(Get-Acl "C:\path\to\repository").Owner
whoami /user
```

すでに登録されている`safe.directory`と、その[設定](/glossary/設定/)が書かれている場所は次の[コマンド](/glossary/コマンド/)で確認できます。

```bash
git config --show-origin --get-all safe.directory
```

何も表示されない場合は、`safe.directory`が登録されていません。

## 信頼できるリポジトリだけを登録する

共有[フォルダ](/glossary/フォルダ/)や[コンテナ](/glossary/コンテナ/)のマウント先など、所有者が異なる状態を意図している場合は、対象の[リポジトリ](/glossary/リポジトリ/)を個別に登録します。[エラーメッセージ](/glossary/エラーメッセージ/)に表示された[パス](/glossary/パス/)を確認し、絶対[パス](/glossary/パス/)で指定してください。

```bash
git config --global --add safe.directory "<repository-path>"
```

Windowsでは、次のようにスラッシュを使った[パス](/glossary/パス/)も指定できます。

```powershell
git config --global --add safe.directory "C:/work/example"
```

[設定](/glossary/設定/)を残さず、その[コマンド](/glossary/コマンド/)だけ実行したい場合は`-c`を使います。

```bash
git -c safe.directory="<repository-path>" status
```

`safe.directory`は複数の値を持てる[設定](/glossary/設定/)です。別の[リポジトリ](/glossary/リポジトリ/)で同じ[エラー](/glossary/エラー/)が発生した場合、その[リポジトリ](/glossary/リポジトリ/)も個別に登録する必要があります。

## `.git/config`に書いても解決しない理由

次の[コマンド](/glossary/コマンド/)で[リポジトリ](/glossary/リポジトリ/)内の[設定](/glossary/設定/)へ追加しても、この[エラー](/glossary/エラー/)は解消しません。

```bash
# この設定では解消しない
git config --local --add safe.directory "<repository-path>"
```

`safe.directory`が有効なのは、system、global、[コマンド](/glossary/コマンド/)行の[設定](/glossary/設定/)だけです。[Git](/glossary/git/)ではこの3つを、利用者または管理者が管理する保護された[設定](/glossary/設定/)として扱います。[リポジトリ](/glossary/リポジトリ/)内の`.git/config`に書かれた値は無視されます。

これは、信頼できない[リポジトリ](/glossary/リポジトリ/)自身が`safe.directory`を書き換え、安全確認を無効にするのを防ぐためです。[Gitの設定範囲に関する公式文書](https://git-scm.com/docs/git-config#Documentation/git-config.txt-Protectedconfiguration)にも、保護された[設定](/glossary/設定/)はsystem、global、commandの3範囲だと記載されています。

## 所有者の設定を直す

自分だけが使う[リポジトリ](/glossary/リポジトリ/)なのに所有者が別の利用者になっている場合は、例外を増やすより所有者を直した方が再発を防げます。

[Linux](/glossary/linux/)では、対象が自分の管理する[リポジトリ](/glossary/リポジトリ/)であることを確認してから、所有者を現在の利用者へ変更します。

```bash
sudo chown -R "$(id -u):$(id -g)" "<repository-path>"
```

`-R`は配下の[ファイル](/glossary/ファイル/)にも変更を適用します。共有[リポジトリ](/glossary/リポジトリ/)やシステム管理者が用意した[フォルダ](/glossary/フォルダ/)では、管理方針を確認せずに実行しないでください。

Windowsでは、[フォルダ](/glossary/フォルダ/)の[プロパティ](/glossary/プロパティ/)にある「[セキュリティ](/glossary/セキュリティ/)」の詳細設定から所有者を変更できます。[コマンド](/glossary/コマンド/)で変更する場合は、管理者として開いたPowerShellまたは[コマンドプロンプト](/glossary/コマンドプロンプト/)で次を実行します。

```powershell
takeown /f "C:\path\to\repository" /r
```

`takeown`は所有者を変更する[コマンド](/glossary/コマンド/)です。`/r`を付けると配下にも適用されます。[Microsoftの公式文書](https://learn.microsoft.com/windows-server/administration/windows-commands/takeown)では、`/a`を付けない場合は現在ログオンしている利用者が所有者になると説明されています。会社や学校の端末では、[権限管理](/glossary/権限管理/)に影響するため管理者へ確認してください。

## コンテナやCIで発生する場合

[Docker](/glossary/docker/)などでホストの[フォルダ](/glossary/フォルダ/)をマウントすると、ホスト側で[ファイル](/glossary/ファイル/)を作った利用者[ID](/glossary/id/)と、[コンテナ](/glossary/コンテナ/)内で[Git](/glossary/git/)を実行する利用者[ID](/glossary/id/)が異なる場合があります。

```bash
ls -ldn "<repository-path>"
id -u
```

2つの[ID](/glossary/id/)が異なる場合は、[コンテナ](/glossary/コンテナ/)をホストと同じ利用者[ID](/glossary/id/)で動かす、マウント先の所有者を実行利用者に合わせる、信頼できる作業[ディレクトリ](/glossary/ディレクトリ/)だけを`safe.directory`へ登録する、という順で対処を検討します。

CIで実行のたびに[環境](/glossary/環境/)が作り直される場合は、処理の開始時に対象の作業[ディレクトリ](/glossary/ディレクトリ/)を登録します。固定[パス](/glossary/パス/)だからという理由だけで、すべての[リポジトリ](/glossary/リポジトリ/)を許可する[設定](/glossary/設定/)へ広げないでください。

## `sudo`で実行した場合

[Linux](/glossary/linux/)などで[Git](/glossary/git/)がrootとして動いている場合、[Git](/glossary/git/)は`SUDO_UID`も確認します。これは、通常の利用者が`sudo`を使って[インストール](/glossary/インストール/)処理を実行する場面に対応するためです。[Git本体の実装](https://github.com/git/git/blob/master/git-compat-util.h)と[公式文書](https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory)の両方で確認できます。

`sudo -i`や`su -`など、元の利用者を示す情報が引き継がれない実行方法では、同じ[フォルダ](/glossary/フォルダ/)でも所有者が一致しないと判断されることがあります。[Git](/glossary/git/)をrootで動かす必要があるかを先に確認し、通常の利用者で実行できる処理なら`sudo`を外してください。

## 広い範囲を許可するときの注意点

現在の[Git](/glossary/git/)公式文書では、[パス](/glossary/パス/)の末尾に`/*`を付けると、その[ディレクトリ](/glossary/ディレクトリ/)配下にある[リポジトリ](/glossary/リポジトリ/)をまとめて登録できます。

```bash
git config --global --add safe.directory "/srv/git/*"
```

この形式は、[Git 2.46.0のリリースノート](https://github.com/git/git/blob/master/Documentation/RelNotes/2.46.0.adoc)で追加が案内されています。古い[Git](/glossary/git/)では利用できない可能性があるため、先に版を確認してください。

```bash
git --version
```

次の[設定](/glossary/設定/)は、所有者の確認をすべての[リポジトリ](/glossary/リポジトリ/)で無効にします。

```bash
git config --global --add safe.directory "*"
```

信頼できない場所に置かれた[リポジトリ](/glossary/リポジトリ/)も対象になるため、通常の解決方法としては推奨できません。個別の[パス](/glossary/パス/)を登録するか、所有者の[設定](/glossary/設定/)を直してください。

## 似ているが別のエラー

`fatal: not a git repository`は、現在の場所から[Git](/glossary/git/)[リポジトリ](/glossary/リポジトリ/)を見つけられない場合の[エラー](/glossary/エラー/)です。所有者の確認で止まっているわけではありません。

`Permission denied`は、[ファイル](/glossary/ファイル/)や[ディレクトリ](/glossary/ディレクトリ/)を読み書きする[権限](/glossary/権限/)がない場合に発生します。`detected dubious ownership`は、読み書きできる場合でも所有者が異なれば発生します。

`cannot use bare repository ... safe.bareRepository`は、ベアリポジトリを使える条件に関する別の安全機能です。`safe.directory`ではなく`safe.bareRepository`の[設定](/glossary/設定/)を確認します。

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

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は[Git](/glossary/git/)および各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
