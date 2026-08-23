---
title: "GitHub の GH013 エラー：原因と解決策"
date: 2026-08-07
description: "GH013 は秘密情報の混入を知らせる符号ではありません。ruleset 違反をまとめた符号で、中身は3系統に分かれます。この記事が扱うのは違反の一覧ではなく、どの仕組みが拒んだかの見分け方と、bypass が効かないときに何を疑うかです。bypass は設定で自分に与えるものではなく、その push を行った身元と照合されます。"
tags: ["GitHub API"]
images: ["og/posts/github_gh013_repository_rule_violations.png"]
errorCode: "GH013"
lastmod: 2026-08-07
service: "GitHub API"
error_type: "GH013"
components: ["Repository Rules", "Push Protection"]
related_services: ["Git", "GitHub Actions", "GitHub Apps"]
trend_incident: false
---

## 冒頭まとめ

`GH013: Repository rule violations found` を検索すると、秘密情報が混ざったときの対処が数多く出てきます。それは3系統あるうちの1つにすぎません。GH013 は ruleset（[リポジトリ](/glossary/リポジトリ/)に設定された規則の集まり）に違反したという符号で、中身は[ブランチ](/glossary/ブランチ/)や[タグ](/glossary/タグ/)への規則、push そのものへの規則、そして秘密情報の検知に分かれます。

見分ける手がかりは、符号のすぐ下に出ます。[GitHub](/glossary/github/) は `Review all repository rules at` に続けて、その[ブランチ](/glossary/ブランチ/)に効いている規則の一覧を示す[URL](/glossary/url/) を返します。公式ドキュメントによれば、この一覧は読み取り[権限](/glossary/権限/)さえあれば誰でも見られます。管理者に問い合わせる前に、まずここを開けば済みます。

もう1つ、bypass（規則を素通りする許可）についての誤解があります。bypass は[アカウント](/glossary/アカウント/)に与える[権限](/glossary/権限/)ではありません。ruleset は push のたびに、そのとき使われた資格情報の持ち主を bypass 一覧と照合します。だから自分を一覧に入れても、CI が別の身元で push していれば拒まれます。手元では通るのに自動処理では落ちる、という報告のほとんどはこれです。

branch protection との違いも押さえてください。公式ドキュメントは、branch protection の制限が既定では管理[権限](/glossary/権限/)を持つ人に適用されないと明記しています。ruleset は逆で、bypass 一覧に載せない限り誰も素通りできません。管理者だから通るはずだ、という前提はここで崩れます。

## エラーの概要

出力は次の形になります。実際に報告された表示です。

```text
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: Review all repository rules at http://github.com/OWNER/REPO/rules?ref=refs/heads/main
remote:
remote: - Changes must be made through a pull request.
To https://github.com/OWNER/REPO
 ! [remote rejected] main -> main (push declined due to repository rule violations)
error: failed to push some refs to 'https://github.com/OWNER/REPO'
```

読む場所は2つです。1つ目は `Review all repository rules at` の[URL](/glossary/url/) で、対象の[ブランチ](/glossary/ブランチ/)に効いている規則がすべて並びます。2つ目はその下の箇条書きで、実際に違反した規則の名前が入ります。

箇条書きの書き出しで系統が分かれます。上の例のように規則名が直接並んでいれば、[ブランチ](/glossary/ブランチ/)や[タグ](/glossary/タグ/)への規則です。一方、`- GITHUB PUSH PROTECTION` という見出しと罫線が挟まっていれば、push への規則か秘密情報の検知です。

```text
remote: - GITHUB PUSH PROTECTION
remote:   —————————————————————————————————————————
remote:     Resolve the following violations before pushing again
remote:
remote:     - Files cannot include restricted file extensions.
```

この見出しの下に `Push cannot contain secrets` が出れば秘密情報の検知、`Files cannot include restricted file extensions.` のように[拡張子](/glossary/拡張子/)や大きさに触れていれば push への規則です。どちらも GH013 として返るため、符号だけでは区別できません。

## まず最初に：規則の一覧を開く

推測の前に、[エラー](/glossary/エラー/)に書かれた[URL](/glossary/url/) を開きます。手元にない場合は、[リポジトリ](/glossary/リポジトリ/)の[URL](/glossary/url/) の末尾に `/rules` を足しても同じ画面に届きます。公式ドキュメントがこの短縮形を案内しています。

[コマンド](/glossary/コマンド/)で確認する手もあります。

