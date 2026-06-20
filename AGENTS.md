# errorlog.jp — Codex 設定

## このファイルの役割

このファイルは Codex 用である。Codex の役割は実装と検証に限る。調査と計画作成は行わない。Claude が立てた計画に沿い、コードと実行結果の整合性を最優先する。計画にない判断が必要になったら、実装を止めて報告すること。

## プロジェクト概要

- サイト: https://errorlog.jp
- 構成: Hugo v0.146+ / PaperMod テーマ / GitHub Pages + Cloudflare CDN
- リポジトリ: https://github.com/ko-508/errorlog
- Zenn: https://zenn.dev/errorlog

## 記事規格

記事規格の詳細は docs/article_spec.md を参照すること。ただし実際の生成挙動は各スクリプト内のシステムプロンプトが持つため、生成を変えたい場合は docs/article_spec.md ではなく該当スクリプトを確認すること。

## 行動の制約（厳守）

- push は指示があるまで行わない: コミットも同様。
- git add -A を使わない: 変更ファイルを個別に指定する。push の前に必ず git pull --rebase する。
- コンフリクトは自動解決しない: 止まって報告する。
- フォールバック禁止: エラーや想定外の入力に、フォールバック値・握りつぶし・症状を隠すガード・暗黙のリカバリを入れない。型やスキーマを緩めて通すこともしない。成功するか、原因・パラメータ・状況を含む明確なエラーで失敗するかのどちらか。直せないなら止まって報告する。
- 現在のデータで正しさを検証できないものは実装しない。
- フロントエンドと画面の変更は既存のデザインに合わせる: 新しい独立したスタイルを作らない。

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
