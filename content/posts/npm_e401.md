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

`npm install`や`npm publish`で次の[エラー](/glossary/エラー/)が出る場合、[パッケージ](/glossary/パッケージ/)の取得先から[認証](/glossary/認証/)を拒否されています。

```text
npm error code E401
npm error Unable to authenticate, your authentication token seems to be invalid.
```

最初に、失敗した[URL](/glossary/url/)と使用中の[レジストリ](/glossary/レジストリ/)を確認してください。次に、`.npmrc`の認証情報がその[レジストリ](/glossary/レジストリ/)に結び付いているか、CIへ`NPM_TOKEN`などの[環境変数](/glossary/環境変数/)が渡されているかを調べます。

[GitHubの公式発表](https://github.blog/changelog/2025-12-09-npm-classic-tokens-revoked-session-based-auth-and-cli-token-management-now-available/)によると、2025年12月9日にnpmのclassic[トークン](/glossary/トークン/)がすべて無効化されました。古い[トークン](/glossary/トークン/)をCIや`.npmrc`に残している場合は、現在有効なgranular access tokenへの交換が必要です。

## npm E401の意味

E401は、接続した[レジストリ](/glossary/レジストリ/)が認証情報を受け付けなかったときに表示されます。[レジストリ](/glossary/レジストリ/)とは、npm[パッケージ](/glossary/パッケージ/)を取得または公開する[サーバー](/glossary/サーバー/)です。

表示は1種類ではありません。代表的には、[トークン](/glossary/トークン/)が無効であるという案内、[パスワード](/glossary/パスワード/)が未設定または誤っているという案内、[二段階認証](/glossary/二段階認証/)を求める案内があります。社内[レジストリ](/glossary/レジストリ/)などでは、[レジストリ](/glossary/レジストリ/)側が返した独自の文が表示される場合もあります。

重要なのは、E401が必ずnpmjs.comから返るとは限らないことです。`@myorg/package`のようにscopeが付いた[パッケージ](/glossary/パッケージ/)は、[設定](/glossary/設定/)によって[GitHub](/glossary/github/) Packagesや社内[レジストリ](/glossary/レジストリ/)へ送られます。[エラー](/glossary/エラー/)に含まれる[URL](/glossary/url/)を基準に調べてください。

## 使用中のレジストリを確認する

既定の[レジストリ](/glossary/レジストリ/)は次の[コマンド](/glossary/コマンド/)で確認できます。

```bash
npm config get registry
```

scope付き[パッケージ](/glossary/パッケージ/)で失敗した場合は、そのscopeに別の[レジストリ](/glossary/レジストリ/)が[設定](/glossary/設定/)されていないか確認します。

```bash
npm config get @myorg:registry
```

たとえば、次の[設定](/glossary/設定/)があると、`@myorg`で始まる[パッケージ](/glossary/パッケージ/)の[インストール](/glossary/インストール/)と公開は[GitHub](/glossary/github/) Packagesへ送られます。

```ini
@myorg:registry=https://npm.pkg.github.com
```

[npm公式のscope文書](https://docs.npmjs.com/cli/v11/using-npm/scope/#associating-a-scope-with-a-registry)では、scopeを[レジストリ](/glossary/レジストリ/)へ関連付けると、そのscopeの[パッケージ](/glossary/パッケージ/)は指定先から取得され、同じ指定先へ公開されると説明されています。

[エラー](/glossary/エラー/)の[URL](/glossary/url/)が`registry.npmjs.org`ではなく、`npm.pkg.github.com`や社内のホスト名なら、その取得先用の認証情報を確認します。

## トークンが期限切れまたは無効になっている

昨日まで動いていたCIが突然E401になった場合は、[トークン](/glossary/トークン/)の期限切れや無効化を確認します。

npmでは2025年12月9日にclassic[トークン](/glossary/トークン/)が恒久的に無効化されました。現在はgranular access tokenだけがサポートされています。また、[2025年9月の公式発表](https://github.blog/changelog/2025-09-29-strengthening-npm-security-important-changes-to-authentication-and-token-management/)では、書き込み[権限](/glossary/権限/)を持つgranular access tokenの有効期限は上限90日とされています。

CIの秘密情報にclassic[トークン](/glossary/トークン/)や期限切れ[トークン](/glossary/トークン/)が残っている場合は、npm上で用途と[権限](/glossary/権限/)を絞った新しいgranular access tokenを作成し、CI側の秘密情報を交換します。[トークン](/glossary/トークン/)の値は`.npmrc`や[ワークフロー](/glossary/ワークフロー/)へ直接書かず、CIの秘密情報として[保存](/glossary/保存/)してください。

ローカル[環境](/glossary/環境/)からnpmjs.comへ公開する場合は、次の[コマンド](/glossary/コマンド/)で[ログイン](/glossary/ログイン/)し直せます。

```bash
npm login
```

2025年12月9日以降、`npm login`で作られるのは2時間で期限切れになるセッショントークンです。これはローカルでの公開操作を続けるための短時間の[認証](/glossary/認証/)であり、CIへ長期保存する[トークン](/glossary/トークン/)には適しません。CIでの公開にはgranular access tokenを使うか、対応環境では[OIDCによるtrusted publishing](https://docs.npmjs.com/trusted-publishers/)を検討します。

## CIに環境変数が渡されているか確認する

`.npmrc`では、[環境変数](/glossary/環境変数/)を次のように参照できます。

```ini
//registry.npmjs.org/:_authToken=${NPM_TOKEN}
```

[npm公式の.npmrc文書](https://docs.npmjs.com/cli/v11/configuring-npm/npmrc/)によると、`NPM_TOKEN`が未定義の場合、`${NPM_TOKEN}`は空文字へ自動変換されず、そのまま残ります。結果として、正しい[トークン](/glossary/トークン/)ではない値で[認証](/glossary/認証/)を試み、E401になる可能性があります。

値そのものを表示せず、[環境変数](/glossary/環境変数/)が[設定](/glossary/設定/)されているかだけを確認してください。macOSや[Linux](/glossary/linux/)の[シェル](/glossary/シェル/)では次を使えます。

```bash
test -n "$NPM_TOKEN" && echo "NPM_TOKEN is set" || echo "NPM_TOKEN is empty"
```

PowerShellでは次のように確認します。

```powershell
if ($env:NPM_TOKEN) { "NPM_TOKEN is set" } else { "NPM_TOKEN is empty" }
```

CIで空になっている場合は、秘密情報の名前、ジョブへ渡す[設定](/glossary/設定/)、実行条件を確認します。外部[リポジトリ](/glossary/リポジトリ/)からの変更要求など、秘密情報が意図的に渡されない実行条件もあります。

変数名の末尾に`?`を付けた`${NPM_TOKEN?}`は、未定義の場合に空文字として扱われます。ただし、認証情報が無い状態になるだけなので、E401の解決にはなりません。必要な処理では、[変数](/glossary/変数/)が無いときにCIを明示的に停止させるほうが原因を特定しやすくなります。

## 認証情報をレジストリに結び付ける

npmの`_authToken`などの認証情報は、送信先を示す[URL](/glossary/url/)と組み合わせて[設定](/glossary/設定/)します。これは、認証情報を誤ったホストへ送らないための仕組みです。

次のように[URL](/glossary/url/)を付けない[設定](/glossary/設定/)は使用しません。

```ini
_authToken=${NPM_TOKEN}
```

npmjs.com用なら、次の形で[設定](/glossary/設定/)します。

```ini
//registry.npmjs.org/:_authToken=${NPM_TOKEN}
```

現在のnpmで[URL](/glossary/url/)のない認証設定が見つかった場合は、次のような別の[エラー](/glossary/エラー/)で止まることがあります。

```text
Invalid auth configuration found: `_authToken` must be renamed to `//registry.npmjs.org/:_authToken` in user config
Please run `npm config fix` to repair your configuration.
```

この場合はE401ではありません。案内どおり、[設定](/glossary/設定/)を確認してから次を実行します。

```bash
npm config fix
```

`npm config fix`は、不正な認証設定を修復し、`_authToken`などを設定済みの[レジストリ](/glossary/レジストリ/)へ結び付けようとする[コマンド](/glossary/コマンド/)です。[npm configの公式文書](https://docs.npmjs.com/cli/v11/commands/npm-config/#fix)にもこの用途が記載されています。実行後は`.npmrc`を開き、意図した取得先へ[設定](/glossary/設定/)されたことを確認してください。

## scopeごとに認証情報を分ける

既定のnpm[レジストリ](/glossary/レジストリ/)と別の[レジストリ](/glossary/レジストリ/)を併用する場合は、それぞれに認証情報が必要です。

```ini
@myorg:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
//registry.npmjs.org/:_authToken=${NPM_TOKEN}
```

この例では、`@myorg`の[パッケージ](/glossary/パッケージ/)には`GITHUB_TOKEN`、npmjs.comには`NPM_TOKEN`を使います。npmjs.com用の[トークン](/glossary/トークン/)だけを[設定](/glossary/設定/)しても、[GitHub](/glossary/github/) Packagesへは送られません。

社内[レジストリ](/glossary/レジストリ/)が特定の[パス](/glossary/パス/)で提供されている場合は、必要に応じて[パス](/glossary/パス/)まで含めて[設定](/glossary/設定/)します。

```ini
@myorg:registry=https://packages.example.com/npm/private/
//packages.example.com/npm/private/:_authToken=${COMPANY_NPM_TOKEN}
```

ホスト名、[パス](/glossary/パス/)、末尾のスラッシュが実際の[レジストリ](/glossary/レジストリ/)[設定](/glossary/設定/)と[対応](/glossary/対応/)しているかを確認してください。別のサービス用[トークン](/glossary/トークン/)を使い回さず、各[レジストリ](/glossary/レジストリ/)が指定する種類と[権限](/glossary/権限/)の[トークン](/glossary/トークン/)を利用します。

## npm whoamiで認証を確認する

[トークン](/glossary/トークン/)の値を画面へ出さず、どの利用者として[認証](/glossary/認証/)されているかを確認するには`npm whoami`を使います。

```bash
npm whoami
```

別の[レジストリ](/glossary/レジストリ/)を調べる場合は、対象を明示します。

```bash
npm whoami --registry=https://npm.pkg.github.com
```

[npm whoamiの公式文書](https://docs.npmjs.com/cli/v11/commands/npm-whoami/)によると、[トークン](/glossary/トークン/)[認証](/glossary/認証/)に[対応](/glossary/対応/)する[レジストリ](/glossary/レジストリ/)では、npmが`/-/whoami`へ接続し、その[トークン](/glossary/トークン/)に[対応](/glossary/対応/)する利用者名を表示します。ただし、[レジストリ](/glossary/レジストリ/)がこの確認方法に[対応](/glossary/対応/)していない場合もあります。

また、OIDCによるtrusted publishingの[認証](/glossary/認証/)は公開処理の実行時に行われるため、`npm whoami`では確認できません。`npm whoami`が失敗したことだけを理由に、trusted publishingの設定不良とは判断できません。

## .npmrcの場所と優先順位を確認する

npmは、[プロジェクト](/glossary/プロジェクト/)、利用者、全体設定など複数の`.npmrc`を読み込みます。想定と違う認証情報が使われている場合は、利用者用と全体用の[設定ファイル](/glossary/設定ファイル/)の場所を確認してください。

```bash
npm config get userconfig
npm config get globalconfig
```

[プロジェクト](/glossary/プロジェクト/)直下の`.npmrc`も確認します。より優先度の高い[設定](/glossary/設定/)によって、`registry`やscope別[レジストリ](/glossary/レジストリ/)が上書きされている可能性があります。

認証情報を調査するときは、[トークン](/glossary/トークン/)の値を[ログ](/glossary/ログ/)へ出さないでください。特にCIでは、[設定ファイル](/glossary/設定ファイル/)全体を`cat`などで表示すると秘密情報が記録されるおそれがあります。確認するのは、[レジストリ](/glossary/レジストリ/)の[URL](/glossary/url/)、認証設定の[キー](/glossary/キー/)、参照している環境変数名までにします。

## 二段階認証を求められた場合

E401と一緒に`This operation requires a one-time password`と表示された場合は、[二段階認証](/glossary/二段階認証/)が必要です。表示された[URL](/glossary/url/)を[ブラウザ](/glossary/ブラウザ/)で開いて[認証](/glossary/認証/)するか、[認証](/glossary/認証/)アプリの一時的な符号を求められている場合は、実行した[コマンド](/glossary/コマンド/)に`--otp`を付けます。

```bash
npm publish --otp=<code>
```

一時的な符号には有効時間があります。入力を間違えた場合や期限が切れた場合は、新しく表示された符号でやり直してください。CIでは対話入力ができないため、npmが提供するCI向けの認証方法を使います。

## package-lock.jsonの削除では直らない

E401は[レジストリ](/glossary/レジストリ/)が[認証](/glossary/認証/)を拒否した結果です。`package-lock.json`を[削除](/glossary/削除/)しても、期限切れ[トークン](/glossary/トークン/)、未設定の[環境変数](/glossary/環境変数/)、誤った[レジストリ](/glossary/レジストリ/)[設定](/glossary/設定/)は直りません。

ロックファイルを[削除](/glossary/削除/)すると依存する版が変わる可能性もあります。先に[エラー](/glossary/エラー/)の[URL](/glossary/url/)、[レジストリ](/glossary/レジストリ/)、`.npmrc`、CIの秘密情報を確認してください。

## 近い認証エラーとの違い

`npm error code EOTP`は、公開などの操作で[二段階認証](/glossary/二段階認証/)の一時的な符号が必要な場合に表示されます。E401でも本文に[二段階認証](/glossary/二段階認証/)の案内が含まれる場合があるため、[コード](/glossary/コード/)だけでなく続く文を確認してください。

`Invalid auth configuration found`は、[URL](/glossary/url/)に結び付いていない`_authToken`などをnpmが設定検証で見つけた状態です。[レジストリ](/glossary/レジストリ/)からE401を返される前に、手元の設定検証で止まっています。

## 解決手順のまとめ

まず[エラー](/glossary/エラー/)に表示された[URL](/glossary/url/)と`npm config get registry`を確認し、[認証](/glossary/認証/)を拒否した[レジストリ](/glossary/レジストリ/)を特定します。scope付き[パッケージ](/glossary/パッケージ/)なら、`npm config get @scope:registry`で別の取得先が[設定](/glossary/設定/)されていないか調べてください。

次に`.npmrc`の認証情報が対象[レジストリ](/glossary/レジストリ/)へ結び付いているか、CIへ必要な[環境変数](/glossary/環境変数/)が渡されているかを確認します。[トークン](/glossary/トークン/)の値は[ログ](/glossary/ログ/)へ表示しません。

classic[トークン](/glossary/トークン/)、期限切れ[トークン](/glossary/トークン/)、無効化された[トークン](/glossary/トークン/)は、現在有効なgranular access tokenへ交換します。ローカルの公開作業は`npm login`で[認証](/glossary/認証/)し直せますが、[セッション](/glossary/セッション/)は2時間で期限切れになるため、CI用の秘密情報としては使いません。

最後に`npm whoami --registry=<URL>`で認証先を確認します。認証情報、取得先、[権限](/glossary/権限/)の[対応](/glossary/対応/)を直すことがE401の解決になります。

免責事項：本記事の内容は一般的なnpm、npmjs.com、[GitHub](/glossary/github/) Packages、CI[環境](/glossary/環境/)を前提としています。[トークン](/glossary/トークン/)や`.npmrc`を変更する前に現在の[設定](/glossary/設定/)を[保存](/glossary/保存/)し、秘密情報を[ログ](/glossary/ログ/)や[リポジトリ](/glossary/リポジトリ/)へ出さないようにしてください。社内[レジストリ](/glossary/レジストリ/)では、管理者が定めた認証方法と更新手順を優先してください。