```bash
gh api "repos/OWNER/REPO/rules/branches/main"
```

この経路の説明には重要な性質が3つ書かれています。指定した[ブランチ](/glossary/ブランチ/)に効いている規則をすべて返すこと、[ブランチ](/glossary/ブランチ/)が実在しなくてもその名前なら効くはずの規則を返すこと、そして[リポジトリ](/glossary/リポジトリ/)側で設定されたものか組織側で設定されたものかを問わず返すことです。施行状態が評価のみか無効の ruleset は返りません。

つまりこの出力に規則が並んでいれば、それは今この瞬間に効いている規則です。[リポジトリ](/glossary/リポジトリ/)の設定画面に見当たらないという理由で、規則の存在を否定できません。

## よくある原因と解決手順

### 原因1：規則そのものに触れている

最も単純な系統です。直接 push を禁じる規則や、[マージ](/glossary/マージ/)前の確認を求める規則に当たっています。公式ドキュメントの一覧では、更新の制限は bypass を持つ人だけが push できるという意味だと説明されています。

対処は規則に沿うことです。`Changes must be made through a pull request.` なら作業用の[ブランチ](/glossary/ブランチ/)へ push して[マージ](/glossary/マージ/)要求を出します。[コミット](/glossary/コミット/)の署名を求める規則なら、設定を直したうえで過去の[コミット](/glossary/コミット/)を書き直す必要があります。公式のトラブルシューティング文書も、この場合は手元で履歴を作り直してから push するよう案内しています。

**Before（保護された行き先へ直接送る）：**

```bash
git push origin main
```

**After（作業用の[ブランチ](/glossary/ブランチ/)を経由する）：**

```bash
git switch -c fix/update-version
git push -u origin fix/update-version
```

### 原因2：bypass 一覧に入れたのに、別の身元で push している

設定画面で自分や[自動化](/glossary/自動化/)用の身元を bypass 一覧に加えたのに変わらない、という場合です。原因は[権限](/glossary/権限/)ではなく、push に使われた資格情報にあります。

[GitHub](/glossary/github/) Actions で起きやすい形が知られています。`actions/checkout` は既定で資格情報を[保存](/glossary/保存/)するため、以降の push はその[保存](/glossary/保存/)された身元で行われます。あとから別の[トークン](/glossary/トークン/)を[変数](/glossary/変数/)に入れても、`git push` はそれを読みません。結果として、bypass 一覧に入れた身元ではなく、既定の[トークン](/glossary/トークン/)の身元で判定されます。

**Before（[保存](/glossary/保存/)された資格情報のまま送る）：**

```yaml
- uses: actions/checkout@v4
- run: git push origin main
```

**After（[保存](/glossary/保存/)を止め、送り先に使う身元を明示する）：**

```yaml
- uses: actions/checkout@v4
  with:
    persist-credentials: false
- run: git push "https://x-access-token:${{ secrets.BYPASS_TOKEN }}@github.com/OWNER/REPO" main
```

[GitHub](/glossary/github/) App を使う場合も同じです。App を bypass 一覧に入れ、App の[トークン](/glossary/トークン/)を発行しても、push がそれを使っていなければ意味がありません。発行した[トークン](/glossary/トークン/)が実際に[送信](/glossary/送信/)に使われているかを、まず確かめてください。

bypass の与え方には2種類あることも押さえておきます。公式ドキュメントによれば、常に許可するほかに、[マージ](/glossary/マージ/)要求を経由する場合だけ許可する設定を選べます。後者を選んだ身元は直接 push できず、要求を出したうえで保護を越えて[マージ](/glossary/マージ/)する形になります。自分がどちらの扱いかは、ruleset を取得したときの `current_user_can_bypass` で確認できます。値は常に許可・要求経由のみ・不可・対象外の4つです。

### 原因3：組織の階層で作られた規則に当たっている

[リポジトリ](/glossary/リポジトリ/)の設定画面を見ても該当する規則が無い、という場合です。ruleset は組織や企業の階層でも作られ、複数の[リポジトリ](/glossary/リポジトリ/)を対象にできます。

公式ドキュメントは、複数の ruleset が同じ[ブランチ](/glossary/ブランチ/)を対象にした場合、優先順位ではなく合算で扱うと説明しています。同じ規則が別々に定義されていれば、最も厳しい版が適用されます。branch protection とも重なって効きます。

