---
title: "Gitのorigin重複エラー対処法"
date: 2026-10-17
slug: git_remote_origin_already_exists
draft: false
description: "error: remote origin already exists.は、同名のリモートが登録済みという意味です。git remote -vで確認し、URL変更はset-url、別の接続先の追加は別名を使います。削除や改名による追跡情報への影響も説明します。"
tags: ["Git", "GitHub"]
images: ["og/posts/git_remote_origin_already_exists.png"]
errorCode: "remote origin already exists"
service: "Git"
error_type: "remote_name_exists"
components: ["git remote"]
related_services: ["GitHub"]
trend_incident: false
---

## 冒頭まとめ

`git remote add origin ...`で次のエラーが出たら、同じ名前のリモートが既に登録されています。リモートは、取得先や送信先のリポジトリに付ける名前です。

```text
error: remote origin already exists.
```

まず登録済みの名前とURLを確認します。

```bash
git remote -v
```

URLが目的のものなら追加し直す必要はありません。既存の`origin`のURLを変えたいなら、`add`ではなく次を使います。

```bash
git remote set-url origin https://github.com/OWNER/REPOSITORY.git
```

URLは実際の接続先へ置き換えます。元の接続先も残したい場合は、後述する別名での追加を使ってください。

## originは登録名であり接続エラーではない

