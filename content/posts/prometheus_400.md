---
title: "Prometheus の 400 エラー：原因と解決策"
date: 2026-06-21
description: "Prometheusに送ったクエリまたはリクエストの形式が正しくない"
tags: ["Prometheus"]
errorCode: "400"
service: "Prometheus"
error_type: "400"
components: []
related_services: ["promtool"]
---

## エラーの概要

Prometheus の 400 Bad Request [エラー](/glossary/エラー/)は、クライアントが Prometheus に送信した[クエリ](/glossary/クエリ/)や[リクエスト](/glossary/リクエスト/)の形式が正しくない場合に発生します。この[エラー](/glossary/エラー/)は [HTTP](/glossary/http/) [API](/glossary/api/) の呼び出しときに最も頻繁に見られ、PromQL の構文[エラー](/glossary/エラー/)やクエリパラメータの不正な指定が原因となります。Prometheus が要求を解析できず、処理を進められない状態を示しています。

## 実際のエラーメッセージ例

**Prometheus 管理UI からの[レスポンス](/glossary/レスポンス/)：**

```json
{
  "status": "error",
  "errorType": "bad_data",
  "error": "invalid expression: \"up{job=\"prometheus\"\n at char 21: unexpected character after expression"
}
```

**[HTTP](/glossary/http/) [API](/glossary/api/) 呼び出し時の[レスポンス](/glossary/レスポンス/)：**

```bash
$ curl 'http://localhost:9090/api/v1/query' \
  -d 'query=up{job=prometheus}' \
  -d 'time=2024-01-15 10:00:00'

HTTP/1.1 400 Bad Request
Content-Type: application/json

{"status":"error","errorType":"bad_data","error":"time parameter has invalid format, expected Unix timestamp"}
```

## よくある原因と解決手順

### 原因1：PromQL の構文エラー（セレクタやカッコの不正）

PromQL の[メトリクス](/glossary/メトリクス/)名やラベルセレクタで括弧やクォート記号が正しく閉じられていないと、パース時に 400 [エラー](/glossary/エラー/)が発生します。オペレータの誤り、関数名のタイポ、ラベルマッチングの形式不正も該当します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests

response = requests.get(
    'http://localhost:9090/api/v1/query',
    params={
        'query': 'up{job="prometheus"',  # 閉じ括弧がない
        'time': '2024-01-15T10:00:00Z'
    }
)
print(response.json())
```

**After（修正後）：**

```python
import requests

response = requests.get(
    'http://localhost:9090/api/v1/query',
    params={
        'query': 'up{job="prometheus"}',  # 括弧を正しく閉じる
        'time': '2024-01-15T10:00:00Z'
    }
)
print(response.json())
```

### 原因2：時刻パラメータの形式が不正

Prometheus [API](/glossary/api/) の `time` [パラメータ](/glossary/パラメータ/)は Unix タイムスタンプ（秒単位の整数）または RFC3339 形式で指定する必要があります。`2024-01-15 10:00:00` のような一般的な日時形式では 400 [エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl 'http://localhost:9090/api/v1/query_range' \
  -d 'query=up' \
  -d 'start=2024-01-15 10:00:00' \
  -d 'end=2024-01-15 11:00:00' \
  -d 'step=1m'
```

**After（修正後）：**

```bash
curl 'http://localhost:9090/api/v1/query_range' \
  -d 'query=up' \
  -d 'start=2024-01-15T10:00:00Z' \
  -d 'end=2024-01-15T11:00:00Z' \
  -d 'step=1m'
```

### 原因3：インスタントクエリとレンジクエリのパラメータ混在

`/api/v1/query` （インスタントクエリ）と `/api/v1/query_range` （レンジクエリ）は異なる[パラメータ](/glossary/パラメータ/)を要求します。インスタントクエリに `start` と `end` を同時に指定したり、レンジクエリに `time` [パラメータ](/glossary/パラメータ/)を指定したりすると 400 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// インスタントクエリなのに start・end パラメータを指定
const response = await fetch(
  'http://localhost:9090/api/v1/query?' +
  new URLSearchParams({
    query: 'up',
    time: '2024-01-15T10:00:00Z',
    start: '2024-01-15T09:00:00Z',  // 不正なパラメータ
    end: '2024-01-15T11:00:00Z'     // 不正なパラメータ
  }).toString()
);
```

**After（修正後）：**

```javascript
// インスタントクエリは time パラメータのみ使用
const response = await fetch(
  'http://localhost:9090/api/v1/query?' +
  new URLSearchParams({
    query: 'up',
    time: '2024-01-15T10:00:00Z'
  }).toString()
);
```

## ツール固有の注意点

Prometheus の 400 [エラー](/glossary/エラー/)は管理 UI で確認するとより詳細な情報が得られます。Prometheus [ダッシュボード](/glossary/ダッシュボード/)（デフォルトでは `http://localhost:9090`）の **Graph** タブに[クエリ](/glossary/クエリ/)を直接入力すると、PromQL の構文[エラー](/glossary/エラー/)が[リアルタイム](/glossary/リアルタイム/)に表示されます。[エラー](/glossary/エラー/)箇所を示すキャレット記号（`^`）が表示されるため、修正が容易になります。

また、Prometheus 2.40 以降ではクライアント側で[クエリ](/glossary/クエリ/)を事前に検証できる `promtool` [コマンド](/glossary/コマンド/)が提供されています。複雑な PromQL を本番環境に送信する前に、ローカル環境で以下のように検証すると 400 [エラー](/glossary/エラー/)を事前に防ぐことができます。

```bash
promtool check query 'up{job="prometheus"} / rate(http_requests_total[5m])'
```

[HTTP](/glossary/http/) [API](/glossary/api/) 使用時は、ユーザー入力をクエリパラメータに含める場合、URL エンコード処理が正しく行われているか確認も必要です。特にプログラミング言語の [HTTP](/glossary/http/) ライブラリを使う際、手動で URL 文字列を組み立てるとエンコード漏れが発生しやすくなります。

## それでも解決しない場合

Prometheus のアクセスログを確認することで、[サーバー](/glossary/サーバー/)が実際に受け取った[リクエスト](/glossary/リクエスト/)の内容を確認できます。デバッグレベルで[ログ](/glossary/ログ/)を出力するには、Prometheus をスタート時に以下のフラグで起動してください。

```bash
./prometheus --log.level=debug
```

出力される[ログ](/glossary/ログ/)に `msg="HTTP request received"` というエントリが記録され、受け取ったクエリパラメータや[ヘッダー](/glossary/ヘッダー/)が表示されます。

PromQL の複雑な式については、Prometheus 公式ドキュメント「[PromQL Examples](https://prometheus.io/docs/prometheus/latest/querying/examples/)」を参照し、標準的なクエリパターンとの比較も有効です。GitHub の Prometheus [リポジトリ](/glossary/リポジトリ/)でも、過去のイシューから類似した 400 [エラー](/glossary/エラー/)の事例が報告されているため、検索して参考にすることもできます。

curl で[リクエスト](/glossary/リクエスト/)を[デバッグ](/glossary/デバッグ/)する場合は、`-v` フラグを付けることで [HTTP](/glossary/http/) [ヘッダー](/glossary/ヘッダー/)とレスポンスボディの全容を確認できます。

```bash
curl -v 'http://localhost:9090/api/v1/query?query=up&time=2024-01-15T10:00:00Z'
```

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*