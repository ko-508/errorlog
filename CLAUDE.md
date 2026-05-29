# errorlog.jp — Claude Code 設定

## プロジェクト概要

- サイト: https://errorlog.jp
- 構成: Hugo v0.146+ / PaperMod テーマ / GitHub Pages + Cloudflare CDN
- リポジトリ: https://github.com/ko-508/errorlog
- Zenn: https://zenn.dev/errorlog

---

## 記事規格（新規記事を生成するときは必ずこれに従う）

- **最低1,500文字以上**（日本語本文のみ、マークダウン記号・URLを除いてカウント）
- **必須セクション（この順番）:**
  1. エラーの概要（2〜3文）
  2. 実際のエラーメッセージ例（コードブロック）
  3. よくある原因と解決手順（Before/After コード対比を必ず含む）
  4. ツール固有の注意点（サービス・設定ごとの深掘り）
  5. それでも解決しない場合
- コードブロックには必ず言語名を指定（bash, json, yaml, python 等）
- プレースホルダーは `<your-xxx>` 形式
- ですます調・断定的に書く
- ふりがな補足は不要
- H1 タイトルは含めない（フロントマターで設定済み）
- 末尾に免責事項フッターを付ける

**フロントマターのテンプレート:**
```yaml
---
title: "{ツール} の {コード} エラー：原因と解決策"
date: YYYY-MM-DD
description: "{meaning}。{ツール} {コード} エラーの原因と解決策を解説します。"
tags: ["{ツール名}"]
errorCode: "{コード}"
---
```

**ファイル命名規則:** `{tool_slug}_{error_code}.md`（例: `docker_404.md`）

**配置先:** `content/posts/`

---

## エラー投げ込みルール

開発中のエラーログ・スタックトレース・壊れたコードを投げた場合、**挨拶・共感を省いて即座に:**
1. 原因を特定して修正する
2. 上記規格を満たす記事 Markdown を `content/posts/` に生成する

---

## このプロジェクトで実際に遭遇したバグ・エラー一覧

| # | エラー | 原因 | 解決策 |
|---|--------|------|--------|
| 1 | `datePublished: 0001-01-01` | PaperMod の `schema_json.html` が `.PublishDate` を `jsonify` なしで出力 | `layouts/_partials/templates/schema_json.html` をオーバーライドして `.Date.UTC.Format "2006-01-02T15:04:05Z" \| jsonify` に修正 |
| 2 | 用語集が `glossary/list.html` を無視 | Hugo v0.146+ でセクション名と同名テンプレート `glossary/glossary.html` が優先 | `_index.md` に `layout: "list"` を明示 |
| 3 | カタカナ誤マッチ（`サポート`→`サ[ポート]`） | 正規表現の文字クラス `゠-ヿ` に `・`（U+30FB）が含まれていた | `ァ-ヺー` に変更 |
| 4 | GitHub Actions YAML の日本語がモジバケ | PowerShell の `Set-Content` がデフォルト UTF-16 で書き込み | 全 YAML フィールドを英語で書き直し |
| 5 | `from google.generativeai import ...` が ImportError | SDK が非推奨、`google-genai` パッケージに移行 | `from google import genai; from google.genai import types` に変更 |
| 6 | Gemini 429 RESOURCE_EXHAUSTED | 無料枠クォータ枯渇 | Gemini をオプション化（GEMINI_API_KEY なしでも動作） |
| 7 | Google Search Console 認証失敗 | Cloudflare が旧メタタグをキャッシュ | DNS TXT レコード方式に切り替え |
| 8 | `zenn_sync` が更新記事をスキップ | `--new-only` でファイル存在チェックのみ、`lastmod` を無視 | `zenn_synced.json` マニフェスト方式に変更し `lastmod > 最終同期日` で再同期 |
| 9 | description に `。。` や語の途中切れ | `meaning_text` 末尾の `。` に `。` を追記 / `causes_list[0][:30]` の途中切れ | 末尾 `。` を strip・cause_hint を廃止 |
| 10 | `expand_articles.py` が薄い記事をスキップ | 用語集リンクの URL パスが文字数カウントに混入 | `re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)` でリンク URL を除去してカウント |
| 11 | Git push 競合（concurrent workflows） | 複数ワークフローが同時に同一ブランチにプッシュ | `for i in 1 2 3; do git pull --rebase && git push && break \|\| sleep 10; done` |
| 12 | Zenn 一括デプロイの投稿数上限 | 90件を一度にプッシュ → Zenn レートリミット | `ZENN_LIMIT` 変数で段階的同期、上限緩和申請 |
| 13 | Qiita API 403 Forbidden | 新規アカウントへの API 投稿制限 | 自動同期を無効化、回復後に手動運用 |

---

## 主要スクリプト

| スクリプト | 役割 |
|-----------|------|
| `scripts/daily_publish.py` | queue.csv から記事生成（毎日3件） |
| `scripts/expand_articles.py` | 1200文字未満の薄い記事を拡張 |
| `scripts/replenish_queue.py` | queue.csv を補充（月1回、90件） |
| `scripts/discover_tools.py` | 新ツールを発見して tools.json に追加 |
| `scripts/refresh_articles.py` | 古い記事をリライト（週次） |
| `scripts/check_quality.py` | 品質チェック（Gemini + Claude） |
| `scripts/insert_glossary_links.py` | 記事に用語集リンクを自動挿入 |
| `scripts/zenn_sync.py` | Hugo 記事を Zenn 形式に変換・同期 |

## 主要ワークフロー

| ファイル | スケジュール | 役割 |
|---------|------------|------|
| `daily.yml` | 毎日 10:00 JST | 記事公開 + 品質チェック + デプロイ |
| `zenn_sync.yml` | daily 完了後に自動 | Zenn 同期 |
| `replenish_queue.yml` | 毎月1日 | キュー補充 + ツール記事生成 |
| `quarterly_refresh.yml` | 毎週金曜 | 古い記事リライト |
| `expand_articles.yml` | 手動 | 薄い記事の拡張 |
