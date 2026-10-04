"""Read-only index of existing Hugo posts used by S0."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import PipelineError
from .store import canonical_json_bytes, sha256_bytes

try:
    import yaml
except ImportError:
    yaml = None


HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)


def _load_frontmatter(path: Path, text: str) -> dict[str, Any]:
    if yaml is None:
        raise PipelineError(
            f"PyYAML が必要です: path={path}, install_command='pip install pyyaml'"
        )
    if not text.startswith("---\n"):
        raise PipelineError(f"記事の frontmatter 開始行がありません: path={path}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise PipelineError(f"記事の frontmatter 終了行がありません: path={path}")
    raw = text[4:end]
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PipelineError(f"記事の frontmatter を解析できません: path={path}, error={exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(
            f"記事の frontmatter が object ではありません: path={path}, type={type(value).__name__}"
        )
    return value


def _string_list(value: Any, *, path: Path, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise PipelineError(
        f"記事索引のフィールド形式が不正です: path={path}, field={field}, value={value!r}"
    )


def build_posts_index(posts_dir: Path) -> list[dict[str, Any]]:
    if not posts_dir.is_dir():
        raise PipelineError(f"記事ディレクトリがありません: path={posts_dir}")
    index: list[dict[str, Any]] = []
    for path in sorted(posts_dir.glob("*.md"), key=lambda item: item.name):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PipelineError(f"記事を読めません: path={path}, error={exc}") from exc
        frontmatter = _load_frontmatter(path, text)
        headings = [match.group(2).strip() for match in HEADING_RE.finditer(text)]
        title = frontmatter.get("title", "")
        error_code = frontmatter.get("errorCode", "")
        if not isinstance(title, str) or not isinstance(error_code, str):
            raise PipelineError(
                f"記事索引の文字列フィールドが不正です: path={path}, "
                f"title_type={type(title).__name__}, errorCode_type={type(error_code).__name__}"
            )
        index.append(
            {
                "slug": path.stem,
                "path": path.relative_to(posts_dir.parent.parent).as_posix(),
                "title": title,
                "errorCode": error_code,
                "tags": _string_list(frontmatter.get("tags"), path=path, field="tags"),
                "top_queries": _string_list(
                    frontmatter.get("top_queries"), path=path, field="top_queries"
                ),
                "headings": headings,
            }
        )
    return index


def posts_index_hash(index: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json_bytes(index))
