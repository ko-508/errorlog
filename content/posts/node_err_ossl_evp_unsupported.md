---
title: "Node.jsの暗号方式unsupported対処法"
date: 2026-10-12
slug: node_err_ossl_evp_unsupported
draft: false
description: "ERR_OSSL_EVP_UNSUPPORTEDでwebpackのビルドが止まる場合、OpenSSLが使えない暗号方式を呼んでいる可能性があります。Node.jsと依存関係の確認、webpackの更新、一時的なlegacy指定と解除を説明します。"
tags: ["Node.js", "webpack"]
images: ["og/posts/node_err_ossl_evp_unsupported.png"]
errorCode: "ERR_OSSL_EVP_UNSUPPORTED"
service: "Node.js"
error_type: "unsupported_crypto"
components: ["OpenSSL", "webpack"]
related_services: ["npm"]
trend_incident: false
---

## 冒頭まとめ

Node.jsの更新後、`npm run build`などで次の[エラー](/glossary/エラー/)が出ることがあります。

```text
Error: error:0308010C:digital envelope routines::unsupported
  code: 'ERR_OSSL_EVP_UNSUPPORTED'
```

OpenSSLは、Node.jsが暗号処理などに使う部品です。この[エラー](/glossary/エラー/)は、OpenSSLの現在の[設定](/glossary/設定/)で使えない方式などを呼び出した場合に起こります。古いwebpackでは、[ファイル](/glossary/ファイル/)を識別する値の計算に使うMD4が原因になる例があります。

まず、[エラー](/glossary/エラー/)の実行履歴に出る[パッケージ](/glossary/パッケージ/)と、その版を確認してください。[更新](/glossary/更新/)で原因を取り除くのが本来の[対応](/glossary/対応/)です。`--openssl-legacy-provider`は、古い方式を利用可能にする一時的な回避策です。

## Node.jsの更新で表面化する理由

