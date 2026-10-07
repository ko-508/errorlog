"""Command-line interface for the resumable article pipeline."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from . import PipelineError
from .config import load_config
from .budget import BudgetLedger, BudgetLock, decimal_value, money, utc_now as budget_utc_now
from .graph import PipelineGraph, StageContext, build_production_stages
from .intake import SLUG_RE, load_topic
from .llm_calls import attempt_key
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


def _verify_budget_integrity(config: dict, store: RunStore) -> None:
    with BudgetLock(store, float(config["llm"]["budget_lock_wait_s"])):
        BudgetLedger(store, config).check(apply=False)


def command_new(args: argparse.Namespace, root: Path) -> int:
    topic_path = Path(args.topic).resolve(strict=True)
    topic = load_topic(topic_path)
    candidate_arg = getattr(args, "url_candidates", None)
    candidate_path = Path(candidate_arg).resolve(strict=True) if candidate_arg else None
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
            url_candidates_source=candidate_path,
        )
        state["new_run_override"] = bool(args.new_run)
        state_file.write(state)
        state_created = True
        context = StageContext(root, store, run_id, config)
        graph.resume(
            context,
            state_file,
            through="S1_plan" if candidate_path is not None else "S0_intake",
        )
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
    if candidate_path is None:
        print("URL 候補が未登録のため S0_intake で停止しました。attach-candidates で登録してください")
    else:
        print("S1_plan まで完了しました。S2 は resume --through S2_sources で明示して実行してください")
    return 0


def command_resume(args: argparse.Namespace, root: Path) -> int:
    config, store, graph = _runtime(root)
    state_file = StateFile(store, args.run)
    state = state_file.read()
    _validate_topic_identity(state)
    _verify_budget_integrity(config, store)
    context = StageContext(root, store, args.run, config)
    if hasattr(args, "through"):
        if args.through:
            through = args.through
        elif getattr(args, "refetch", None) is not None:
            through = "S2_sources"
        else:
            through = "S1_plan"
    else:
        through = "S0_intake"
    with SlugLock(store, state["slug"], args.run):
        graph.resume(
            context,
            state_file,
            through=through,
            from_stage=args.from_stage,
            accept_modified=args.accept_modified or (),
            refetch=getattr(args, "refetch", None),
            retry_unknown_llm_calls=getattr(args, "retry_unknown_llm_calls", False),
        )
    print(f"再開判定が完了しました: run_id={args.run}, through={through}")
    return 0


def command_attach_candidates(args: argparse.Namespace, root: Path) -> int:
    config, store, _graph = _runtime(root)
    del config
    state_file = StateFile(store, args.run)
    state = state_file.read()
    _validate_topic_identity(state)
    candidate_path = Path(args.file).resolve(strict=True)
    from .plan_manual import load_candidates

    topic = load_topic(Path(state["topic_source"]))
    runtime_config = load_config(config_path(root))
    load_candidates(
        candidate_path,
        hint_urls=topic.get("hint_urls", []),
        max_sources=runtime_config["acquire"]["max_sources"],
    )
    with SlugLock(store, state["slug"], args.run):
        current = state_file.read()
        if "url_candidates_source" in current:
            raise PipelineError(
                "URL 候補ファイルは1回だけ登録できます: "
                f"run_id={args.run}, current={current['url_candidates_source']}"
            )
        current["url_candidates_source"] = str(candidate_path)
        state_file.write(current)
    print(f"URL 候補ファイルを登録しました: run_id={args.run}, path={candidate_path}")
    return 0


def command_status(args: argparse.Namespace, root: Path) -> int:
    config, store, graph = _runtime(root)
    state_file = StateFile(store, args.run)
    state = state_file.read()
    _validate_topic_identity(state)
    _verify_budget_integrity(config, store)
    context = StageContext(root, store, args.run, config)
    state = graph.verify_status(context, state_file)
    print(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2))
    sufficiency_relative = context.artifact_relative("sufficiency.json")
    if store.exists(sufficiency_relative):
        sufficiency = store.read_json(sufficiency_relative)
        if isinstance(sufficiency, dict) and sufficiency.get("sufficient") is False:
            print(f"S4 には進めません: missing={sufficiency.get('missing')}")
    return 0


def command_claims(args: argparse.Namespace, root: Path) -> int:
    config, store, graph = _runtime(root)
    state_file = StateFile(store, args.run)
    state = graph.verify_status(StageContext(root, store, args.run, config), state_file)
    del state
    relative = Path("runs") / args.run / ("claims.json" if store.exists(Path("runs") / args.run / "claims.json") else "claims.extracted.json")
    document = store.read_json(relative)
    claims = document.get("claims") if isinstance(document, dict) else None
    if not isinstance(claims, list):
        raise PipelineError(f"主張一覧がありません: run_id={args.run}, path={relative}")
    if args.show is None:
        for claim in claims:
            print(f"{claim.get('claim_id')}\t{claim.get('kind')}\t{claim.get('status', 'extracted')}\t{_safe_display(str(claim.get('text', '')))}")
        return 0
    matches = [claim for claim in claims if claim.get("claim_id") == args.show]
    if len(matches) != 1:
        raise PipelineError(f"claim_id が見つからないか重複しています: claim_id={args.show}, count={len(matches)}")
    print(json.dumps(matches[0], ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _journal_records(store: RunStore, run_id: str | None = None) -> list[tuple[Path, dict]]:
    root = store.path("runs")
    if not root.exists():
        return []
    pattern = f"{run_id}/llm_journal/*/attempt-*.json" if run_id else "*/llm_journal/*/attempt-*.json"
    records = []
    for path in sorted(root.glob(pattern)):
        if path.name.endswith(".response.json"):
            continue
        value = store.read_json(path.relative_to(store.root))
        if not isinstance(value, dict) or value.get("schema") != "llm_attempt/v2":
            raise PipelineError(f"LLM ジャーナルが不正です: path={path}")
        records.append((path, value))
    return records


def command_llm_calls(args: argparse.Namespace, root: Path) -> int:
    _config, store, _graph = _runtime(root)
    for _path, record in _journal_records(store, args.run):
        if args.logical_key and record["logical_key"] != args.logical_key:
            continue
        print(
            f"{record['run_id']}\t{record['stage']}\t{record['logical_key']}\t"
            f"{record['attempt']}\t{record['state']}\t{record.get('actual_usd')}"
        )
    return 0


def command_llm_reconcile(args: argparse.Namespace, root: Path) -> int:
    if not args.note.strip():
        raise PipelineError("llm reconcile には空でない --note が必要です")
    actual = Decimal(0) if args.not_billed else decimal_value(args.actual_usd, label="actual_usd")
    config, store, _graph = _runtime(root)
    state = StateFile(store, args.run).read()
    with SlugLock(store, state["slug"], args.run):
        matches = [
            (path, record) for path, record in _journal_records(store, args.run)
            if record["logical_key"] == args.logical_key and record["attempt"] == args.attempt
        ]
        if len(matches) != 1:
            raise PipelineError(f"照合対象の試行が見つからないか重複しています: count={len(matches)}")
        path, record = matches[0]
        expected_attempt_key = attempt_key(record["logical_key"], record["attempt"])
        expected = {
            "run_id": args.run,
            "attempt_key": expected_attempt_key,
            "reservation_id": "rsv_" + expected_attempt_key,
            "settlement_id": "stl_" + expected_attempt_key,
        }
        differing = [key for key, value in expected.items() if record.get(key) != value]
        if path.parent.name != record["logical_key"]:
            differing.append("logical_key_path")
        if path.name != f"attempt-{record['attempt']}.json":
            differing.append("attempt_path")
        if differing:
            raise PipelineError(
                "試行の識別子が一致しません: "
                f"logical_key={args.logical_key}, attempt={args.attempt}, differing={differing}"
            )
        _verify_budget_integrity(config, store)
        rejected_unreconciled = (
            record["state"] == "rejected"
            and record.get("api_outcome") == "rejected"
            and record.get("billing_status") == "unreconciled"
            and record.get("actual_usd") is None
            and record.get("http_status") in {400, 401, 403, 404, 422, 429}
        )
        if record["state"] not in {"unknown_outcome", "reconciled"} and not rejected_unreconciled:
            raise PipelineError(f"照合待ちではない試行です: state={record['state']}")
        if record["state"] == "reconciled":
            if record.get("actual_usd") == money(actual) and record.get("reconciliation_note") == args.note:
                print(f"同じ照合が既に記録されています: logical_key={args.logical_key}, attempt={args.attempt}")
                return 0
            raise PipelineError(
                "同じ試行に内容の異なる照合を記録できません: "
                f"logical_key={args.logical_key}, attempt={args.attempt}"
            )
        ledger = BudgetLedger(store, config)
        ledger.settle({**record, "amount_usd": record["proposed_reserve_usd"]}, actual, event="reconcile", note=args.note)
        updated = {
            **record, "state": "reconciled", "actual_usd": money(actual),
            "reconciliation_note": args.note,
        }
        if rejected_unreconciled:
            updated["billing_status"] = "settled"
        updated["history"] = [*record.get("history", []), {"state": "reconciled", "at": budget_utc_now(), "note": args.note}]
        store.write_json(path.relative_to(store.root), updated)
    print(f"照合を記録しました: logical_key={args.logical_key}, attempt={args.attempt}, actual_usd={money(actual)}")
    return 0


def command_budget(args: argparse.Namespace, root: Path) -> int:
    config, store, _graph = _runtime(root)
    ledger = BudgetLedger(store, config)
    if args.budget_command == "status":
        month = args.month or datetime.now(timezone.utc).strftime("%Y-%m")
        total, runs = ledger.counted(month)
        print(json.dumps({"month": month, "counted_usd": money(total), "runs": {key: money(value) for key, value in sorted(runs.items())}}, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.budget_command == "check":
        with BudgetLock(store, float(config["llm"]["budget_lock_wait_s"])):
            result = ledger.check(apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.budget_command == "repair":
        if not args.yes:
            raise PipelineError("budget repair は --yes が必要です")
        with BudgetLock(store, float(config["llm"]["budget_lock_wait_s"])):
            result = ledger.repair(args.month)
            result["check"] = ledger.check(apply=False)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.budget_command == "release":
        if not args.note.strip():
            raise PipelineError("budget release には空でない --note が必要です")
        matches = [(path, record) for path, record in _journal_records(store) if record.get("reservation_id") == args.reservation]
        if len(matches) != 1:
            raise PipelineError(f"解放対象の予約が見つからないか重複しています: reservation_id={args.reservation}, count={len(matches)}")
        path, record = matches[0]
        state = StateFile(store, record["run_id"]).read()
        with SlugLock(store, state["slug"], record["run_id"]):
            record = store.read_json(path.relative_to(store.root))
            if record.get("reservation_id") != args.reservation:
                raise PipelineError(
                    "slug ロック取得後に解放対象の予約が変わりました: "
                    f"expected={args.reservation}, actual={record.get('reservation_id')}"
                )
            if record["state"] != "proposed":
                raise PipelineError(f"送信前と確認できる proposed の予約だけ解放できます: state={record['state']}")
            ledger.release(record, args.note)
            updated = {**record, "state": "released"}
            updated["history"] = [*record.get("history", []), {"state": "released", "at": budget_utc_now(), "note": args.note}]
            store.write_json(path.relative_to(store.root), updated)
        print(f"予約を解放しました: reservation_id={args.reservation}")
        return 0
    raise PipelineError(f"budget のサブコマンドが不正です: value={args.budget_command!r}")


def _safe_display(text: str) -> str:
    output = []
    for char in text:
        code = ord(char)
        if char == "\n":
            output.append(char)
        elif char == "\t":
            output.append("\\t")
        elif unicodedata.category(char) == "Cc":
            output.append(f"\\x{code:02x}" if code <= 0xFF else f"\\u{code:04x}")
        else:
            output.append(char)
    return "".join(output)


def command_sources(args: argparse.Namespace, root: Path) -> int:
    config, store, graph = _runtime(root)
    state_file = StateFile(store, args.run)
    state = state_file.read()
    _validate_topic_identity(state)
    context = StageContext(root, store, args.run, config)
    graph.verify_status(context, state_file)
    index_relative = context.artifact_relative("sources/index.json")
    index = store.read_json(index_relative)
    sources = index.get("sources") if isinstance(index, dict) else None
    if not isinstance(sources, list):
        raise PipelineError(f"sources/index.json の sources が配列ではありません: run_id={args.run}")
    if args.show is None:
        for source in sources:
            text = source.get("text") if isinstance(source.get("text"), dict) else {}
            size = text.get("chars", 0)
            digest = str(text.get("sha256", ""))[:19]
            host = ""
            requests = source.get("requests", [])
            if requests:
                from urllib.parse import urlsplit

                host = urlsplit(requests[-1].get("final_url", "")).hostname or ""
            print(
                f"{source.get('source_id')}\t{source.get('status')}\t{source.get('reason')}\t"
                f"{host}\t{size}\t{digest}"
            )
        return 0
    matches = [source for source in sources if source.get("source_id") == args.show]
    if len(matches) != 1:
        raise PipelineError(f"source_id が見つからないか重複しています: source_id={args.show}, count={len(matches)}")
    source = matches[0]
    text_info = source.get("text")
    if not isinstance(text_info, dict) or not isinstance(text_info.get("path"), str):
        raise PipelineError(f"資料に表示できる text.txt がありません: source_id={args.show}, status={source.get('status')}")
    text = store.read_text(context.artifact_relative("sources/" + text_info["path"]))
    lines = text.splitlines()
    start, end = 1, len(lines)
    if args.lines:
        match = re.fullmatch(r"([1-9]\d*)-([1-9]\d*)", args.lines)
        if match is None or int(match.group(1)) > int(match.group(2)):
            raise PipelineError(f"--lines は <start>-<end> 形式が必要です: value={args.lines!r}")
        start, end = int(match.group(1)), int(match.group(2))
        if end > len(lines):
            raise PipelineError(f"--lines が本文の行数を超えています: end={end}, lines={len(lines)}")
    for number in range(start, end + 1):
        print(f"{number:6d}  {_safe_display(lines[number - 1])}")
    github = source.get("github")
    if isinstance(github, dict) and github.get("line_anchor") == "supported" and args.lines:
        print(f"参照URL: {github['permalink']}#L{start}-L{end}")
    return 0


def command_unlock(args: argparse.Namespace, root: Path) -> int:
    if args.budget:
        _config, store, _graph = _runtime(root)
        relative = Path("locks/budget.lock")
        if not store.exists(relative):
            raise PipelineError(f"予算ロックがありません: path={store.path(relative)}")
        print(json.dumps(store.read_json(relative), ensure_ascii=False, sort_keys=True, indent=2))
        if not args.yes:
            print("--yes がないためロックは削除していません")
            return 0
        store.remove(relative)
        print("予算ロックを削除しました")
        return 0
    if args.slug is None or not SLUG_RE.fullmatch(args.slug):
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
    new_parser.add_argument("--url-candidates")

    attach_parser = subparsers.add_parser("attach-candidates")
    attach_parser.add_argument("--run", required=True)
    attach_parser.add_argument("--file", required=True)

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--run", required=True)
    resume_parser.add_argument("--from", dest="from_stage")
    resume_parser.add_argument("--accept-modified", action="append")
    resume_parser.add_argument("--through", choices=("S1_plan", "S2_sources", "S3_claims", "S3_support"))
    resume_parser.add_argument("--refetch", choices=("failed", "all"))
    resume_parser.add_argument("--retry-unknown-llm-calls", action="store_true")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run", required=True)

    sources_parser = subparsers.add_parser("sources")
    sources_parser.add_argument("--run", required=True)
    sources_parser.add_argument("--show")
    sources_parser.add_argument("--lines")

    claims_parser = subparsers.add_parser("claims")
    claims_parser.add_argument("--run", required=True)
    claims_parser.add_argument("--show")

    llm_parser = subparsers.add_parser("llm")
    llm_subparsers = llm_parser.add_subparsers(dest="llm_command", required=True, parser_class=Parser)
    llm_calls = llm_subparsers.add_parser("calls")
    llm_calls.add_argument("--run")
    llm_calls.add_argument("--logical-key")
    llm_reconcile = llm_subparsers.add_parser("reconcile")
    llm_reconcile.add_argument("--run", required=True)
    llm_reconcile.add_argument("--logical-key", required=True)
    llm_reconcile.add_argument("--attempt", required=True, type=int)
    reconcile_amount = llm_reconcile.add_mutually_exclusive_group(required=True)
    reconcile_amount.add_argument("--actual-usd")
    reconcile_amount.add_argument("--not-billed", action="store_true")
    llm_reconcile.add_argument("--note", required=True)

    budget_parser = subparsers.add_parser("budget")
    budget_subparsers = budget_parser.add_subparsers(dest="budget_command", required=True, parser_class=Parser)
    budget_status = budget_subparsers.add_parser("status")
    budget_status.add_argument("--month")
    budget_check = budget_subparsers.add_parser("check")
    budget_check.add_argument("--apply", action="store_true")
    budget_repair = budget_subparsers.add_parser("repair")
    budget_repair.add_argument("--month", required=True)
    budget_repair.add_argument("--yes", action="store_true")
    budget_release = budget_subparsers.add_parser("release")
    budget_release.add_argument("--reservation", required=True)
    budget_release.add_argument("--note", required=True)

    unlock_parser = subparsers.add_parser("unlock")
    unlock_target = unlock_parser.add_mutually_exclusive_group(required=True)
    unlock_target.add_argument("--slug")
    unlock_target.add_argument("--budget", action="store_true")
    unlock_parser.add_argument("--yes", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        root = repo_root()
        handlers = {
            "new": command_new,
            "attach-candidates": command_attach_candidates,
            "resume": command_resume,
            "status": command_status,
            "sources": command_sources,
            "claims": command_claims,
            "llm": lambda parsed, base: command_llm_calls(parsed, base) if parsed.llm_command == "calls" else command_llm_reconcile(parsed, base),
            "budget": command_budget,
            "unlock": command_unlock,
        }
        return handlers[args.command](args, root)
    except (PipelineError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
