---
title: "GitHub の Repository not found エラー：原因と解決策"
date: 2026-08-07
description: "git clone や git push で出る Repository not found は、綴りの誤りを知らせる文言ではありません。この文言は2行で出て、1行目は GitHub が返した応答本文、2行目は git が HTTP 404 を受け取ったときだけ出す判断です。404 は未認証では返らないため、この2行が並んだ時点で認証は通っていて、その資格情報の持ち主にリポジトリが見えていないと読めます。"
tags: ["GitHub API"]
images: ["og/posts/github_repository_not_found.png"]
errorCode: "Repository not found"
lastmod: 2026-08-07
service: "GitHub API"
error_type: "Repository not found"
components: ["Git over HTTPS", "Git over SSH"]
related_services: ["Git", "GitHub Actions", "GitHub CLI"]
trend_incident: false
---

## 冒頭まとめ

[git](/glossary/git/) の `Repository not found` は必ず2行で出ますが、その2行は書き手が違います。1行目は [GitHub](/glossary/github/) の[サーバー](/glossary/サーバー/)が返した[レスポンス](/glossary/レスポンス/)本文を [git](/glossary/git/) がそのまま転記したもので、2行目は [git](/glossary/git/) 自身の判断です。書き手を分けて読むと、原因の範囲が一度に絞れます。

決め手は2行目です。[git](/glossary/git/) の実装では、`fatal: repository '...' not found` は [HTTP](/glossary/http/) 404 を受け取ったときにしか出ません（`remote-curl.c` の分岐と `http.h` の `missing__target`）。一方、2026年8月7日の実測では、[GitHub](/glossary/github/) は未[認証](/glossary/認証/)の[リクエスト](/glossary/リクエスト/)に 404 ではなく 401 を返しました。この2行が並んだ時点で、[認証](/glossary/認証/)そのものは成功していて、その[トークン](/glossary/トークン/)や鍵の持ち主に[リポジトリ](/glossary/リポジトリ/)が見えていない、という一点に絞られます。

ここで、よくある誤解が2つ崩れます。綴りの見直しは優先順位が下がります。[GitHub](/glossary/github/) は所有者名と[リポジトリ](/glossary/リポジトリ/)名を大文字小文字の違いを無視して解決するため、`OCTOCAT/HELLO-WORLD` でも通りました（実測で 200）。改名や移管を疑う必要もほとんどありません。旧[パス](/glossary/パス/)への `git clone`・`git fetch`・`git push` は新しい場所への操作として動き続ける、と公式ドキュメントが明記しています。

最初に確定させるべきなのは、いま自分がどの[アカウント](/glossary/アカウント/)として [GitHub](/glossary/github/) と[通信](/glossary/通信/)しているかです。[HTTPS](/glossary/https/) なら保存済みの資格情報、SSH なら提示している鍵が、その入口になります。

## エラーの概要

[HTTPS](/glossary/https/) で出る場合、[ログ](/glossary/ログ/)は次のようになります。[GitHub](/glossary/github/) Actions 上の実際の報告では、[git](/glossary/git/) の終了[コード](/glossary/コード/)は 128 でした。

```text
remote: Repository not found.
fatal: repository 'https://github.com/OWNER/REPO.git/' not found
```

[URL](/glossary/url/) 末尾のスラッシュは入力の誤りではありません。[git](/glossary/git/) は通信前に `end_url_with_slash()` で末尾を揃えており、揃えた後の値を表示しているだけです。ここを直しても何も変わりません。

SSH の場合は文言が変わります。

```text
ERROR: Repository not found.
fatal: Could not read from remote repository.
Please make sure you have the correct access rights
and the repository exists.
```

1行目の `ERROR:` は [GitHub](/glossary/github/) の SSH [サーバー](/glossary/サーバー/)が出したものです。2行目以降は [git](/glossary/git/) の `connect.c` にある `die_initial_contact()` の文言で、相手が[プロトコル](/glossary/プロトコル/)の応答を1つも返さずに接続を閉じると出ます。SSH に [HTTP](/glossary/http/) の[ステータスコード](/glossary/ステータスコード/)はないため、判断材料はこの1行だけです。