したがって、1つの ruleset で bypass を持っていても、別の ruleset に当たれば拒まれます。前述の `rules/branches` の経路は階層を問わず返すため、ここで全体を確認するのが確実です。

**Before（[リポジトリ](/glossary/リポジトリ/)の設定画面だけを見る）：**

```text
Settings → Rules → Rulesets
```

**After（効いている規則をすべて列挙する）：**

```bash
gh api "repos/OWNER/REPO/rules/branches/main" --jq '.[] | {type, ruleset_id, ruleset_source_type}'
```

`ruleset_source_type` には `Repository` か `Organization` が入るので、どちらで設定されたものかが分かります。`ruleset_source` には設定元の名前が入ります。

### 原因4：秘密情報の検知で止まっている

`GITHUB PUSH PROTECTION` の見出しの下に `Push cannot contain secrets` が出る場合です。検知された種類と、どの[コミット](/glossary/コミット/)のどの[ファイル](/glossary/ファイル/)の何行目かが併記されます。

ここで多い失敗は、[ファイル](/glossary/ファイル/)を消して[コミット](/glossary/コミット/)し直すだけで送ろうとすることです。検知の対象は履歴に含まれる[コミット](/glossary/コミット/)なので、消した事実を追加しても過去の[コミット](/glossary/コミット/)は残ります。強制的に送り直しても結果は変わりません。

対処は履歴からの除去です。直前の[コミット](/glossary/コミット/)だけなら作り直しで足り、複数にまたがるなら履歴の書き換えが要ります。書き換えた場合は、漏れた値そのものを失効させてください。除去しても、その値が一度でも外に出た可能性は消えません。

出力には解除用の[URL](/glossary/url/) も併記されます。これは検知が誤りである場合に使うもので、実際に有効な値であれば使うべきではありません。

### 原因5：push への規則に当たっている

`GITHUB PUSH PROTECTION` の下に、[拡張子](/glossary/拡張子/)・大きさ・経路に関する文が出る場合です。公式ドキュメントによれば、push への規則は[ブランチ](/glossary/ブランチ/)の指定を必要とせず、その[リポジトリ](/glossary/リポジトリ/)へのすべての push に適用されます。しかも、その[リポジトリ](/glossary/リポジトリ/)から派生した全体にも及びます。

制限できるのは、[ファイル](/glossary/ファイル/)の経路、経路の長さ、[拡張子](/glossary/拡張子/)、[ファイル](/glossary/ファイル/)の大きさの4つです。大きな[ファイル](/glossary/ファイル/)で止まっている場合は、対象を履歴から取り除くか、別の保管方法へ移してください。

もう1つ、公式のトラブルシューティング文書に書かれた上限があります。push への規則が有効な場合、1回の push で更新できる参照は1000件までで、超えると拒まれます。大量の[ブランチ](/glossary/ブランチ/)や[タグ](/glossary/タグ/)をまとめて送るときに当たります。

## 補足：似ているが別のもの

`GH006: Protected branch update failed` は branch protection 由来で、GH013 とは別の仕組みです。公式ドキュメントには `remote: error: GH006: Protected branch update failed for refs/heads/main.` の形で例が載っています。既定の扱いが逆である点に注意してください。branch protection は管理[権限](/glossary/権限/)を持つ人に既定で適用されず、素通りを止めるには明示的な設定が要ります。

`Repository not found` は、そもそも相手が見えていない場合の応答です。規則の話にすら進んでいません（[GitHub の Repository not found の記事](/posts/github_repository_not_found/)）。

`remote: Permission to OWNER/REPO.git denied to USER.` は、[リポジトリ](/glossary/リポジトリ/)への書き込み[権限](/glossary/権限/)が無い場合です。規則ではなく[ロール](/glossary/ロール/)の問題なので、bypass 一覧をいくら直しても変わりません。

[REST](/glossary/rest/) [API](/glossary/api/) 経由の書き込みでも push への規則は効きます。公式のトラブルシューティング文書は、blob の作成・tree の作成・[ファイル](/glossary/ファイル/)の作成と更新の3つの経路に適用されると明記しています。[API](/glossary/api/) を使えば回避できる、という理解は成り立ちません。

施行状態が評価のみの ruleset は拒みません。この状態では違反しても push は通り、記録だけが残ります。GH013 が出ていないのに規則が見えている場合は、この状態を疑ってください。

## 切り分けの順序