[GitHubのリモート管理の公式説明](https://docs.github.com/en/get-started/git-basics/managing-remote-repositories)は、このエラーを、ローカルリポジトリに存在する名前を再び追加しようとした状態と説明しています。

`origin`は特別なURLやGitHub上のリポジトリ名ではなく、手元で接続先を識別する登録名です。別のURLを指定しても、同じ名前が使われていれば追加は拒否されます。

逆に、同じURLを違う名前で登録することもできます。エラーの判定対象はURLの一致ではなく、名前の重複です。

今回のGit 2.51.1による確認では、clone済みのリポジトリに再び`origin`を追加すると、上記の文言と終了コード3になりました。失敗した追加操作の前後で、リポジトリの設定ファイルは変わっていませんでした。

URLの存在やアクセス権を確認する段階のエラーではありません。再試行やパスワード変更だけで、名前の重複がなくなるわけではありません。

## 登録済みのURLと作業場所を確認する

別のプロジェクトを操作していないかも含めて、現在の対象を確認します。

```bash
git rev-parse --show-toplevel
git remote -v
git remote get-url --all origin
git remote get-url --push --all origin
```

`--show-toplevel`は作業ディレクトリの最上位を表示します。`get-url`の後半二つは、取得側と送信側のURLをそれぞれ確認する指定です。

通常の設定例では、`git remote -v`に次のように表示されます。

```text
origin  https://github.com/OWNER/REPOSITORY.git (fetch)
origin  https://github.com/OWNER/REPOSITORY.git (push)
```

`fetch`は取得、`push`は送信に使うURLです。二行あるだけで、`origin`が二重登録されているという意味ではありません。

[cloneの公式文書](https://git-scm.com/docs/git-clone)によると、cloneでは既定で複製元が`origin`として登録されます。clone後に、初期化済みのリポジトリ向けの`remote add origin`手順を繰り返せば、名前が重なります。`clone --origin`などで名前を指定した場合は、実際の一覧で判断します。

URLに認証情報が含まれている場合は、確認結果をそのまま公開しないでください。

## URLの変更にはset-urlを使う

既存の接続先が誤っている、または同じリポジトリへのHTTPSとSSHを切り替えたい場合は、URLを変更します。

```bash
git remote set-url origin https://github.com/OWNER/REPOSITORY.git
git remote -v
```

[Gitのremote公式文書](https://git-scm.com/docs/git-remote)には、既存リモートのURLを変更する`set-url`が説明されています。今回の最小例でも、変更後のURLが表示され、現在のコミットと`origin/main`などの追跡情報は残りました。

ただし、URLを変えても、その接続先から最新情報を取得したことにはなりません。特に別のリポジトリへ変更した場合、既存の`origin/main`が新しい接続先の最新状態を表しているとは限りません。

取得先と送信先のURLを別々に登録している場合や、複数のURLがある場合もあります。通常の`set-url`一回ですべてを変更したつもりにならず、変更後も両側の一覧を確認してください。

`set-url`に成功しても、URLの正しさやアクセス権、pushできることまで確認できたわけではありません。登録の修正と、その後の通信結果を分けて判断します。

## 元の接続先を残すなら別名で追加する

元の接続先も必要なら、`origin`を上書きせず、未使用の名前を付けます。

```bash
git remote add upstream https://github.com/OTHER/REPOSITORY.git
git remote -v
```

`upstream`は名前の例で、既に登録済みなら別の名前にします。登録しただけでは、取得や送信は実行されません。この例には、追加直後に取得する`-f`も付けていません。

既存の`origin`を別名で残し、新しい接続先を`origin`にする方針なら、改名してから追加する方法もあります。

```bash
git remote rename origin old-origin
git remote add origin https://github.com/OWNER/NEW-REPOSITORY.git
git remote -v
```

これは前の例とは別の選択です。両方をまとめて実行する必要はありません。

公式文書によると、`rename`ではリモート追跡ブランチと関連設定も更新されます。今回の確認でも、`origin/main`は`old-origin/main`へ変わりました。

改名先が既に使われていると、次のように同じ種類のエラーになります。

```text
error: remote upstream already exists.
```

これはローカルの登録名の変更です。GitHub上のリポジトリ名そのものを変更する操作ではありません。

## removeで追加し直す前に影響を確認する

不要になったリモートなら削除できます。

```bash
git remote remove origin
```

ただし、remoteの公式文書は、関連するリモート追跡ブランチと設定も削除すると説明しています。今回の確認でも、削除対象の追跡情報は一覧から消えました。一方、現在のローカルブランチのコミットは変わっていませんでした。

[GitHubの公式説明](https://docs.github.com/en/get-started/git-basics/managing-remote-repositories#removing-a-remote-repository)も、ローカルの関連付けを外す操作であり、サーバー上のリポジトリを削除しないと説明しています。

URLを変えたいだけなら、先に`set-url`を使う方法を検討してください。削除して追加し直すことは、URLの変更と同じ影響範囲ではありません。

`origin/main`などの追跡情報と、自分が作業する`main`などのローカルブランチも区別します。削除した登録名を自動処理で使っていないか、操作前に確認してください。

## Repository not foundやNo such remoteとの違い

`Repository not found`は、接続先のURLやアクセス権に関係するエラーです。`remote origin already exists`を解消した後でも、URLが誤っていれば別に発生し得ます。

存在しない名前を`set-url`へ渡した今回の確認では、次の結果になりました。

```text
error: No such remote 'missing'
```

この場合は、追加ではなく、変更しようとした名前の不在が問題です。`git remote -v`で登録名を確認します。

`not a git repository`なら、現在のディレクトリからリポジトリが認識できていません。リモート名を直す前に、作業場所を確認してください。

[GitHub CLIのIssue #2166](https://github.com/cli/cli/issues/2166)には、`gh repo create`によるGitHub上の作成後、`origin`の重複で停止した報告があります。2020年のGitHub CLIの事例で、表示や終了コードも今回検証したGitとは異なります。現在のGitHub CLI全般で同じ問題が残るという意味ではありません。道具全体の操作が途中で止まった場合は、サーバー側で何が作成済みかも分けて確認します。

## 解決手順のまとめ

まず現在のリポジトリと登録済みURLを確認します。既存のURLが正しければ、同名リモートの追加は不要です。

URLの変更は`set-url`、元の接続先を残す追加は別名、登録名の整理は`rename`を使います。`remove`は追跡情報と設定も消すため、URL変更だけの目的で最初に選ばないようにします。

この記事ではLinux上のGit 2.51.1で、ローカルclone後の重複追加、URL変更、改名先の重複、正常な改名、削除、存在しない名前へのURL変更を確認しました。重複追加と重複改名は終了コード3でした。外部リポジトリへのfetch・pushと、Windows上の実行は未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