[HTTPS](/glossary/https/) 側は実測で確かめられます。2026年8月7日に探索[エンドポイント](/glossary/エンドポイント/)へ直接送ったところ、存在しない[リポジトリ](/glossary/リポジトリ/)への未[認証](/glossary/認証/)[リクエスト](/glossary/リクエスト/)に返ってきたのは 401 でした。

```text
HTTP/2 401
www-authenticate: Basic realm="GitHub"
content-type: text/plain; charset=UTF-8
content-length: 21

Repository not found.
```

同じ[エンドポイント](/glossary/エンドポイント/)へ無効な[トークン](/glossary/トークン/)を付けると、状態[コード](/glossary/コード/)は 401 のままで本文だけが変わります。この本文は実在する公開[リポジトリ](/glossary/リポジトリ/)に対しても同じで、[リポジトリ](/glossary/リポジトリ/)の側については何も語りません。

```text
Invalid username or token. Password authentication is not supported for Git operations.
```

応答本文と2行目は対応しています。本文が `Repository not found.` で2行目が `fatal: repository '...' not found` なら、最終的な応答は 404 です。本文が `Invalid username or token.` で始まり2行目が `fatal: Authentication failed for '...'` なら 401 です。前者は[認証](/glossary/認証/)が通った上での不可視、後者は[認証](/glossary/認証/)そのものの失敗で、直す場所が違います。

## まず最初に：いま誰として通信しているかを確定する

原因を推測する前に、[通信](/glossary/通信/)の主体を1つに固定します。[HTTPS](/glossary/https/) なら、[git](/glossary/git/) が実際に取り出す資格情報を表示させます。`git credential fill` は、設定と保存先と補助[プログラム](/glossary/プログラム/)を経由して、その[エンドポイント](/glossary/エンドポイント/)に使う値を決める公式の手段です。

```bash
printf 'protocol=https\nhost=github.com\n\n' | git credential fill
```

出力の `username` が想定した[アカウント](/glossary/アカウント/)と一致するかを見ます。会社用と個人用を使い分けている[環境](/glossary/環境/)では、別人の名前が出ることが珍しくありません。

SSH なら、鍵がどの[アカウント](/glossary/アカウント/)として受け付けられるかを確認します。公式ドキュメントが示す成功時の出力は、名前が入った1行です。

```bash
ssh -T git@github.com
# -> Hi USERNAME! You've successfully authenticated, but GitHub does not provide shell access.
```

ここに出た `USERNAME` が想定と違えば、その時点で原因は確定します。想定どおりなら、次はその[アカウント](/glossary/アカウント/)に対象が見えるかどうかの問題へ移ります。

## よくある原因と解決手順

### 原因1：保存済みの資格情報が別のアカウントのもの（HTTPS）

資格情報の保存先に古い[トークン](/glossary/トークン/)や別[アカウント](/glossary/アカウント/)の[トークン](/glossary/トークン/)が残っていると、[git](/glossary/git/) はそれを黙って使います。値そのものは有効なので[認証](/glossary/認証/)は成功し、しかしその持ち主には対象が見えないため、[GitHub](/glossary/github/) は 404 を返します。公式ドキュメントも、古い資格情報が保存されたままになっていないか確かめるよう促しています。無効な[トークン](/glossary/トークン/)なら 401 になって別の文言が出るので、`Repository not found` が出ているなら値は生きています。疑うべきは値の正しさではなく、持ち主です。

**Before（保存されている値を確かめずに再試行する）：**

```bash
git clone https://github.com/OWNER/REPO.git
# -> remote: Repository not found.
```

**After（使われる資格情報を表示し、違えば消してから入れ直す）：**

```bash
printf 'protocol=https\nhost=github.com\n\n' | git credential fill
printf 'protocol=https\nhost=github.com\n\n' | git credential reject
git clone https://github.com/OWNER/REPO.git
```

`reject` は保存先から該当の値を消します。次の[通信](/glossary/通信/)で入力を求められるので、そこで正しい[アカウント](/glossary/アカウント/)の[トークン](/glossary/トークン/)を渡します。

### 原因2：トークンの適用範囲に、そのリポジトリが入っていない

