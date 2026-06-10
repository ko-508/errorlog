# Cloudflare Bot 対策 運用手順書

対象サイト: errorlog.jp  
対象プラン: **Cloudflare 無料プラン**（有料機能は明示して区別）

> **前提**: DNS 移行中（XServer → Cloudflare）の間は Cloudflare ゾーンが "Active" にならないと
> 以下の設定は反映されない。`https://dash.cloudflare.com/<zone>/dns` の
> ステータスが "Active" になってから実施すること。

---

## 1. Bot Fight Mode の有効化（無料プランで使える一番手軽な方法）

### 手順

1. Cloudflare ダッシュボード → 対象ゾーン（errorlog.jp）を選択
2. 左メニュー **Security** → **Bots** を開く
3. **Bot Fight Mode** のトグルを **On** に切り替える
4. 確認ダイアログが出た場合は「Enable」をクリック

### 効果

- Cloudflare が既知の悪性ボットとスクレイパーを検知し、JS チャレンジを発行する
- チャレンジを解けないボット（JS 非実行環境）はページを取得できず、GA4 イベントも発生しない
- 設定変更は即時反映（伝播待ち不要）

### 制約事項（重要）

| 制約 | 内容 |
| :--- | :--- |
| 除外設定不可 | 無料プランの Bot Fight Mode は特定 IP・UA を除外できない。誤検知が多い場合は本機能を Off にして WAF カスタムルール（下記）に移行する |
| Workers との干渉 | Cloudflare Workers を使用している場合、Bot Fight Mode が Workers へのリクエストをブロックする場合がある。Workers 利用時は動作確認を必ず行うこと |
| Verified bot の扱い | Googlebot・Bingbot 等の Verified bot は自動的に除外される。IndexNow 検証アクセスも除外対象（Cloudflare が認識する bot リスト準拠） |

---

## 2. WAF カスタムルール（Bot Fight Mode が粗すぎた場合の代替）

Bot Fight Mode で誤検知が出る、または細かい制御が必要な場合に使用する。

### 無料プランで使えるフィールド vs 有料専用フィールド

| フィールド | 無料プラン | 説明 |
| :--- | :---: | :--- |
| `ip.src` | 使える | 送信元 IP アドレス |
| `http.user_agent` | 使える | User-Agent 文字列 |
| `http.request.uri.path` | 使える | リクエストパス |
| `ip.geoip.country` | 使える | 国コード（JP, SG など） |
| `cf.client.bot` | 使える | Cloudflare が bot と判定（true/false）|
| `cf.verified_bot` | 使える | Verified bot（Googlebot 等）は true |
| `cf.bot_management.score` | **有料のみ** | Bot Management スコア（0-100）|
| `cf.bot_management.verified_bot` | **有料のみ** | Bot Management 版 Verified bot |
| `cf.bot_management.ja3_hash` | **有料のみ** | JA3 TLS フィンガープリント |

> **注意**: `cf.bot_management.*` 系フィールドは Bot Management アドオン（有料）が必要。
> 無料プランで使えないフィールドをルール式に含めると、ルール作成画面でエラーになる。

### 推奨カスタムルール例（無料プランで実施可能）

**目的**: Singapore からの短時間アクセス（bot 疑い）に Managed Challenge をかける

```
# WAF > カスタムルール > ルール作成
# 条件式（Expression Editor に貼り付け）:
(ip.geoip.country eq "SG") and (not cf.verified_bot)

# アクション: Managed Challenge
```

**補足**:
- `not cf.verified_bot` で Googlebot 等の正規 bot は除外される
- Managed Challenge は CAPTCHA より軽い JS チャレンジ。人間のブラウザなら透過的に通過できる
- Singapore 以外に bot の拠点が移った場合は `ip.geoip.country eq "HK"` 等を条件に追加する

### ルール作成手順

1. Cloudflare ダッシュボード → **Security** → **WAF**
2. **Custom rules** タブ → **Create rule**
3. Rule name: `Block SG bot traffic`
4. **Edit expression** をクリックして Expression Editor を開く
5. 上記の条件式を貼り付ける
6. **Choose action**: `Managed Challenge`
7. **Deploy** をクリック

