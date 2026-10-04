"""State schema and checked transitions for article pipeline runs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from . import PipelineError, SCHEMA_VERSION
from .store import RunStore


STAGE_STATUSES = {"pending", "running", "done", "failed", "invalidated"}
RUN_ID_RE = re.compile(
    r"^(?P<prefix>cand|cmp)_(?P<stamp>\d{8}T\d{6}Z)_(?P<slug>[a-z0-9_+\-]+)_(?P<random>[0-9a-f]{4})$"
)
TRANSITIONS = {
    "pending": {"running", "failed", "invalidated"},
    "running": {"done", "failed"},
    "done": {"running", "invalidated"},
    "failed": {"running", "invalidated"},
    "invalidated": {"running"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def initial_state(
    *,
    run_id: str,
    slug: str,
    mode: str,
    topic_source: Path,
    stage_names: list[str],
) -> dict[str, Any]:
    if mode not in {"candidate", "comparison"}:
        raise PipelineError(f"実行モードが不正です: mode={mode}")
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "slug": slug,
        "mode": mode,
        "topic_source": str(topic_source.resolve(strict=True)),
        "created_at": utc_now(),
        "stages": {name: {"status": "pending", "attempts": 0} for name in stage_names},
        "draft_revisions": [],
    }
    if mode == "comparison":
        state["publish_allowed"] = False
    return state


class StateFile:
    def __init__(self, store: RunStore, run_id: str) -> None:
        self.store = store
        self.run_id = run_id
        self.relative = Path("runs") / run_id / "state.json"

    def read(self) -> dict[str, Any]:
        value = self.store.read_json(self.relative)
        self.validate(value)
        return value

    def write(self, state: dict[str, Any]) -> None:
        self.validate(state)
        self.store.write_json(self.relative, state)

    def transition(
        self,
        state: dict[str, Any],
        stage_name: str,
        status: str,
        **fields: Any,
    ) -> dict[str, Any]:
        if stage_name not in state["stages"]:
            raise PipelineError(f"state に工程がありません: stage={stage_name}, run_id={self.run_id}")
        old = state["stages"][stage_name]["status"]
        if status not in TRANSITIONS.get(old, set()):
            raise PipelineError(
                f"不正な状態遷移です: stage={stage_name}, from={old}, to={status}, run_id={self.run_id}"
            )
        updated = deepcopy(state)
        updated["stages"][stage_name] = {**updated["stages"][stage_name], **fields, "status": status}
        self.write(updated)
        return updated

    def validate(self, value: Any) -> None:
        if not isinstance(value, dict):
            raise PipelineError(
                f"state.json のルートが object ではありません: run_id={self.run_id}, type={type(value).__name__}"
            )
        required = {"schema_version", "run_id", "slug", "mode", "topic_source", "created_at", "stages"}
        missing = sorted(required - value.keys())
        if missing:
            raise PipelineError(f"state.json に必須キーがありません: run_id={self.run_id}, missing={missing}")
        if value["schema_version"] != SCHEMA_VERSION:
            raise PipelineError(
                f"state.json の schema_version が未対応です: run_id={self.run_id}, "
                f"actual={value['schema_version']}, expected={SCHEMA_VERSION}"
            )
        if value["run_id"] != self.run_id:
            raise PipelineError(
                f"state.json の run_id がディレクトリと一致しません: directory={self.run_id}, value={value['run_id']}"
            )
        mode = value["mode"]
        expected_prefix = "cand_" if mode == "candidate" else "cmp_" if mode == "comparison" else None
        if expected_prefix is None or not self.run_id.startswith(expected_prefix):
            raise PipelineError(
                f"作成後に mode を変更できません: run_id={self.run_id}, mode={mode}, expected_prefix={expected_prefix}"
            )
        match = RUN_ID_RE.fullmatch(self.run_id)
        if match is None:
            raise PipelineError(f"run_id の形式が不正です: run_id={self.run_id}")
        if match.group("slug") != value["slug"]:
            raise PipelineError(
                "作成後に slug を変更できません。新しい run を作成してください: "
                f"run_id={self.run_id}, run_id_slug={match.group('slug')!r}, state_slug={value['slug']!r}"
            )
        if mode == "comparison" and value.get("publish_allowed") is not False:
            raise PipelineError(
                f"comparison の publish_allowed は false 固定です: run_id={self.run_id}, value={value.get('publish_allowed')}"
            )
        stages = value["stages"]
        if not isinstance(stages, dict):
            raise PipelineError(f"state.json の stages が object ではありません: run_id={self.run_id}")
        for name, stage in stages.items():
            if not isinstance(stage, dict) or stage.get("status") not in STAGE_STATUSES:
                raise PipelineError(
                    f"工程状態が不正です: run_id={self.run_id}, stage={name}, value={stage}"
                )