[トークン](/glossary/トークン/)が有効でも、届く範囲は種類ごとに決まっており、範囲外の[リポジトリ](/glossary/リポジトリ/)は[権限](/glossary/権限/)不足ではなく不在として扱われます。

細かい[権限](/glossary/権限/)を指定する新しい[トークン](/glossary/トークン/)（fine-grained）は、作成時に対象[リポジトリ](/glossary/リポジトリ/)を選びます。公式ドキュメントは、この[トークン](/glossary/トークン/)が常に全公開[リポジトリ](/glossary/リポジトリ/)への読み取りを含むと説明しています。そのため公開[リポジトリ](/glossary/リポジトリ/)では何も起きず、非公開のものだけが見えないという紛らわしい状態になります。

従来型の[トークン](/glossary/トークン/)（classic）は[スコープ](/glossary/スコープ/)で範囲が決まります。公式ドキュメントは、[スコープ](/glossary/スコープ/)を1つも与えていない[トークン](/glossary/トークン/)が公開情報にしかアクセスできないと明記しており、非公開[リポジトリ](/glossary/リポジトリ/)には `repo` の指定が要ります。

[GitHub](/glossary/github/) Actions が自動で用意する `GITHUB_TOKEN` は、さらに範囲が狭くなります。公式ドキュメントは、この[トークン](/glossary/トークン/)の[権限](/glossary/権限/)がワークフローを含む[リポジトリ](/glossary/リポジトリ/)に限られると明記しており、同じ組織の別[リポジトリ](/glossary/リポジトリ/)にも届きません。

単一サインオン（SSO）を使う組織では、もう1段あります。従来型の[トークン](/glossary/トークン/)は作成後に組織ごとの承認が必要で、承認前は対象が見えません。

**Before（既定の[トークン](/glossary/トークン/)で別[リポジトリ](/glossary/リポジトリ/)を取得しようとする）：**

```yaml
- uses: actions/checkout@v4
  with:
    submodules: recursive
```

**After（対象[リポジトリ](/glossary/リポジトリ/)に届く資格情報を明示的に渡す）：**

```yaml
- uses: actions/checkout@v4
  with:
    token: ${{ secrets.CROSS_REPO_TOKEN }}
    submodules: recursive
```

### 原因3：SSH の鍵が、そのリポジトリを見られない相手に結び付いている

SSH で[通信](/glossary/通信/)の主体を決めるのは[秘密鍵](/glossary/秘密鍵/)です。鍵が別の[アカウント](/glossary/アカウント/)に登録されていれば、[GitHub](/glossary/github/) はその別人として応答します。鍵が複数あると、意図しないものが先に提示されることもあります。

[デプロイ](/glossary/デプロイ/)用の鍵には、さらに厳しい制限があります。公式ドキュメントは、この鍵が1つの[リポジトリ](/glossary/リポジトリ/)にしか[権限](/glossary/権限/)を与えず、使い回せないと明記しています。1台の[サーバー](/glossary/サーバー/)で複数を扱うなら、作り分けが要ります。SSO を使う組織では、鍵そのものにも承認が必要です。

**Before（どの鍵が使われるか任せている）：**

```bash
git clone git@github.com:OWNER/REPO.git
# -> ERROR: Repository not found.
```

**After（対象ごとに別名を用意し、使う鍵を1つに固定する）：**

```
Host github-work
    Hostname github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes
```

```bash
git clone git@github-work:OWNER/REPO.git
```

`IdentitiesOnly yes` は、指定した鍵だけを提示させる設定です。これがないと、エージェントが抱える別の鍵が先に通り、想定と違う[アカウント](/glossary/アカウント/)として扱われることがあります。

### 原因4：トークンを直したのに、通信経路が SSH のまま

[トークン](/glossary/トークン/)を作り直しても状況が変わらないなら、そもそもそれが使われていない可能性があります。公式ドキュメントは、[トークン](/glossary/トークン/)が [HTTPS](/glossary/https/) の [git](/glossary/git/) 操作でしか使えず、SSH のアドレスを設定している場合は [HTTPS](/glossary/https/) への切り替えが要ると明記しています。逆に、鍵を整備したのに [URL](/glossary/url/) が [HTTPS](/glossary/https/) のままでも同じことが起きます。

**Before（経路を確かめずに[トークン](/glossary/トークン/)だけ入れ替える）：**

