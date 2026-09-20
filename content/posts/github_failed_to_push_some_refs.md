---
title: "GitHub の failed to push some refs：原因と解決策"
date: 2026-09-15
description: "failed to push some refs は理由を含まない要約行です。この記事が扱うのは原因の一覧ではなく、拒否された行の括弧に出る6語の読み方と、hint が1つしか出ない仕組み、そして hint が何も出ない2つの場合の見分け方です。"
tags: ["GitHub API"]
images: ["og/posts/github_failed_to_push_some_refs.png"]
errorCode: "failed to push some refs"
error_name: "error: failed to push some refs to '<url>'"
error_aliases:
  - "failed to push some refs"
  - "failed to push some refs to"
  - "Updates were rejected"
lastmod: 2026-09-15
service: "GitHub API"
error_type: "failed to push some refs"
components: ["Git Push", "Transport"]
related_services: ["Git", "GitHub Actions", "GitLab"]
error_cases:
  - id: "non-fast-forward"
    situation: "同じブランチを別の場所からも更新している"
    messages:
      - "(non-fast-forward)"
      - "Updates were rejected because the tip of your current branch is behind"
    cause: "送ろうとしている位置が、相手の現在位置の続きになっていない"
    check: "git log --oneline main..origin/main で、相手にだけある変更を数える"
    fix: "git pull で取り込んでから送り直す"
  - id: "fetch-first"
    situation: "浅い取得や単一ブランチの取得を使っている"
    messages:
      - "(fetch first)"
      - "Updates were rejected because the remote contains work that you do not"
    cause: "相手の現在位置が指す中身を手元が持っておらず、続きかどうかを判定できない"
    check: "git fetch origin を実行し、同じ操作を試す"
    fix: "取得してから判定させる。取得の深さを制限している場合はその制限を外す"
  - id: "already-exists"
    situation: "同じ名前のタグを作り直して送っている"
    messages:
      - "(already exists)"
      - "Updates were rejected because the tag already exists in the remote."
    cause: "タグは上書きの対象外で、相手に同名があれば常に拒まれる"
    check: "git ls-remote --tags origin で相手側の同名タグの有無を確認する"
    fix: "別の名前にするか、相手側のタグを削除してから送る"
  - id: "needs-force"
    situation: "注釈付きタグを軽量タグに置き換えている"
    messages:
      - "(needs force)"
      - "You cannot update a remote ref that points at a non-commit object,"
    cause: "書き換え前か書き換え後の位置が、コミット以外のものを指している"
    check: "git cat-file -t で、相手側と手元それぞれの種類を確認する"
    fix: "種類を揃えるか、意図した置き換えであれば強制の指定を付ける"
  - id: "stale-info"
    situation: "--force-with-lease を付けている"
    messages:
      - "(stale info)"
    cause: "期待していた相手の位置と実際の位置が食い違っている"
    check: "git ls-remote origin <branch> で相手の現在位置を直接見る"
    fix: "取得して中身を確認したうえで送り直す"
  - id: "remote-rejected"
    situation: "hint が1行も出ない"
    messages:
      - "[remote rejected]"
    cause: "git ではなく受け取り側が断っている"
    check: "[remote rejected] の括弧に入っている相手側の文言を読む"
    fix: "保護設定や規則、受け取り側のスクリプトの条件に合わせる"
trend_incident: false
---

## 冒頭まとめ

`error: failed to push some refs to '...'` は、理由を含んでいません。[git](/glossary/git/) の実装では、[送信](/glossary/送信/)の処理が失敗して戻ってきたときに、この1行を無条件で出します。中身が何であれ表示されるため、この行を[検索](/glossary/検索/)しても自分の状況に合う答えには辿り着きにくくなります。

理由は、この行の1つ上に出ます。`! [rejected]` で始まる行の末尾、括弧の中に入る語がそれです。入りうる語は `non-fast-forward`、`fetch first`、`already exists`、`needs force`、`stale info` の5つと、受け取り側が断ったことを示す `[remote rejected]` です。

