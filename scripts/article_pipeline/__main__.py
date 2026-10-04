"""Command-line interface for article pipeline P1."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import PipelineError
from .graph import PipelineGraph, StageContext, build_production_stages
from .intake import SLUG_RE, load_config, load_topic
from .locks import SlugLock, process_is_alive
from .state import StateFile, initial_state, utc_now
from .store import RunStore


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PipelineError(f"CLI 引数が不正です: {message}")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def config_path(root: Path) -> Path:
    return root / "config/openai_article_pipeline.yml"


def new_run_id(mode: str, slug: str) -> str:
    prefix = "cand" if mode == "candidate" else "cmp"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{slug}_{secrets.token_hex(2)}"


def _runtime(root: Path) -> tuple[dict, RunStore, PipelineGraph]:
    config = load_config(config_path(root))
    store = RunStore(root, Path(config["paths"]["run_root"]))
    store.ensure_gitignored()
    graph = PipelineGraph(build_production_stages())
    return config, store, graph


def _validate_topic_identity(state: dict) -> None:
    topic_path = Path(state["topic_source"])
    topic = load_topic(topic_path)
    if topic["slug"] != state["slug"]:
        raise PipelineError(
            "run 作成後に slug は変更できません。新しい run を作成してください: "
            f"run_id={state['run_id']}, fixed_slug={state['slug']!r}, "
            f"topic_slug={topic['slug']!r}, topic_path={topic_path}"
        )


def command_new(args: argparse.Namespace, root: Path) -> int:
    topic_path = Path(args.topic).resolve(strict=True)
    topic = load_topic(topic_path)
    run_id = new_run_id(args.mode, topic["slug"])
    config, store, graph = _runtime(root)
    lock = SlugLock(store, topic["slug"], run_id)
    lock.acquire()
    state_file = StateFile(store, run_id)
    state_created = False
    try:
        store.mkdir(Path("runs") / run_id, exclusive=True)
        state = initial_state(
            run_id=run_id,
            slug=topic["slug"],
            mode=args.mode,
            topic_source=topic_path,
            stage_names=graph.stage_names,
        )
        state["new_run_override"] = bool(args.new_run)
        state_file.write(state)
        state_created = True
        context = StageContext(root, store, run_id, config)
        graph.resume(context, state_file, through="S0_intake")
    except Exception as exc:
        if state_created:
            current = state_file.read()
            s0 = current["stages"]["S0_intake"]
            if s0["status"] in {"pending", "running"}:
                current = state_file.transition(
                    current,
                    "S0_intake",
                    "failed",
                    finished_at=utc_now(),
                    error=f"{type(exc).__name__}: {exc}",
                )
        raise
    finally:
        lock.release()
    print(f"run を作成しました: run_id={run_id}, slug={topic['slug']}, mode={args.mode}")
    print("S1 は未実装です（P2 以降）")
    return 0


def command_resume(args: argparse.Namespace, root: Path) -> int:
    config, store, graph = _runtime(root)
    state_file = StateFile(store, args.run)
    state = state_file.read()
    _validate_topic_identity(state)
    context = StageContext(root, store, args.run, config)
    with SlugLock(store, state["slug"], args.run):
        graph.resume(
            context,
            state_file,
            through="S0_intake",
            from_stage=args.from_stage,
            accept_modified=args.accept_modified or (),
        )
    print(f"S0 の再開判定が完了しました: run_id={args.run}")
    print("S1 は未実装です（P2 以降）")
    return 0


def command_status(args: argparse.Namespace, root: Path) -> int:
    config, store, graph = _runtime(root)
    state_file = StateFile(store, args.run)
    state = state_file.read()
    _validate_topic_identity(state)
    context = StageContext(root, store, args.run, config)
    graph.verify_status(context, state_file)
    print(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def command_unlock(args: argparse.Namespace, root: Path) -> int:
    if not SLUG_RE.fullmatch(args.slug):
        raise PipelineError(
            f"unlock の slug が不正です: slug={args.slug!r}, pattern={SLUG_RE.pattern}"
        )
    _config, store, _graph = _runtime(root)
    holder = SlugLock.read_holder(store, args.slug)
    displayed = {**holder, "process_alive": process_is_alive(holder.get("pid"))}
    print(json.dumps(displayed, ensure_ascii=False, sort_keys=True, indent=2))
    if not args.yes:
        print("--yes がないためロックは削除していません")
        return 0
    store.remove(Path("locks") / f"{args.slug}.lock")
    print(f"ロックを削除しました: slug={args.slug}")
    return 0


def build_parser() -> Parser:
    parser = Parser(prog="python -m scripts.article_pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=Parser)

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("--topic", required=True)
    new_parser.add_argument("--mode", choices=("candidate", "comparison"), required=True)
    new_parser.add_argument("--new-run", action="store_true")

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--run", required=True)
    resume_parser.add_argument("--from", dest="from_stage")
    resume_parser.add_argument("--accept-modified", action="append")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run", required=True)

    unlock_parser = subparsers.add_parser("unlock")
    unlock_parser.add_argument("--slug", required=True)
    unlock_parser.add_argument("--yes", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        root = repo_root()
        handlers = {
            "new": command_new,
            "resume": command_resume,
            "status": command_status,
            "unlock": command_unlock,
        }
        return handlers[args.command](args, root)
    except (PipelineError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