```bash
git remote -v
# -> origin  git@github.com:OWNER/REPO.git (fetch)
```

**After（使う経路に合わせてアドレスを揃える）：**

```bash
git remote set-url origin https://github.com/OWNER/REPO.git
git remote -v
```

### 原因5：リポジトリが本当に存在しない

ここまでの確認で主体が正しいと分かった場合に限り、不在を疑います。公式ドキュメントは、存在しない[リポジトリ](/glossary/リポジトリ/)へ push しようとした場合にもこの文言が出ると説明しています。

改名や移管そのものは原因になりません。ただし例外が2つ、公式に警告として書かれています。1つは、旧名で新しい[リポジトリ](/glossary/リポジトリ/)を作ると転送が失われること。もう1つは [GitHub](/glossary/github/) Actions に限った話で、改名された[リポジトリ](/glossary/リポジトリ/)にある[アクション](/glossary/アクション/)への呼び出しは転送されず、それを使うワークフローは `repository not found` で失敗します。

綴りについても公式ドキュメントは確認を挙げていますが、大文字小文字は原因になりません。実測では `OCTOCAT/HELLO-WORLD` のように字種を変えた[リクエスト](/glossary/リクエスト/)でも 200 が返っています。疑うべきは字種ではなく、ハイフンとアンダースコアの取り違えや、似た名前の別[リポジトリ](/glossary/リポジトリ/)の指定です。

## 補足：似ているが別のもの

`remote: Permission to OWNER/REPO.git denied to USER.` は、別の状況を指します。相手には[リポジトリ](/glossary/リポジトリ/)が見えており、その操作に必要な[権限](/glossary/権限/)だけが足りていません。公式ドキュメントはこれを、鍵が対象へのアクセスを持たない[アカウント](/glossary/アカウント/)に結び付いている場合の文言として説明し、対処は所有者に共同作業者として追加してもらうことだとしています。鍵が別[リポジトリ](/glossary/リポジトリ/)の[デプロイ](/glossary/デプロイ/)用として登録されていると、末尾が[アカウント](/glossary/アカウント/)名ではなく `OWNER/OTHER-REPO` になります。

`No anonymous write access.` は、公開[リポジトリ](/glossary/リポジトリ/)へ未[認証](/glossary/認証/)のまま push しようとしたときの応答本文で、実測での状態[コード](/glossary/コード/)は 401 でした。[リポジトリ](/glossary/リポジトリ/)は見えているため、`Repository not found` にはなりません。

`fatal: Authentication failed for '...'` は[認証](/glossary/認証/)そのものの失敗です。直前の `remote:` 行に `Invalid username or token.` が出ていれば、[トークン](/glossary/トークン/)の値が誤っているか、期限切れか失効です。

`git@github.com: Permission denied (publickey).` は、提示した鍵がどの[アカウント](/glossary/アカウント/)としても受け付けられなかった状態です。[GitHub](/glossary/github/) が相手を誰とも認識していないため、[リポジトリ](/glossary/リポジトリ/)の判定にまだ進んでいません。

[REST](/glossary/rest/) [API](/glossary/api/) の 404 も考え方は同じですが、応答の読み方が違います。[API](/glossary/api/) 側は [JSON](/glossary/json/) 本文に `message` と `documentation_url` を返すため、判断材料が増えます。詳しくは [GitHub API の 404 の記事](/posts/github_api_404/)を参照してください。[トークン](/glossary/トークン/)の値そのものが疑わしい場合は [GitHub API の 401 の記事](/posts/github_api_401/)が対応します。

## 切り分けの順序