[Node.js 17.0.0の公式リリース説明](https://nodejs.org/en/blog/release/v17.0.0)は、OpenSSL 3.0の導入と、利用できる方式や鍵の長さの制限変更を説明しています。同じ説明は、`ERR_OSSL_EVP_UNSUPPORTED`が出る場合、アプリや依存する[モジュール](/glossary/モジュール/)が既定では許可されない方式などを使っている可能性が高いとしています。

ただし、Node.js 17以降なら必ず[エラー](/glossary/エラー/)になるわけではありません。呼び出す方式、依存する[パッケージ](/glossary/パッケージ/)の実装、OpenSSLの[設定](/glossary/設定/)によって結果が変わります。Node.jsをさらに新しくするだけで、古いMD4呼び出しが直るとも限りません。

この記事では、Node.js 24.19.0・OpenSSL 3.5.7で、MD4の直接呼び出しによる同じ文言を確認しました。通信先の[証明書](/glossary/証明書/)を検証する[エラー](/glossary/エラー/)とは区別します。

## Node.jsと原因パッケージを確認する

失敗する[プロジェクト](/glossary/プロジェクト/)の[環境](/glossary/環境/)で、次を確認します。

```bash
node -v
node -p "process.versions.openssl"
npm ls webpack
npm ls react-scripts @vue/cli-service
```

後半は、それらの道具を使っている場合の確認例です。`npm ls`では、直接指定した依存だけでなく、別の道具が内部で使うwebpackも確認します。依存関係に問題があると、終了[コード](/glossary/コード/)が非0になる場合があります。

[エラー](/glossary/エラー/)の下に並ぶ実行履歴も読みます。`node:crypto`の直後に`webpack/lib/util/createHash.js`が出る場合と、別のloaderや自分の[コード](/glossary/コード/)が出る場合では、[更新](/glossary/更新/)する対象が異なります。

`npx webpack --version`は、ローカルに実行対象がない場合に取得を促すことがあります。調査のために別のwebpackを取得するより、まず導入済みの依存関係を確認してください。

## webpack本体と周辺の道具を更新する

[webpack 4.47.0のcreateHash実装](https://github.com/webpack/webpack/blob/v4.47.0/lib/util/createHash.js)では、`md4`指定に対し、Node.js 18以上ならwebpack自身のMD4実装を使います。18未満ではNode.jsの`crypto.createHash`へ[処理](/glossary/処理/)が渡ります。webpack 4でも、版と実行環境によって経路が異なります。

webpackを直接管理している[プロジェクト](/glossary/プロジェクト/)なら、[webpackの移行ガイド](https://webpack.js.org/migrate/5/)を参照し、[設定](/glossary/設定/)・loader・pluginを含めて[更新](/glossary/更新/)します。webpack 4を維持する場合も、4.47.0の実装を確認したうえで、[プロジェクト](/glossary/プロジェクト/)の対応範囲内で検証してください。

react-scriptsやVue [CLI](/glossary/cli/)などがwebpackを内部で管理している場合、webpackだけを追加しても、その道具の内部の依存が置き換わるとは限りません。管理元の道具と関連する依存を確認します。

webpack 5という大きな版番号だけでも判断できません。[webpackのIssue #14532](https://github.com/webpack/webpack/issues/14532)には、webpack 5.59.0・Node.js 17.0.0で同じ[エラー](/glossary/エラー/)が出た報告があります。更新後は、[エラー](/glossary/エラー/)を出していた実際の[処理](/glossary/処理/)が通るか確認します。

[output.hashFunctionの公式説明](https://webpack.js.org/configuration/output/#outputhashfunction)にはハッシュ方式の指定があります。ただし、この[設定](/glossary/設定/)がすべてのloaderやpluginの呼び出しを変えるわけではありません。[設定](/glossary/設定/)を一か所変えれば必ず直るとは扱わないでください。

## legacy指定は今回だけの回避に使う

Node.jsの公式[リリース](/glossary/リリース/)説明は、legacy指定を一時的な回避策としています。[Node.jsのコマンドライン文書](https://nodejs.org/api/cli.html#--openssl-legacy-provider)にも、この指定が掲載されています。

macOS・[Linux](/glossary/linux/)の[bash](/glossary/bash/)やzshでは、対象[コマンド](/glossary/コマンド/)だけに[環境変数](/glossary/環境変数/)を渡せます。

```bash
NODE_OPTIONS=--openssl-legacy-provider npm run build
```

Windowsの[コマンドプロンプト](/glossary/コマンドプロンプト/)では、現在の画面で[設定](/glossary/設定/)して実行し、その後に解除します。以下は、既存の`NODE_OPTIONS`が空である場合の例です。

```bat
set "NODE_OPTIONS=--openssl-legacy-provider"
npm run build
set "NODE_OPTIONS="
```

PowerShellでは、同じく未設定の状態なら次を使えます。

```powershell
$env:NODE_OPTIONS = '--openssl-legacy-provider'
npm run build
Remove-Item Env:NODE_OPTIONS
```

[環境変数](/glossary/環境変数/)の操作は[Microsoftのset文書](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/set_1)と[PowerShellの環境変数の説明](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables)を参照してください。Windows上での実行確認は行っていません。

既存の`NODE_OPTIONS`がある場合は、値を記録し、必要な指定を消さないようにしてください。上の代入は既存値を上書きします。恒久的な環境設定や全[プロジェクト](/glossary/プロジェクト/)共通の[設定](/glossary/設定/)へ無条件に追加しないようにします。

## MD4の最小例で確認する

webpackを介さず、Node.jsの呼び出しだけでも確認できます。

```bash
node -e "require('node:crypto').createHash('md4')"
```

この記事の[環境](/glossary/環境/)では、[エラー](/glossary/エラー/)の`message`、`library`、`reason`、`code`を取り出すと次の値になりました。

```text
message: error:0308010C:digital envelope routines::unsupported
library: digital envelope routines
reason: unsupported
code: ERR_OSSL_EVP_UNSUPPORTED
```

同じ[環境](/glossary/環境/)で次を実行すると、MD4の計算は成功しました。

```bash
node --openssl-legacy-provider -e "console.log(require('node:crypto').createHash('md4').update('hello').digest('hex'))"
```

これは、その[環境](/glossary/環境/)でMD4の呼び出しとlegacy指定の効果を確認する例です。[プロジェクト](/glossary/プロジェクト/)全体の修正完了を保証する[テスト](/glossary/テスト/)ではありません。[エラー](/glossary/エラー/)の数値部分や実行履歴の[行番号](/glossary/行番号/)が、すべての[環境](/glossary/環境/)で同じになるとも断定しません。

自分の[コード](/glossary/コード/)で古い方式を指定している場合は、用途に合った方式へ変更します。単なるビルド用の識別値なのか、署名・[認証](/glossary/認証/)・外部とのデータ交換に使うのかで必要な条件が異なるため、置き換え先を一律には決められません。

## 証明書エラーやモジュールエラーとの違い

`CERT_HAS_EXPIRED`や`CERTIFICATE_VERIFY_FAILED`は、通信相手の[証明書](/glossary/証明書/)の検証に関係する[エラー](/glossary/エラー/)です。今回のMD4の例は[通信](/glossary/通信/)を行わずに発生しています。証明書検証の無効化やnpmの`strict-ssl=false`は、このMD4呼び出しへの対処にはなりません。

`ERR_REQUIRE_ESM`は、[モジュール](/glossary/モジュール/)を読み込む方式に関係する別の[エラー](/glossary/エラー/)です。legacy指定でCommonJSとES[モジュール](/glossary/モジュール/)の読み込み規則が変わるわけではありません。

`npm warn EBADENGINE`は、[パッケージ](/glossary/パッケージ/)が要求するNode.jsなどの版と、現在の版の不一致を知らせる警告です。今回の[エラー](/glossary/エラー/)は、実行中の暗号処理から出ています。導入時の警告と、実行時の失敗を分けて確認します。

## 解決手順のまとめ

Node.jsとOpenSSLの版、導入済みwebpackと周辺の道具、失敗した呼び出しの実行履歴を確認します。webpack本体を直すべきか、内部でwebpackを使う道具や別の依存を直すべきかを判断してください。

一時的にlegacy指定を使った場合は、更新後にその指定を外して同じビルドや起動を確認します。指定付きで成功するだけでは、古い方式への依存がなくなったとは判断できません。

今回確認したのはNode.js 24.19.0・OpenSSL 3.5.7によるMD4の最小例です。webpackを追加[インストール](/glossary/インストール/)したビルド検証、Node.js 17での実行、Windowsでの[環境変数](/glossary/環境変数/)の実行確認は行っていません。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
