---
title: "Supabase の 429 エラー：原因と解決策"
date: 2026-06-05
description: "Supabaseのレート制限または利用枠の上限に達した"
tags: ["Supabase"]
errorCode: "429"
service: "Supabase"
error_type: "429"
components: ["JavaScript Client", "Edge Functions", "Database", "Authentication API"]
related_services: ["HTTP", "Webhook"]
top_queries:
- '{"error": "too many requests", "message": "rate limit exceeded. please try again later."}'
- 'request failed with status code 429'
---
## エラーの概要

429は [HTTP](/glossary/http/) 標準の[レート制限](/glossary/レート制限/)（許可された[リクエスト](/glossary/リクエスト/)数を超過）を示し、Supabaseでは無料プランのリソース上限または [API](/glossary/api/) [レート制限](/glossary/レート制限/)に達したことを意味します。データベースリクエスト、Edge Functions、[認証](/glossary/認証/) [API](/glossary/api/) など、複数のサービスで発生する可能性があり、放置するとアプリケーション全体が一時的に利用不可になります。

## 実際のエラーメッセージ例

**Supabase JavaScript Clientを経由した[エラー](/glossary/エラー/)：**

```json
{
  "status": 429,
  "error": "Too Many Requests",
  "message": "Rate limit exceeded. Please try again later.",
  "statusText": "Too Many Requests"
}
```

**Edge Functions呼び出し時の[レスポンス](/glossary/レスポンス/)：**

```bash
curl https://<project>.supabase.co/functions/v1/<function-name> \
  -H "Authorization: Bearer <token>"

HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{"error":"rate_limit_exceeded"}
```

## よくある原因と解決手順

### 原因1：Edge Functionsの呼び出し回数が上限を超えた

無料プランのEdge Functionsは月間500,000回の呼び出しが上限です。不要な呼び出しや[Webhook](/glossary/webhook/)設定の誤りにより、短時間で大量の[リクエスト](/glossary/リクエスト/)が発生すると429[エラー](/glossary/エラー/)が返されます。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// ❌ フロントエンドで毎回Edge Functionを呼び出し
async function processPayment(orderId) {
  const response = await fetch(
    'https://<project>.supabase.co/functions/v1/process-payment',
    {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ orderId })
    }
  );
  
  // 同期・キャッシング戦略なし
  return response.json();
}

// ページ読み込みのたびに呼び出す（重複リクエスト）
useEffect(() => {
  processPayment(orderId);
}, []); // 依存関係配列が空
```

**修正後：**

```javascript
// ✅ キャッシュを活用し、必要な場合のみ呼び出し
const cache = new Map();

async function processPayment(orderId) {
  // キャッシュをチェック
  if (cache.has(orderId)) {
    const cachedData = cache.get(orderId);
    if (Date.now() - cachedData.timestamp < 60000) {
      return cachedData.result;
    }
  }

  const response = await fetch(
    'https://<project>.supabase.co/functions/v1/process-payment',
    {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ orderId })
    }
  );

  const result = await response.json();
  cache.set(orderId, { result, timestamp: Date.now() });
  return result;
}

// 依存関係を正確に指定
useEffect(() => {
  processPayment(orderId);
}, [orderId]);
```

### 原因2：データベースリクエストが短時間に集中している

バッチ処理の非効率さやポーリング実装により、短時間に大量のデータベースリクエストが発生すると[レート制限](/glossary/レート制限/)に引っかかります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// ❌ ループ内で個別のリクエストを連発
async function fetchAllUsers() {
  const userIds = [1, 2, 3, 4, 5];
  const results = [];
  
  for (const id of userIds) {
    const { data, error } = await supabase
      .from('users')
      .select('*')
      .eq('id', id);
    
    if (error) throw error;
    results.push(data);
  }
  
  return results;
}
```

**修正後：**

```javascript
// ✅ 単一クエリで複数件取得
async function fetchAllUsers() {
  const userIds = [1, 2, 3, 4, 5];
  
  const { data, error } = await supabase
    .from('users')
    .select('*')
    .in('id', userIds);
  
  if (error) throw error;
  return data;
}
```

### 原因3：認証APIへのリクエストが短時間に集中している

ユーザー登録・[ログイン](/glossary/ログイン/)処理が短時間に大量発生する場合（例：バッチユーザー作成スクリプト）、Supabase[認証](/glossary/認証/) [API](/glossary/api/) の[レート制限](/glossary/レート制限/)に引っかかります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// ❌ 並列で大量の認証APIリクエストを送信
async function createUsersInBatch(emails) {
  const promises = emails.map(email =>
    supabase.auth.signUp({ email, password: 'temp123' })
  );
  
  // 制限なく100件以上を同時実行
  const results = await Promise.all(promises);
  return results;
}

createUsersInBatch([...100個のメールアドレス]);
```

**修正後：**

```javascript
// ✅ リクエストを順序立てて実行、遅延を挿入
async function createUsersInBatch(emails) {
  const results = [];
  
  for (const email of emails) {
    const result = await supabase.auth.signUp({
      email,
      password: 'temp123'
    });
    results.push(result);
    
    // リクエスト間に遅延を挿入
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  
  return results;
}

createUsersInBatch([...100個のメールアドレス]);
```

## ツール固有の注意点

Supabase[ダッシュボード](/glossary/ダッシュボード/)の「Usage」セクションで、どのリソースが上限に達しているかを確認することが重要です。Edge Functions・[認証](/glossary/認証/) [API](/glossary/api/) はそれぞれ個別にカウントされるため、原因の特定にはこのページの確認が必須です。無料プランと有料プラン（Pro）では制限値が大きく異なり、ProプランはEdge Functions呼び出しが2,000,000回/月に拡張されます。

Supabaseはリージョンごとに独立した制限を持つため、複数のプロジェクトを運用している場合は各プロジェクトの使用状況を個別に確認する必要があります。開発環境と本番環境で異なるプロジェクトを使い分けている場合、本番環境だけが429[エラー](/glossary/エラー/)になるケースも一般的です。

リアルタイム機能を使用している場合、接続数の上限（無料プランで100同時接続）に達することでも間接的に429が発生することがあります。Presence機能やPostgres変更リッスン（[データベース](/glossary/データベース/)変更を監視する機能）の設定を見直し、必要最小限の接続に絞ることも対策の一つです。

## それでも解決しない場合

Supabase[ダッシュボード](/glossary/ダッシュボード/)の「Logs」セクションでリアルタイムのリクエストログを確認し、どの[エンドポイント](/glossary/エンドポイント/)やファンクションが頻繁に呼び出されているかを特定してください。ブラウザーの開発者ツール（Networkタブ）で、予期しない[リクエスト](/glossary/リクエスト/)が送信されていないか確認することも効果的です。

以下の[コマンド](/glossary/コマンド/)でプロジェクトの [API](/glossary/api/) 使用状況を [CLI](/glossary/cli/) 経由で確認できます：

```bash
supabase projects info --project-ref <project-ref>
```

それでも解決しない場合は、Supabaseの公式ドキュメント「[Rate Limiting](https://supabase.com/docs/guides/platform/rate-limits)」を参照するか、Supabase公式サポート（有料プランのみ）に問い合わせてください。無料プランの場合は、Discordコミュニティーでの相談も有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*