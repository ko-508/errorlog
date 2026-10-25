---
title: "npmのMissing scriptエラー対処法"
date: 2026-10-15
slug: npm_missing_script
draft: false
description: "npm startやnpm run devでMissing scriptが出たら、npm runで定義を確認します。実行場所、workspace、scriptsへの追加、server.jsの例外、ENOENTや実行コマンドの失敗との違いを説明します。"
tags: ["npm", "Node.js"]
images: ["og/posts/npm_missing_script.png"]
errorCode: "Missing script"
service: "npm"
error_type: "missing_script"
components: ["package.json", "npm run"]
related_services: ["Node.js"]
trend_incident: false
---

## 冒頭まとめ

`npm start`や`npm run dev`で次の[エラー](/glossary/エラー/)が出たら、まず利用できる[スクリプト](/glossary/スクリプト/)を確認します。ここでの[スクリプト](/glossary/スクリプト/)は、package.jsonの`scripts`に登録した[コマンド](/glossary/コマンド/)です。

```text
npm error Missing script: "start"
```

```bash
npm run
```

一覧に`dev`はあって`start`がないなら、その[プロジェクト](/glossary/プロジェクト/)の説明を確認し、開発用の起動には`npm run dev`を使う場合があります。名前と用途は[プロジェクト](/glossary/プロジェクト/)ごとに異なります。

npmの再[インストール](/glossary/インストール/)や[キャッシュ](/glossary/キャッシュ/)[削除](/glossary/削除/)より先に、対象のpackage.json、登録名、実行場所を確認してください。

## Missing scriptは登録した名前が見つからないという意味

[npm runの公式文書](https://docs.npmjs.com/cli/v11/commands/npm-run/)は、package.jsonの`scripts`から指定した名前を実行し、名前を省略すると一覧を表示すると説明しています。

たとえば次の定義なら、`npm run dev`と`npm run build`は別の[処理](/glossary/処理/)です。

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  }
}
```

これはViteを使う場合の例です。この内容を、別の道具を使う[プロジェクト](/glossary/プロジェクト/)へそのまま追加するものではありません。

`npm run index.js`は、単に`index.js`という[ファイル](/glossary/ファイル/)を実行する指定ではなく、`scripts`の`index.js`という名前を探します。Node.jsで[ファイル](/glossary/ファイル/)を直接実行したいなら、用途に応じて`node index.js`を使います。

`Missing script`の段階では、目的の[スクリプト](/glossary/スクリプト/)本体は実行されていません。ただし、npmには`start`などの特別な動作があり、すべての名前を同じ条件で説明できるわけではありません。

## npm runで名前と用途を確認する

まず一覧を表示します。

```bash
npm run
```

package.jsonも開き、`scripts`内の名前と[コマンド](/glossary/コマンド/)を読みます。`build`が定義されているのに`biuld`と入力していれば、名前を直します。package.jsonを編集した直後なら、保存済みかも確認してください。

[エラー](/glossary/エラー/)には`Did you mean`という候補が出ることがあります。ただし、候補は起動方法を正しく推測した結果とは限りません。

今回のnpm 11.9.0による確認では、`start`がない状態で`npm start`を実行すると、次の候補が表示されました。

```text
Did you mean one of these?
  npm star # Mark your favorite packages
  npm stars # View packages marked as favorites