---

## 3. 導入後 1 週間の観測手順

### Security Events でのチャレンジ確認

1. Cloudflare ダッシュボード → **Security** → **Events**
2. フィルタ: `Action = Challenge` または `Action = Managed Challenge`
3. 確認ポイント:
   - チャレンジを発行した User-Agent の種類（Bot らしいか）
   - チャレンジ通過率（Pass Rate）: 低ければ bot が多い証拠
   - 発生頻度の推移（導入前後で増減を比較）

### 誤爆チェックリスト

導入後 1 週間は以下を毎日確認する。

| 確認対象 | 確認方法 | 判定基準 |
| :--- | :--- | :--- |
| **Googlebot** | Security Events で `user_agent contains "Googlebot"` でフィルタ | チャレンジされていれば Bot Fight Mode を Off にする |
| **Bingbot** | 同上 `"bingbot"` でフィルタ | 同上 |
| **RSSリーダー** (Feedly, Inoreader 等) | `user_agent contains "Feedly"` 等 | チャレンジされていれば WAF ルールで除外条件を追加 |
| **IndexNow 検証アクセス** | `http.request.uri.path contains ".txt"` でフィルタ | キーファイル（`/6776a5591ab1e3d637232be8c7d5526c.txt`）へのアクセスがブロックされていないこと |
| **Search Console クロール** | Google Search Console → カバレッジ → エラー増加がないか確認 | 導入前後 1 週間でクロールエラーが急増していないこと |
| **GA4 トラフィック** | GA4 → リアルタイム → 日本からのセッションが正常に計測されていること | 正規ユーザーが弾かれていないこと |

### ロールバック手順

誤爆が確認された場合:

**Bot Fight Mode の場合:**
1. Security → Bots → Bot Fight Mode を **Off** に切り替える（即時反映）

**WAF カスタムルールの場合:**
1. Security → WAF → Custom rules
2. 対象ルールの右端にある **…** → **Disable** をクリック（削除より無効化を推奨。後で調整しやすい）

---

## 4. 効果測定

### 観測指標と確認場所

| 指標 | 確認場所 | 期待する変化 |
| :--- | :--- | :--- |
| Singapore からの GA4 セッション数 | GA4 → レポート → ユーザー → 国 | 週次で減少傾向 |
| 週次ノイズ除外件数 | GitHub Issues の週次レポート「### 3. ノイズ除外サマリー」 | 減少（edge で止まるため分析側フィルタに到達しなくなる） |
| Cloudflare チャレンジ数 | Security → Events → Challenge 件数 | 増加（edge で受け止めている証拠） |
| Search Console 表示回数・クリック数 | Google Search Console → 検索パフォーマンス | 変化なし（正規検索流入は影響を受けない） |

### 前後比較の手順

1. Bot Fight Mode / WAF ルール有効化の日付を記録する
2. 有効化前後の週次レポート Issue（GitHub Issues → `weekly-report` ラベル）を比較する
3. **「ノイズ除外サマリー」セクション**の除外件数を比較する:
   - 除外件数が減る = Cloudflare が edge でブロックしている（狙い通り）
   - 除外件数が変わらない = Bot Fight Mode を回避している bot が存在する可能性
4. GA4 の国別データ（Singapore の UU 数）も合わせて確認する

---

## 参考: 二段構えの構成図

```
[外部アクセス]
    |
    v
[Cloudflare edge] --- Bot Fight Mode / WAF カスタムルール
    |                  ↑ 一段目: JS 非実行の bot はここで止まる
    | (通過したトラフィック)
    v
[Hugo / GitHub Pages]
    |
    v
[GA4 イベント送信] --- ga4_analyzer.py _drop_noise()
                       ↑ 二段目(保険): JS を実行できた bot が来ても
                         NOISE_COUNTRIES + 短時間セッションでフィルタ
```