その下に続く `hint:` の行にも注意が要ります。[git](/glossary/git/) は拒否の理由を集めたうえで、if と else if の並びで最初に当てはまった1件だけを表示します。つまり2つの[ブランチ](/glossary/ブランチ/)が別々の理由で拒まれても、助言は片方の分しか出ません。助言のとおりに `git pull` をしても、もう一方は直りません。

助言が1行も出ない場合もあります。`stale info` と `[remote rejected]` は、どちらも助言の対象から外れているためです。何も出ないから情報が無いのではなく、そこが読むべき箇所だと考えてください。

## エラーの概要

出力は次の形になります。

```text
To https://github.com/OWNER/REPO.git
 ! [rejected]        main -> main (fetch first)
error: failed to push some refs to 'https://github.com/OWNER/REPO.git'
hint: Updates were rejected because the remote contains work that you do not
hint: have locally. This is usually caused by another repository pushing to
hint: the same ref. If you want to integrate the remote changes, use
hint: 'git pull' before pushing again.
```

読む順序は下からではありません。`!` で始まる行が先で、`error:` の行は結果の要約です。送ろうとした[ブランチ](/glossary/ブランチ/)が複数あれば、`!` の行も複数並びます。

括弧に入る5語は、[git](/glossary/git/) が次の順で判定した結果です。まず送り先が[タグ](/glossary/タグ/)で相手に同名があれば `already exists`。次に相手の現在位置が指す[オブジェクト](/glossary/オブジェクト/)を手元が持っていなければ `fetch first`。次に相手の位置か送る位置のどちらかが[コミット](/glossary/コミット/)でなければ `needs force`。最後に、送る位置が相手の位置の子孫でなければ `non-fast-forward` です。`stale info` だけは別経路で、`--force-with-lease` を付けたときの照合に失敗した場合に出ます。

同じ「更新を拒んだ」でも、この5語は互いに排他です。上から順に当てはまった時点で確定するため、たとえば `fetch first` と表示されているときに履歴の前後関係を調べても意味がありません。判定はそこまで進んでいません。

## まず最初に：拒否された行だけを取り出す

出力が長いときは、[送信](/glossary/送信/)を実際には行わずに結果だけを見ます。

```bash
git push --dry-run origin main
```

`--dry-run` は[送信](/glossary/送信/)せずに同じ判定を行い、同じ `!` の行を表示します。相手を壊す心配なく何度でも試せます。

次に、相手と手元の位置関係を数えます。

```bash
git fetch origin
git log --oneline main..origin/main
git log --oneline origin/main..main
```

上の[コマンド](/glossary/コマンド/)は相手にだけある[コミット](/glossary/コミット/)、下は手元にだけある[コミット](/glossary/コミット/)を並べます。上が空でなければ、相手が進んでいます。両方とも空でないなら、履歴が分岐しています。

## よくある原因と解決手順

### 原因1：手元の履歴が相手の続きになっていない（non-fast-forward） {#non-fast-forward}

最も多い形です。相手の現在位置から手元の位置へ辿れないため、[git](/glossary/git/) は更新を拒みます。同じ[ブランチ](/glossary/ブランチ/)を複数人が触っている場合か、手元で `git commit --amend` や `git rebase` を行って履歴を作り直した場合に起きます。

表示はこうなります。

```text
 ! [rejected]        main -> main (non-fast-forward)
hint: Updates were rejected because the tip of your current branch is behind
hint: its remote counterpart. If you want to integrate the remote changes,
hint: use 'git pull' before pushing again.
```

いま作業している[ブランチ](/glossary/ブランチ/)ではなく別の[ブランチ](/glossary/ブランチ/)が拒まれた場合は、文面が `a pushed branch tip is behind its remote counterpart` に変わります。指し示す対象が違うだけで、判定は同じです。

対処は2つに分かれます。相手の変更を取り込んでよいなら、取り込んでから送り直します。

```bash
git pull --rebase origin main
git push origin main
```

手元で履歴を作り直した結果として相手を[上書き](/glossary/上書き/)したい場合は、`--force-with-lease` を使います。`--force` は相手の状態を一切見ないため、他人の[コミット](/glossary/コミット/)を消す事故につながります。

### 原因2：相手の現在位置を手元が持っていない（fetch first） {#fetch-first}

