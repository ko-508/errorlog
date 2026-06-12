---
title: "jqでJSONログが途中で途切れる？リアルタイムログストリーム処理の課題と解決策"
date: 2026-06-10
lastmod: 2026-06-10
draft: false
description: "開発サーバーのログをjqで処理しようとして、非JSON行でパイプが途切れて困った経験はありませんか？本記事では、リアルタイムログストリームにおけるjqの課題と、その解決策としてlogtidyを紹介します。"
tags: ["Dev.to - DevOps"]
trend_incident: true
---

## エラーの概要

このエラーは、`jq`コマンドが標準入力から受け取ったデータの中に、有効なJSON形式ではない行が含まれていた場合に発生します。`jq`はストリーム全体がJSON形式であることを前提としているため、非JSON行に遭遇すると処理を中断し、エラーメッセージを出力します。開発サーバーの出力など、JSONログとプレーンテキストが混在するリアルタイムログストリームを処理しようとした際によく見られます。

## 実際のエラーメッセージ例

開発サーバーの出力を`jq`にパイプした場合に発生する典型的なエラーメッセージは以下の通りです。

```
npm run dev | jq
{
  "level": 30,
  "msg": "server started",
  ...
}
jq: error (at <stdin>:0): Cannot index string with "level"
```

この例では、最初の数行はJSONとして処理されたものの、その後に非JSON行（例えば、アプリケーションの起動バナーや`console.log`出力、スタックトレースなど）が出現したため、`jq`がエラーを吐いて処理を停止しています。

## よくある原因と解決手順

### 原因1：JSONと非JSONが混在するログストリームを処理している

リアルタイムのログ出力は、純粋なJSON形式であることは稀です。構造化されたJSONログ（Pino, Winston, Zapなど）と、フレームワークの出力、デバッグ用の`print()`文、スタックトレースなどのプレーンテキストが混在していることがほとんどです。`jq`はこのような混在ストリームを想定していないため、非JSON行で処理が中断されます。

**Before（エラーが起きるコード）：**

```bash
# 開発サーバーの出力を直接jqにパイプ
npm run dev | jq
```

**After（修正後）：**

```bash
# JSONと非JSONが混在するログストリームに対応するツール（logtidy）を使用する
npm run dev 2>&1 | npx logtidy
```

`logtidy`のようなツールは、JSON形式の行は整形して出力し、非JSON形式の行はそのまま通過させることで、パイプが途切れることなくログストリーム全体を処理できます。

### 原因2：ログ出力に意図しないプレーンテキストが含まれている

アプリケーションコード内で、JSONロガーとは別に`console.log()`や`print()`などの標準出力への書き込みを行っている場合、それらの出力はJSON形式ではないため、`jq`がエラーの原因となります。特に、開発中のデバッグ目的で一時的に挿入された出力が原因となることがあります。

**Before（エラーが起きるコード）：**

```javascript
// app.js
const logger = require('pino')();
logger.info('Server starting...');
console.log('--- Application Banner ---'); // 非JSON出力
logger.info({ port: 3000 }, 'Server started');
```

```bash
# 上記のログをjqで処理しようとすると、"--- Application Banner ---" でエラーになる
node app.js | jq
```

**After（修正後）：**

```javascript
// app.js
const logger = require('pino')();
logger.info('Server starting...');
// console.log()ではなく、ロガーを使って構造化ログとして出力するか、
// ログストリーム処理ツールで対応する
logger.info({ banner: 'Application Banner' }, 'Application Banner');
logger.info({ port: 3000 }, 'Server started');
```

```bash
# ロガーで統一するか、logtidyのようなツールで処理する
node app.js | npx logtidy
```

理想的には、すべてのログ出力を構造化ロガーに統一することが望ましいですが、現実的には難しい場合も多いため、`logtidy`のようなツールが有効な解決策となります。

### 原因3：スタックトレースやエラーメッセージがJSON形式ではない

