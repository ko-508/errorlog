# 週次レポート仕様書

errorlog.jp の週次 GA4 + GSC 統合分析パイプラインの仕様です。
実装と乖離が生じた場合はこのドキュメントを更新してください。

---

## 概要

| 項目 | 内容 |
| :--- | :--- |
| ワークフロー | `.github/workflows/weekly_ga4.yml` |
| 実行タイミング | 毎週月曜 7:00 JST（cron: `0 22 * * 0` UTC）、手動実行（`workflow_dispatch`）も可 |
| 出力 | `reports/ga4/weekly_report_YYYYMMDD.json`、GitHub Issue（`weekly-report` ラベル） |

---

## スクリプト実行順序

```
1. ga4_analyzer.py          GA4データ取得・Claude分析・MD レポート生成
2. ga4_feedback_loop.py     リライト優先度スコアリング（Task 07+08）
3. fetch_search_console.py  GSCデータ取得・ボトルネック記事抽出・FM top_queries 更新
4. weekly_report.py         GA4+GSC 統合レポート JSON 生成・Issue本文生成
5. query_coverage_analyzer.py  Content Gap 分析（continue-on-error）
6. update_rewrite_results.py   CTR実験 after 指標更新（continue-on-error）
7. Commit and push report   成果物をリポジトリにコミット（if: always()）
8. Create unified weekly report issue  GitHub Issue 作成
```

ステップ 5・6 は `continue-on-error: true` のため失敗しても後続処理は継続する。
失敗時は Issue 冒頭の「今週の処理状況」セクションに記録される（後述）。

---

## 集計期間

```
開始: 実行日 - 9 日
終了: 実行日 - 3 日
```

GA4・GSC ともにデータ反映に 2〜3 日のラグがあるため、直近 3 日を除外した 7 日間を対象とする。

**前週との比較が必要な場合:** 実行日 -16 日〜-10 日が前週相当の期間になる。
（現時点では前週比の自動計算は未実装）

> `ga4_analyzer.py` は `TODAY - 6 日〜TODAY` の 7 日間を使用しており、`weekly_report.py` の集計期間（-9〜-3 日）とは異なる。両者を比較する際は注意すること。

---

## GA4 ホスト名フィルタ

### 背景

errorlog.jp の記事は Zenn にクロスポストしており、Zenn のページビューが同一 GA4 プロパティに混入する。確認時（2026-06-08〜14）の内訳：

| ホスト | PV | PV% | UU% |
| :--- | :--- | :--- | :--- |
| zenn.dev | 289 | 54% | 81% |
| errorlog.jp | 246 | 46% | 19% |

### フィルタ仕様

`weekly_report.py` および `ga4_analyzer.py` の全クエリに `hostName CONTAINS "errorlog.jp"` フィルタを適用している。

```python
# weekly_report.py / ga4_analyzer.py 共通
FilterExpression(
    filter=Filter(
        field_name="hostName",
        string_filter=Filter.StringFilter(
            match_type=Filter.StringFilter.MatchType.CONTAINS,
            value="errorlog.jp",
        ),
    )
)
```

### ホスト別サマリー（混入監視）

メイン集計とは別に、フィルタなしで全ホストの内訳を取得して `ga4_host_summary` として記録する。

```json
{
  "primary_host": "errorlog.jp",
  "hosts": [
    {"host": "errorlog.jp", "pv": 246, "uu": 58, "sessions": 93, "pv_share": 0.46, "uu_share": 0.186},
    {"host": "zenn.dev",    "pv": 289, "uu": 254, "sessions": 324, "pv_share": 0.54, "uu_share": 0.814}
  ],
  "primary_host_pv_share": 0.46,
  "total_pv_all_hosts": 535,
  "total_uu_all_hosts": 312
}
```

Issue 本文の「ホスト別トラフィック内訳（混入監視）」セクションに毎週表示される。
zenn.dev のデータは削除せず、この監視セクションで継続観測する。

---

## GSC 認証

### 使用する認証情報

| Secret | 用途 |
| :--- | :--- |
| `GSC_OAUTH_REFRESH_TOKEN` | GSC 専用リフレッシュトークン（優先） |
| `GA4_OAUTH_REFRESH_TOKEN` | フォールバック（`GSC_OAUTH_REFRESH_TOKEN` がない場合） |
| `GA4_OAUTH_CLIENT_ID` | OAuth クライアント ID |
| `GA4_OAUTH_CLIENT_SECRET` | OAuth クライアントシークレット |

### トークン失効時のリスク

リフレッシュトークンが失効すると `fetch_search_console.py` は認証エラーを内部で catch し、`gsc_summary = {}` を返す。ステップ自体は **成功扱いになるが** データは 0 件となり、レポートが偽の正常表示を出す。

このリスクに対し、`weekly_report.py` が生成する JSON の `gsc_summary` が空オブジェクト（`{}`）の場合、Issue 冒頭に以下を表示する（処理状況セクション参照）：

```
🔴 GSCデータ取得失敗の可能性: Search Console データが空です。認証トークンを確認してください。
```

### トークン再発行手順

`scripts/_get_refresh_token.py` を使用してリフレッシュトークンを再発行する（同ファイル内に手順コメントあり）。
再発行後は GitHub Secrets の `GSC_OAUTH_REFRESH_TOKEN` と `GA4_OAUTH_REFRESH_TOKEN` の両方を更新すること。

---