`non-fast-forward` と混同されやすい状態です。[git](/glossary/git/) は、相手の現在位置が指す[オブジェクト](/glossary/オブジェクト/)が手元の[データベース](/glossary/データベース/)に無いかどうかを先に調べます。無ければ、続きかどうかを判定する材料自体が無いため `fetch first` になります。

```text
 ! [rejected]        main -> main (fetch first)
```

取得していないだけのこともあれば、取得の範囲を絞っていることが原因のこともあります。[自動化](/glossary/自動化/)の中で `--depth 1` や単一[ブランチ](/glossary/ブランチ/)の取得を使っている場合、手元には最新の1件しか無く、相手の位置が手元に存在しません。

対処は取得です。

```bash
git fetch origin
git push origin main
```

これで解消しない場合は、取得の深さが制限されていないかを確認します。

```bash
git rev-parse --is-shallow-repository
```

`true` が返れば範囲が絞られています。`git fetch --unshallow` で全体を取り直すか、[自動化](/glossary/自動化/)側の取得[設定](/glossary/設定/)を見直してください。

### 原因3：同じ名前のタグが相手に既にある（already exists） {#already-exists}

[タグ](/glossary/タグ/)は特別扱いです。判定の並びで最初に置かれており、相手に同じ名前があれば、中身が何であっても拒まれます。

```text
 ! [rejected]        v1.0.0 -> v1.0.0 (already exists)
hint: Updates were rejected because the tag already exists in the remote.
```

[ブランチ](/glossary/ブランチ/)と違い、位置関係は見ません。[タグ](/glossary/タグ/)は特定の時点を指す固定の名前として扱われるためです。

まず相手側を確認します。

```bash
git ls-remote --tags origin
```

対処は、別の名前を付けるか、相手側の[タグ](/glossary/タグ/)を[削除](/glossary/削除/)してから送るかです。公開済みの[タグ](/glossary/タグ/)を作り直すと、既に取得した人の手元と食い違うため、名前を変えるほうが安全です。

### 原因4：コミット以外を指す参照を書き換えようとしている（needs force） {#needs-force}

注釈付き[タグ](/glossary/タグ/)を軽量[タグ](/glossary/タグ/)に置き換える場合などに出ます。[git](/glossary/git/) は、書き換え前の位置と書き換え後の位置の両方について、それが[コミット](/glossary/コミット/)として解決できるかを調べます。どちらか一方でも解決できなければ、この判定に落ちます。

```text
 ! [rejected]        v1.0.0 -> v1.0.0 (needs force)
hint: You cannot update a remote ref that points at a non-commit object,
hint: or update a remote ref to make it point at a non-commit object,
hint: without using the '--force' option.
```

種類を確認します。

```bash
git cat-file -t v1.0.0
```

`tag` なら注釈付き、`commit` なら軽量です。意図した置き換えであれば強制の指定を付け、そうでなければ種類を揃えてください。

### 原因5：--force-with-lease の期待値がずれている（stale info） {#stale-info}

`--force-with-lease` は、相手の現在位置が自分の知っている位置と同じであることを条件に[上書き](/glossary/上書き/)します。食い違えば拒みます。

```text
 ! [rejected]        main -> main (stale info)
```

この場合、助言は出ません。表示されるのは要約行と `!` の行だけです。

相手の位置を直接確認します。

```bash
git ls-remote origin refs/heads/main
```

自分が知っている位置と違っていれば、その間に誰かが送っています。取得して中身を確かめ、[上書き](/glossary/上書き/)してよいと判断してから送り直してください。

### 原因6：相手側が受け取りを断っている（remote rejected） {#remote-rejected}

`!` の行が `[rejected]` ではなく `[remote rejected]` になっている場合、判定を行ったのは[git](/glossary/git/) ではありません。受け取り側が断っています。

```text
 ! [remote rejected] main -> main (protected branch hook declined)
```

括弧の中には、相手が返した文言がそのまま入ります。[GitHub](/glossary/github/) であれば保護された[ブランチ](/glossary/ブランチ/)の[設定](/glossary/設定/)や ruleset、[自動化](/glossary/自動化/)のために置かれた受け取り側の[スクリプト](/glossary/スクリプト/)が理由になります。この経路には助言が付きません。読む場所は括弧の中だけです。

