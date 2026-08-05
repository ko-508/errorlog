# Anthropic Article Generation Rules

このファイルは Anthropic API で ErrorLog 記事を生成するときの追加ルールです。
基本方針は `docs/article_spec.md` を正とし、このファイルでは API 生成時に守る
出力契約だけを固定します。

## 出力契約

- Markdown 記事全体を出力する。
- 先頭に Hugo front matter を含める。
- front matter の `draft` は必ず `true` にする。
- H1 見出しは本文に含めない。
- 本文末尾に ErrorLog の免責事項を含める。
- 公式文書、公式 API、実装コード、公式 Issue を優先する。
- 根拠を確認できない数値、設定名、レスポンス例、コマンドを作らない。
- 危険な回避策を主解決策として推奨しない。
- 読者が原因を切り分けられる確認方法を必ず書く。
- 既存記事と同じ範囲を扱う場合は、この記事が扱う境界を本文で明確にする。
- 別言語の混入、文字化け、半角カタカナの混入を避ける。
- API キー、トークン、秘密鍵、パスワードは必ず `<your-xxx>` 形式のプレースホルダーにする。

## 必須 front matter

```yaml
---
title: "..."
date: YYYY-MM-DD
draft: true
description: "..."
tags: ["..."]
errorCode: "..."
urgency: "medium"
service: "..."
error_type: "..."
components: []
related_services: []
---
```

## 必須本文要素

RunContainerError のリライトで採用した次の章立てを標準フォーマットにする。

- 冒頭まとめ
- エラーの概要
- まず最初に見るべき切り分け軸
- よくある原因と解決手順
- 補足：似ているが別のもの
- 危険な対応を行う前の確認
- 切り分けの順序
- 確認コマンド集
- 免責事項

Editor's Note は、関連する仕様変更や障害の歴史が理解に役立ち、かつ根拠 URL を
確認できる場合だけ追加する。根拠不足なら追加しない。
