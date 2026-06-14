---
title: "Hugo PaperMod で datePublished が 0001-01-01 になるバグ：原因と解決策"
date: 2026-05-29
description: "Hugo PaperMod の構造化データで datePublished が 0001-01-01 になる原因と、テンプレートオーバーライドによる修正方法を解説します。"
tags: ["Hugo"]
service: "Hugo"
components: ["PaperMod"]
related_services: ["Google", "JSON-LD", "Git", "GitHub Actions"]
---

## エラーの概要

Hugo（PaperMod テーマ）で構築したサイトの構造化データ（[JSON](/glossary/json/)-LD）を Google のリッチリザルトテストで確認したところ、`datePublished` と `dateModified` に `0001-01-01T00:00:00Z` という明らかに誤った日付が出力されていた。記事のフロントマターには正しく `date: 2026-05-29` を設定していたにもかかわらず、構造化データには Go の「ゼロ値」に相当する日付が混入していた。

---

## 実際のエラー出力例

Google のリッチリザルトテストおよびページソースで確認された [JSON](/glossary/json/)-LD の内容：

```json
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": "Docker の 404 エラー：原因と解決策",
  "datePublished": 0001-01-01 00:00:00 +0000 UTC,
  "dateModified": 0001-01-01 00:00:00 +0000 UTC,
  "publisher": {
    "@type": "Organization",
    "name": "ErrorLog"
  }
}
```

これは有効な [JSON](/glossary/json/) ですらなく、Google ボットがパースに失敗する状態だった。

---

## 原因

PaperMod テーマの `themes/PaperMod/layouts/_partials/templates/schema_json.html` における日付出力の実装が問題だった。

**問題のあったテンプレートコード（Before）：**

```html
"datePublished": {{ .PublishDate }},
"dateModified": {{ .Lastmod }},
```

Hugo テンプレートで `{{ .PublishDate }}` を素のまま展開すると、Go の `time.Time` 型がデフォルト形式でシリアライズされる。この形式は `0001-01-01 00:00:00 +0000 UTC` のような文字列になり、[JSON](/glossary/json/) として無効な出力になる。

さらに `.PublishDate` はフロントマターに `publishDate` を明示しない場合にゼロ値（`0001-01-01`）になることがある（Hugo のバージョンや設定により挙動が異なる）。`lastmod` も同様で、フロントマターに未設定の場合にゼロ値が返る。

---

## 解決手順

**解決策（テンプレートオーバーライドで日付フォーマットを修正）：**

### 1. テーマのテンプレートをオーバーライドする

Hugo はテーマのテンプレートを `layouts/` 以下の同名ファイルで上書きできる。テーマファイルを直接編集すると git submodule 更新時に差分が消えるため、必ずオーバーライドで対応する。

```bash
mkdir -p layouts/_partials/templates
cp themes/PaperMod/layouts/_partials/templates/schema_json.html \
   layouts/_partials/templates/schema_json.html
```

### 2. 日付出力を修正する（After）

```html
{{- $pubDate := .Date }}
{{- $modDate := .Lastmod }}
{{- if .Lastmod.IsZero }}{{- $modDate = .Date }}{{- end }}

"datePublished": {{ $pubDate.UTC.Format "2006-01-02T15:04:05Z" | jsonify }},
"dateModified": {{ $modDate.UTC.Format "2006-01-02T15:04:05Z" | jsonify }},
```

**修正のポイント：**

- `.PublishDate` の代わりに `.Date` を使う（フロントマターの `date:` フィールドを確実に参照する）
- `.Lastmod.IsZero` で未設定チェックをして、ゼロ値の場合は `.Date` にフォールバックする
- `jsonify` フィルタで文字列として正しくクォートする
- `.UTC.Format "2006-01-02T15:04:05Z"` で ISO 8601 フルフォーマットに変換する（Go の時刻フォーマットは参照日時 `2006-01-02T15:04:05Z07:00` を使う点に注意）

### 3. 出力結果の確認

修正後の [JSON](/glossary/json/)-LD：

```json
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": "Docker の 404 エラー：原因と解決策",
  "datePublished": "2026-05-29T00:00:00Z",
  "dateModified": "2026-05-29T00:00:00Z",
  "publisher": {
    "@type": "Organization",
    "name": "ErrorLog"
  }
}
```

有効な ISO 8601 形式で出力されるようになった。

---

## Hugo 固有の注意点

### `lastmod` の自動設定

`hugo.toml`（または `config.yaml`）に以下を設定すると、Hugo がファイルの git [コミット](/glossary/コミット/)日時を `lastmod` として自動設定する：

```toml
[frontmatter]
  lastmod = [":git", "lastmod", ":fileModTime", ":default"]
```

ただし GitHub Actions 環境では `actions/checkout` がデフォルトでシャロークローンを行うため、git の履歴に基づく日時が正しく取得できないことがある。その場合は `fetch-depth: 0` を指定するか、フロントマターに明示的に `lastmod:` を書く。

### PaperMod のバージョンと `schema_json.html` の仕様変更

PaperMod v8 以降、`schema_json.html` の構造が変更されている場合がある。テーマを更新した際はオーバーライドファイルとの差分を確認すること。

```bash
diff themes/PaperMod/layouts/_partials/templates/schema_json.html \
     layouts/_partials/templates/schema_json.html
```

---

## それでも解決しない場合

- [Google リッチリザルトテスト](https://search.google.com/test/rich-results) でページの URL を直接[テスト](/glossary/テスト/)して、構造化データのパースエラーを確認する
- Hugo の `hugo server` でローカルビルドし、ページのソースを直接確認する
- PaperMod の [GitHub Issues](https://github.com/adityatelange/hugo-PaperMod/issues) で同様の報告を検索する

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