規則違反であれば [GitHub の GH013 の記事](/posts/github_gh013_repository_rule_violations/)で扱っています。

## 補足：似ているが別のもの

`Everything up-to-date` は失敗ではありません。送るべき差がないという意味です。[コミット](/glossary/コミット/)を作り忘れているか、送り先の指定が想定と違います。

`fatal: Could not read from remote repository.` や `Repository not found` は、この記事の要約行より手前で止まっています。[認証](/glossary/認証/)や宛先の段階なので、判定まで進んでいません。前者は [publickey の記事](/posts/github_permission_denied_publickey/)、後者は [Repository not found の記事](/posts/github_repository_not_found/)を参照してください。

`! [remote failure]` は受け取り側が結果を報告しなかった場合です。拒否とは別で、[通信](/glossary/通信/)が途中で終わったときに出ます。

## 切り分けの順序

1. `!` で始まる行を数える。複数あれば、助言は最優先の1件分しか出ていないと考える
2. `[rejected]` か `[remote rejected]` かを見る。後者なら判定したのは相手側で、括弧の中がすべて
3. `[rejected]` なら括弧の5語を確認する
4. `fetch first` なら `git fetch` を先に行い、取得範囲が絞られていないかを調べる
5. `non-fast-forward` なら相手と手元の差を数え、取り込むか[上書き](/glossary/上書き/)するかを決める
6. `already exists` と `needs force` は[タグ](/glossary/タグ/)まわりなので、相手側の同名と種類を確認する
7. `stale info` は助言が出ないため、相手の現在位置を直接見る

## 確認コマンド集

```bash
# 1. 送信せずに判定だけを見る（最初に行う）
git push --dry-run origin main

# 2. 送り先の宛先を確認する
git remote -v

# 3. 相手にだけある変更を数える
git fetch origin
git log --oneline main..origin/main

# 4. 手元にだけある変更を数える
git log --oneline origin/main..main

# 5. 相手の現在位置を直接見る
git ls-remote origin refs/heads/main

# 6. 相手側のタグ一覧を見る
git ls-remote --tags origin

# 7. 取得範囲が絞られていないか調べる
git rev-parse --is-shallow-repository

# 8. 参照が指しているものの種類を調べる
git cat-file -t v1.0.0
```

## Editor's Note

`--force-with-lease` は安全な[上書き](/glossary/上書き/)の手段として広く紹介されています。ところが [git](/glossary/git/) 自身は、このこの指定が条件付きでしか安全でないと説明しています。

[公式ドキュメント](https://github.com/git/git/blob/master/Documentation/git-push.adoc)には、背景で `git fetch --all` を走らせる仕組みがあると、この方法は完全に無効化されると書かれています。理由は照合の対象にあります。`--force-with-lease` が期待値として使うのは、手元に[保存](/glossary/保存/)されている相手の位置の記録です。編集[ツール](/glossary/ツール/)や[自動化](/glossary/自動化/)が裏で取得を行えば、その記録は内容を確認しないまま新しい位置へ進みます。期待値が実際の値に追いついてしまうため、照合は通り、他人の[コミット](/glossary/コミット/)は消えます。

[git](/glossary/git/) はこの問題に対して、2020年公開の 2.30 で `--force-if-includes` を追加しました。[リリースノート](https://github.com/git/git/blob/master/Documentation/RelNotes/2.30.0.adoc)には、`--force-with-lease` は自分で `git fetch` をよく管理していない限り[コミット](/glossary/コミット/)を失いやすい、と率直に書かれています。追加された確認は、置き換えようとしている相手の位置を実際に見たうえで手元の内容が作られたかどうかを調べるものです。

実務上の意味はこうです。`stale info` が出たときは、照合が働いたということです。むしろ出なかったときのほうを疑ってください。`--force-with-lease` が静かに通った直後に他人の変更が消えているなら、背景の取得が期待値を進めていた可能性があります。[上書き](/glossary/上書き/)を日常的に行う[リポジトリ](/glossary/リポジトリ/)では、`--force-if-includes` を併せて指定しておくほうが確実です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
