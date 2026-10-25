---
title: "ERR_REQUIRE_ESMの対処法"
date: 2026-10-08T09:00:00+09:00
draft: false
description: "ERR_REQUIRE_ESMは、ESモジュールをrequire()で読み込めないときのエラーです。Node.jsの版、読み込み元と対象ファイルを確認し、dynamic import()、実行環境の更新、依存パッケージの対応を切り分けます。"
tags: ["Node.js", "JavaScript"]
images: ["og/posts/node_err_require_esm.png"]
errorCode: "ERR_REQUIRE_ESM"
urgency: "medium"
service: "Node.js"
error_type: "ERR_REQUIRE_ESM"
components: ["Node.js", "CommonJS", "ESM", "package.json"]
related_services: []
trend_incident: false
publish_slug: "node_err_require_esm"
publish_note: "新規作成。Node.js公式文書・実装、Chalk公式README、webpackの実例を照合。ローカル最小例を実行確認"
publish_zenn: true
---

## 冒頭まとめ

`ERR_REQUIRE_ESM`は、`require()`でES[モジュール](/glossary/モジュール/)を読み込もうとして、その実行環境が読み込みを拒否したときに出ます。ES[モジュール](/glossary/モジュール/)(ESM)は、主に`import`と`export`で読み書きする形式です。CommonJS(CJS)は、`require()`と`module.exports`を使う形式です。

最初に[エラー](/glossary/エラー/)に出た読み込み先と読み込み元、実際に使われたNode.jsの版を確認します。自分のCommonJS[コード](/glossary/コード/)なら、[非同期](/glossary/非同期/)の`import()`に書き換える方法があります。依存[パッケージ](/glossary/パッケージ/)内部で起きているなら、呼び出している[パッケージ](/glossary/パッケージ/)の[対応版](/glossary/対応版/)も調べてください。

新しいNode.jsは同期的なESMを`require()`で読み込めます。ただし、[更新](/glossary/更新/)だけで元の使い方が必ず通るわけではありません。[戻り値](/glossary/戻り値/)の取り出し方と、依存先を含めたトップレベルの`await`の有無も確認します。

## エラーのパスと実行環境を確認する

次は表示例です。[パス](/glossary/パス/)は説明用で、文言や補足はNode.jsの版によって変わります。

```text
Error [ERR_REQUIRE_ESM]: require() of ES Module /project/lib.mjs from /project/main.cjs not supported.
```

`lib.mjs`が読み込もうとした[ファイル](/glossary/ファイル/)、`from`の後ろにある`main.cjs`が読み込み元です。両方の[パス](/glossary/パス/)を確認すると、自分の[コード](/glossary/コード/)と依存[パッケージ](/glossary/パッケージ/)内部のどちらを直す必要があるかを判断できます。