エラー発生時に出力されるスタックトレースや詳細なエラーメッセージは、通常、複数行にわたるプレーンテキスト形式です。これらがJSONログの間に挿入されると、`jq`はこれを有効なJSONとして解析できず、処理を中断します。

**Before（エラーが起きるコード）：**

```javascript
// app.js
const logger = require('pino')();
logger.info('Processing request...');
try {
  throw new Error('Something went wrong!');
} catch (e) {
  logger.error(e, 'Request failed'); // JSONログ
  console.error(e.stack); // 非JSONのスタックトレース
}
```

```bash
# 上記のログをjqで処理しようとすると、console.error(e.stack) でエラーになる
node app.js | jq
```

**After（修正後）：**

```javascript
// app.js
const logger = require('pino')();
logger.info('Processing request...');
try {
  throw new Error('Something went wrong!');
} catch (e) {
  // スタックトレースもJSONログの一部として含める
  logger.error({ err: e.stack }, 'Request failed');
}
```

```bash
# ロガーで統一するか、logtidyのようなツールで処理する
node app.js | npx logtidy
```

`logtidy`を使用すれば、スタックトレースのような非JSON行もそのまま通過させるため、エラー発生時の重要なコンテキストを失うことなくログ全体を確認できます。

## ツール固有の注意点

`jq`は強力なJSON処理ツールですが、その設計思想は「入力全体が有効なJSONであること」を前提としています。そのため、リアルタイムのログストリームのように、JSONと非JSONが混在する環境ではその特性がボトルネックとなります。

一方、`logtidy`は、このようなリアルタイムログストリームの課題を解決するために設計されています。

*   **JSON行の自動整形**: `logtidy`は、`time`/`ts`/`timestamp`、`level`/`lvl`/`severity`、`msg`/`message`などの一般的なロガーのフィールド名を自動的に認識し、人間が読みやすい形式に整形します。ネストされたJSONオブジェクトも`req.method=GET`のようにフラット化して表示します。
*   **非JSON行のパススルー**: JSON形式ではない行は、一切変更せずにそのまま出力します。これにより、起動バナー、スタックトレース、デバッグ出力など、重要なコンテキストを失うことなくログ全体を把握できます。
*   **フィルタリング機能**: `--level`フラグで指定したレベル以上のログのみを表示したり、`--fields`フラグで特定のフィールドのみに絞って表示したりできます。非JSON行はレベルに関わらず常に表示されるため、スタックトレースを見逃す心配がありません。
*   **ゼロ依存**: Node.js版は`npx logtidy`、Python版は`pipx run logtidy`で実行でき、どちらもゼロ依存で動作します。既存の環境に余計なライブラリをインストールする必要がありません。

## それでも解決しない場合

`logtidy`を使用しても期待通りの出力が得られない場合や、特定の問題が発生する場合は、以下の点を確認してください。

*   **`logtidy`のバージョン**: 最新バージョンを使用しているか確認してください。`npx logtidy --version`または`pipx run logtidy --version`で確認できます。
*   **ログの出力形式**: `logtidy`が認識する一般的なフィールド名（`time`, `level`, `msg`など）がログに含まれているか確認してください。カスタムフィールド名を使用している場合は、`logtidy`がそれを認識できない可能性があります。
*   **公式ドキュメントの参照**: `logtidy`のGitHubリポジトリ（`<logtidyのGitHubリポジトリURL>`）には、詳細なREADMEやissueトラッカーがあります。既知の問題や、サポートされているロガー形式について確認できます。
*   **問題の再現**: 特定のログ行で`logtidy`が正しく動作しない場合は、その行を切り出して`echo '<問題のログ行>' | npx logtidy`のように単独で実行し、挙動を確認してください。
*   **デバッグ出力**: `logtidy`自体にデバッグオプションがある場合は、それを利用して内部処理を確認します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*