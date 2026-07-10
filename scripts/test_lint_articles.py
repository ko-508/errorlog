"""ユニットテスト: lint_articles.py の各ルール。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lint_articles import (
    ARTICLE_CATEGORY_ERROR,
    ARTICLE_CATEGORY_NON_ERROR,
    check_a4,
    check_a5,
    check_a6,
    check_a8,
    check_b2,
    check_d1_d2,
    check_secret_token,
    classify_article,
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


def test_lint_article_missing_errorcode_on_error_article(tmp_path):
    """エラー記事（_500 ファイル名）で errorCode 欠落 → A6 FAIL。"""
    content = f"""---
title: "テスト記事"
description: "テスト。"
tags: ["Tool"]
---
{VALID_BODY}
{'あ' * 1500}
"""
    p = tmp_path / "test_500.md"
    p.write_text(content, encoding="utf-8")
    result = lint_article(p)
    fail_rules = {f["rule"] for f in result["fails"]}
    assert "A6" in fail_rules
    assert result["category"] == ARTICLE_CATEGORY_ERROR


def test_lint_article_non_error_article_skips_errorcode(tmp_path):
    """規格外ページ（errorCode なし・数字コードなし）は A6 で errorCode を要求しない。"""
    content = f"""---
title: "ツール紹介"
description: "ツールの紹介です。"
tags: ["Tool"]
---
{VALID_BODY}
{'あ' * 1500}
"""
    p = tmp_path / "tool_foo.md"
    p.write_text(content, encoding="utf-8")
    result = lint_article(p)
    assert result["category"] == ARTICLE_CATEGORY_NON_ERROR
    # A1/B1 は skipped なので fails に含まれない
    fail_rules = {f["rule"] for f in result["fails"]}
    assert "A1" not in fail_rules
    assert "B1" not in fail_rules
    assert "A6" not in fail_rules  # tags/title は揃っているので A6 も出ない


def test_classify_article_by_filename(tmp_path):
    """ファイル名に 3桁コードがあれば errorCode FM なしでもエラー記事扱い。"""
    p = tmp_path / "nginx_404.md"
    p.write_text("---\ntitle: t\n---\nbody", encoding="utf-8")
    from lint_articles import classify_article, split_frontmatter
    fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
    assert classify_article(p, fm) == ARTICLE_CATEGORY_ERROR


def test_classify_article_non_error(tmp_path):
    """tool_ 記事・数字コードなし・auto_日付形式は non_error_article。"""
    for stem in (
        "tool_docker_compose",
        "hugo_papermod_schema_date",
        "auto_2026-06-10_from-500-to-50-000-concurrent-users",
        "auto_2026-06-12_cómo-solucionar-docker-run-con-exit-code-1",
    ):
        p = tmp_path / f"{stem}.md"
        p.write_text("---\ntitle: t\n---\nbody", encoding="utf-8")
        from lint_articles import classify_article, split_frontmatter
        fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
        assert classify_article(p, fm) == ARTICLE_CATEGORY_NON_ERROR, stem



# ── A8 冒頭まとめ ─────────────────────────────────────────────────────────────

def test_a8_pass_with_conclusion_frontmatter():
    assert check_a8({"conclusion": "要点のまとめ。"}, "## 概要\n本文") == []


def test_a8_pass_with_bluf_heading_in_body():
    body = "## 冒頭まとめ\n\n要点。\n\n## エラーの概要\n本文"
    assert check_a8({}, body) == []


def test_a8_warn_when_both_missing():
    issues = check_a8({}, "## エラーの概要\n本文")
    assert issues and issues[0][0] == "A8"


def test_a8_ignores_bluf_inside_code_block():
    body = "```md\n## 冒頭まとめ\n```\n\n## エラーの概要\n本文"
    issues = check_a8({}, body)
    assert issues and issues[0][0] == "A8"


# ── C1 ルールID（ブロックゲート照合の前提） ──────────────────────────────────

def test_c1_rule_id_is_plain_c1():
    """秘密鍵検出のルールIDは接頭辞なしの "C1"（daily_publish のゲート照合前提）。"""
    body = "```bash\nexport TOKEN=xoxb-9f8g7h6j5k4l3m2n1\n```"
    issues = check_secret_token(body)
    assert issues and all(r == "C1" for r, _ in issues)