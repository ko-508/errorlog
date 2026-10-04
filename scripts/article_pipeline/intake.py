"""S0 topic validation, mode gates, comparison capture, and deduplication."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from . import PipelineError
from .posts_index import build_posts_index, posts_index_hash
from .store import canonical_json_bytes, sha256_bytes, sha256_file

try:
    import yaml
except ImportError:
    yaml = None


SLUG_RE = re.compile(r"^[a-z0-9_+\-]+$")
ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
ALLOWED_TOPIC_KEYS = {
    "slug",
    "service",
    "error_text",
    "error_code",
    "target_versions",
    "hint_urls",
    "notes",
}
REQUIRED_TOPIC_KEYS = {"slug", "service", "error_text", "error_code"}


if yaml is not None:
    class UniqueKeyLoader(yaml.SafeLoader):
        pass


    def _construct_unique_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key: {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping


    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        _construct_unique_mapping,
    )


def load_strict_yaml(path: Path) -> Any:
    if yaml is None:
        raise PipelineError(
            f"PyYAML が必要です: path={path}, install_command='pip install pyyaml'"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PipelineError(f"YAML ファイルを読めません: path={path}, error={exc}") from exc
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise PipelineError(f"YAML を解析できません: path={path}, error={exc}") from exc


def load_topic(path: Path) -> dict[str, Any]:
    value = load_strict_yaml(path)
    if not isinstance(value, dict):
        raise PipelineError(
            f"topic.yml のルートが object ではありません: path={path}, type={type(value).__name__}"
        )
    unknown = sorted(set(value) - ALLOWED_TOPIC_KEYS)
    missing = sorted(REQUIRED_TOPIC_KEYS - set(value))
    if unknown:
        raise PipelineError(f"topic.yml に未知のキーがあります: path={path}, keys={unknown}")
    if missing:
        raise PipelineError(f"topic.yml に必須キーがありません: path={path}, keys={missing}")
    for field in REQUIRED_TOPIC_KEYS:
        if not isinstance(value[field], str) or not value[field]:
            raise PipelineError(
                f"topic.yml の必須値が空または文字列ではありません: path={path}, field={field}, value={value[field]!r}"
            )
    if not SLUG_RE.fullmatch(value["slug"]):
        raise PipelineError(
            f"topic.yml の slug が不正です: path={path}, slug={value['slug']!r}, pattern={SLUG_RE.pattern}"
        )
    if "hint_urls" in value:
        urls = value["hint_urls"]
        if not isinstance(urls, list) or not all(
            isinstance(url, str) and url.startswith("https://") for url in urls
        ):
            raise PipelineError(
                f"topic.yml の hint_urls は https:// 文字列の配列でなければなりません: path={path}, value={urls!r}"
            )
    if "notes" in value and not isinstance(value["notes"], str):
        raise PipelineError(
            f"topic.yml の notes は文字列でなければなりません: path={path}, value={value['notes']!r}"
        )
    if "target_versions" in value and not isinstance(value["target_versions"], list):
        raise PipelineError(
            f"topic.yml の target_versions は配列でなければなりません: path={path}, value={value['target_versions']!r}"
        )
    return value


def load_config(path: Path) -> dict[str, Any]:
    value = load_strict_yaml(path)
    if not isinstance(value, dict):
        raise PipelineError(f"設定のルートが object ではありません: path={path}")
    if set(value) != {"paths", "intake"}:
        raise PipelineError(
            f"設定のトップレベルキーが不正です: path={path}, actual={sorted(value)}, expected=['intake', 'paths']"
        )
    paths = value["paths"]
    intake = value["intake"]
    expected_paths = {"run_root", "posts_dir", "drafts_dir"}
    expected_intake = {"overlap_threshold", "overlap_top_n"}
    if not isinstance(paths, dict) or set(paths) != expected_paths:
        raise PipelineError(
            f"設定 paths のキーが不正です: path={path}, actual={sorted(paths) if isinstance(paths, dict) else type(paths).__name__}, expected={sorted(expected_paths)}"
        )
    if not isinstance(intake, dict) or set(intake) != expected_intake:
        raise PipelineError(
            f"設定 intake のキーが不正です: path={path}, actual={sorted(intake) if isinstance(intake, dict) else type(intake).__name__}, expected={sorted(expected_intake)}"
        )
    if paths["run_root"] != "run/article_pipeline":
        raise PipelineError(
            f"設定 paths.run_root は固定です: path={path}, actual={paths['run_root']!r}, expected='run/article_pipeline'"
        )
    if not all(isinstance(paths[key], str) and paths[key] for key in expected_paths):
        raise PipelineError(f"設定 paths の値は空でない文字列が必要です: path={path}, value={paths!r}")
    threshold = intake["overlap_threshold"]
    top_n = intake["overlap_top_n"]
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0 <= threshold <= 1:
        raise PipelineError(
            f"overlap_threshold は 0 以上 1 以下の数値が必要です: path={path}, value={threshold!r}"
        )
    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n <= 0:
        raise PipelineError(
            f"overlap_top_n は正の整数が必要です: path={path}, value={top_n!r}"
        )
    return value


def _git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise PipelineError(f"git を実行できません: repo={repo_root}, args={args}, error={exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "出力なし"
        raise PipelineError(
            f"git コマンドが失敗しました: repo={repo_root}, args={args}, returncode={result.returncode}, detail={detail}"
        )
    return result.stdout.strip()


def comparison_target(repo_root: Path, post_path: Path) -> dict[str, str]:
    relative = post_path.relative_to(repo_root).as_posix()
    return {
        "path": relative,
        "repo_head": _git(repo_root, "rev-parse", "HEAD"),
        "blob_sha": _git(repo_root, "hash-object", relative),
    }


def _tokens(value: str) -> set[str]:
    ascii_tokens = {
        token.lower() for token in ASCII_TOKEN_RE.findall(value) if len(token) >= 2
    }
    unicode_runs: list[str] = []
    current: list[str] = []
    for char in value:
        if ord(char) > 127 and (char.isalnum() or char == "_"):
            current.append(char)
        elif current:
            unicode_runs.append("".join(current))
            current = []
    if current:
        unicode_runs.append("".join(current))
    bigrams = {
        run[index : index + 2]
        for run in unicode_runs
        for index in range(len(run) - 1)
    }
    return ascii_tokens | bigrams


def _topic_fields(topic: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "slug": _tokens(topic["slug"]),
        "service": _tokens(topic["service"]),
        "error_text": _tokens(topic["error_text"]),
        "error_code": _tokens(topic["error_code"]),
    }


def _post_fields(post: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "slug": _tokens(post["slug"]),
        "title": _tokens(post["title"]),
        "errorCode": _tokens(post["errorCode"]),
        "tags": _tokens(" ".join(post["tags"])),
        "top_queries": _tokens(" ".join(post["top_queries"])),
        "headings": _tokens(" ".join(post["headings"])),
    }


def rank_overlaps(
    topic: dict[str, Any],
    posts: list[dict[str, Any]],
    *,
    threshold: float,
    top_n: int,
) -> list[dict[str, Any]]:
    topic_fields = _topic_fields(topic)
    topic_tokens = set().union(*topic_fields.values())
    ranked: list[dict[str, Any]] = []
    for post in posts:
        post_fields = _post_fields(post)
        post_tokens = set().union(*post_fields.values())
        union = topic_tokens | post_tokens
        score = len(topic_tokens & post_tokens) / len(union) if union else 0.0
        matched = sorted(
            post_name
            for post_name, tokens in post_fields.items()
            if tokens & topic_tokens
        )
        ranked.append(
            {
                "slug": post["slug"],
                "path": post["path"],
                "score": round(score, 12),
                "matched_fields": matched,
                "possible_overlap": score >= threshold,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["slug"]))
    return ranked[:top_n]


def _ready_candidate_runs(run_root: Path, slug: str, current_run_id: str) -> list[str]:
    runs_dir = run_root / "runs"
    if not runs_dir.exists():
        return []
    ready: list[str] = []
    for state_path in sorted(runs_dir.glob("*/state.json")):
        if state_path.parent.name == current_run_id:
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PipelineError(
                f"既存 run の state.json を読めません: path={state_path}, error={exc}"
            ) from exc
        if (
            state.get("slug") == slug
            and state.get("mode") == "candidate"
            and state.get("verdict") in {"ready_for_human_review", "approved", "published"}
        ):
            ready.append(state_path.parent.name)
    return ready


def prepare_intake(
    *,
    repo_root: Path,
    config: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    topic_path = Path(state["topic_source"])
    topic = load_topic(topic_path)
    if topic["slug"] != state["slug"]:
        raise PipelineError(
            "run 作成後に slug は変更できません。新しい run を作成してください: "
            f"run_id={state['run_id']}, fixed_slug={state['slug']!r}, "
            f"topic_slug={topic['slug']!r}, topic_path={topic_path}"
        )
    mode = state["mode"]
    paths = config["paths"]
    posts_dir = (repo_root / paths["posts_dir"]).resolve(strict=False)
    drafts_dir = (repo_root / paths["drafts_dir"]).resolve(strict=False)
    run_root = (repo_root / paths["run_root"]).resolve(strict=False)
    post_path = posts_dir / f"{state['slug']}.md"
    draft_path = drafts_dir / f"{state['slug']}.md"
    post_exists = post_path.is_file()
    draft_exists = draft_path.is_file()
    target: dict[str, str] | None = None
    if mode == "candidate":
        if post_exists:
            raise PipelineError(
                f"candidate の既存記事があるため停止します: slug={state['slug']}, path={post_path}"
            )
        if draft_exists:
            raise PipelineError(
                f"candidate の人手下書きと衝突するため停止します: slug={state['slug']}, path={draft_path}"
            )
        ready = _ready_candidate_runs(run_root, state["slug"], state["run_id"])
        if ready and not state.get("new_run_override", False):
            raise PipelineError(
                "ready_for_human_review 以上の candidate run が残っています。"
                f"新しい run が必要なら --new-run を指定してください: slug={state['slug']}, runs={ready}"
            )
    elif mode == "comparison":
        if not post_exists:
            raise PipelineError(
                f"comparison の比較対象記事がありません: slug={state['slug']}, path={post_path}"
            )
        target = comparison_target(repo_root, post_path)
    else:
        raise PipelineError(f"state.json の mode が不正です: run_id={state['run_id']}, mode={mode}")

    posts = build_posts_index(posts_dir)
    excluded: list[dict[str, str]] = []
    overlap_posts = posts
    if mode == "comparison":
        excluded = [
            {"slug": post["slug"], "path": post["path"]}
            for post in posts
            if post["slug"] == state["slug"]
        ]
        overlap_posts = [post for post in posts if post["slug"] != state["slug"]]
    intake_config = config["intake"]
    overlaps = rank_overlaps(
        topic,
        overlap_posts,
        threshold=float(intake_config["overlap_threshold"]),
        top_n=intake_config["overlap_top_n"],
    )
    dedup_report = {
        "slug": state["slug"],
        "mode": mode,
        "overlap_threshold": intake_config["overlap_threshold"],
        "overlaps": overlaps,
        "excluded_for_comparison": excluded,
        "draft_exists": draft_exists,
    }
    input_parts: dict[str, Any] = {
        "topic": sha256_file(topic_path),
        "mode": mode,
        "posts_index": posts_index_hash(posts),
        "config.S0": sha256_bytes(canonical_json_bytes(intake_config)),
    }
    if target is not None:
        input_parts["comparison_blob_sha"] = target["blob_sha"]
    return {
        "topic": topic,
        "dedup_report": dedup_report,
        "comparison_target": target,
        "input_parts": input_parts,
    }
