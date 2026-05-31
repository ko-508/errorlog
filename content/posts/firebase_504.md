---
title: "Firebase の 504 エラー：原因と解決策"
date: 2026-05-28
description: "Firebase HostingまたはCloud Functionsがバックエンドからの応…。Cloud Functionsの処理時間がHostingの統など、Firebase 504 エラーの原因と解決策を解説。"
tags: ["Firebase"]
errorCode: "504"
---

Firebase HostingまたはCloud Functionsの[バックエンド](/glossary/バックエンド/)処理が[タイムアウト](/glossary/タイムアウト/)し、クライアントに504エラーが返される状況です。この記事では原因の特定と具体的な解決方法を解説します。

## よくある原因

**Cloud Functionsの処理時間がFirebase Hostingの[タイムアウト](/glossary/タイムアウト/)を超えている**

Firebase HostingからCloud Functionsを呼び出す場合、Hostingの統合[タイムアウト](/glossary/タイムアウト/)制限（通常60秒）内に関数が応答を返す必要があります。データベースクエリが遅い、外部[API](/glossary/api/)の呼び出しが遅延している、複雑な計算処理が走っているなど、処理時間が長くなると504エラーが発生します。

**[コールドスタート](/glossary/コールドスタート/)時の初期化処理に時間がかかっている**

Cloud Functionsは関数が実行されていない状態から起動する際（[コールドスタート](/glossary/コールドスタート/)）、メモリ確保、ライブラリの読み込み、[データベース](/glossary/データベース/)接続の初期化などの処理が発生します。この初期化処理が[タイムアウト](/glossary/タイムアウト/)制限内に完了しないと504エラーになります。特にNode.jsで大量の依存ライブラリをインポートしている場合に顕著です。

**外部サービスへの依存処理の遅延**

Cloud Functionsから外部[API](/glossary/api/)やサードパーティサービスを呼び出す場合、そのサービスの応答時間がFirebaseの[タイムアウト](/glossary/タイムアウト/)制限を超えると504エラーになります。[ネットワーク](/glossary/ネットワーク/)状況が悪い、外部サービスが過負荷状態である、タイムゾーン違いで[レスポンス](/glossary/レスポンス/)が遅くなるなどの原因が考えられます。

## 解決手順

**手順1: Cloud Functionsの[タイムアウト](/glossary/タイムアウト/)設定を確認・延長する**

Firebase Console（console.firebase.google.com）にアクセスし、プロジェクトを選択します。左メニューから「ビルド」→「Cloud Functions」を開き、該当の関数をクリックします。「トリガー」タブで[タイムアウト](/glossary/タイムアウト/)値を確認し、必要に応じて変更します。

```bash
# コマンドラインでデプロイする場合、firebase.json で設定する
gcloud functions deploy <関数名> \
  --runtime nodejs18 \
  --timeout=540s \
  --memory=512MB \
  --region=asia-northeast1
```

[タイムアウト](/glossary/タイムアウト/)値は最大540秒（9分）まで延長できます。ただし処理が本当に長い場合は、後述の最適化を優先してください。

**手順2: 初期化処理をグローバルスコープに移動し[コールドスタート](/glossary/コールドスタート/)を高速化する**

Cloud Functionsでは、関数のハンドラ外（グローバルスコープ）に記述した処理は[コールドスタート](/glossary/コールドスタート/)時に1回だけ実行され、以後の[リクエスト](/glossary/リクエスト/)で再実行されません。[データベース](/glossary/データベース/)接続、ライブラリの初期化、認証情報の読み込みなどをグローバルスコープに移動します。

```javascript
// 悪い例：毎回実行される
exports.myFunction = functions.https.onRequest((req, res) => {
  const db = admin.database(); // 毎回初期化される
  const query = db.ref('users').orderByChild('age').limitToFirst(100);
  query.once('value').then(snapshot => {
    res.send(snapshot.val());
  });
});

// 良い例：初期化は1回だけ
const admin = require('firebase-admin');
admin.initializeApp();
const db = admin.database(); // グローバルスコープで1回だけ実行

exports.myFunction = functions.https.onRequest((req, res) => {
  const query = db.ref('users').orderByChild('age').limitToFirst(100);
  query.once('value').then(snapshot => {
    res.send(snapshot.val());
  });
});
```

**手順3: 数分後に再試行する**

[コールドスタート](/glossary/コールドスタート/)による一時的な504エラーの場合、クライアント側で数秒～数分待機後に自動再試行する仕組みを実装します。Firebaseクライアントライブラリは自動[リトライ](/glossary/リトライ/)を行いますが、明示的に指定することもできます。

```javascript
// JavaScript/TypeScript クライアント側での再試行例
async function callFunctionWithRetry(functionName, data, maxRetries = 3) {
  const functions = firebase.functions('asia-northeast1');
  const callable = functions.httpsCallable(functionName);
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const result = await callable(data);
      return result.data;
    } catch (error) {
      if (error.code === 'unavailable' || error.code === 'deadline-exceeded') {
        if (attempt < maxRetries - 1) {
          const delay = Math.pow(2, attempt) * 1000; // 指数バックオフ
          await new Promise(resolve => setTimeout(resolve, delay));
          continue;
        }
      }
      throw error;
    }
  }
}
```

**手順4: 関数のメモリ割り当てを増やす**

メモリ割り当てを増やすと、CPUリソースも同時に増加し、処理速度が上がります。Firebase Consoleで関数をクリックし、「ランタイム設定」からメモリを変更します（256MB～8GBで選択可能）。

```bash
# コマンドラインでメモリ設定（例：1GB）
gcloud functions deploy <関数名> \
  --memory=1GB \
  --timeout=300s
```

**手順5: 処理を分割し、非同期タスクキューを使う**

[データベース](/glossary/データベース/)の大量書き込みなど時間がかかる処理は、Cloud Tasks（非同期タスクキュー）に委譲します。クライアントには素早く応答を返し、バックグラウンドで処理を続けます。

```javascript
// Cloud Tasks へのエンキュー例
const tasks = require('@google-cloud/tasks');
const tasksClient = new tasks.CloudTasksClient();

exports.enqueueTask = functions.https.onRequest(async (req, res) => {
  const project = '<your-project-id>';
  const queue = 'my-queue';
  const location = 'asia-northeast1';
  const parent = tasksClient.queuePath(project, location, queue);
  
  const task = {
    httpRequest: {
      httpMethod: 'POST',
      url: 'https://<region>-<your-project-id>.cloudfunctions.net/slowProcess',
      headers: { 'Content-Type': 'application/json' },
      body: Buffer.from(JSON.stringify(req.body)).toString('base64'),
    },
  };
  
  await tasksClient.createTask({ parent, task });
  res.json({ message: 'タスクをキューに追加しました' });
});
```

## それでも解決しない場合

Firebase Consoleの「[ログ](/glossary/ログ/)」タブでCloud Functionsの詳細なエラーログを確認してください。特に関数実行時間の推移、メモリ使用量、エラーメッセージを調査します。外部[API](/glossary/api/)の遅延が原因の場合は、その[API](/glossary/api/)の[タイムアウト](/glossary/タイムアウト/)設定や[ヘルスチェック](/glossary/ヘルスチェック/)状況を確認し、フォールバック処理の実装を検討してください。それでも解決しない場合はFirebase サポートに詳細な[ログ](/glossary/ログ/)とともに問い合わせてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*