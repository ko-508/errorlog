---
title: "npm E401の原因と対処法"
date: 2026-09-22
draft: false
description: "npm installやnpm publishでE401が出る場合の原因と対処法を解説します。期限切れトークン、未設定の環境変数、scope別レジストリ、.npmrcの認証設定を順に確認します。"
tags: ["npm"]
images: ["og/posts/npm_e401.png"]
errorCode: "npm error code E401"
urgency: "high"
service: "npm"
error_type: "E401"
components: ["authentication", ".npmrc", "npm registry"]
related_services: ["GitHub Packages", "CI/CD"]
trend_incident: false
---

## 冒頭まとめ

`npm install`や`npm publish`で次のエラーが出る場合、パッケージの取得先から認証を拒否されています。

```text
npm error code E401
npm error Unable to authenticate, your authentication token seems to be invalid.
```

最初に、失敗したURLと使用中のレジストリを確認してください。次に、`.npmrc`の認証情報がそのレジストリに結び付いているか、CIへ`NPM_TOKEN`などの環境変数が渡されているかを調べます。

[GitHubの公式発表](https://github.blog/changelog/2025-12-09-npm-classic-tokens-revoked-session-based-auth-and-cli-token-management-now-available/)によると、2025年12月9日にnpmのclassicトークンがすべて無効化されました。古いトークンをCIや`.npmrc`に残している場合は、現在有効なgranular access tokenへの交換が必要です。

## npm E401の意味

E401は、接続したレジストリが認証情報を受け付けなかったときに表示されます。レジストリとは、npmパッケージを取得または公開するサーバーです。

表示は1種類ではありません。代表的には、トークンが無効であるという案内、パスワードが未設定または誤っているという案内、二段階認証を求める案内があります。社内レジストリなどでは、レジストリ側が返した独自の文が表示される場合もあります。

重要なのは、E401が必ずnpmjs.comから返るとは限らないことです。`@myorg/package`のようにscopeが付いたパッケージは、設定によってGitHub Packagesや社内レジストリへ送られます。エラーに含まれるURLを基準に調べてください。

## 使用中のレジストリを確認する

既定のレジストリは次のコマンドで確認できます。

```bash
npm config get registry
```

scope付きパッケージで失敗した場合は、そのscopeに別のレジストリが設定されていないか確認します。

```bash
npm config get @myorg:registry
```

たとえば、次の設定があると、`@myorg`で始まるパッケージのインストールと公開はGitHub Packagesへ送られます。

```ini
@myorg:registry=https://npm.pkg.github.com
```

[npm公式のscope文書](https://docs.npmjs.com/cli/v11/using-npm/scope/#associating-a-scope-with-a-registry)では、scopeをレジストリへ関連付けると、そのscopeのパッケージは指定先から取得され、同じ指定先へ公開されると説明されています。

エラーのURLが`registry.npmjs.org`ではなく、`npm.pkg.github.com`や社内のホスト名なら、その取得先用の認証情報を確認します。

## トークンが期限切れまたは無効になっている

昨日まで動いていたCIが突然E401になった場合は、トークンの期限切れや無効化を確認します。

npmでは2025年12月9日にclassicトークンが恒久的に無効化されました。現在はgranular access tokenだけがサポートされています。また、[2025年9月の公式発表](https://github.blog/changelog/2025-09-29-strengthening-npm-security-important-changes-to-authentication-and-token-management/)では、書き込み権限を持つgranular access tokenの有効期限は上限90日とされています。

CIの秘密情報にclassicトークンや期限切れトークンが残っている場合は、npm上で用途と権限を絞った新しいgranular access tokenを作成し、CI側の秘密情報を交換します。トークンの値は`.npmrc`やワークフローへ直接書かず、CIの秘密情報として保存してください。

ローカル環境からnpmjs.comへ公開する場合は、次のコマンドでログインし直せます。

```bash
npm login
```

2025年12月9日以降、`npm login`で作られるのは2時間で期限切れになるセッショントークンです。これはローカルでの公開操作を続けるための短時間の認証であり、CIへ長期保存するトークンには適しません。CIでの公開にはgranular access tokenを使うか、対応環境では[OIDCによるtrusted publishing](https://docs.npmjs.com/trusted-publishers/)を検討します。

## CIに環境変数が渡されているか確認する

`.npmrc`では、環境変数を次のように参照できます。

```ini
//registry.npmjs.org/:_authToken=${NPM_TOKEN}
```

[npm公式の.npmrc文書](https://docs.npmjs.com/cli/v11/configuring-npm/npmrc/)によると、`NPM_TOKEN`が未定義の場合、`${NPM_TOKEN}`は空文字へ自動変換されず、そのまま残ります。結果として、正しいトークンではない値で認証を試み、E401になる可能性があります。

値そのものを表示せず、環境変数が設定されているかだけを確認してください。macOSやLinuxのシェルでは次を使えます。

```bash
test -n "$NPM_TOKEN" && echo "NPM_TOKEN is set" || echo "NPM_TOKEN is empty"
```

PowerShellでは次のように確認します。

```powershell
if ($env:NPM_TOKEN) { "NPM_TOKEN is set" } else { "NPM_TOKEN is empty" }
```

CIで空になっている場合は、秘密情報の名前、ジョブへ渡す設定、実行条件を確認します。外部リポジトリからの変更要求など、秘密情報が意図的に渡されない実行条件もあります。

変数名の末尾に`?`を付けた`${NPM_TOKEN?}`は、未定義の場合に空文字として扱われます。ただし、認証情報が無い状態になるだけなので、E401の解決にはなりません。必要な処理では、変数が無いときにCIを明示的に停止させるほうが原因を特定しやすくなります。

## 認証情報をレジストリに結び付ける

npmの`_authToken`などの認証情報は、送信先を示すURLと組み合わせて設定します。これは、認証情報を誤ったホストへ送らないための仕組みです。

次のようにURLを付けない設定は使用しません。

```ini
_authToken=${NPM_TOKEN}
```

npmjs.com用なら、次の形で設定します。

```ini
//registry.npmjs.org/:_authToken=${NPM_TOKEN}
```

現在のnpmでURLのない認証設定が見つかった場合は、次のような別のエラーで止まることがあります。

```text
Invalid auth configuration found: `_authToken` must be renamed to `//registry.npmjs.org/:_authToken` in user config
Please run `npm config fix` to repair your configuration.
```

この場合はE401ではありません。案内どおり、設定を確認してから次を実行します。

```bash
npm config fix
```

`npm config fix`は、不正な認証設定を修復し、`_authToken`などを設定済みのレジストリへ結び付けようとするコマンドです。[npm configの公式文書](https://docs.npmjs.com/cli/v11/commands/npm-config/#fix)にもこの用途が記載されています。実行後は`.npmrc`を開き、意図した取得先へ設定されたことを確認してください。

## scopeごとに認証情報を分ける

既定のnpmレジストリと別のレジストリを併用する場合は、それぞれに認証情報が必要です。

```ini
@myorg:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
//registry.npmjs.org/:_authToken=${NPM_TOKEN}
```

この例では、`@myorg`のパッケージには`GITHUB_TOKEN`、npmjs.comには`NPM_TOKEN`を使います。npmjs.com用のトークンだけを設定しても、GitHub Packagesへは送られません。

社内レジストリが特定のパスで提供されている場合は、必要に応じてパスまで含めて設定します。

```ini
@myorg:registry=https://packages.example.com/npm/private/
//packages.example.com/npm/private/:_authToken=${COMPANY_NPM_TOKEN}
```

ホスト名、パス、末尾のスラッシュが実際のレジストリ設定と対応しているかを確認してください。別のサービス用トークンを使い回さず、各レジストリが指定する種類と権限のトークンを利用します。

## npm whoamiで認証を確認する

トークンの値を画面へ出さず、どの利用者として認証されているかを確認するには`npm whoami`を使います。

```bash
npm whoami
```

別のレジストリを調べる場合は、対象を明示します。

```bash
npm whoami --registry=https://npm.pkg.github.com
```

[npm whoamiの公式文書](https://docs.npmjs.com/cli/v11/commands/npm-whoami/)によると、トークン認証に対応するレジストリでは、npmが`/-/whoami`へ接続し、そのトークンに対応する利用者名を表示します。ただし、レジストリがこの確認方法に対応していない場合もあります。

また、OIDCによるtrusted publishingの認証は公開処理の実行時に行われるため、`npm whoami`では確認できません。`npm whoami`が失敗したことだけを理由に、trusted publishingの設定不良とは判断できません。

## .npmrcの場所と優先順位を確認する

npmは、プロジェクト、利用者、全体設定など複数の`.npmrc`を読み込みます。想定と違う認証情報が使われている場合は、利用者用と全体用の設定ファイルの場所を確認してください。

```bash
npm config get userconfig
npm config get globalconfig
```

プロジェクト直下の`.npmrc`も確認します。より優先度の高い設定によって、`registry`やscope別レジストリが上書きされている可能性があります。

認証情報を調査するときは、トークンの値をログへ出さないでください。特にCIでは、設定ファイル全体を`cat`などで表示すると秘密情報が記録されるおそれがあります。確認するのは、レジストリのURL、認証設定のキー、参照している環境変数名までにします。

## 二段階認証を求められた場合

E401と一緒に`This operation requires a one-time password`と表示された場合は、二段階認証が必要です。表示されたURLをブラウザで開いて認証するか、認証アプリの一時的な符号を求められている場合は、実行したコマンドに`--otp`を付けます。

```bash
npm publish --otp=<code>
```

一時的な符号には有効時間があります。入力を間違えた場合や期限が切れた場合は、新しく表示された符号でやり直してください。CIでは対話入力ができないため、npmが提供するCI向けの認証方法を使います。

## package-lock.jsonの削除では直らない

E401はレジストリが認証を拒否した結果です。`package-lock.json`を削除しても、期限切れトークン、未設定の環境変数、誤ったレジストリ設定は直りません。

ロックファイルを削除すると依存する版が変わる可能性もあります。先にエラーのURL、レジストリ、`.npmrc`、CIの秘密情報を確認してください。

## 近い認証エラーとの違い

`npm error code EOTP`は、公開などの操作で二段階認証の一時的な符号が必要な場合に表示されます。E401でも本文に二段階認証の案内が含まれる場合があるため、コードだけでなく続く文を確認してください。

`Invalid auth configuration found`は、URLに結び付いていない`_authToken`などをnpmが設定検証で見つけた状態です。レジストリからE401を返される前に、手元の設定検証で止まっています。

## 解決手順のまとめ

まずエラーに表示されたURLと`npm config get registry`を確認し、認証を拒否したレジストリを特定します。scope付きパッケージなら、`npm config get @scope:registry`で別の取得先が設定されていないか調べてください。

次に`.npmrc`の認証情報が対象レジストリへ結び付いているか、CIへ必要な環境変数が渡されているかを確認します。トークンの値はログへ表示しません。

classicトークン、期限切れトークン、無効化されたトークンは、現在有効なgranular access tokenへ交換します。ローカルの公開作業は`npm login`で認証し直せますが、セッションは2時間で期限切れになるため、CI用の秘密情報としては使いません。

最後に`npm whoami --registry=<URL>`で認証先を確認します。認証情報、取得先、権限の対応を直すことがE401の解決になります。

免責事項：本記事の内容は一般的なnpm、npmjs.com、GitHub Packages、CI環境を前提としています。トークンや`.npmrc`を変更する前に現在の設定を保存し、秘密情報をログやリポジトリへ出さないようにしてください。社内レジストリでは、管理者が定めた認証方法と更新手順を優先してください。