[Node.js v22.12.0のエラー生成実装](https://github.com/nodejs/node/blob/v22.12.0/lib/internal/errors.js)には、`.mjs`の場合、ESM構文を含む場合、近くの`package.json`の`"type": "module"`によってESMとして扱う場合に応じた補足があります。ただし、補足の種類だけで対処を固定せず、実際の[コード](/glossary/コード/)と[設定](/glossary/設定/)も確認します。

失敗した[処理](/glossary/処理/)と同じ[ターミナル](/glossary/ターミナル/)やCIジョブで、次を実行してください。

```bash
node -v
node -p "process.execPath"
node -p "JSON.stringify({execArgv: process.execArgv, NODE_OPTIONS: process.env.NODE_OPTIONS})"
```

最後の[コマンド](/glossary/コマンド/)は、その確認用[プロセス](/glossary/プロセス/)の起動引数と`NODE_OPTIONS`を表示します。npm[スクリプト](/glossary/スクリプト/)や[ツール](/glossary/ツール/)が別途渡す[引数](/glossary/引数/)は、その実行設定も確認してください。Node.jsを[更新](/glossary/更新/)したつもりでも、[IDE](/glossary/ide/)、CI、[コンテナ](/glossary/コンテナ/)では別の実行[ファイル](/glossary/ファイル/)を使っている場合があります。

## Node.jsの版による違いを切り分ける

[公式の変更履歴](https://nodejs.org/api/modules.html#loading-ecmascript-modules-using-require)では、[同期](/glossary/同期/)ESMの`require()`[対応](/glossary/対応/)はNode.js 20.17.0と22.0.0に追加されました。当初は`--experimental-require-module`で有効にする機能でした。

| 系列・版 | [同期](/glossary/同期/)ESMをrequire()する機能 |
|---|---|
| Node.js 18系 | この機能に未対応 |
| 20.17.0〜20.18.x | 実験的フラグで有効化 |
| 20.19.0以降の20系 | 既定で有効 |
| 22.0.0〜22.11.x | 実験的フラグで有効化 |
| 22.12.0以降の22系 | 既定で有効 |
| 23.0.0以降の系列 | 既定で有効。無効化設定にも注意 |

これは機能が導入された境界の表です。古い系列への[更新](/glossary/更新/)を推奨する表ではありません。更新先は、[Node.js公式のサポート状況](https://nodejs.org/en/about/previous-releases)と[プロジェクト](/glossary/プロジェクト/)の[要件](/glossary/要件/)を確認して、サポート中のLTS(長期サポート版)から選びます。2026年10月8日の確認では22系と24系がLTS、20系は[サポート終了](/glossary/サポート終了/)です。

機能を無効化している場合、新しい版でも`ERR_REQUIRE_ESM`が出ることがあります。起動設定や`NODE_OPTIONS`の`--no-experimental-require-module`などを確認します。フラグの名称や利用可否は、使用中の版の文書に合わせてください。

[公式エラー文書](https://nodejs.org/api/errors.html#err_require_esm)がこの[エラー](/glossary/エラー/)を非推奨としている理由は、[同期](/glossary/同期/)ESMを`require()`で読み込めるようになったためです。非推奨という表示は、発生頻度や件数の根拠ではありません。

## CommonJSを残してimport()に書き換える

CommonJSのままESMを読み込むには、`import()`を使えます。[ESMの公式文書](https://nodejs.org/download/release/v22.12.0/docs/api/esm.html#interoperability-with-commonjs)も、CommonJS内からESMを読み込む方法として説明しています。

次は外部[パッケージ](/glossary/パッケージ/)を使わない例です。2つの[ファイル](/glossary/ファイル/)を同じ[ディレクトリ](/glossary/ディレクトリ/)へ[保存](/glossary/保存/)します。

```javascript
// lib.mjs
export default function greet(name) {
  return `Hello, ${name}`;
}
export const label = 'example';
```

```javascript
// main.cjs
async function main() {
  const { default: greet, label } = await import('./lib.mjs');
  console.log(greet(label));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
```

```bash
node main.cjs
```

`import()`はPromiseを返すため、読み込み完了を待ってから使います。CommonJSの[ファイル](/glossary/ファイル/)直下にそのまま`await import(...)`を書かず、この例のように`async`関数内へ入れます。呼び出し側も、結果が[非同期](/glossary/非同期/)で返ることに合わせる必要があります。

この例の`default: greet`は、`export default`で公開された[関数](/glossary/関数/)を取り出す指定です。名前付きの`export const label`は`label`で取り出します。実際の[パッケージ](/glossary/パッケージ/)では、READMEにある公開方法に合わせてください。

上の最小例はNode.js 24.19.0で実行し、`Hello, example`を表示して終了[コード](/glossary/コード/)0になることを確認しました。外部[パッケージ](/glossary/パッケージ/)や各ビルドツールでの動作を確認した結果ではありません。

## 更新後も戻り値とawaitを確認する

[同期](/glossary/同期/)ESMの`require()`に[対応](/glossary/対応/)したNode.jsなら、前節の`lib.mjs`は次のようにも読み込めます。

```javascript
// require.cjs
const { default: greet, label } = require('./lib.mjs');
console.log(greet(label));
```

[公式文書](https://nodejs.org/download/release/v22.12.0/docs/api/modules.html#loading-ecmascript-modules-using-require)が説明する通常の[戻り値](/glossary/戻り値/)は、公開された値をまとめた[オブジェクト](/glossary/オブジェクト/)です。`export default`の値は`.default`から取り出します。[パッケージ](/glossary/パッケージ/)が特別な互換用の公開方法を使っている場合は[戻り値](/glossary/戻り値/)が変わるので、その[パッケージ](/glossary/パッケージ/)の説明を確認します。

そのため、以前の`const greet = require(...)`を残すと、読み込みは成功しても`greet`を[関数](/glossary/関数/)として呼べない場合があります。[エラー](/glossary/エラー/)が消えた後も、使っている値が意図した[関数](/glossary/関数/)や[オブジェクト](/glossary/オブジェクト/)かを確認してください。上の`require.cjs`もNode.js 24.19.0で実行成功を確認しました。

一方、読み込むESM自身、またはそこから読み込まれる依存先にトップレベルの`await`があると、`ERR_REQUIRE_ASYNC_MODULE`になります。トップレベルの`await`は、[関数](/glossary/関数/)の外で実行する`await`です。単に`async`[関数](/glossary/関数/)が定義されているだけでは、この条件には当たりません。

[非同期](/glossary/非同期/)ESMは`import()`で読み込みます。ESMの再公開だけを行うラッパーを追加しても、古いNode.jsの`require()`制限や非同期読み込みの必要性はなくなりません。

## パッケージやビルドツール内部で起きる場合

[パッケージ](/glossary/パッケージ/)更新後に発生したなら、更新履歴と導入された版を確認します。[Chalkの公式README](https://github.com/chalk/chalk#install)は、Chalk 5がESMであることを明記しています。CommonJSから直接読み込んでいた[コード](/glossary/コード/)では、利用方法の変更が必要になる例です。

[エラー](/glossary/エラー/)にChalkが出ている場合は、次で依存関係を調べられます。

```bash
npm ls chalk
npm explain chalk
```

別の[パッケージ](/glossary/パッケージ/)で起きている場合は名前を置き換えます。依存[パッケージ](/glossary/パッケージ/)が内部で`require()`しているなら、自分のソースにある`require()`だけを変えても、その呼び出しは残ります。呼び出している[パッケージ](/glossary/パッケージ/)の[対応版](/glossary/対応版/)や、[ツール](/glossary/ツール/)の公式案内を確認します。

実例として、[webpackのIssue #15930](https://github.com/webpack/webpack/issues/15930)には、Node.js 16・Windows 10・webpack 5.73.0で、ESMとして書いたloaderを`loader-runner`が読み込む際に`ERR_REQUIRE_ESM`となった報告があります。[エラー](/glossary/エラー/)の読み込み元は利用者のエントリーファイルではなく、[ツール](/glossary/ツール/)内部でした。この過去の報告だけで現在のwebpackも同じ制限を持つとは判断できません。

CommonJSに[対応](/glossary/対応/)する旧版を一時的に使う方法もありますが、対象[パッケージ](/glossary/パッケージ/)の対応表、修正状況、ほかの依存との組み合わせを確認して選びます。`node_modules`の直接編集は、再[インストール](/glossary/インストール/)で失われるため通常の[対応](/glossary/対応/)にはしません。

[プロジェクト](/glossary/プロジェクト/)全体をESMへ移す場合は、`"type": "module"`を追加するだけで完了とは考えないでください。既存の`require()`、`module.exports`、[ファイル](/glossary/ファイル/)参照や[ツール](/glossary/ツール/)[設定](/glossary/設定/)も影響を受けます。自作[ファイル](/glossary/ファイル/)が本来CommonJSの[コード](/glossary/コード/)なら`.cjs`で明示する方法がありますが、`import`・`export`を含むESMの[拡張子](/glossary/拡張子/)だけを変えてもCommonJSには変換されません。

## 補足：似ているが別のエラー

| 表示 | 確認すること |
|---|---|
| `ERR_REQUIRE_ESM` | ESMのrequire()が拒否された。Node.jsの版、[設定](/glossary/設定/)、読み込み元と先を確認 |
| `ERR_REQUIRE_ASYNC_MODULE` | 自身や依存先にトップレベルのawaitがある。import()で[非同期](/glossary/非同期/)に読み込む |
| `require is not defined` | ESMとして実行する[コード](/glossary/コード/)内でrequireを使っていないか確認 |
| `Cannot use import statement outside a module` | import文を書いた[ファイル](/glossary/ファイル/)がESMとして扱われているか確認 |
| `ERR_REQUIRE_CYCLE_MODULE` | CommonJSとESMの読み込みが即時の循環になっていないか確認 |

`ERR_REQUIRE_ASYNC_MODULE`は、すべての`ERR_REQUIRE_ESM`を置き換えた名称ではありません。[非同期](/glossary/非同期/)ESMを[同期](/glossary/同期/)の`require()`で読み込めない場合の別の[エラー](/glossary/エラー/)です。また、`ERR_REQUIRE_CYCLE_MODULE`も、あらゆる循環依存で出るものではありません。[公式のエラー一覧](https://nodejs.org/api/errors.html#err_require_cycle_module)で対象条件を確認します。

[npmのEBADENGINE](/posts/npm_ebadengine/)は、[パッケージ](/glossary/パッケージ/)が要求するNode.jsやnpmの版と現在の[環境](/glossary/環境/)が合わない警告・[エラー](/glossary/エラー/)です。今回のERR_REQUIRE_ESMは、[モジュール](/glossary/モジュール/)を読み込む段階の拒否を扱います。

## 解決手順のまとめ

まず、[エラー](/glossary/エラー/)の読み込み元と先を特定し、失敗した[環境](/glossary/環境/)のNode.jsの版と起動設定を確認します。自分のCommonJS[コード](/glossary/コード/)であれば、`async`関数内の`import()`に変更し、公開された値を正しく取り出します。

Node.jsを[更新](/glossary/更新/)する場合は、[プロジェクト](/glossary/プロジェクト/)が[対応](/glossary/対応/)するサポート中の版を選びます。更新後は、[戻り値](/glossary/戻り値/)とトップレベルの`await`の条件を確認してください。依存[パッケージ](/glossary/パッケージ/)内部で起きているなら、呼び出している[パッケージ](/glossary/パッケージ/)や[ツール](/glossary/ツール/)の[対応](/glossary/対応/)を調べ、元の[処理](/glossary/処理/)と[テスト](/glossary/テスト/)を再実行します。

免責事項：本記事の内容は一般的なNode.jsの構成を前提としています。[モジュール](/glossary/モジュール/)の読み込み方法や[戻り値](/glossary/戻り値/)は、Node.js、依存[パッケージ](/glossary/パッケージ/)、ビルドツールの版と[設定](/glossary/設定/)によって異なります。[環境](/glossary/環境/)や依存関係を変更する前に、[プロジェクト](/glossary/プロジェクト/)の[要件](/glossary/要件/)を確認してください。
