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

`ERR_REQUIRE_ESM`は、`require()`でESモジュールを読み込もうとして、その実行環境が読み込みを拒否したときに出ます。ESモジュール(ESM)は、主に`import`と`export`で読み書きする形式です。CommonJS(CJS)は、`require()`と`module.exports`を使う形式です。

最初にエラーに出た読み込み先と読み込み元、実際に使われたNode.jsの版を確認します。自分のCommonJSコードなら、非同期の`import()`に書き換える方法があります。依存パッケージ内部で起きているなら、呼び出しているパッケージの対応版も調べてください。

新しいNode.jsは同期的なESMを`require()`で読み込めます。ただし、更新だけで元の使い方が必ず通るわけではありません。戻り値の取り出し方と、依存先を含めたトップレベルの`await`の有無も確認します。

## エラーのパスと実行環境を確認する

次は表示例です。パスは説明用で、文言や補足はNode.jsの版によって変わります。

```text
Error [ERR_REQUIRE_ESM]: require() of ES Module /project/lib.mjs from /project/main.cjs not supported.
```

`lib.mjs`が読み込もうとしたファイル、`from`の後ろにある`main.cjs`が読み込み元です。両方のパスを確認すると、自分のコードと依存パッケージ内部のどちらを直す必要があるかを判断できます。

