---
draft: true
title: "Datadog の 503 エラー：原因と解決策"
date: 2026-06-25
description: "Datadogで503エラーはサーバー側の一時的な障害やメンテナンスが原因で発生する。エージェントがサーバーに到達できない場合も同様のエラーが返る。"
tags: ["Datadog"]
errorCode: "503"
urgency: "high"
service: "Datadog"
error_type: "503"
components: []
related_services: ["Datadog エージェント", "curl"]
---

## エラーの概要

Datadog で 503 [エラー](/glossary/エラー/)が発生した場合、Datadog の[サーバー](/glossary/サーバー/)側が一時的に機能していないか、メンテナンス中、または過負荷状態にあることを示しています。エージェントが[サーバー](/glossary/サーバー/)に正しく到達できていない場合もこの[エラー](/glossary/エラー/)が返されます。

## 実際のエラーメッセージ例

```json
{
  "status": 503,
  "errors": [
    "Service Unavailable"
  ]
}
```

```
Service Unavailable (503)
Unable to connect to Datadog backend
```

**[エラーメッセージ](/glossary/エラーメッセージ/)の読み方：**

- `503` → [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)：[サーバー](/glossary/サーバー/)が一時的に利用不可能な状態
- `Service Unavailable` → 理由フレーズ：[リクエスト](/glossary/リクエスト/)の処理ができない状況を示す
- `Unable to connect to Datadog backend` → エージェント側が Datadog [バックエンド](/glossary/バックエンド/)到達できていない

## よくある原因と解決手順

### 原因1：Datadog サービスのメンテナンスまたは障害

Datadog 側でメンテナンスが実施中、または一時的な障害が発生している場合、すべての[リクエスト](/glossary/リクエスト/)が 503 で拒否されます。この場合、ユーザー側の設定や環境は問題ではなく、サービスの復旧を待つ必要があります。

**確認方法：**

Datadog の公式ステータスページ（https://status.datadoghq.com）にアクセスし、現在の障害またはメンテナンス情報を確認してください。

✅ 修正後の確認：

ステータスページで「All Systems Operational」と表示されていれば、Datadog 側は正常です。その場合は、エージェント側の設定を確認してください。

### 原因2：Datadog エージェントの API キーまたはサイト設定が正しくない

エージェントが無効な [API](/glossary/api/) キーやサイト URL を使用している場合、[リクエスト](/glossary/リクエスト/)が拒否される可能性があります。特に、複数環境を運用している場合に [API](/glossary/api/) キーを誤設定することが多くあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# envの設定が間違っているか、プレースホルダーのままになっているケース
export DD_API_KEY="YOUR_API_KEY"
export DD_SITE="datadoghq.com"  # サイトが統一されていない場合
```

**After（修正後）：**

```bash
# 正しい API キーとサイトを設定（EU の場合の例）
export DD_API_KEY="<your-actual-api-key>"
export DD_SITE="datadoghq.eu"  # 利用地域に応じた正しいサイト
```

✅ 修正後の確認：

```bash
# Datadog エージェントの設定を確認
sudo datadog-agent configcheck
```

エージェントが設定を正常に読み込み、「Check Configurations」セクションで [API](/glossary/api/) キーとサイトが正しく表示されていれば成功です。

### 原因3：ネットワーク接続またはプロキシ設定の問題

Datadog エージェントが Datadog [サーバー](/glossary/サーバー/)に[通信](/glossary/通信/)できない[ネットワーク](/glossary/ネットワーク/)環境（[ファイアウォール](/glossary/ファイアウォール/)、[プロキシ](/glossary/プロキシ/)経由）では 503 が返される場合があります。特に企業[ネットワーク](/glossary/ネットワーク/)環境で代理[サーバー](/glossary/サーバー/)を経由する場合、[プロキシ](/glossary/プロキシ/)認証設定が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# /etc/datadog-agent/datadog.yaml (プロキシ設定がない例)
dd_url: https://api.datadoghq.com
```

**After（修正後）：**

```yaml
# プロキシ経由での通信設定
dd_url: https://api.datadoghq.com
proxy:
  https: http://<proxy-host>:<proxy-port>
  http: http://<proxy-host>:<proxy-port>
# プロキシ認証が必要な場合
# https: http://<proxy-username>:<proxy-password>@<proxy-host>:<proxy-port>
```

✅ 修正後の確認：

```bash
# ネットワーク接続をテスト
curl -i https://api.datadoghq.com/api/v1/validate
```

[HTTP](/glossary/http/) 200 が返されれば、Datadog [バックエンド](/glossary/バックエンド/)への接続が正常です。

### 原因4：エージェントのバージョンが古すぎるまたは非対応

Datadog エージェントの実行中の[バージョン](/glossary/バージョン/)が古い場合、[API](/glossary/api/) の仕様変更により 503 が返される可能性があります。最新[バージョン](/glossary/バージョン/)で修正されていることもあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# バージョン確認（古い可能性がある）
sudo datadog-agent version
# 6.x 系で実行中
```

**After（修正後）：**

```bash
# 最新バージョンへのアップグレード（Ubuntu/Debian）
sudo apt-get update
sudo apt-get install datadog-agent

# またはHomebrew（macOS）
brew upgrade datadog-agent
```

✅ 修正後の確認：

```bash
# アップグレード後のバージョン確認
sudo datadog-agent version
```

7.x 以上の最新安定版が表示されていれば成功です。

### 原因5：Datadog API のレート制限に達している

短時間に大量の[リクエスト](/glossary/リクエスト/)を送信すると、Datadog [API](/glossary/api/) の[レート制限](/glossary/レート制限/)に抵触し、503 が返される場合があります。これは特にカスタムメトリクスの送信やバッチ処理で発生しやすいです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
# レート制限を考慮していない例
import requests
import time

api_key = "<your-api-key>"
for i in range(1000):
    requests.post(
        "https://api.datadoghq.com/api/v1/series",
        headers={"DD-API-KEY": api_key},
        json={"series": [{"metric": "custom.metric", "points": [[int(time.time()), i]]}]}
    )
    # 待機なし（レート制限に抵触する）
```

