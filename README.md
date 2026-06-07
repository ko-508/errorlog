# errorlog.jp

**エラーコード解決ガイド** — 開発・運用中に遭遇するHTTPエラーの意味・原因・解決策をツール別に解説する、自律運営型の技術リファレンスメディアです。

🌐 **https://errorlog.jp**

---

## 概要

<!-- STATUS_BEGIN -->
公開記事数: **137 件** ／ 対応ツール数: **17 種**

AWS / Azure / Docker / Docker Compose / Firebase / GCP / GitHub API / Hugo / Kubernetes / Minikube / Nginx / OpenAI API / Podman / Slack / Stripe / Supabase / Vercel
<!-- STATUS_END -->

HTTPエラーコード（400〜504）について、**実際のエラーメッセージ例・Before/After コード対比・ツール固有の注意点**をセットで解説します。

記事の生成・リライト・品質チェック・Zenn同期まで、コンテンツパイプライン全体を GitHub Actions で自律運営しています。

---

## ターミナルから即デコード（CLI）

```bash
python scripts/cli_errlog.py docker_compose 503
```

```
────────────────────────────────────────────────────
  docker_compose  >  503
────────────────────────────────────────────────────

現象
  サービスが起動できないか利用できない状態にある。

原因
  1. 依存サービスが起動完了する前にアクセスしようとしている
  2. depends_on の condition が service_healthy だがヘルスチェックが失敗している
  3. コンテナが起動直後に停止している

対策
  1. compose.yml の depends_on に condition: service_healthy を設定する
  2. ヘルスチェックコマンドを手動で確認する
  3. docker compose logs で起動失敗の原因を調べる

────────────────────────────────────────────────────
Before/After の修正コードを含む詳細な検証ログを確認する
  ->  https://errorlog.jp/posts/docker_compose_503/
────────────────────────────────────────────────────
```

出力末尾の URL から該当記事へアクセスすると、Before/After コードブロックと詳細解説を確認できます。

---

## 自動化パイプライン

| スクリプト | 役割 |
|---|---|
| `scripts/daily_publish.py` | キューから毎日3記事を Claude で自動生成 |
| `scripts/refresh_articles.py` | 90日以上経過した記事を Gemini + Claude で自動リライト（セルフレビュー付き） |
| `scripts/replenish_queue.py` | 月1回 Gemini + SEO API でキューを自動補充 |
| `scripts/expand_articles.py` | 薄い記事（1,200文字未満）を自動拡張 |
| `scripts/check_quality.py` | Before/After・免責事項・文字数を品質チェック |
| `scripts/zenn_sync.py` | Hugo 記事を Zenn 形式に変換・同期 |
| `scripts/ga4_feedback_loop.py` | GA4 投票データからリライト優先度を自動スコアリング |
| `scripts/cli_errlog.py` | ターミナル完結型エラーコードデコーダー |

---

## セットアップ（ローカル開発）

```bash
git clone https://github.com/ko-508/errorlog.git
cd errorlog
```

### CLIツールの実行（依存ライブラリ不要）

```bash
python scripts/cli_errlog.py <tool> <error_code>

# 例
python scripts/cli_errlog.py docker 404
python scripts/cli_errlog.py github_api 422
python scripts/cli_errlog.py aws 403
```

### 自動化スクリプトの実行（要 API キー）

```bash
pip install anthropic google-genai google-analytics-data
```

必要な環境変数:

| 変数名 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | 記事生成・品質チェック（Claude API） |
| `GEMINI_API_KEY` | リサーチ・キュー補充（Gemini API） |
| `GA4_PROPERTY_ID` | GA4 分析（週次レポート） |
| `GA4_SERVICE_ACCOUNT_KEY` | GA4 認証（サービスアカウント JSON 文字列） |

---

## 技術スタック

- **サイト**: [Hugo](https://gohugo.io/) v0.146+ / [PaperMod](https://github.com/adityatelange/hugo-PaperMod) テーマ
- **ホスティング**: GitHub Pages + Cloudflare CDN
- **AI**: Claude API（Anthropic）/ Gemini API（Google）
- **分析**: Google Analytics 4 Data API
- **クロスポスト**: Zenn

---

## 関連リンク

- **サイト本体**: [errorlog.jp](https://errorlog.jp)
- **Zenn**: [zenn.dev/errorlog](https://zenn.dev/errorlog)

---

## ライセンス

MIT License
