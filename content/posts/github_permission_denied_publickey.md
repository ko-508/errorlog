---
title: "GitHubのpublickeyエラー：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "Permission denied (publickey) はリポジトリ権限ではなく、GitHubとのSSH認証で鍵が受け入れられなかった状態です。ssh -vTのOffering public keyを境に、鍵を提示していないのか、提示した鍵が登録・選択されていないのかを切り分けます。"
tags: ["GitHub"]
images: ["og/posts/github_permission_denied_publickey.png"]
errorCode: "Permission denied (publickey)"
lastmod: 2026-08-05T00:00:00+09:00
service: "GitHub"
error_type: "PermissionDeniedPublickey"
components: ["SSH", "ssh-agent", "Git"]
related_services: ["OpenSSH", "GitHub Enterprise", "SAML SSO"]
trend_incident: false
---

## 冒頭まとめ

`git clone`、`git pull`、`git push` で次のエラーが出た場合、[GitHub](https://github.com/)とのSSH認証が完了していません。

```text
git@github.com: Permission denied (publickey).
fatal: Could not read from remote repository.

Please make sure you have the correct access rights
and the repository exists.
```

最初に押さえるべきは、**この時点では対象リポジトリの権限確認まで進んでいない**ことです。[GitHub公式の説明](https://docs.github.com/en/authentication/troubleshooting-ssh/error-permission-denied-publickey)でも、`Permission denied` はサーバーが接続を拒否した状態とされています。共同編集者の権限、ブランチ保護、リポジトリの公開・非公開を調べる前に、SSH認証を直します。

また、末尾の `publickey` は「公開鍵ファイルが壊れた」という意味ではありません。サーバーが続行を許可した認証方式が公開鍵認証だけで、その方式では利用者を確認できなかったという意味です。実際の認証では、端末にある秘密鍵で署名し、GitHubに登録した公開鍵で検証します。GitHubへ追加するのは `.pub` 側だけです。秘密鍵は送信も貼り付けもしません。

最初の診断は次の1行です。

```bash
ssh -vT git@github.com
```

注目するのは、長い出力の中に `Offering public key` があるかどうかです。

```text
Offering public key がない
  → 使える鍵を見つけていない、または選択していない

Offering public key はあるが、認証されない
  → 提示した鍵がGitHubの該当アカウントに登録されていない、または別の鍵を提示している

Server accepts key の後に signing failed
  → 鍵は認識されたが、ssh-agentなどが署名できていない

Hi USERNAME! You've successfully authenticated...
  → SSH認証は成功。次にリポジトリ権限、remote、SSOを確認する
```

つまり、**新しい鍵を作ることから始めない**のが要点です。まず、失敗したGit操作と同じ端末・同じSSHクライアントが、どの鍵を提示したかを確定します。

## エラーの概要

SSH形式のremoteは、次のような形です。

```text
git@github.com:OWNER/REPOSITORY.git
```

ここで `git` はGitHubのアカウント名ではなく、GitHub.comへのSSH接続で共通して使う利用者名です。どのGitHubアカウントとして認証されるかは、提示したSSH鍵によって決まります。

Git操作は、大きく次の順で進みます。

1. remoteから接続先と方式を決める。
2. SSHクライアントが設定とssh-agentから鍵を選ぶ。
3. GitHubが提示された鍵をアカウントまたはDeploy keyと照合する。
4. 認証後、その主体が対象リポジトリを読み書きできるか確認する。

`Permission denied (publickey)` は3番までに失敗した文言です。末尾に続く `Please make sure you have the correct access rights and the repository exists` は広い案内ですが、そこから先にリポジトリ設定を調べると順番が逆になります。

接続だけを試す公式の確認方法は次のとおりです。

```bash
ssh -T git@github.com
```

成功すると、次の形で認証されたアカウント名が返ります。

```text
Hi USERNAME! You've successfully authenticated, but GitHub does not provide shell access.
```

「shell accessを提供しない」は失敗の説明ではありません。GitHubのSSH接続はGit操作用で、対話型シェルを開かないという意味です。[公式の接続テスト](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection)には、**この成功時にもコマンドは終了コード1を返す**と明記されています。CIやスクリプトで終了コードだけを見ると、成功を失敗と判定するため注意してください。

## まず最初に：失敗した経路で提示した鍵を確認する

第一に、対象リポジトリのremoteを確認します。

```bash
git remote -v
git remote get-url origin
```

第二に、GitがSSHの実行方法を上書きしていないか確認します。

```bash
git config --show-origin --get core.sshCommand
```

何も出なければ、`core.sshCommand` による上書きはありません。値が出た場合は、普段ターミナルで実行している `ssh` と別の実行ファイルや鍵を指定していないかを見ます。

第三に、失敗したGit操作と同じ環境で詳細ログを出します。macOS・Linux・Git Bashでは次のとおりです。

```bash
command -v git
command -v ssh
ssh -vT git@github.com
```

WindowsのPowerShellまたはコマンドプロンプトでは、使用される実行ファイルを次で確認できます。

```powershell
where.exe git
where.exe ssh
ssh -vT git@github.com
```

第四に、`Offering public key` の行に出たファイル名やSHA256フィンガープリントを記録します。鍵の本文ではなく、フィンガープリントで照合します。

## よくある原因と解決手順

### 原因1：remoteの利用者名または接続先が違う

GitHub.comへのSSH接続では、remoteの利用者名は常に `git` です。[GitHub公式](https://docs.github.com/en/authentication/troubleshooting-ssh/error-permission-denied-publickey#always-use-the-git-user)は、GitHubのアカウント名をSSHの利用者名にすると認証に失敗すると説明しています。

**Before（GitHubのアカウント名を使っている）：**

```text
octocat@github.com:OWNER/REPOSITORY.git
```

**After（SSHの利用者名を `git` にする）：**

```bash
git remote set-url origin git@github.com:OWNER/REPOSITORY.git
```

変更後、remoteと接続を確認します。

```bash
git remote -v
ssh -T git@github.com
```

GitHub Enterprise Serverやデータ所在地付きのEnterprise Cloudを使っている場合は、`github.com` ではなく組織から案内されたホスト名を使います。最初から別ホストへ接続しているなら、GitHub.com側へ鍵を登録してもその接続は直りません。

### 原因2：SSHが秘密鍵を見つけていない

`ssh -vT` に次のような行が並び、`Offering public key` が出ない場合です。

```text
identity file /home/user/.ssh/id_ed25519 type -1
Trying private key: /home/user/.ssh/id_ed25519
No more authentication methods to try.
Permission denied (publickey).
```

公式文書では、`identity file` の末尾が `-1` なら使用するファイルを見つけられていないと説明されています。まず既存の鍵を確認します。

```bash
ls -al ~/.ssh
```

[GitHubが案内する既定の公開鍵名](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/checking-for-existing-ssh-keys)は、`id_rsa.pub`、`id_ecdsa.pub`、`id_ed25519.pub` です。秘密鍵は同名から `.pub` を除いた側です。

鍵を既定以外の名前で保存した場合は、ssh-agentへ明示的に追加します。

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519_github
ssh-add -l -E sha256
```

常にその鍵を使うなら、`~/.ssh/config` に指定します。

```text
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_github
    IdentitiesOnly yes
```

`IdentitiesOnly yes` は、ssh-agentに多数の鍵が入っていても、このホストでは指定した鍵だけを使わせる設定です。変更後に `ssh -vT git@github.com` を再実行し、対象の鍵が `Offering public key` に出ることを確認します。

### 原因3：提示した公開鍵がGitHubアカウントに登録されていない

`Offering public key` は出るものの認証されない場合は、提示した鍵とGitHubに登録した鍵をフィンガープリントで照合します。

ssh-agentに読み込まれている鍵は次で確認できます。

```bash
ssh-add -l -E sha256
```

公開鍵ファイルから直接確認する場合は次のとおりです。

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub -E sha256
```

表示されたSHA256フィンガープリントを、GitHubの `Settings` → `SSH and GPG keys` にある鍵と比べます。[GitHub公式の手順](https://docs.github.com/en/authentication/troubleshooting-ssh/error-permission-denied-publickey#verify-the-public-key-is-attached-to-your-account)も、ssh-agentのフィンガープリントとアカウント側の一覧を照合する流れです。

登録されていなければ、公開鍵の内容を追加します。

```bash
cat ~/.ssh/id_ed25519.pub
```

画面へ貼り付けてよいのは、先頭が `ssh-ed25519` などで始まる `.pub` ファイルだけです。次の秘密鍵は表示、共有、GitHubへの登録をしません。

```text
~/.ssh/id_ed25519          ← 秘密鍵。共有しない
~/.ssh/id_ed25519.pub      ← 公開鍵。GitHubへ登録する
```

見覚えのないSSH鍵がGitHubの設定にある場合は、単なる接続不良として放置しません。公式文書は、その鍵を削除してGitHub Supportへ連絡するよう警告しています。

### 原因4：複数アカウント用の別の鍵を提示している

仕事用と個人用など複数のGitHubアカウントを使う環境では、鍵自体は有効でも、対象リポジトリへアクセスできないアカウントの鍵を選ぶことがあります。

まず認証されたアカウント名を見ます。

```bash
ssh -T git@github.com
```

`Hi USERNAME!` の `USERNAME` が想定と違うなら、鍵の選択を固定して試します。

```bash
GIT_SSH_COMMAND='ssh -i ~/.ssh/id_ed25519_work -o IdentitiesOnly=yes -v' \
  git ls-remote origin
```

これで通るなら、ネットワークやリポジトリの存在ではなく、通常時の鍵選択が原因です。[GitHub公式の複数アカウント手順](https://docs.github.com/en/account-and-profile/how-tos/account-management/managing-multiple-accounts#contributing-to-multiple-accounts-using-ssh-and-git_ssh_command)でも、`GIT_SSH_COMMAND` と `-i`、`IdentitiesOnly=yes` を使ってリポジトリごとに鍵を選ぶ方法が示されています。

継続利用する場合は、SSHのホスト別名を作れます。

```text
Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes

Host github-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_personal
    IdentitiesOnly yes
```

対象リポジトリのremoteも、使いたい別名へ合わせます。

```bash
git remote set-url origin git@github-work:OWNER/REPOSITORY.git
ssh -T git@github-work
```

GitHubのコミット作者を決める `user.name`、`user.email` と、SSHで接続するアカウントは別の設定です。`git config user.email` を変えても、提示するSSH鍵は変わりません。

### 原因5：ターミナルとGitHub Desktop・IDE・WSLで実行環境が違う

同じ端末に見えても、GitHub Desktop、IDE、Git Bash、PowerShell、WSL、コンテナ、CIは、別のSSH実行ファイル、別のホームディレクトリ、別のssh-agentを使うことがあります。

たとえば、ターミナルの `ssh -T` が成功しても、GUI側のGit操作が同じ鍵を使っている証明にはなりません。確認すべきなのは失敗した経路です。

```bash
# ターミナル側
command -v ssh
printf '%s\n' "$SSH_AUTH_SOCK"
ssh-add -l -E sha256

# Gitがcore.sshCommandで別のSSHを指定していないか
git config --show-origin --get core.sshCommand
```

WindowsではGit BashとPowerShellでそれぞれ確認します。

```powershell
where.exe ssh
where.exe git
ssh-add -l -E sha256
```

`sudo git pull` や管理者権限でのGit実行も同じ問題を作ります。GitHub公式は、通常権限で作った鍵と `sudo` で実行したGitでは使用される鍵が同じにならないため、Gitに `sudo` や昇格権限を使わないよう案内しています。

```bash
# 避ける
sudo git pull
sudo git push

# リポジトリとファイルの所有権を正したうえで通常利用者として実行する
git pull
git push
```

リポジトリの所有権エラーを `sudo` で隠している場合は、SSH鍵を直す前に、なぜその作業ディレクトリが別利用者の所有になったかを確認してください。

### 原因6：秘密鍵が拒否された、またはssh-agentが署名できない

鍵は存在していても、SSHクライアントが安全でない権限だと判断すると秘密鍵を無視します。

```text
WARNING: UNPROTECTED PRIVATE KEY FILE!
Permissions for '/home/user/.ssh/id_ed25519' are too open.
This private key will be ignored.
```

macOS・Linuxでは、所有者だけが秘密鍵を読める状態へ戻します。

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

`chmod 777` は逆効果です。秘密鍵を全利用者へ開くため、OpenSSHがその鍵を拒否し、漏えいの危険も作ります。WindowsはNTFSのアクセス制御を使うため、Git Bash向けの `chmod` をそのまま答えにせず、`ssh -vT` を実行したSSHクライアントが示すファイルと権限を確認します。

次の形なら、サーバーが公開鍵を認識した後、ssh-agentが秘密鍵による署名に失敗しています。

```text
Agent admitted failure to sign using the key.
sign_and_send_pubkey: signing failed
Permission denied (publickey).
```

[GitHubの接続テスト](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection#testing-your-ssh-connection)にも、この形が一部のLinux環境で発生する既知の問題として記載されています。鍵を作り直す前に、agentへ読み込み直し、同じ鍵で署名できるかを確認します。

```bash
ssh-add -d ~/.ssh/id_ed25519
ssh-add ~/.ssh/id_ed25519
ssh -vT git@github.com
```

古い鍵形式と古いSSHクライアントにも注意が必要です。GitHubは2022年3月15日からDSA鍵をサポートしていません。また、2021年11月2日以降に作られたRSA鍵はSHA-2署名を使う必要があり、古いクライアントでは更新が必要な場合があります。

既存の対応鍵がないと確認できた場合だけ、新しい鍵を作ります。既存の既定鍵を誤って上書きしないよう、用途が分かる名前を指定します。

```bash
ssh-keygen -t ed25519 -C "you@example.com" -f ~/.ssh/id_ed25519_github
ssh-add ~/.ssh/id_ed25519_github
```

生成後は `.pub` 側をGitHubへ登録し、`~/.ssh/config` の `IdentityFile` と一致させます。

### 原因7：SSH認証後のリポジトリ権限またはSSOで拒否されている

`ssh -T git@github.com` が `Hi USERNAME!` まで進むなら、`Permission denied (publickey)` の切り分けは完了です。そのアカウントで対象リポジトリへアクセスできるかを調べます。

```bash
git remote get-url origin
git ls-remote origin
```

ここで `Repository not found` や `Permission to OWNER/REPOSITORY denied to OTHER-USER` が出るなら、SSH鍵がないのではなく、認証された主体とリポジトリ権限の組み合わせが違います。

組織がSSOを使う場合は、鍵を個人アカウントへ登録しただけでは足りないことがあります。[GitHub Enterprise Cloudの公式手順](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-single-sign-on/authorizing-an-ssh-key-for-use-with-single-sign-on)に従い、`Settings` → `SSH and GPG keys` → 対象鍵の `Configure SSO` から組織へ許可します。`Configure SSO` が出ない場合は、その組織のIdPで一度認証し、外部IDを関連付ける必要があります。

Deploy keyは個人アカウントではなく、特定のリポジトリへ公開鍵を直接関連付ける仕組みです。別リポジトリには自動で権限が広がりません。[公式文書](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#deploy-keys)では、Deploy keyは既定で読み取り専用であり、複数リポジトリで同じDeploy keyを再利用できないと説明されています。

## 補足：似ているが別のもの

`Host key verification failed` は、GitHub側のサーバー鍵を確認できない状態です。利用者の公開鍵認証とは方向が逆で、`known_hosts` とGitHubが公開するホスト鍵フィンガープリントを確認します。

`Connection timed out` またはポート22への接続失敗は、鍵を提示する前のネットワーク問題です。ファイアウォールがSSHを遮断する環境では、[GitHub公式のSSH over HTTPS port](https://docs.github.com/en/authentication/troubleshooting-ssh/using-ssh-over-the-https-port)を試せます。

```bash
ssh -T -p 443 git@ssh.github.com
```

ポート443で使うホスト名は `github.com` ではなく `ssh.github.com` です。GitHub Enterprise Serverと、データ所在地付きのEnterprise Cloudでは、この方法はサポートされていません。

HTTPS形式のremoteで出る資格情報エラーは、SSH鍵の問題ではありません。

```text
https://github.com/OWNER/REPOSITORY.git
```

この場合は、Git Credential Manager、個人アクセストークン、ブラウザ認証など、HTTPS側の資格情報を確認します。SSH鍵を追加してもHTTPS remoteの認証には使われません。

`Could not resolve hostname github.com` は名前解決、`Connection refused` は接続先の待受、`no matching host key type found` は暗号方式の交渉です。いずれも `Offering public key` より前に止まるため、アカウントへの公開鍵登録から調べる問題ではありません。

## 切り分けの順序

1. `git remote get-url origin` でSSH形式かHTTPS形式か、接続先ホストがどこかを確認する。
2. GitHub.comのSSH remoteなら、利用者名がGitHubアカウント名ではなく `git` になっているか確認する。
3. 失敗した端末・GUI・WSL・CIと同じ環境で `ssh -vT git@github.com` を実行する。
4. `Offering public key` がなければ、既存鍵、ssh-agent、`IdentityFile`、`core.sshCommand` を確認する。
5. `Offering public key` があれば、そのフィンガープリントとGitHubの `SSH and GPG keys` を照合する。
6. 複数アカウントなら `Hi USERNAME!` の名前を確認し、`-i` と `IdentitiesOnly=yes` で対象鍵を固定して試す。
7. `Server accepts key` の後で止まるなら、agentの署名失敗や秘密鍵の権限を確認する。
8. `Hi USERNAME!` まで通ったら、初めてremoteの所有者、リポジトリ権限、Deploy key、SSOの許可を確認する。
9. 鍵を作り直すのは、既存の対応鍵がない、または失効・漏えいなどで交換が必要だと確認した後にする。

## 確認コマンド集

```bash
# 1. remoteの方式・利用者名・ホストを確認する
git remote -v
git remote get-url origin

# 2. Git側でSSHコマンドを上書きしていないか確認する
git config --show-origin --get core.sshCommand

# 3. 実際に使われるGitとSSHを確認する（macOS・Linux・Git Bash）
command -v git
command -v ssh

# 4. SSH認証を詳細ログ付きで試す
ssh -vT git@github.com

# 5. ssh-agentが保持する鍵とフィンガープリントを確認する
ssh-add -l -E sha256

# 6. 既存の鍵ファイルを確認する
ls -al ~/.ssh

# 7. 公開鍵ファイルのフィンガープリントを確認する
ssh-keygen -lf ~/.ssh/id_ed25519.pub -E sha256

# 8. 特定の鍵だけで対象remoteを試す
GIT_SSH_COMMAND='ssh -i ~/.ssh/id_ed25519_github -o IdentitiesOnly=yes -v' \
  git ls-remote origin

# 9. SSH設定を展開し、接続先・利用者・鍵の指定を確認する
ssh -G github.com | grep -E '^(hostname|user|identityfile|identitiesonly) '

# 10. ポート22が遮断されている場合だけ、443で接続を試す
ssh -T -p 443 git@ssh.github.com
```

## Editor's Note

このエラーの難しさは、**同じPC上のすべてのGit操作が、同じSSHを使うとは限らない**ことです。GitHub Desktopの公式リポジトリには、その境界が見えにくかった記録が残っています。

2019年の報告（[Unable to push/pull from GitHub Desktop after adding SSH key to account](https://github.com/desktop/desktop/issues/7337)）では、SSH鍵をアカウントへ追加し、CLIではremoteを設定してpushできた一方、GitHub Desktopでは取得に失敗しました。画面が示したのは「リポジトリの権限がないか、アーカイブ済みかもしれない」という広い案内です。課題は環境依存として閉じられており、原因は確定していませんが、**CLIで通ることはGUIが同じ認証経路を使う証明にならない**という切り分け上の注意を示しています。

2023年の報告（[SSH key bad permissions results in no error message in GitHub Desktop](https://github.com/desktop/desktop/issues/16875)）では、違いがさらに具体的です。Windowsのネットワークドライブに置いた秘密鍵をGit Bash側のSSHは読めた一方、system OpenSSHはアクセス権が広すぎるとして拒否しました。GitHub Desktopがsystem OpenSSHを使った操作ではpushが終わらず、利用者が期待した `UNPROTECTED PRIVATE KEY FILE` の情報も画面に出ませんでした。

2件を並べると、アカウント画面、remote、鍵ファイルの存在だけを見ても足りない理由が分かります。**SSH認証の成否を決めるのは、失敗した処理が実際に起動したSSHクライアント、そのクライアントが読んだ設定、接続できたagent、そして提示した鍵です**。上位のGUIやIDEが要約すると、途中に出た具体的な理由が「Authentication failed」の一文へ畳まれることがあります。

だから、本記事では鍵の再生成を最初の手順にしていません。まず失敗した経路で `ssh -vT` を実行し、`Offering public key` を境に分ける。提示していないならローカルの選択を直し、提示しているならフィンガープリントを照合する。`Hi USERNAME!` まで通って初めてリポジトリ権限を見る。この順序なら、別の原因に同じ修正を繰り返さずに済みます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
