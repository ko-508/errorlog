---
title: "GitHub API の 502 エラー：原因と解決策"
date: 2026-01-01
description: "502 Bad Gateway は、GitHub API がリクエストを処理するサーバー間の通信に障害が発生したときに返されるエラーです。"
tags: ["GitHub API"]
errorCode: "502"
lastmod: 2026-05-31
---

## エラーの概要

502 Bad Gateway は、GitHub [API](/glossary/api/) が[リクエスト](/glossary/リクエスト/)を処理する[サーバー](/glossary/サーバー/)間の[通信](/glossary/通信/)に障害が発生したときに返される[エラー](/glossary/エラー/)です。クライアントからの[リクエスト](/glossary/リクエスト/)そのものは正しくても、GitHub の内部インフラストラクチャでゲートウェイ層が上位[サーバー](/glossary/サーバー/)から不正な応答を受け取った状態を示します。この[エラー](/glossary/エラー/)が発生すると、[API](/glossary/api/)呼び出しは失敗し、データの取得や更新ができなくなります。

## 実際のエラーメッセージ例

```json
{
  "message": "Bad Gateway",
  "documentation_url": "https://docs.github.com/rest"
}
```

```
HTTP/1.1 502 Bad Gateway
Content-Type: application/json

{
  "message": "502",
  "status": 502
}
```

## よくある原因と解決手順

### 原因1：GitHub 側のメンテナンスやインシデント

**なぜ発生するか**
GitHub は定期的にインフラメンテナンスを実施します。メンテナンス中は [API](/glossary/api/) [サーバー](/glossary/サーバー/)が一時的に不安定になり、[リクエスト](/glossary/リクエスト/)がゲートウェイで処理できず 502 が返されます。

**Before（[エラー](/glossary/エラー/)が起きる状態）**
```bash
curl -H "Authorization: token <your-github-token>" \
  https://api.github.com/user
```

```
HTTP/1.1 502 Bad Gateway
```

**After（解決方法）**
GitHub の Status ページ（https://www.githubstatus.com）を確認し、メンテナンスやインシデントが報告されているかチェックします。メンテナンス中の場合は復旧を待ちます。

```bash
# ステータスを確認してから数分待機後にリトライ
curl -H "Authorization: token <your-github-token>" \
  https://api.github.com/user
```

### 原因2：無効な Authorization ヘッダーまたは認証エラー

**なぜ発生するか**
[トークン](/glossary/トークン/)の形式が不正、有効期限が切れている、または[スコープ](/glossary/スコープ/)が不足している場合、認証層で処理できずゲートウェイエラーとして返されることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）**
```python
import requests

token = "ghp_invalidtoken"  # 形式が不正
headers = {"Authorization": f"token {token}"}
response = requests.get("https://api.github.com/user", headers=headers)
print(response.status_code)  # 502 が返される
```

**After（修正後）**
```python
import requests

# 有効な Personal Access Token を使用
token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
headers = {"Authorization": f"token {token}"}
response = requests.get("https://api.github.com/user", headers=headers)

if response.status_code == 401:
    print("認証失敗：トークンが無効です")
elif response.status_code == 200:
    print("認証成功:", response.json()["login"])
```

### 原因3：API レート制限への到達

**なぜ発生するか**
短時間に大量の[リクエスト](/glossary/リクエスト/)を送信すると、[レート制限](/glossary/レート制限/)に達した後の[リクエスト](/glossary/リクエスト/)で 502 が返されることがあります。特に[認証](/glossary/認証/)なしでのアクセスや、古い [API](/glossary/api/) バージョンを使用している場合に顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）**
```javascript
// 認証なしで連続リクエスト
for (let i = 0; i < 100; i++) {
  fetch(`https://api.github.com/users/github/repos?page=${i}`)
    .then(res => res.json())
    .catch(err => console.error("502 エラー:", err));
}
```

**After（修正後）**
```javascript
// 認証トークンを使用し、レート制限を考慮
const token = '<your-github-token>';

