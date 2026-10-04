---
title: "Gitのローカル変更上書きエラーの対処法"
date: 2026-10-02
draft: false
description: "GitのYour local changes would be overwrittenは、未コミットの変更を上書きから守るための停止です。差分の確認、コミット、一時退避、対象ファイルだけの破棄と、未追跡ファイルの扱いを解説します。"
tags: ["git"]
images: ["og/posts/git_overwritten_by_merge.png"]
errorCode: "Your local changes to the following files would be overwritten"
urgency: "medium"
service: "git"
error_type: "local_changes_would_be_overwritten"
components: ["Git", "merge", "checkout"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

`git pull`や[ブランチ](/glossary/ブランチ/)の切り替えで次の[エラー](/glossary/エラー/)が出た場合、[Git](/glossary/git/)は未[コミット](/glossary/コミット/)の変更を上書きしないように操作を止めています。

```text
error: Your local changes to the following files would be overwritten by merge:
        src/config.py
Please commit your changes or stash them before you merge.
Aborting
```

最初に`git status`、`git diff`、`git diff --cached`で手元の変更を確認してください。変更を記録できるなら[コミット](/glossary/コミット/)し、作業途中なら`git stash push`で一時退避します。不要だと確認できた変更だけを破棄してください。

対象は`git add`済みの変更に限りません。まだステージしていない追跡[ファイル](/glossary/ファイル/)の変更でも止まります。[エラー](/glossary/エラー/)に並んだ[ファイル](/glossary/ファイル/)を確認せずに、[リポジトリ](/glossary/リポジトリ/)全体を強制的に戻す必要はありません。

## エラーメッセージの意味

mergeは別の履歴を取り込む操作、checkoutやswitchは[ブランチ](/glossary/ブランチ/)を切り替える操作です。切り替え時には次のような文言になります。

```text
error: Your local changes to the following files would be overwritten by checkout:
        src/config.py
Please commit your changes or stash them before you switch branches.
Aborting
```

[Git](/glossary/git/)の[unpack-trees.c](https://github.com/git/git/blob/master/unpack-trees.c)では、操作の種類に応じて文言を選び、上書きを拒む[ファイル名](/glossary/ファイル名/)を表示します。`git switch`でも、表示の中では`checkout`という語が使われる場合があります。

この停止は、未[コミット](/glossary/コミット/)の変更を残せない操作を拒んだものです。変更があるだけで、必ずすべてのmergeや[ブランチ](/glossary/ブランチ/)切り替えが拒まれるわけではありません。ただし、[git-mergeの公式文書](https://git-scm.com/docs/git-merge#_pre_merge_checks)は、取り込み対象と重なる作業ツリーの変更や、原則としてHEADと異なる索引の変更がある場合の停止を説明しています。

索引は、次の[コミット](/glossary/コミット/)に含める内容を保持する場所で、ステージとも呼ばれます。作業ツリーは、実際に編集している[ファイル](/glossary/ファイル/)です。同じ[ファイル](/glossary/ファイル/)でも、両方に異なる変更があることがあります。

案内文は`advice.commitBeforeMerge`などの[設定](/glossary/設定/)や、停止した処理の経路によって表示が変わります。`Please commit...`が出なくても、手元の変更を確認する必要があります。案内を非表示にする[設定](/glossary/設定/)は、[上書き](/glossary/上書き/)拒否を解除するものではありません。

## 最初に作業ツリーとステージの差分を確認する

[リポジトリ](/glossary/リポジトリ/)の中で次を実行します。

```bash
git status --short
git diff
git diff --cached
```

`git diff`は、ステージに入っている内容と作業ツリーの違いを表示します。`git diff --cached`は、最新の[コミット](/glossary/コミット/)とステージの違いを表示します。前者が空でも、後者に変更があれば、未[コミット](/glossary/コミット/)の変更は残っています。

[エラー](/glossary/エラー/)に表示された[ファイル](/glossary/ファイル/)だけを調べる場合は、次のように指定します。`src/config.py`は実際の[ファイル名](/glossary/ファイル名/)に置き換えてください。

```bash
git diff -- src/config.py
git diff --cached -- src/config.py
```

自分で編集していないように見える場合も、内容を確認します。[ComfyUIのIssue #6726](https://github.com/Comfy-Org/ComfyUI/issues/6726)には、更新処理で`git pull`が止まり、複数の`web/assets`[ファイル](/glossary/ファイル/)と`web/index.html`が列挙された報告があります。報告本文だけでは、各[ファイル](/glossary/ファイル/)を誰が変更したかまでは確認できません。[エラー](/glossary/エラー/)の一覧は、まず調べる対象を示しています。

変更が[設定ファイル](/glossary/設定ファイル/)や自動生成された[ファイル](/glossary/ファイル/)でも、[削除](/glossary/削除/)してよいとは限りません。元の内容と差分を確認したうえで、残し方を決めてください。

## 変更を残すならコミットして再実行する

変更が一段落していて、現在の[ブランチ](/glossary/ブランチ/)へ記録してよい場合は[コミット](/glossary/コミット/)します。対象[ファイル](/glossary/ファイル/)を確認してから個別に指定してください。

```bash
git add -- src/config.py
git diff --cached
git commit -m "設定変更を記録"
```

`git commit`は、ここで指定した[ファイル](/glossary/ファイル/)だけでなく、すでにステージ済みの変更も記録します。そのため、直前の`git diff --cached`で[コミット](/glossary/コミット/)全体の内容を確認します。

[コミット](/glossary/コミット/)できたら、止まった操作を再実行します。`git pull`で止まっていた場合は次を使います。

```bash
git pull
```

[ブランチ](/glossary/ブランチ/)切り替えで止まっていた場合は、元の`git switch`または`git checkout`を再実行してください。ローカルの変更を[コミット](/glossary/コミット/)しても、取り込む履歴との競合までなくなるわけではありません。次に`CONFLICT`が出たら、[マージ](/glossary/マージ/)の競合として内容を解決します。

## 作業途中ならstashで一時退避する

まだ[コミット](/glossary/コミット/)したくない場合は、一時退避を使います。[git-stashの公式文書](https://git-scm.com/docs/git-stash)では、`push`が作業ツリーと索引の変更を[保存](/glossary/保存/)し、元の状態へ戻す操作として説明されています。

```bash
git stash push -m "before update"
git stash list
```

新しい退避が作られたことと、その名前を確認します。`No local changes to save`と出た場合は、新しい退避は作られていません。古い`stash@{0}`を今回の変更だと思って適用しないでください。

退避後、止まった操作を再実行します。成功したら、確認した退避を適用します。次は今回の退避が`stash@{0}`だった場合の例です。

```bash
git pull
```

```bash
git stash apply "stash@{0}"
git status
```

`git pull`が失敗した場合は、原因を確認してから進めます。成功したか分からないまま退避を適用しないでください。

`apply`は退避を一覧に残します。作業内容を確認して不要になった後に、同じ退避を[削除](/glossary/削除/)します。

```bash
git stash drop "stash@{0}"
```

途中で別の退避を作ると番号が変わるため、削除前にも`git stash list`で対象を確認します。ステージ済みだった状態も戻したい場合は、`apply --index`がありますが、競合などで[復元](/glossary/復元/)できない場合があります。

### 適用時に競合した場合

`git stash apply`や`git stash pop`で競合したら、`git status`で対象を確認し、[ファイル](/glossary/ファイル/)の内容を編集して残す変更を決めます。解決した[ファイル](/glossary/ファイル/)は`git add -- <ファイル名>`でステージします。

`git stash pop`は、適用に成功したときに退避を[削除](/glossary/削除/)します。競合した場合は退避が残ることが公式文書に明記されています。競合状態のまま`pop`を繰り返したり、`--theirs`で片方を一律に選んだりせず、両方の変更を確認してください。

## 不要な変更だけを破棄する

変更が不要だと確認できた場合に限り、対象[ファイル](/glossary/ファイル/)を戻します。まず、ステージに入っていない編集だけを破棄する場合です。

```bash
git restore -- src/config.py
```

この操作の復元元は通常、索引です。[git-restoreの公式文書](https://git-scm.com/docs/git-restore)によると、`--staged`を付けない場合の既定の復元元は索引になります。したがって、すでにステージした変更は、この[コマンド](/glossary/コマンド/)では消えません。

ステージ済みの内容も含め、対象[ファイル](/glossary/ファイル/)を最新[コミット](/glossary/コミット/)の内容へ戻す場合は、復元元と範囲を明示します。

```bash
git restore --source=HEAD --staged --worktree -- src/config.py
```

この[コマンド](/glossary/コマンド/)は、対象[ファイル](/glossary/ファイル/)の索引と作業ツリーをHEADの内容へ戻します。未[コミット](/glossary/コミット/)の編集は失われるため、必要な内容がないことを確認し、不明なら先に退避してください。

戻した後に、差分がなくなったことを確認します。

```bash
git status --short
git diff -- src/config.py
git diff --cached -- src/config.py
```

その後、元の操作を再実行します。[エラー](/glossary/エラー/)に出た[ファイル](/glossary/ファイル/)だけを扱えばよい状況で、`git reset --hard`や`git clean -fd`を[リポジトリ](/glossary/リポジトリ/)全体へ実行する必要はありません。

## 未追跡ファイルと近いエラーを区別する

未追跡[ファイル](/glossary/ファイル/)が上書きされる場合は、文言の冒頭が異なります。

```text
error: The following untracked working tree files would be overwritten by merge:
        src/config.py
Please move or remove them before you merge.
Aborting
```

未追跡とは、索引に登録されていない[ファイル](/glossary/ファイル/)です。通常の`git stash push`では未追跡[ファイル](/glossary/ファイル/)を含めません。まとめて退避したい場合は、次のように指定できます。

```bash
git stash push --include-untracked -m "before update with untracked files"
git stash list
```

`--include-untracked`は未追跡[ファイル](/glossary/ファイル/)を含めますが、無視対象の[ファイル](/glossary/ファイル/)まで含める指定ではありません。必要な[ファイル](/glossary/ファイル/)を[リポジトリ](/glossary/リポジトリ/)の外へコピーして[保存](/glossary/保存/)する方法もあります。

取り込み後に同じ[パス](/glossary/パス/)へ追跡[ファイル](/glossary/ファイル/)が作られた場合は、退避した未追跡[ファイル](/glossary/ファイル/)をそのまま戻せないことがあります。[保存](/glossary/保存/)した内容と取り込まれた内容を比較し、必要な変更を反映してください。別名へ移動した[ファイル](/glossary/ファイル/)を、確認せずに元の[パス](/glossary/パス/)へ戻して上書きする手順は避けます。

### pullの取り込み方法による違い

[git-pullの公式文書](https://git-scm.com/docs/git-pull)では、取得した履歴の統合方法が[設定](/glossary/設定/)やオプションで変わることが説明されています。mergeで取り込む場合と、`--rebase`で[コミット](/glossary/コミット/)を並べ直す場合では、最初に出る[エラー](/glossary/エラー/)が異なることがあります。

| 表示 | 確認する状態 |
|---|---|
| `Your local changes ... would be overwritten` | 未[コミット](/glossary/コミット/)の変更が操作を妨げている |
| `The following untracked working tree files ...` | 未追跡[ファイル](/glossary/ファイル/)が更新先の[パス](/glossary/パス/)にある |
| `CONFLICT (content)` | 取り込みや退避の適用で内容の競合が生じた |
| `cannot pull with rebase: You have unstaged changes` | rebaseを始める前の未ステージ変更 |

`git restore <ファイル名>`は、変更を破棄するための操作です。[ブランチ](/glossary/ブランチ/)切り替えが変更を保護して止まる場合と同じものとして扱わないでください。

## 解決手順のまとめ

最初に、[エラー](/glossary/エラー/)に表示された[ファイル](/glossary/ファイル/)と`git status`を確認し、`git diff`と`git diff --cached`の両方で変更内容を調べます。

記録できる変更なら[コミット](/glossary/コミット/)し、作業途中なら退避します。退避を使った場合は、新しい退避が作られたことを確認してから元の操作を再実行し、成功後に`apply`で戻します。内容を確認できるまでは退避を[削除](/glossary/削除/)しないでください。

変更を破棄する場合は対象[ファイル](/glossary/ファイル/)を限定します。通常の`git restore`は索引からの[復元](/glossary/復元/)なので、ステージ済みの変更も破棄する場合は、HEADを復元元に指定して索引と作業ツリーの両方を戻します。

免責事項：本記事の内容は一般的な[Git](/glossary/git/)[リポジトリ](/glossary/リポジトリ/)を前提としています。変更の破棄や退避の[削除](/glossary/削除/)は、内容と対象を確認してから実行してください。サブモジュールや特殊な[設定](/glossary/設定/)がある[環境](/glossary/環境/)では、対象ごとの状態を確認し、必要な作業内容を別途保存してください。