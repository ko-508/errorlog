"""ユニットテスト: lint_articles.py の各ルール。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lint_articles import (
    body_char_count,
    check_a1,
    check_a3,
    check_a4,
    check_a5,
    check_a6,
    check_b1,
    check_b2,
    check_b3,
    check_d1_d2,
    classify_domain,
    lint_article,
    split_frontmatter,
)

# ── 共通フィクスチャ ──────────────────────────────────────────────────────────

VALID_BODY = """\
## エラーの概要

Nginx で 500 エラーが発生した場合、サーバー内部で問題が起きています。

## 実際のエラーメッセージ例

```bash
$ curl https://example.com
HTTP/1.1 500 Internal Server Error
```

## よくある原因と解決手順

### 原因1: 設定ミス

**Before:**

```nginx
server { proxy_pass http://bad_host; }
```

**After:**

```nginx
server { proxy_pass http://127.0.0.1:8080; }
```

## ツール固有の注意点

Nginx のバージョンによって挙動が異なります。

## それでも解決しない場合

公式ドキュメント(https://nginx.org/docs)を参照してください。

---
*免責事項: 本記事は情報提供のみを目的としています。*
"""

VALID_FM = {
    "title": "Nginx の 500 エラー：原因と解決策",
    "errorCode": "500",
    "tags": '["Nginx"]',
    "description": "Nginx で 500 エラーが発生する原因と解決策を解説します。",
}

# ── body_char_count ───────────────────────────────────────────────────────────

def test_body_char_count_excludes_code_blocks():
    body = "本文テキスト\n```python\ncode here\n```\n追加テキスト"
    count = body_char_count(body)
    assert "本文テキスト" in "本文テキスト追加テキスト"
    # コードブロックの 'code here' が含まれないことを確認
    assert count < body_char_count("本文テキスト\ncode here\n追加テキスト")


def test_body_char_count_excludes_urls():
    body = "テキスト https://example.com/long/path 末尾"
    count = body_char_count(body)
    assert count <= len("テキスト末尾")


def test_body_char_count_excludes_md_link_urls():
    """[テキスト](url) → テキストのみカウント。"""
    body = "[クリックここ](https://example.com/very/long/path)"
    count = body_char_count(body)
    assert count == len("クリックここ")


def test_body_char_count_1500_boundary():
    """1500文字ちょうどは基準を満たす。"""
    body = "あ" * 1500
    assert body_char_count(body) == 1500


def test_body_char_count_strips_md_symbols():
    body = "## 見出し\n**太字**\n`インライン`"
    count = body_char_count(body)
    # MD記号を除いて「見出し太字インライン」が残る
    raw = "見出し太字インライン"
    assert count == len(raw)


# ── A1 必須セクション ─────────────────────────────────────────────────────────

def test_a1_pass_all_sections_present():
    assert check_a1(VALID_BODY) == []


def test_a1_fail_missing_section():
    body = VALID_BODY.replace("## 実際のエラーメッセージ例", "## その他")
    issues = check_a1(body)
    assert any("エラーメッセージ例" in d for _, d in issues)


def test_a1_accepts_variant_headings():
    """「よくある原因と解決手順」→「原因と解決手順」に変えても合格。"""
    body = VALID_BODY.replace("## よくある原因と解決手順", "## 原因と解決手順")
    assert check_a1(body) == []


def test_a1_accepts_tool_specific_without_prefix():
    """「ツール固有の注意点」→「注意点」でも合格。"""
    body = VALID_BODY.replace("## ツール固有の注意点", "## 注意点")
    assert check_a1(body) == []


def test_a1_all_missing():
    issues = check_a1("## 関係ないセクション\n本文のみ")
    assert len(issues) == 5


# ── A3 文字数 ─────────────────────────────────────────────────────────────────

def test_a3_pass_sufficient_chars():
    body = "あ" * 1500 + "\n## エラーの概要\n"
    assert check_a3(body) == []


def test_a3_fail_insufficient_chars():
    issues = check_a3("## 概要\n短い本文")
    assert len(issues) == 1
    assert "A3" == issues[0][0]


def test_a3_fail_code_heavy_body():
    """コードブロックが多くても実文字数が足りなければ FAIL。"""
    code_only = "```python\n" + "x = 1\n" * 200 + "```\n"
    issues = check_a3(code_only)
    assert len(issues) == 1


# ── A4 コードブロック言語名 ───────────────────────────────────────────────────

def test_a4_pass_all_named():
    assert check_a4(VALID_BODY) == []


def test_a4_warn_unnamed_block():
    body = VALID_BODY + "\n```\nunnamed code\n```\n"
    issues = check_a4(body)
    assert any("A4" == r for r, _ in issues)


# ── A5 プレースホルダー形式 ───────────────────────────────────────────────────

def test_a5_pass_correct_placeholder():
    body = "設定値は <your-api-key> を使用します。"
    assert check_a5(body) == []


def test_a5_warn_uppercase_placeholder():
    body = "export API_KEY=YOUR_API_KEY"
    issues = check_a5(body)
    assert any("A5" == r for r, _ in issues)


# ── A6 フロントマター ─────────────────────────────────────────────────────────

def test_a6_pass_valid_frontmatter():
    assert check_a6(VALID_FM, VALID_BODY) == []


def test_a6_fail_missing_error_code():
    fm = {**VALID_FM}
    del fm["errorCode"]
    issues = check_a6(fm, VALID_BODY)
    assert any("errorCode" in d for _, d in issues)


def test_a6_fail_missing_tags():
    fm = {**VALID_FM, "tags": "[]"}
    issues = check_a6(fm, VALID_BODY)
    assert any("tags" in d for _, d in issues)


def test_a6_fail_description_double_period():
    fm = {**VALID_FM, "description": "概要です。。"}
    issues = check_a6(fm, VALID_BODY)
    assert any("。。" in d for _, d in issues)


def test_a6_fail_missing_title():
    fm = {**VALID_FM, "title": ""}
    issues = check_a6(fm, VALID_BODY)
    assert any("title" in d for _, d in issues)


# ── B1 エラーパターン ─────────────────────────────────────────────────────────

def test_b1_pass_http_status_in_code():
    assert check_b1(VALID_BODY) == []


def test_b1_pass_exception_name():
    body = """\
## 実際のエラーメッセージ例

```python
raise FileNotFoundError("file missing")
```

## よくある原因と解決手順
"""
    assert check_b1(body) == []


def test_b1_pass_exit_code():
    body = """\
## 実際のエラーメッセージ例

```bash
Process exited with exit code 1
```
"""
    assert check_b1(body) == []


def test_b1_pass_posix_errno():
    body = """\
## 実際のエラーメッセージ例

```c
if (errno == EACCES) { ... }
```
"""
    assert check_b1(body) == []


def test_b1_pass_signal():
    body = """\
## 実際のエラーメッセージ例

```bash
Killed by SIGKILL
```
"""
    assert check_b1(body) == []


def test_b1_fail_no_error_pattern():
    body = """\
## 実際のエラーメッセージ例

```bash
hello world
this is fine
```
"""
    issues = check_b1(body)
    assert any("B1" == r for r, _ in issues)


def test_b1_no_code_block_in_section():
    body = """\
## 実際のエラーメッセージ例

コードブロックがなく、テキストだけです。

## よくある原因と解決手順
"""
    issues = check_b1(body)
    assert any("B1" == r for r, _ in issues)


def test_b1_skip_when_section_missing():
    """エラーメッセージ例セクションなしなら B1 を出力しない（A1 が先に検出）。"""
    body = "## 別のセクション\n\n本文\n"
    assert check_b1(body) == []


# ── B2 不適格マーカー ─────────────────────────────────────────────────────────

def test_b2_fail_http_status_not_related():
    body = "この問題はHTTPステータスコードに直結するものではなく、設計の問題です。"
    issues = check_b2(body)
    assert any("B2" == r for r, _ in issues)


def test_b2_fail_soft_error_framing():
    body = "この状況は「エラー」としてエラーとして捉えることができます。"
    issues = check_b2(body)
    assert any("B2" == r for r, _ in issues)


def test_b2_fail_no_specific_error_code():
    body = "これは特定のHTTPエラーコードを直接扱うものではありません。"
    issues = check_b2(body)
    assert any("B2" == r for r, _ in issues)


def test_b2_fail_indirect_error_message():
    body = "問題は直接的なエラーメッセージとして現れることもあれば間接的に現れることもある。"
    issues = check_b2(body)
    assert any("B2" == r for r, _ in issues)


def test_b2_pass_normal_body():
    """通常のエラー記事本文では B2 が出ない。"""
    assert check_b2(VALID_BODY) == []


# ── D1/D2 URL 分類 ────────────────────────────────────────────────────────────

def test_classify_official():
    assert classify_domain("https://docs.docker.com/engine/reference/run/") == "official"
    assert classify_domain("https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500") == "official"


def test_classify_semi_official():
    assert classify_domain("https://www.ietf.org/rfc/rfc2616.txt") == "semi_official"


def test_classify_community():
    assert classify_domain("https://stackoverflow.com/questions/12345") == "community"


def test_classify_personal():
    assert classify_domain("https://qiita.com/user/items/xxx") == "personal"
    assert classify_domain("https://zenn.dev/author/articles/xxx") == "personal"


def test_classify_grounding_redirect():
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xxx"
    assert classify_domain(url) == "grounding_redirect"


def test_d2_warn_when_grounding_over_50_percent():
    body = (
        "[a](https://vertexaisearch.cloud.google.com/a) "
        "[b](https://vertexaisearch.cloud.google.com/b) "
        "[c](https://stackoverflow.com/c)"
    )
    _, issues = check_d1_d2(body)
    assert any("D2" == r for r, _ in issues)


def test_d2_no_warn_when_grounding_under_50_percent():
    body = (
        "[a](https://vertexaisearch.cloud.google.com/a) "
        "[b](https://stackoverflow.com/b) "
        "[c](https://docs.docker.com/c)"
    )
    _, issues = check_d1_d2(body)
    assert all("D2" != r for r, _ in issues)


# ── lint_article 統合テスト ───────────────────────────────────────────────────

def test_lint_article_clean(tmp_path):
    content = f"""---
title: "Nginx の 500 エラー：原因と解決策"
description: "Nginx で 500 エラーが発生する原因と解決策を解説します。"
tags: ["Nginx"]
errorCode: "500"
---
{VALID_BODY}
{'あ' * 1500}
"""
    p = tmp_path / "nginx_500.md"
    p.write_text(content, encoding="utf-8")
    result = lint_article(p)
    assert result["fails"] == []


def test_lint_article_missing_errorcode(tmp_path):
    content = f"""---
title: "テスト記事"
description: "テスト。"
tags: ["Tool"]
---
{VALID_BODY}
{'あ' * 1500}
"""
    p = tmp_path / "test.md"
    p.write_text(content, encoding="utf-8")
    result = lint_article(p)
    fail_rules = {f["rule"] for f in result["fails"]}
    assert "A6" in fail_rules