**After（修正後）：**

```python
# 待機時間を追加し、バッチ送信にする例
import requests
import time

api_key = "<your-api-key>"
batch_size = 10
for i in range(0, 1000, batch_size):
    batch = []
    for j in range(batch_size):
        batch.append({
            "metric": "custom.metric",
            "points": [[int(time.time()), i + j]]
        })

    requests.post(
        "https://api.datadoghq.com/api/v1/series",
        headers={"DD-API-KEY": api_key},
        json={"series": batch}
    )
    time.sleep(1)  # 1秒待機してレート制限を回避
```

✅ 修正後の確認：

```bash
# Datadog API のレート制限ヘッダーを確認
curl -i -H "DD-API-KEY: <your-api-key>" https://api.datadoghq.com/api/v1/validate
```

レスポンスヘッダーに `X-RateLimit-Remaining` が表示され、値が正常な範囲にあれば、[レート制限](/glossary/レート制限/)に達していません。

## 解決策の早見表

| 解決策 | 実装難易度 | 再起動要否 | 対応[OS](/glossary/os/) |
|--------|-----------|-----------|-------|
| ステータスページで障害確認 | 低 | 不要 | 全[OS](/glossary/os/) |
| [API](/glossary/api/) キーとサイト設定確認 | 低 | 必要 | 全[OS](/glossary/os/) |
| [プロキシ](/glossary/プロキシ/)設定の追加 | 中 | 必要 | 全[OS](/glossary/os/) |
| エージェントバージョン更新 | 中 | 必要 | 全[OS](/glossary/os/) |
| [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)間隔調整 | 中 | 不要 | 全[OS](/glossary/os/) |

## ツール固有の注意点

Datadog エージェントが 503 を返す場合、複数の要因が重なっていることがあります。まず https://status.datadoghq.com で Datadog 側に障害がないか確認することが最優先です。その上で、`sudo datadog-agent status` [コマンド](/glossary/コマンド/)でエージェントの健全性を確認してください。エージェントの再起動が必要な場合は、`sudo systemctl restart datadog-agent`（Linux）または `sudo launchctl restart com.datadoghq.agent`（macOS）で実行できます。

複数のリージョンで Datadog を利用している場合、[API](/glossary/api/) キーが正しいリージョンに対応しているか確認が重要です。EU リージョンの場合は `datadoghq.eu`、US の場合は `datadoghq.com` を使い分ける必要があります。

## それでも解決しない場合

Datadog エージェントの詳細[ログ](/glossary/ログ/)を確認してください。

```bash
# ログの確認（Linux）
sudo tail -f /var/log/datadog/agent.log

# または systemd ジャーナル経由
sudo journalctl -u datadog-agent -f
```

[ログ](/glossary/ログ/)に `Connection refused`、`Name or service not known`、`403 Forbidden` などが表示される場合は、[ネットワーク](/glossary/ネットワーク/)設定または[ファイアウォール](/glossary/ファイアウォール/)設定を再度確認してください。

[ファイアウォール](/glossary/ファイアウォール/)側で Datadog への[通信](/glossary/通信/)が遮断されている可能性もあります。以下の IP レンジと [ポート](/glossary/ポート/)443 への外向き[通信](/glossary/通信/)が許可されているか、ネットワークチーム経由で確認してください。Datadog の公式ドキュメント（https://docs.datadoghq.com/ja/agent/guide/network/）に許可すべき IP レンジと ホスト名が記載されています。

## 代替ツールの検討

この[エラー](/glossary/エラー/)が頻発して運用に支障が出る場合は、以下のツールへの移行を検討できます。

- **New Relic**：UI が直感的で、可観測性機能が充実しています。503 [エラー](/glossary/エラー/)の頻度が低く、サービスの安定性が高いという報告があります。

- **Splunk Observability Cloud**：エンタープライズ向けの強力な[ログ](/glossary/ログ/)分析機能を備えており、オンプレミス環境との統合がしやすい設計になっています。

- **Grafana Cloud**：オープンソース ベースで拡張性に優れており、コスト面でも柔軟な選択肢が可能です。小～中規模環境での運用が効率的です。

## Editor's Note

Datadog の 503 [エラー](/glossary/エラー/)について、GitHub の報告を確認すると、Datadog エージェント側の実装に関する問題と、[ネットワーク](/glossary/ネットワーク/)設定の問題が大部分を占めています。[kumahq/kuma#11632](https://github.com/kumahq/kuma/issues/11632) では、[プロキシ](/glossary/プロキシ/)経由での通信時にコネクションが適切にリセットされず、503 が継続的に返されるケースが報告されています。一方、[DataDog/datadog-agent#5418](https://github.com/DataDog/datadog-agent/issues/5418) では、[DNS](/glossary/dns/) 解決の失敗と Datadog [API](/glossary/api/) [エンドポイント](/glossary/エンドポイント/)の[タイムアウト](/glossary/タイムアウト/)が原因になる事例が多く挙げられています。公式ドキュメントではステータスページ確認が推奨されていますが、現場では [API](/glossary/api/) キーの有効性確認と[ネットワーク](/glossary/ネットワーク/)到達性[テスト](/glossary/テスト/)を最初に実施するのが有効です。

> **調査について**　この記事の解決策は、GitHub Issues への公開報告を Gemini + Google Search で検索・精査し、実効性の高いものを整理したものです。参照元の URL は Editor's Note に記載しています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