1. 出力の `Review all repository rules at` の[URL](/glossary/url/) を開き、効いている規則を確認する。
2. 箇条書きに `GITHUB PUSH PROTECTION` の見出しがあるかを見る。あれば原因4か原因5、無ければ原因1から原因3。
3. 見出しがある場合、下の文が秘密情報か[拡張子](/glossary/拡張子/)などかで原因4と原因5に分ける。
4. 見出しが無い場合、違反した規則の名前を読み、その規則に沿えるかどうかを判断する。
5. bypass を持っているはずなら、`rules/branches` の経路で規則の出どころを確認する。組織側の別の ruleset に当たっていることがある。
6. それでも拒まれるなら、push に使われた資格情報の持ち主を確認する。設定画面ではなく、実際の[送信](/glossary/送信/)に使われた身元を見る。
7. 自動処理なら、資格情報が[保存](/glossary/保存/)されたまま使われていないかを確認する。
8. 直せない規則であれば、[マージ](/glossary/マージ/)要求を経由する経路に切り替える。

## 確認コマンド集

```bash
# 1. 対象のブランチに効いている規則をすべて表示する（最初に行う）
gh api "repos/OWNER/REPO/rules/branches/main"

# 2. 規則の種類と出どころだけを抜き出す（組織側かリポジトリ側かが分かる）
gh api "repos/OWNER/REPO/rules/branches/main" --jq '.[] | {type, ruleset_source_type, ruleset_source}'

# 3. リポジトリに設定されている ruleset の一覧と施行状態を見る
gh api "repos/OWNER/REPO/rulesets" --jq '.[] | {id, name, enforcement}'

# 4. 個別の ruleset の bypass 一覧と、自分の扱いを確認する
gh api "repos/OWNER/REPO/rulesets/RULESET_ID" \
  --jq '{name, enforcement, current_user_can_bypass, bypass_actors}'

# 5. 直近の評価結果を、拒まれたものだけに絞って一覧する
gh api "repos/OWNER/REPO/rulesets/rule-suites?rule_suite_result=fail"

# 6. いま使われている資格情報の持ち主を確認する（HTTPS の場合）
printf 'protocol=https\nhost=github.com\n\n' | git credential fill

# 7. 保存された資格情報を消して、送信に使う身元を入れ直す
printf 'protocol=https\nhost=github.com\n\n' | git credential reject

# 8. 送られる参照を事前に確認する（push への規則は1回あたり1000件が上限）
git push --dry-run --all origin
```

## Editor's Note

bypass 一覧に入れたのに拒まれるという現象は、[GitHub コミュニティの Discussion #110674](https://github.com/orgs/community/discussions/110674) に典型例が残っています。2024年3月に回答が付いています。

投稿者の状況はこうです。main への直接の push を禁じる規則を作り、bypass 一覧に自分を追加した。手元から push すると素通りできる。ところが [GitHub](/glossary/github/) Actions の[ワークフロー](/glossary/ワークフロー/)から同じことをすると `GH013: Repository rule violations found for refs/heads/main.` が返る。設定画面の書き込み[権限](/glossary/権限/)も有効にしてある。

原因は[権限](/glossary/権限/)ではありませんでした。投稿者自身が書いた回答によれば、`actions/checkout` が既定で資格情報を[保存](/glossary/保存/)するため、以降の push がその[保存](/glossary/保存/)された身元で行われていたのです。解決は2段構えでした。取得の段階で[保存](/glossary/保存/)を止め、そのうえで push の[コマンド](/glossary/コマンド/)に、bypass を持つ利用者の[トークン](/glossary/トークン/)を明示的に渡すことです。

同じ構図は [GitHub](/glossary/github/) App でも報告されています。[Discussion #136531](https://github.com/orgs/community/discussions/136531) では、App にすべての[権限](/glossary/権限/)を与え、bypass 一覧にも加え、短命な[トークン](/glossary/トークン/)を発行したうえで、それを[変数](/glossary/変数/)に入れて push しています。それでも同じ符号が返りました。寄せられた指摘は、App の[トークン](/glossary/トークン/)ではなく既定の[トークン](/glossary/トークン/)で送っているのではないか、というものでした。

2件に共通するのは、設定画面で完結すると考えた点です。bypass 一覧は身元の名簿であって、[アカウント](/glossary/アカウント/)に付与される[権限](/glossary/権限/)ではありません。判定されるのは、その push を実際に行った身元です。GH013 が出て bypass を疑うときは、設定を見直す前に、いま誰として送っているのかを確かめてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*