[Node.js v22.12.0のエラー生成実装](https://github.com/nodejs/node/blob/v22.12.0/lib/internal/errors.js)には、`.mjs`の場合、ESM構文を含む場合、近くの`package.json`の`"type": "module"`によってESMとして扱う場合に応じた補足があります。ただし、補足の種類だけで対処を固定せず、実際のコードと設定も確認します。

失敗した処理と同じターミナルやCIジョブで、次を実行してください。

```bash
node -v
node -p "process.execPath"
node -p "JSON.stringify({execArgv: process.execArgv, NODE_OPTIONS: process.env.NODE_OPTIONS})"
```

最後のコマンドは、その確認用プロセスの起動引数と`NODE_OPTIONS`を表示します。npmスクリプトやツールが別途渡す引数は、その実行設定も確認してください。Node.jsを更新したつもりでも、IDE、CI、コンテナでは別の実行ファイルを使っている場合があります。

## Node.jsの版による違いを切り分ける

[公式の変更履歴](https://nodejs.org/api/modules.html#loading-ecmascript-modules-using-require)では、同期ESMの`require()`対応はNode.js 20.17.0と22.0.0に追加されました。当初は`--experimental-require-module`で有効にする機能でした。

| 系列・版 | 同期ESMをrequire()する機能 |
|---|---|
| Node.js 18系 | この機能に未対応 |
| 20.17.0〜20.18.x | 実験的フラグで有効化 |
| 20.19.0以降の20系 | 既定で有効 |
| 22.0.0〜22.11.x | 実験的フラグで有効化 |
| 22.12.0以降の22系 | 既定で有効 |
| 23.0.0以降の系列 | 既定で有効。無効化設定にも注意 |

これは機能が導入された境界の表です。古い系列への更新を推奨する表ではありません。更新先は、[Node.js公式のサポート状況](https://nodejs.org/en/about/previous-releases)とプロジェクトの要件を確認して、サポート中のLTS(長期サポート版)から選びます。2026年10月8日の確認では22系と24系がLTS、20系はサポート終了です。

機能を無効化している場合、新しい版でも`ERR_REQUIRE_ESM`が出ることがあります。起動設定や`NODE_OPTIONS`の`--no-experimental-require-module`などを確認します。フラグの名称や利用可否は、使用中の版の文書に合わせてください。

[公式エラー文書](https://nodejs.org/api/errors.html#err_require_esm)がこのエラーを非推奨としている理由は、同期ESMを`require()`で読み込めるようになったためです。非推奨という表示は、発生頻度や件数の根拠ではありません。

## CommonJSを残してimport()に書き換える

CommonJSのままESMを読み込むには、`import()`を使えます。[ESMの公式文書](https://nodejs.org/download/release/v22.12.0/docs/api/esm.html#interoperability-with-commonjs)も、CommonJS内からESMを読み込む方法として説明しています。

次は外部パッケージを使わない例です。2つのファイルを同じディレクトリへ保存します。

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

`import()`はPromiseを返すため、読み込み完了を待ってから使います。CommonJSのファイル直下にそのまま`await import(...)`を書かず、この例のように`async`関数内へ入れます。呼び出し側も、結果が非同期で返ることに合わせる必要があります。

この例の`default: greet`は、`export default`で公開された関数を取り出す指定です。名前付きの`export const label`は`label`で取り出します。実際のパッケージでは、READMEにある公開方法に合わせてください。

上の最小例はNode.js 24.19.0で実行し、`Hello, example`を表示して終了コード0になることを確認しました。外部パッケージや各ビルドツールでの動作を確認した結果ではありません。

## 更新後も戻り値とawaitを確認する

同期ESMの`require()`に対応したNode.jsなら、前節の`lib.mjs`は次のようにも読み込めます。

```javascript
// require.cjs
const { default: greet, label } = require('./lib.mjs');
console.log(greet(label));
```

[公式文書](https://nodejs.org/download/release/v22.12.0/docs/api/modules.html#loading-ecmascript-modules-using-require)が説明する通常の戻り値は、公開された値をまとめたオブジェクトです。`export default`の値は`.default`から取り出します。パッケージが特別な互換用の公開方法を使っている場合は戻り値が変わるので、そのパッケージの説明を確認します。

そのため、以前の`const greet = require(...)`を残すと、読み込みは成功しても`greet`を関数として呼べない場合があります。エラーが消えた後も、使っている値が意図した関数やオブジェクトかを確認してください。上の`require.cjs`もNode.js 24.19.0で実行成功を確認しました。

一方、読み込むESM自身、またはそこから読み込まれる依存先にトップレベルの`await`があると、`ERR_REQUIRE_ASYNC_MODULE`になります。トップレベルの`await`は、関数の外で実行する`await`です。単に`async`関数が定義されているだけでは、この条件には当たりません。

非同期ESMは`import()`で読み込みます。ESMの再公開だけを行うラッパーを追加しても、古いNode.jsの`require()`制限や非同期読み込みの必要性はなくなりません。

## パッケージやビルドツール内部で起きる場合

パッケージ更新後に発生したなら、更新履歴と導入された版を確認します。[Chalkの公式README](https://github.com/chalk/chalk#install)は、Chalk 5がESMであることを明記しています。CommonJSから直接読み込んでいたコードでは、利用方法の変更が必要になる例です。

エラーにChalkが出ている場合は、次で依存関係を調べられます。

```bash
npm ls chalk
npm explain chalk
```

別のパッケージで起きている場合は名前を置き換えます。依存パッケージが内部で`require()`しているなら、自分のソースにある`require()`だけを変えても、その呼び出しは残ります。呼び出しているパッケージの対応版や、ツールの公式案内を確認します。

実例として、[webpackのIssue #15930](https://github.com/webpack/webpack/issues/15930)には、Node.js 16・Windows 10・webpack 5.73.0で、ESMとして書いたloaderを`loader-runner`が読み込む際に`ERR_REQUIRE_ESM`となった報告があります。エラーの読み込み元は利用者のエントリーファイルではなく、ツール内部でした。この過去の報告だけで現在のwebpackも同じ制限を持つとは判断できません。

CommonJSに対応する旧版を一時的に使う方法もありますが、対象パッケージの対応表、修正状況、ほかの依存との組み合わせを確認して選びます。`node_modules`の直接編集は、再インストールで失われるため通常の対応にはしません。

プロジェクト全体をESMへ移す場合は、`"type": "module"`を追加するだけで完了とは考えないでください。既存の`require()`、`module.exports`、ファイル参照やツール設定も影響を受けます。自作ファイルが本来CommonJSのコードなら`.cjs`で明示する方法がありますが、`import`・`export`を含むESMの拡張子だけを変えてもCommonJSには変換されません。

## 補足：似ているが別のエラー

| 表示 | 確認すること |
|---|---|
| `ERR_REQUIRE_ESM` | ESMのrequire()が拒否された。Node.jsの版、設定、読み込み元と先を確認 |
| `ERR_REQUIRE_ASYNC_MODULE` | 自身や依存先にトップレベルのawaitがある。import()で非同期に読み込む |
| `require is not defined` | ESMとして実行するコード内でrequireを使っていないか確認 |
| `Cannot use import statement outside a module` | import文を書いたファイルがESMとして扱われているか確認 |
| `ERR_REQUIRE_CYCLE_MODULE` | CommonJSとESMの読み込みが即時の循環になっていないか確認 |

`ERR_REQUIRE_ASYNC_MODULE`は、すべての`ERR_REQUIRE_ESM`を置き換えた名称ではありません。非同期ESMを同期の`require()`で読み込めない場合の別のエラーです。また、`ERR_REQUIRE_CYCLE_MODULE`も、あらゆる循環依存で出るものではありません。[公式のエラー一覧](https://nodejs.org/api/errors.html#err_require_cycle_module)で対象条件を確認します。

[npmのEBADENGINE](/posts/npm_ebadengine/)は、パッケージが要求するNode.jsやnpmの版と現在の環境が合わない警告・エラーです。今回のERR_REQUIRE_ESMは、モジュールを読み込む段階の拒否を扱います。

## 解決手順のまとめ

まず、エラーの読み込み元と先を特定し、失敗した環境のNode.jsの版と起動設定を確認します。自分のCommonJSコードであれば、`async`関数内の`import()`に変更し、公開された値を正しく取り出します。

Node.jsを更新する場合は、プロジェクトが対応するサポート中の版を選びます。更新後は、戻り値とトップレベルの`await`の条件を確認してください。依存パッケージ内部で起きているなら、呼び出しているパッケージやツールの対応を調べ、元の処理とテストを再実行します。

免責事項：本記事の内容は一般的なNode.jsの構成を前提としています。モジュールの読み込み方法や戻り値は、Node.js、依存パッケージ、ビルドツールの版と設定によって異なります。環境や依存関係を変更する前に、プロジェクトの要件を確認してください。