## GSC ボトルネック記事の判定条件

以下のいずれかを満たすページをボトルネックとして抽出する：

| 条件 | 閾値 |
| :--- | :--- |
| 低 CTR | インプレッション ≥ 10 件 かつ CTR < `min(1.5%, 全ページ平均CTR × 0.7)` |
| 掲載順位停滞 | インプレッション ≥ 5 件 かつ 掲載順位 11〜20 位 |

CTR の判定に使う `effective_ctr` は `min(CTR_THRESHOLD=1.5%, 全ページ平均CTR × 0.7)` で計算される。
全ページ CTR の平均が低い週は閾値も自動的に下がる。

これらの閾値は環境変数で上書き可能：

```
CTR_IMP_THRESHOLD=10
CTR_THRESHOLD=0.015
POS_IMP_THRESHOLD=5
POS_MIN=11.0
POS_MAX=20.0
```

---

## 国別分布セクション

`weekly_report.py` がホストフィルタ済みの GA4 データから上位 10 カ国を記録する。

| 取得指標 | 内容 |
| :--- | :--- |
| sessions | セッション数 |
| activeUsers | アクティブユーザー数 |
| engagementRate | エンゲージ率 |
| averageSessionDuration | 平均エンゲージ時間（秒） |
| bounceRate | 直帰率 |

**参考フラグ（⚠️）の付与条件（どちらか一方でも該当すれば付与）：**

| 指標 | 閾値 |
| :--- | :--- |
| 平均エンゲージ時間 | < 10 秒 |
| 直帰率 | > 90% |

このフラグは **bot 判定の参考であり断定ではない**。
エラー解決サイトでは検索流入後すぐ離脱する正常な利用も多いため、このフラグだけで自動除外・ブロックは行わない。
毎週の推移を人が見て判断するための記録として位置づける。

---

## ノイズ除外サマリー

`ga4_analyzer.py` が国別データ取得後に適用するフィルタ。

| 設定 | 値 |
| :--- | :--- |
| 対象国 | Singapore（`NOISE_COUNTRIES` 環境変数で指定、現在 weekly_ga4.yml でハードコード） |
| 除外条件 | 対象国 **かつ** 平均エンゲージ時間 < 5.0 秒（`NOISE_TIME_THRESHOLD`） |
| 動作 | 両条件を同時に満たす行のみ除外（国条件 OR ではない） |

`NOISE_COUNTRIES` が未設定の場合は除外をスキップし、安全側に倒す。
除外結果は `reports/ga4/noise_stats.json` に保存され、Issue の「ノイズ除外サマリー」セクションに表示される。

> `weekly_report.py` の国別分布セクションにもノイズ除外後のデータが使われる。
> ただし国別分布は `weekly_report.py` が独自に GA4 から取得するため（`ga4_analyzer.py` の除外結果は直接引き継がない）、両者で国数が異なることがある。

---

## 処理状況セクション（改善 8）

各ステップの成否を `reports/ga4/step_status.json` に記録し、Issue 冒頭に表示する。

### 対象ステップ

| id | ステップ名 | continue-on-error | 失敗時の影響 |
| :--- | :--- | :--- | :--- |
| `ga4_analyzer` | GA4分析 | いいえ | GA4トラフィックデータが更新されていません |
| `ga4_feedback` | GA4フィードバック | いいえ | リライト優先度スコアが更新されていません |
| `fetch_gsc` | Search Console取得 | いいえ | GSCボトルネック・クエリデータが更新されていません |
| `weekly_report_step` | 週次レポート生成 | いいえ | Issueが生成されない可能性があります |
| `content_gap` | Content Gap分析 | **はい** | Content Gap分析は今週更新されていません |
| `rewrite_results` | リライト実績更新 | **はい** | CTR実験のafter指標が更新されていません |

### Issue への表示

- **全成功時**: `✅ すべてのステップが正常に完了しました。`
- **失敗ありの場合**: ステップ名・設定（`continue-on-error`）・影響を表形式で表示
- **GSC データ空の場合**: `🔴 GSCデータ取得失敗の可能性` 警告を追記

`Collect step status` ステップは `if: always()` で動作し、前段が失敗してもステータスを収集する。
`Commit and push report` も `if: always()` のため、前段失敗時も `step_status.json` をリポジトリに保存する。

---

## duration 系指標の扱い方針

`averageSessionDuration`（平均セッション継続時間）は内部トラフィックや少数アクセスの週で大きくブレるため、**主判断には使わず参考値として扱う**。
ボトルネック判定・ノイズ判定の閾値としては使用しない。

---

## 未実装（リライトフェーズで実装予定）

データが十分に蓄積される 2〜3 ヶ月後を目処に実装を検討している項目：

| 項目 | 概要 |
| :--- | :--- |
| 前週比 | activeUsers・sessions・PV の週次増減率を自動計算して Issue に表示 |
| recommended_action | ボトルネック記事ごとに推奨アクション（リライト・内部リンク追加等）を自動生成 |
| 新規 vs 既存記事の成果分離 | 新規公開記事と既存記事のトラフィック寄与を分けて集計 |
| クエリ単位の変化追跡 | 特定クエリの掲載順位・CTR 推移を週次で追う |
| IndexNow 効果追跡 | IndexNow 送信後のインデックス登録速度・トラフィック変化を計測 |
| 作業チェックリスト | ボトルネック対応状況をチェックボックス形式で Issue に追記 |