async function fetchWithRetry(url) {
  const response = await fetch(url, {
    headers: { Authorization: `token ${token}` }
  });

  if (response.status === 502) {
    console.log("サーバー一時エラー：1秒後に再試行");
    await new Promise(resolve => setTimeout(resolve, 1000));
    return fetchWithRetry(url);
  }

  // X-RateLimit ヘッダーを確認
  const remaining = response.headers.get('x-ratelimit-remaining');
  if (remaining < 10) {
    const reset = response.headers.get('x-ratelimit-reset');
    const waitTime = Math.max(0, (reset * 1000) - Date.now());
    console.log(`レート制限間近。${waitTime}ms 待機します`);
    await new Promise(resolve => setTimeout(resolve, waitTime + 1000));
  }

  return response.json();
}

fetchWithRetry('https://api.github.com/user/repos');
```

### 原因4：不正なまたは廃止された API エンドポイント

**なぜ発生するか**
GitHub [API](/glossary/api/) v3 の廃止や、[エンドポイント](/glossary/エンドポイント/)の URL が変更された場合、ゲートウェイが[リクエスト](/glossary/リクエスト/)を処理できず 502 を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）**
```bash
# 廃止された v3 エンドポイント
curl -H "Authorization: token <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/issues
```

**After（修正後）**
```bash
# GraphQL API（推奨）またはREST API v3 の最新エンドポイントを使用
curl -H "Authorization: token <your-github-token>" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/<owner>/<repo>/issues
```

## ツール固有の注意点

GitHub [API](/glossary/api/) 固有の 502 対策として以下を確認してください：

**[API](/glossary/api/) バージョンの確認**
GitHub は [REST](/glossary/rest/) [API](/glossary/api/) v3 をメインで提供していますが、古いクライアントライブラリを使用している場合は更新が必要です。Accept [ヘッダー](/glossary/ヘッダー/)で [API](/glossary/api/) バージョンを明示的に指定することをお勧めします。

**[GraphQL](/glossary/graphql/) [API](/glossary/api/) への移行**
複数の[エンドポイント](/glossary/エンドポイント/)からデータを取得する場合、[GraphQL](/glossary/graphql/) [API](/glossary/api/) を使用するとゲートウェイへの負荷が分散され、502 [エラー](/glossary/エラー/)の頻度が低下します。

```bash
curl -H "Authorization: Bearer <your-github-token>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/graphql \
  -d '{"query":"query { viewer { login } }"}'
```

**[Webhook](/glossary/webhook/) の署名検証**
webhook を受信する場合、GitHub からの[ペイロード](/glossary/ペイロード/)署名を検証し、[リクエスト](/glossary/リクエスト/)処理に失敗した場合は適切な[ステータスコード](/glossary/ステータスコード/)を返します。GitHub は 5xx [エラー](/glossary/エラー/)を受け取ると[リトライ](/glossary/リトライ/)を繰り返すため、[エラーハンドリング](/glossary/エラーハンドリング/)が重要です。

## それでも解決しない場合

**[ログ](/glossary/ログ/)と[ヘッダー](/glossary/ヘッダー/)確認**
[デバッグ](/glossary/デバッグ/)の際には、レスポンスヘッダー内の `X-RateLimit-*`、`X-GitHub-Request-Id` を確認します。Request ID は GitHub サポートへの問い合わせに役立ちます。

```bash
# 詳細なヘッダー情報を表示
curl -v -H "Authorization: token <your-github-token>" \
  https://api.github.com/user
```

**公式ドキュメントの参照**
GitHub [API](/glossary/api/) のドキュメント（https://docs.github.com/en/rest）の「HTTP status codes」セクションで詳細な仕様を確認してください。また Status ページ（https://www.githubstatus.com）で リアルタイムのインシデント情報をチェックできます。

**GitHub Community への相談**
個別の問題については GitHub Discussions（https://github.com/orgs/github/discussions）または Stack Overflow の github-api タグで質問することで、コミュニティからの支援が得られます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*