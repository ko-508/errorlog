# エラー・バグ記録（記事化のネタ帳）

このプロジェクトで実際に遭遇したバグ・エラーの記録。errorlog.jp での記事化候補として保管する。

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

## 【停止中】エラー投げ込みルール

現在このルールは停止中。即時記事化は行わず、データ蓄積を優先している。再開時にこのルールを運用に戻す。

開発中のエラーログ・スタックトレース・壊れたコードを投げた場合、挨拶・共感を省いて即座に:
1. 原因を特定して修正する
2. 記事規格（docs/article_spec.md）を満たす記事 Markdown を content/posts/ に生成する