1. `git remote -v` で、通信経路が [HTTPS](/glossary/https/) か SSH かを確定する。以降の確認先がここで分かれる。
2. [HTTPS](/glossary/https/) なら `git credential fill` で、実際に使われる資格情報の持ち主を表示する。想定と違えば原因1で確定する。
3. SSH なら `ssh -T git@github.com` で、鍵がどの[アカウント](/glossary/アカウント/)として認識されるかを表示する。想定と違えば原因3で確定する。
4. 確実に見えるはずの公開[リポジトリ](/glossary/リポジトリ/)に対して、同じ形のクローンを試す。ここで失敗するなら、原因は対象[リポジトリ](/glossary/リポジトリ/)ではなく経路や設定の側にある。
5. `curl -i` で探索[エンドポイント](/glossary/エンドポイント/)を直接叩き、状態[コード](/glossary/コード/)と本文を確認する。
6. 401 なら[認証](/glossary/認証/)の問題として原因1と原因4を、404 なら不可視の問題として原因2と原因3を見る。
7. [トークン](/glossary/トークン/)や鍵の適用範囲、および SSO の承認状態を確認する。組織の設定画面で承認が必要な場合がある。
8. ここまで問題がなければ、Web 画面で存在そのものを確認する。旧名を再利用していないか、Actions から改名済み[リポジトリ](/glossary/リポジトリ/)を呼んでいないかも見る。

## 確認コマンド集

```bash
# 1. 通信経路を確認する（git@ で始まれば SSH、https:// なら HTTPS）
git remote -v

# 2. HTTPS で実際に使われる資格情報の持ち主を表示する
printf 'protocol=https\nhost=github.com\n\n' | git credential fill

# 3. 保存されている資格情報を削除して、入力し直せる状態に戻す
printf 'protocol=https\nhost=github.com\n\n' | git credential reject

# 4. SSH の鍵がどのアカウントとして認識されるかを確認する
ssh -T git@github.com

# 5. 実際に提示された鍵を確認する（offering public key の行を見る）
ssh -v -T git@github.com 2>&1 | grep -i "offering\|Authenticated"

# 6. 探索エンドポイントを直接叩き、状態コードと本文を確認する
curl -i "https://github.com/OWNER/REPO.git/info/refs?service=git-upload-pack"

# 7. トークンを付けた場合の応答を確認する（401 か 404 かで分岐が決まる）
curl -i -u "USERNAME:<your-github-token>" \
  "https://github.com/OWNER/REPO.git/info/refs?service=git-upload-pack"

# 8. 入力待ちを止めて、隠れていた失敗をそのまま表示させる
GIT_TERMINAL_PROMPT=0 git clone https://github.com/OWNER/REPO.git
```

## Editor's Note

この文言がどう人を迷わせるかは、[actions/checkout の Issue #2080](https://github.com/actions/checkout/issues/2080) によく残っています。2025年2月13日に開かれ、現在も開いたままの報告です。

報告者は、非公開[リポジトリ](/glossary/リポジトリ/)の中に同じ組織の非公開[リポジトリ](/glossary/リポジトリ/)をサブモジュールとして抱えた構成を、[GitHub](/glossary/github/) Actions で取得しようとしました。手元の操作でも Web 画面でも扱えているのに、ワークフロー上ではサブモジュールのすべてに `remote: Repository not found.` が返ります。報告者は組織の管理者で、すべての[リポジトリ](/glossary/リポジトリ/)にアクセスできる立場でした。それでもこの文言が出ています。

後から参加した別の利用者が、公式ドキュメントを引いて理由を説明しています。`GITHUB_TOKEN` は [GitHub](/glossary/github/) App の設置[トークン](/glossary/トークン/)であり、その[権限](/glossary/権限/)はワークフローを含む[リポジトリ](/glossary/リポジトリ/)に限られる、という一文です。同じ組織が持つ[リポジトリ](/glossary/リポジトリ/)でも同じだけ信頼されているとは限らないため、これは仕様である、と整理されています。そのうえで、この[エラー](/glossary/エラー/)文言は出来が悪い、とも書き添えられています。

解決の報告も複数あります。従来型の[トークン](/glossary/トークン/)に差し替えた例、`contents` の読み取りと `metadata` を与えた細かい[権限](/glossary/権限/)の[トークン](/glossary/トークン/)を渡した例、[GitHub](/glossary/github/) App の短命な[トークン](/glossary/トークン/)を発行して届かせたい[リポジトリ](/glossary/リポジトリ/)を列挙した例です。いずれも直したのは[リポジトリ](/glossary/リポジトリ/)の側ではなく、[通信](/glossary/通信/)の主体でした。存在を疑うより先に誰として[通信](/glossary/通信/)しているかを確かめる手順が、この[エラー](/glossary/エラー/)には有効に働きます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*