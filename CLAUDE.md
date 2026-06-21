# errorlog.jp — Claude Code 設定

## このファイルの役割

このファイルは Claude Code 用である。Claude Code の役割は調査・アーキテクチャ提案・要約・計画作成に限る。実装と検証は行わない。実装は Codex が AGENTS.md に従って担当する。コードを変更せず、調査結果と計画を報告し、ユーザーの承認を得ること。

## プロジェクト概要

- サイト: https://errorlog.jp
- 構成: Hugo v0.146+ / PaperMod テーマ / GitHub Pages + Cloudflare CDN
- リポジトリ: https://github.com/ko-508/errorlog
- Zenn: https://zenn.dev/errorlog

## 記事規格

記事規格の詳細は docs/article_spec.md を参照すること。ただし実際の生成挙動は各スクリプト内のシステムプロンプトが持つため、生成を変えたい場合は docs/article_spec.md ではなく該当スクリプトを確認すること。

## 行動の制約（厳守）

- 調査を先行させる: 問題・要望を受けたらまず現行システムの状態を調査してレポートする。ユーザーの明示的な承認を得てから、実装は Codex に渡す。
- push は指示があるまで行わない: コミットも同様。
- フォールバック禁止: エラーや想定外の入力に、フォールバック値・握りつぶし・症状を隠すガード・暗黙のリカバリを入れない。型やスキーマを緩めて通すこともしない。成功するか、原因・パラメータ・状況を含む明確なエラーで失敗するかのどちらか。直せないなら止まって報告する。
- 断定しない: API 仕様・UI ナビゲーション・外部サービスの設定箇所など変わりやすい情報は、確信がない場合「〜のはずです」「〜も試してください」のように不確かさを示す。確認できないことは事実として書かない。

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

## Claude Code メモリ

残タスク・フィードバック・プロジェクト状況は以下で管理している:

```
C:\Users\oobak\.claude\projects\c--Users-oobak-errorlog\memory\MEMORY.md
```