```

これらは[パッケージ](/glossary/パッケージ/)のお気に入りに関する[コマンド](/glossary/コマンド/)で、アプリを起動する操作ではありません。候補をそのまま実行するのではなく、[プロジェクト](/glossary/プロジェクト/)の説明と[スクリプト](/glossary/スクリプト/)一覧を確認します。

同じ確認で、`biuld`に対する`build`の候補は表示されませんでした。似た名前が必ず案内されるとは考えないでください。

## 実行場所とworkspaceを確認する

同じ[リポジトリ](/glossary/リポジトリ/)に複数のpackage.jsonがある場合、別の[パッケージ](/glossary/パッケージ/)に目的の[スクリプト](/glossary/スクリプト/)が定義されていることがあります。

macOS・[Linux](/glossary/linux/)・[Git](/glossary/git/) Bashなら、現在の場所を次で確認できます。

```bash
pwd
```

Windowsの[コマンドプロンプト](/glossary/コマンドプロンプト/)なら、次を使います。

```bat
cd
```

READMEなどが案内する[ディレクトリ](/glossary/ディレクトリ/)へ移動し、そこで`npm run`を確認します。子[ディレクトリ](/glossary/ディレクトリ/)からの実行では親の[パッケージ](/glossary/パッケージ/)が使われる場合もあるため、現在の場所に[ファイル](/glossary/ファイル/)がないことだけで判断しないでください。

workspaceは、複数の[パッケージ](/glossary/パッケージ/)をまとめて管理するnpmの機能です。設定済みのworkspaceがある場合は、対象を明示できます。

```bash
npm run --workspace=app
npm run dev --workspace=app
```

最初は対象の一覧表示、次が`dev`の実行です。`app`は実際のworkspace名に置き換えます。[公式文書のworkspaceの説明](https://docs.npmjs.com/cli/v11/commands/npm-run/#workspaces-support)には、名前や[パス](/glossary/パス/)で対象を選ぶ方法があります。

今回の最小例では、ルートに`dev`がなく、workspaceの`app`だけにある構成を作りました。ルートの`npm run dev`は失敗し、`--workspace=app`を付けると成功しました。

## 必要な場合だけscriptsへ追加する

既に別名で正しい[処理](/glossary/処理/)が定義されているなら、名前を増やす必要はありません。配布先や運用が`npm start`を必要とし、[プロジェクト](/glossary/プロジェクト/)側でも定義する方針なら、実際の起動[コマンド](/glossary/コマンド/)を登録します。

Node.jsで`index.js`を実行するアプリの例です。

```json
{
  "scripts": {
    "start": "node index.js"
  }
}
```

既存の`scripts`にほかの項目がある場合は、それらを残して追加してください。`index.js`も実際の起動[ファイル](/glossary/ファイル/)に合わせます。[フレームワーク](/glossary/フレームワーク/)を使う場合は、その公式手順に沿った起動[コマンド](/glossary/コマンド/)を指定します。

package.jsonの`main`と`scripts.start`は別の項目です。[npm startの公式文書](https://docs.npmjs.com/cli/v11/commands/npm-start/)も、`npm start`と、`main`を参照する`node .`の動作を区別しています。

[npm CLIのIssue #8002](https://github.com/npm/cli/issues/8002)には、HTMLとCSSの[フォルダ](/glossary/フォルダ/)で初期化後に`npm start`が失敗し、http-serverを導入しても同じだったという報告があります。[パッケージ](/glossary/パッケージ/)を入れることと、`start`の実行内容を定義することは別です。この報告の全原因や解決までを確認したものではありません。

## server.jsとif-presentの例外を確認する

npm 11.9.0では、`scripts.start`がなくても、[パッケージ](/glossary/パッケージ/)のルートに`server.js`があると`npm start`が`node server.js`を実行しました。[npmのスクリプト公式文書](https://docs.npmjs.com/cli/v11/using-npm/scripts/#default-values)にも、この既定動作が説明されています。

ただし、名前が違う[ファイル](/glossary/ファイル/)を自動で探して起動するわけではありません。`server.js`を置くだけで、任意の[フレームワーク](/glossary/フレームワーク/)の[設定](/glossary/設定/)が完成するわけでもありません。実際の[エラー](/glossary/エラー/)が出る[環境](/glossary/環境/)では、npmの版と[プロジェクト](/glossary/プロジェクト/)の定義を確認してください。

存在する場合だけ実行したい任意の[スクリプト](/glossary/スクリプト/)なら、`--if-present`を使えます。

```bash
npm run lint --if-present
```

[if-presentの公式説明](https://docs.npmjs.com/cli/v11/using-npm/config/#if-present)は、定義がなければ[エラー](/glossary/エラー/)にせず、定義があってその実行が失敗した場合は失敗として扱うとしています。

今回の確認でも、未定義の`lint`は終了[コード](/glossary/コード/)0、定義済みで終了[コード](/glossary/コード/)7を返す[処理](/glossary/処理/)は7でした。失敗をすべて無視する指定ではありません。

必須の起動や検査に付けると、[処理](/glossary/処理/)を実行していないのに成功したように扱われるため、単に[エラー](/glossary/エラー/)を消す目的では使わないでください。

## ENOENTやコマンド本体の失敗との違い

package.jsonを見つけられない場合は、[スクリプト](/glossary/スクリプト/)名の不足とは異なります。今回、親にもpackage.jsonがない独立した[ディレクトリ](/glossary/ディレクトリ/)で`npm start`を実行すると、次の表示で停止しました。

```text
npm error code ENOENT
npm error syscall open
npm error enoent Could not read package.json
```

この場合は、[ファイル](/glossary/ファイル/)の場所や取得した[プロジェクト](/glossary/プロジェクト/)を確認します。既存[プロジェクト](/glossary/プロジェクト/)を使うつもりなら、違う場所で`npm init`して[エラー](/glossary/エラー/)を消すより先に、正しいpackage.jsonを探してください。

一方、[スクリプト](/glossary/スクリプト/)名は見つかったが、その中の[コマンド](/glossary/コマンド/)がない場合は、`command not found`やWindowsの[コマンド](/glossary/コマンド/)未認識など、別の[エラー](/glossary/エラー/)になります。その段階では、定義された[コマンド](/glossary/コマンド/)名と依存関係の導入状況を確認します。

構文が壊れたpackage.jsonも、登録名の不足とは別の問題です。`Missing script`だけでなく、[エラー](/glossary/エラー/)全体を読んで確認箇所を分けます。

## 解決手順のまとめ

最初に`npm run`で一覧を見て、指定名と用途を確認します。次に実行場所を確認し、workspaceを使う場合は対象を指定してください。

定義を追加する必要がある場合だけ、実際の起動方法に合わせて`scripts`を編集します。`--if-present`は任意の[処理](/glossary/処理/)に使い、必須の起動を省略して成功扱いにするためには使いません。

この記事の実行確認は[Linux](/glossary/linux/)上のnpm 11.9.0で行いました。未定義[スクリプト](/glossary/スクリプト/)、一覧表示、打ち間違い、server.jsの既定起動、package.json不在、workspace指定、if-presentの成功と失敗を、追加[パッケージ](/glossary/パッケージ/)の導入なしで確認しています。npm 12系およびWindows上での実行は未検証です。先頭の接頭辞や候補の表示がすべての版で同じとは扱っていません。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
