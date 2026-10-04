"""Stage graph, fingerprints, resume checks, and invalidation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import PipelineError
from .state import StateFile, utc_now
from .store import RunStore, canonical_json_bytes, sha256_bytes


ARTIFACT_KINDS = {"generated", "editable", "derived"}
InputProvider = Callable[["StageContext", dict[str, Any]], Mapping[str, Any]]
StageRunner = Callable[["StageContext", dict[str, Any]], Mapping[str, Any] | None]


@dataclass(frozen=True)
class ArtifactSpec:
    path: str
    kind: str = "generated"

    def __post_init__(self) -> None:
        if self.kind not in ARTIFACT_KINDS:
            raise ValueError(f"unknown artifact kind: {self.kind}")
        path = Path(self.path)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise ValueError(f"artifact path must be relative: {self.path}")


@dataclass(frozen=True)
class StageSpec:
    name: str
    stage_version: int
    dependencies: tuple[str, ...] = ()
    config_keys: tuple[str, ...] = ()
    artifacts: tuple[ArtifactSpec, ...] = ()
    input_provider: InputProvider | None = None
    runner: StageRunner | None = None


@dataclass
class StageContext:
    repo_root: Path
    store: RunStore
    run_id: str
    config: dict[str, Any]
    cache: dict[str, Any] = field(default_factory=dict)

    def artifact_relative(self, artifact_path: str) -> Path:
        return Path("runs") / self.run_id / artifact_path

    def write_json(self, artifact_path: str, value: Any) -> None:
        self.store.write_json(self.artifact_relative(artifact_path), value)

    def write_text(self, artifact_path: str, value: str) -> None:
        self.store.write_text(self.artifact_relative(artifact_path), value)


class PipelineGraph:
    def __init__(self, stages: Sequence[StageSpec]) -> None:
        self.stages = list(stages)
        self.by_name = {stage.name: stage for stage in self.stages}
        if len(self.by_name) != len(self.stages):
            raise ValueError("stage names must be unique")
        seen: set[str] = set()
        for stage in self.stages:
            missing = set(stage.dependencies) - seen
            if missing:
                raise ValueError(
                    f"stage dependencies must precede the stage: stage={stage.name}, missing={sorted(missing)}"
                )
            seen.add(stage.name)

    @property
    def stage_names(self) -> list[str]:
        return [stage.name for stage in self.stages]

    def input_parts(
        self,
        stage: StageSpec,
        context: StageContext,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        parts: dict[str, Any] = {"stage_version": stage.stage_version}
        for dependency in stage.dependencies:
            record = state["stages"][dependency]
            if record["status"] != "done":
                raise PipelineError(
                    f"依存工程が完了していません: stage={stage.name}, dependency={dependency}, status={record['status']}"
                )
            parts[f"dependency.{dependency}"] = record.get("outputs", {})
        for key in stage.config_keys:
            parts[f"config.{key}"] = self._config_value(context.config, key)
        if stage.input_provider is not None:
            provided = stage.input_provider(context, state)
            if not isinstance(provided, Mapping):
                raise PipelineError(
                    f"入力指紋プロバイダーが mapping を返しません: stage={stage.name}, type={type(provided).__name__}"
                )
            for key, value in provided.items():
                if key in parts:
                    raise PipelineError(
                        f"入力指紋のキーが重複しています: stage={stage.name}, key={key}"
                    )
                parts[key] = value
        return parts

    def fingerprint(self, parts: Mapping[str, Any]) -> str:
        return sha256_bytes(canonical_json_bytes(parts))

    def resume(
        self,
        context: StageContext,
        state_file: StateFile,
        *,
        through: str | None = None,
        from_stage: str | None = None,
        accept_modified: Sequence[str] = (),
    ) -> dict[str, Any]:
        if through is not None and through not in self.by_name:
            raise PipelineError(f"終了工程が不明です: stage={through}")
        if from_stage is not None and from_stage not in self.by_name:
            raise PipelineError(f"--from の工程が不明です: stage={from_stage}")
        state = state_file.read()
        state = self._inspect_resume_outputs(
            context, state_file, state, accept_modified=accept_modified
        )
        if from_stage is not None:
            state = self.invalidate_from(
                context, state_file, state, from_stage, reason=f"--from {from_stage}"
            )
        for stage in self.stages:
            record = state["stages"][stage.name]
            if record["status"] == "running":
                state = self._recover_interrupted(context, state_file, state, stage)
                record = state["stages"][stage.name]
            parts = self.input_parts(stage, context, state)
            fingerprint = self.fingerprint(parts)
            if (
                record["status"] == "done"
                and record.get("stage_version") == stage.stage_version
                and record.get("input_fingerprint") == fingerprint
            ):
                if stage.name == through:
                    break
                continue
            if stage.runner is None:
                raise PipelineError(f"工程は未実装です: stage={stage.name}")
            previous_outputs = dict(record.get("outputs", {}))
            if record["status"] in {"done", "failed"}:
                state = self._archive_current_stage_outputs(context, state_file, state, stage)
            state = self._run_stage(
                context,
                state_file,
                state,
                stage,
                input_parts=parts,
                input_fingerprint=fingerprint,
                previous_outputs=previous_outputs,
            )
            if stage.name == through:
                break
        return state

    def verify_status(self, context: StageContext, state_file: StateFile) -> dict[str, Any]:
        state = state_file.read()
        for stage in self.stages:
            record = state["stages"].get(stage.name)
            if record is None:
                raise PipelineError(
                    f"state.json に登録工程がありません: run_id={context.run_id}, stage={stage.name}"
                )
            if record["status"] != "done":
                continue
            if record.get("stage_version") != stage.stage_version:
                raise PipelineError(
                    f"工程版が現在の実装と一致しません: stage={stage.name}, "
                    f"recorded={record.get('stage_version')}, current={stage.stage_version}"
                )
            current_parts = self.input_parts(stage, context, state)
            current_fingerprint = self.fingerprint(current_parts)
            if record.get("input_fingerprint") != current_fingerprint:
                raise PipelineError(
                    f"工程の入力指紋が一致しません: stage={stage.name}, "
                    f"recorded={record.get('input_fingerprint')}, current={current_fingerprint}"
                )
            recorded = record.get("outputs", {})
            for artifact in stage.artifacts:
                relative = context.artifact_relative(artifact.path)
                if not context.store.exists(relative):
                    raise PipelineError(
                        f"工程の出力ファイルが欠損しています: stage={stage.name}, path={context.store.path(relative)}"
                    )
                actual = context.store.hash(relative)
                expected = recorded.get(artifact.path)
                if actual != expected:
                    raise PipelineError(
                        f"工程の出力ハッシュが一致しません: stage={stage.name}, "
                        f"path={context.store.path(relative)}, expected={expected}, actual={actual}"
                    )
        self._verify_body_hash_records(context)
        return state

    def invalidate_from(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        stage_name: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        targets = {stage_name} | self.descendants(stage_name)
        return self._invalidate(context, state_file, state, targets, invalidated_by=reason)

    def descendants(self, stage_name: str) -> set[str]:
        descendants: set[str] = set()
        changed = True
        while changed:
            changed = False
            for stage in self.stages:
                if stage.name in descendants or stage.name == stage_name:
                    continue
                if any(dep == stage_name or dep in descendants for dep in stage.dependencies):
                    descendants.add(stage.name)
                    changed = True
        return descendants

    def _run_stage(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        stage: StageSpec,
        *,
        input_parts: Mapping[str, Any],
        input_fingerprint: str,
        previous_outputs: Mapping[str, str],
    ) -> dict[str, Any]:
        attempts = int(state["stages"][stage.name].get("attempts", 0)) + 1
        state = state_file.transition(
            state,
            stage.name,
            "running",
            stage_version=stage.stage_version,
            input_parts=dict(input_parts),
            input_fingerprint=input_fingerprint,
            attempts=attempts,
            started_at=utc_now(),
        )
        try:
            updates = stage.runner(context, state) if stage.runner is not None else None
            outputs: dict[str, str] = {}
            snapshots: dict[str, str] = {}
            kinds: dict[str, str] = {}
            for artifact in stage.artifacts:
                relative = context.artifact_relative(artifact.path)
                if not context.store.exists(relative):
                    raise PipelineError(
                        f"工程が宣言した出力を作成しませんでした: stage={stage.name}, path={context.store.path(relative)}"
                    )
                digest = context.store.hash(relative)
                snapshot = self._snapshot_relative(
                    context.run_id, stage.name, artifact.path, digest
                )
                context.store.copy_bytes(relative, snapshot)
                outputs[artifact.path] = digest
                snapshots[artifact.path] = snapshot.as_posix()
                kinds[artifact.path] = artifact.kind
            current = state_file.read()
            revisions = current.setdefault("draft_revisions", [])
            for artifact in stage.artifacts:
                if artifact.kind == "editable":
                    revisions.append(
                        {
                            "rev": len(revisions) + 1,
                            "sha256": outputs[artifact.path],
                            "source": stage.name,
                            "created_at": utc_now(),
                            "path": artifact.path,
                        }
                    )
            if updates:
                for key, value in updates.items():
                    if key in {"schema_version", "run_id", "slug", "mode", "topic_source", "created_at", "stages"}:
                        raise PipelineError(
                            f"工程が固定 state キーを変更しようとしました: stage={stage.name}, key={key}"
                        )
                    current[key] = value
                state_file.write(current)
            state = state_file.transition(
                current,
                stage.name,
                "done",
                stage_version=stage.stage_version,
                input_parts=dict(input_parts),
                input_fingerprint=input_fingerprint,
                outputs=outputs,
                artifact_kinds=kinds,
                output_snapshots=snapshots,
                attempts=attempts,
                finished_at=utc_now(),
            )
        except Exception as exc:
            current = state_file.read()
            if current["stages"][stage.name]["status"] == "running":
                state_file.transition(
                    current,
                    stage.name,
                    "failed",
                    finished_at=utc_now(),
                    error=f"{type(exc).__name__}: {exc}",
                )
            raise
        if previous_outputs and dict(previous_outputs) != state["stages"][stage.name]["outputs"]:
            state = self._invalidate(
                context,
                state_file,
                state,
                self.descendants(stage.name),
                invalidated_by=stage.name,
            )
        return state

    def _inspect_resume_outputs(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        *,
        accept_modified: Sequence[str],
    ) -> dict[str, Any]:
        accepted = set(accept_modified)
        used: set[str] = set()
        for stage in self.stages:
            record = state["stages"][stage.name]
            if record["status"] != "done":
                continue
            for artifact in stage.artifacts:
                relative = context.artifact_relative(artifact.path)
                absolute = context.store.path(relative)
                if not absolute.is_file():
                    raise PipelineError(
                        "工程の出力ファイルが欠損しています。欠損は人の編集として扱わず、"
                        "--accept-modified でも受け入れません: "
                        f"stage={stage.name}, kind={artifact.kind}, path={absolute}"
                    )
                actual = context.store.hash(relative)
                expected = record.get("outputs", {}).get(artifact.path)
                if actual == expected:
                    continue
                accepted_key = self._accepted_key(
                    accepted, context, relative, artifact.path
                )
                if artifact.kind == "derived":
                    raise PipelineError(
                        "派生物が直接変更されています。正本を修正してください: "
                        f"stage={stage.name}, path={absolute}, expected={expected}, actual={actual}"
                    )
                if artifact.kind == "generated" and accepted_key is None:
                    raise PipelineError(
                        "generated 出力が変更されています。受け入れる場合は --accept-modified で"
                        "このファイルを明示してください: "
                        f"stage={stage.name}, path={absolute}, expected={expected}, actual={actual}"
                    )
                if accepted_key is not None:
                    used.add(accepted_key)
                state = self._accept_changed_artifact(
                    context,
                    state_file,
                    state,
                    stage,
                    artifact,
                    actual,
                )
                record = state["stages"][stage.name]
        unused = sorted(accepted - used)
        if unused:
            raise PipelineError(
                f"--accept-modified が変更済み generated 出力と一致しません: values={unused}, run_id={context.run_id}"
            )
        return state

    def _accept_changed_artifact(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        stage: StageSpec,
        artifact: ArtifactSpec,
        actual_hash: str,
    ) -> dict[str, Any]:
        record = state["stages"][stage.name]
        old_hash = record["outputs"][artifact.path]
        old_snapshot = record.get("output_snapshots", {}).get(artifact.path)
        if not old_snapshot or not context.store.exists(old_snapshot):
            raise PipelineError(
                f"変更前出力の snapshot がありません: stage={stage.name}, path={artifact.path}, snapshot={old_snapshot}"
            )
        stamp = self._stamp()
        superseded = Path("runs") / context.run_id / "superseded" / stamp / stage.name / artifact.path
        context.store.copy_bytes(old_snapshot, superseded)
        relative = context.artifact_relative(artifact.path)
        new_snapshot = self._snapshot_relative(
            context.run_id, stage.name, artifact.path, actual_hash
        )
        context.store.copy_bytes(relative, new_snapshot)
        record["outputs"][artifact.path] = actual_hash
        record["output_snapshots"][artifact.path] = new_snapshot.as_posix()
        record["accepted_modified_at"] = utc_now()
        record["accepted_modified_path"] = artifact.path
        if artifact.kind == "editable":
            revisions = state.setdefault("draft_revisions", [])
            revisions.append(
                {
                    "rev": len(revisions) + 1,
                    "sha256": actual_hash,
                    "source": "human_edit",
                    "created_at": utc_now(),
                    "path": artifact.path,
                }
            )
        state_file.write(state)
        return self._invalidate(
            context,
            state_file,
            state,
            self.descendants(stage.name),
            invalidated_by=stage.name,
        )

    def _recover_interrupted(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        stage: StageSpec,
    ) -> dict[str, Any]:
        state = state_file.transition(
            state,
            stage.name,
            "failed",
            finished_at=utc_now(),
            error="前回の実行が running のまま終了しました",
        )
        return self._archive_current_stage_outputs(context, state_file, state, stage)

    def _archive_current_stage_outputs(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        stage: StageSpec,
    ) -> dict[str, Any]:
        stamp = self._stamp()
        moved = False
        for artifact in stage.artifacts:
            source = context.artifact_relative(artifact.path)
            if context.store.exists(source):
                destination = (
                    Path("runs")
                    / context.run_id
                    / "superseded"
                    / stamp
                    / stage.name
                    / artifact.path
                )
                context.store.move(source, destination)
                moved = True
        if moved:
            state["stages"][stage.name]["superseded_dir"] = (
                Path("superseded") / stamp / stage.name
            ).as_posix()
            state_file.write(state)
        return state

    def _invalidate(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        targets: set[str],
        *,
        invalidated_by: str,
    ) -> dict[str, Any]:
        if not targets:
            return state
        stamp = self._stamp()
        for stage in self.stages:
            if stage.name not in targets:
                continue
            record = state["stages"][stage.name]
            for artifact in stage.artifacts:
                source = context.artifact_relative(artifact.path)
                if context.store.exists(source):
                    destination = (
                        Path("runs")
                        / context.run_id
                        / "superseded"
                        / stamp
                        / stage.name
                        / artifact.path
                    )
                    context.store.move(source, destination)
            record["status"] = "invalidated"
            record["invalidated_by"] = invalidated_by
            record["invalidated_at"] = utc_now()
            record["superseded_dir"] = (
                Path("superseded") / stamp / stage.name
            ).as_posix()
        state_file.write(state)
        return state

    def _verify_body_hash_records(self, context: StageContext) -> None:
        expected_files = {
            "draft_annotated_sha256": "draft.annotated.md",
            "draft_sha256": "draft.md",
        }
        for record_name in ("verification.json", "verdict.json"):
            record_relative = context.artifact_relative(record_name)
            if not context.store.exists(record_relative):
                continue
            record = context.store.read_json(record_relative)
            if not isinstance(record, dict):
                raise PipelineError(
                    f"検証記録が object ではありません: path={context.store.path(record_relative)}"
                )
            for key, body_name in expected_files.items():
                if key not in record:
                    continue
                body_relative = context.artifact_relative(body_name)
                if not context.store.exists(body_relative):
                    raise PipelineError(
                        f"検証対象本文が欠損しています: record={record_name}, path={context.store.path(body_relative)}"
                    )
                actual = context.store.hash(body_relative)
                if record[key] != actual:
                    raise PipelineError(
                        "検証結果は無効です（本文が検証後に変わっています）: "
                        f"record={record_name}, body={body_name}, expected={record[key]}, actual={actual}"
                    )

    @staticmethod
    def _accepted_key(
        accepted: set[str],
        context: StageContext,
        relative: Path,
        artifact_path: str,
    ) -> str | None:
        absolute = str(context.store.path(relative).resolve(strict=False))
        candidates = {
            artifact_path,
            relative.as_posix(),
            str(relative),
            absolute,
        }
        return next((candidate for candidate in accepted if candidate in candidates), None)

    @staticmethod
    def _snapshot_relative(run_id: str, stage_name: str, artifact_path: str, digest: str) -> Path:
        return (
            Path("runs")
            / run_id
            / ".snapshots"
            / stage_name
            / digest.removeprefix("sha256:")
            / artifact_path
        )

    @staticmethod
    def _stamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    @staticmethod
    def _config_value(config: Mapping[str, Any], dotted: str) -> Any:
        value: Any = config
        for key in dotted.split("."):
            if not isinstance(value, Mapping) or key not in value:
                raise PipelineError(f"工程が読む設定キーがありません: key={dotted}")
            value = value[key]
        return value


def build_production_stages() -> list[StageSpec]:
    from .intake import prepare_intake

    def s0_inputs(context: StageContext, state: dict[str, Any]) -> Mapping[str, Any]:
        prepared = prepare_intake(
            repo_root=context.repo_root,
            config=context.config,
            state=state,
        )
        context.cache["S0_intake"] = prepared
        return prepared["input_parts"]

    def s0_run(context: StageContext, state: dict[str, Any]) -> Mapping[str, Any]:
        prepared = context.cache.get("S0_intake")
        if prepared is None:
            prepared = prepare_intake(
                repo_root=context.repo_root,
                config=context.config,
                state=state,
            )
        context.write_json("topic.json", prepared["topic"])
        context.write_json("dedup_report.json", prepared["dedup_report"])
        updates: dict[str, Any] = {}
        if prepared["comparison_target"] is not None:
            updates["comparison_target"] = prepared["comparison_target"]
        return updates

    return [
        StageSpec(
            "S0_intake",
            1,
            artifacts=(ArtifactSpec("topic.json"), ArtifactSpec("dedup_report.json")),
            input_provider=s0_inputs,
            runner=s0_run,
        ),
        StageSpec(
            "S1_plan",
            1,
            dependencies=("S0_intake",),
            artifacts=(ArtifactSpec("research_plan.json"),),
        ),
        StageSpec(
            "S2_sources",
            1,
            dependencies=("S1_plan",),
            artifacts=(ArtifactSpec("sources/index.json"),),
        ),
        StageSpec(
            "S3_claims",
            1,
            dependencies=("S2_sources",),
            artifacts=(ArtifactSpec("claims.json"), ArtifactSpec("sufficiency.json")),
        ),
        StageSpec(
            "S4_write",
            1,
            dependencies=("S3_claims",),
            artifacts=(
                ArtifactSpec("draft.annotated.md", "editable"),
                ArtifactSpec("draft.md", "derived"),
            ),
        ),
        StageSpec(
            "S5_code",
            1,
            dependencies=("S4_write",),
            artifacts=(ArtifactSpec("code_verification.json"),),
        ),
        StageSpec(
            "S6_verify",
            1,
            dependencies=("S2_sources", "S3_claims", "S4_write", "S5_code"),
            artifacts=(ArtifactSpec("verification.json"),),
        ),
        StageSpec(
            "S7_verdict",
            1,
            dependencies=("S5_code", "S6_verify"),
            artifacts=(ArtifactSpec("verdict.json"),),
        ),
    ]
