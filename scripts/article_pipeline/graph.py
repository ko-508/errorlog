"""Stage graph, fingerprints, resume checks, and invalidation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
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
    manifest: bool = False

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
    owned_dirs: tuple[str, ...] = ()
    input_provider: InputProvider | None = None
    runner: StageRunner | None = None

    def __post_init__(self) -> None:
        for owned in self.owned_dirs:
            path = Path(owned)
            if path.is_absolute() or not path.parts or ".." in path.parts:
                raise ValueError(f"owned directory must be relative: {owned}")


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

    def write_bytes(self, artifact_path: str, value: bytes) -> None:
        self.store.write_bytes(self.artifact_relative(artifact_path), value)


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
        refetch: str | None = None,
    ) -> dict[str, Any]:
        if through is not None and through not in self.by_name:
            raise PipelineError(f"終了工程が不明です: stage={through}")
        if from_stage is not None and from_stage not in self.by_name:
            raise PipelineError(f"--from の工程が不明です: stage={from_stage}")
        if refetch not in {None, "failed", "all"}:
            raise PipelineError(f"--refetch の値が不正です: value={refetch!r}")
        state = state_file.read()
        pending = state.get("pending_recovery")
        s2_index = self.stage_names.index("S2_sources") if "S2_sources" in self.by_name else None
        from_index = self.stage_names.index(from_stage) if from_stage is not None else None
        recovery_scope = (
            from_stage is not None
            and s2_index is not None
            and from_index is not None
            and from_index <= s2_index
        )
        if refetch is not None and from_stage is None:
            raise PipelineError("--refetch は --from S0_intake|S1_plan|S2_sources と一緒に指定してください")
        if refetch is not None and not recovery_scope:
            raise PipelineError(
                f"--refetch は S2_sources 以前からの再実行にだけ指定できます: from={from_stage}"
            )
        if through is not None and from_stage is not None:
            if self.stage_names.index(through) < self.stage_names.index(from_stage):
                raise PipelineError(
                    f"--through は --from と同じ工程か後続工程が必要です: from={from_stage}, through={through}"
                )
        if refetch is not None and through is not None and s2_index is not None:
            if self.stage_names.index(through) < s2_index:
                raise PipelineError(
                    f"--refetch を指定した復旧は S2_sources まで実行する必要があります: through={through}"
                )
        continued_recovery = False
        if recovery_scope and refetch is None:
            raise PipelineError(
                "S2_sources 以前から再実行するときは --refetch failed|all が必要です: "
                f"from={from_stage}"
            )
        if pending is not None:
            report = context.store.read_json(pending["report"])
            expected_from = report.get("from_stage")
            if not recovery_scope or refetch != "all" or from_stage != expected_from:
                raise PipelineError(
                    "未完了の復旧があります。通常の resume は実行できません。"
                    f"同じ復旧コマンドを再実行してください: pending_recovery={pending}, "
                    f"command='resume --run {context.run_id} --from {expected_from} --refetch all'"
                )
            state = self._continue_pending_recovery(context, state_file, state)
            continued_recovery = True
        if from_stage is None:
            state = self._inspect_resume_outputs(
                context, state_file, state, accept_modified=accept_modified
            )
        else:
            if continued_recovery:
                issues = []
                material_issues = []
            else:
                issues = self._collect_output_issues(context, state)
                upstream_names = set(self.stage_names[:from_index])
                protected_names = {name for name in ("S0_intake", "S1_plan") if name in self.by_name}
                blocking = [item for item in issues if item["stage"] in upstream_names | protected_names]
                if blocking:
                    raise PipelineError(self._issues_message(context, blocking))
                material_issues = [item for item in issues if item["stage"] == "S2_sources"]
            if continued_recovery:
                pass
            elif material_issues:
                if refetch != "all":
                    raise PipelineError(
                        self._issues_message(context, material_issues)
                        + f"\n壊れた資料は --refetch all でのみ復旧できます。"
                    )
                state = self._start_recovery(
                    context,
                    state_file,
                    state,
                    from_stage=from_stage,
                    issues=issues,
                    refetch=refetch,
                )
            else:
                state = self.invalidate_from(
                    context, state_file, state, from_stage, reason=f"--from {from_stage}"
                )
        context.cache["refetch"] = refetch
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
            if stage.name == "S2_sources":
                context.cache["previous_S2_quarantined"] = bool(record.get("quarantined"))
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
        if state.get("pending_recovery") is not None:
            pending = state["pending_recovery"]
            report = context.store.read_json(pending["report"])
            expected_from = report.get("from_stage", "S2_sources")
            raise PipelineError(
                "未完了の復旧があります。status は変更せず停止します: "
                f"pending_recovery={pending}, "
                f"command='resume --run {context.run_id} --from {expected_from} --refetch all'"
            )
        issues = self._collect_output_issues(context, state, include_running=True)
        if issues:
            raise PipelineError(self._issues_message(context, issues))
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
        running_fields: dict[str, Any] = {
            "stage_version": stage.stage_version,
            "input_parts": dict(input_parts),
            "input_fingerprint": input_fingerprint,
            "attempts": attempts,
            "started_at": utc_now(),
        }
        if stage.name == "S2_sources":
            running_fields["refetch"] = context.cache.get("refetch")
            running_fields["quarantined"] = False
        state = state_file.transition(
            state,
            stage.name,
            "running",
            **running_fields,
        )
        try:
            updates = stage.runner(context, state) if stage.runner is not None else None
            outputs: dict[str, str] = {}
            snapshots: dict[str, str] = {}
            kinds: dict[str, str] = {}
            for owned in stage.owned_dirs:
                if owned.endswith(".staging") and context.store.exists(context.artifact_relative(owned)):
                    raise PipelineError(
                        f"工程完了時に作業用ディレクトリが残っています: stage={stage.name}, "
                        f"path={context.store.path(context.artifact_relative(owned))}"
                    )
            for artifact in stage.artifacts:
                relative = context.artifact_relative(artifact.path)
                if not context.store.exists(relative):
                    raise PipelineError(
                        f"工程が宣言した出力を作成しませんでした: stage={stage.name}, path={context.store.path(relative)}"
                    )
                if artifact.manifest:
                    manifest_issues = self._manifest_issues(
                        context, stage, artifact, check_recorded_manifest=False
                    )
                    if manifest_issues:
                        raise PipelineError(self._issues_message(context, manifest_issues))
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
                    if key in {
                        "schema_version", "run_id", "slug", "mode", "topic_source",
                        "url_candidates_source", "created_at", "stages", "pending_recovery",
                    }:
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
        issues = self._collect_output_issues(context, state)
        blocking = [
            item for item in issues
            if item.get("manifest") or item["kind"] in {"missing", "extra", "link", "staging"}
        ]
        if blocking:
            raise PipelineError(self._issues_message(context, blocking))
        for stage in self.stages:
            record = state["stages"][stage.name]
            if record["status"] != "done":
                continue
            for artifact in stage.artifacts:
                if artifact.manifest:
                    continue
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
        return self._archive_current_stage_outputs(
            context, state_file, state, stage, reason="interrupted"
        )

    def _archive_current_stage_outputs(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        stage: StageSpec,
        *,
        reason: str = "rerun",
    ) -> dict[str, Any]:
        stamp = self._stamp()
        moved, destination = self._archive_stage_content(
            context, stage, stamp=stamp, reason=reason
        )
        if moved:
            state["stages"][stage.name]["superseded_dir"] = destination
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
            _moved, destination = self._archive_stage_content(
                context, stage, stamp=stamp, reason="invalidated"
            )
            record["status"] = "invalidated"
            record["invalidated_by"] = invalidated_by
            record["invalidated_at"] = utc_now()
            record["superseded_dir"] = destination
        state_file.write(state)
        return state

    def _archive_stage_content(
        self,
        context: StageContext,
        stage: StageSpec,
        *,
        stamp: str,
        reason: str,
    ) -> tuple[bool, str]:
        destination_relative = (Path("superseded") / stamp / stage.name).as_posix()
        destination_base = Path("runs") / context.run_id / destination_relative
        inventory: list[dict[str, Any]] = []
        moved = False
        for owned in stage.owned_dirs:
            source = context.artifact_relative(owned)
            if not context.store.exists(source):
                continue
            destination = destination_base / owned
            entries = context.store.move_tree(source, destination)
            inventory.extend({**entry, "path": f"{owned}/{entry['path']}"} for entry in entries)
            moved = True
        for artifact in stage.artifacts:
            if any(Path(artifact.path).is_relative_to(Path(owned)) for owned in stage.owned_dirs):
                continue
            source = context.artifact_relative(artifact.path)
            if context.store.exists(source):
                digest = context.store.hash(source)
                size = len(context.store.read_bytes(source))
                destination = destination_base / artifact.path
                context.store.move(source, destination)
                inventory.append(
                    {"path": artifact.path, "kind": "file", "bytes": size, "sha256": digest}
                )
                moved = True
        if moved:
            context.store.write_json(
                destination_base / "archive_note.json",
                {"reason": reason, "stage": stage.name, "inventory": inventory},
            )
        return moved, destination_relative

    def _collect_output_issues(
        self,
        context: StageContext,
        state: dict[str, Any],
        *,
        include_running: bool = False,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for stage in self.stages:
            record = state["stages"][stage.name]
            if include_running or record["status"] != "running":
                for owned in stage.owned_dirs:
                    if owned.endswith(".staging"):
                        relative = context.artifact_relative(owned)
                        if context.store.exists(relative):
                            issues.append(
                                {
                                    "stage": stage.name,
                                    "path": owned,
                                    "kind": "staging",
                                    "expected": "absent",
                                    "actual": "present",
                                    "manifest": True,
                                }
                            )
            if record["status"] != "done":
                continue
            for artifact in stage.artifacts:
                if artifact.manifest:
                    issues.extend(self._manifest_issues(context, stage, artifact))
                    continue
                relative = context.artifact_relative(artifact.path)
                absolute = context.store.root / relative
                if self._path_has_link(absolute, context.store.root):
                    issues.append(
                        {
                            "stage": stage.name,
                            "path": artifact.path,
                            "kind": "link",
                            "expected": record.get("outputs", {}).get(artifact.path),
                            "actual": "link",
                            "manifest": False,
                        }
                    )
                elif not absolute.is_file():
                    issues.append(
                        {
                            "stage": stage.name,
                            "path": artifact.path,
                            "kind": "missing",
                            "expected": record.get("outputs", {}).get(artifact.path),
                            "actual": None,
                            "manifest": False,
                        }
                    )
                else:
                    actual = context.store.hash(relative)
                    expected = record.get("outputs", {}).get(artifact.path)
                    if actual != expected:
                        issues.append(
                            {
                                "stage": stage.name,
                                "path": artifact.path,
                                "kind": "modified",
                                "expected": expected,
                                "actual": actual,
                                "manifest": False,
                            }
                        )
        return issues

    def _manifest_issues(
        self,
        context: StageContext,
        stage: StageSpec,
        artifact: ArtifactSpec,
        *,
        check_recorded_manifest: bool = True,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        relative = context.artifact_relative(artifact.path)
        absolute = context.store.root / relative
        record = context.store.read_json(Path("runs") / context.run_id / "state.json")
        expected_manifest = (
            record["stages"][stage.name].get("outputs", {}).get(artifact.path)
            if check_recorded_manifest
            else None
        )
        if self._path_has_link(absolute, context.store.root):
            return [{"stage": stage.name, "path": artifact.path, "kind": "link", "expected": expected_manifest, "actual": "link", "manifest": True}]
        if not absolute.is_file():
            return [{"stage": stage.name, "path": artifact.path, "kind": "missing", "expected": expected_manifest, "actual": None, "manifest": True}]
        actual_manifest = context.store.hash(relative)
        if expected_manifest is not None and actual_manifest != expected_manifest:
            issues.append({"stage": stage.name, "path": artifact.path, "kind": "modified", "expected": expected_manifest, "actual": actual_manifest, "manifest": True})
        try:
            manifest = context.store.read_json(relative)
        except PipelineError as exc:
            issues.append({"stage": stage.name, "path": artifact.path, "kind": "modified", "expected": "valid manifest", "actual": str(exc), "manifest": True})
            return issues
        members = manifest.get("members") if isinstance(manifest, dict) else None
        if not isinstance(members, list):
            issues.append({"stage": stage.name, "path": artifact.path, "kind": "modified", "expected": "members array", "actual": type(members).__name__, "manifest": True})
            return issues
        root = absolute.parent
        expected_paths = {Path(artifact.path).name}
        seen: set[str] = set()
        for index, member in enumerate(members):
            if not isinstance(member, dict) or set(member) != {"path", "sha256"}:
                issues.append({"stage": stage.name, "path": f"members[{index}]", "kind": "modified", "expected": "{path, sha256}", "actual": repr(member), "manifest": True})
                continue
            member_path = member["path"]
            path = Path(member_path) if isinstance(member_path, str) else Path()
            if not isinstance(member_path, str) or path.is_absolute() or not path.parts or ".." in path.parts:
                issues.append({"stage": stage.name, "path": str(member_path), "kind": "modified", "expected": "sources-relative path", "actual": "invalid path", "manifest": True})
                continue
            if member_path in seen:
                issues.append({"stage": stage.name, "path": member_path, "kind": "modified", "expected": "unique member", "actual": "duplicate", "manifest": True})
                continue
            seen.add(member_path)
            expected_paths.add(path.as_posix())
            target = root.joinpath(*path.parts)
            if self._path_has_link(target, root):
                issues.append({"stage": stage.name, "path": member_path, "kind": "link", "expected": member["sha256"], "actual": "link", "manifest": True})
            elif not target.is_file():
                issues.append({"stage": stage.name, "path": member_path, "kind": "missing", "expected": member["sha256"], "actual": None, "manifest": True})
            else:
                from .store import sha256_file

                actual = sha256_file(target)
                if actual != member["sha256"]:
                    issues.append({"stage": stage.name, "path": member_path, "kind": "modified", "expected": member["sha256"], "actual": actual, "manifest": True})
        try:
            inventory = context.store.inspect_tree(relative.parent)
        except PipelineError as exc:
            issues.append({"stage": stage.name, "path": str(relative.parent), "kind": "modified", "expected": "readable tree", "actual": str(exc), "manifest": True})
            return issues
        actual_paths = {entry["path"] for entry in inventory}
        for extra in sorted(actual_paths - expected_paths):
            kind = next(entry["kind"] for entry in inventory if entry["path"] == extra)
            issues.append({"stage": stage.name, "path": extra, "kind": "link" if kind == "link" else "extra", "expected": None, "actual": kind, "manifest": True})
        return issues

    def _issues_message(self, context: StageContext, issues: list[dict[str, Any]]) -> str:
        lines = ["工程の出力に不一致または欠損があります。何も変更せず停止します:"]
        for item in issues:
            lines.append(
                f"- stage={item['stage']}, path={item['path']}, kind={item['kind']}, "
                f"expected={item.get('expected')}, actual={item.get('actual')}"
            )
        if any(item.get("manifest") for item in issues):
            lines.append(
                "復旧コマンド: "
                f"resume --run {context.run_id} --from S2_sources --refetch all"
            )
        return "\n".join(lines)

    def _start_recovery(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
        *,
        from_stage: str,
        issues: list[dict[str, Any]],
        refetch: str,
    ) -> dict[str, Any]:
        stamp = self._stamp()
        target_names = {from_stage} | self.descendants(from_stage)
        planned: list[dict[str, str]] = []
        for stage in self.stages:
            if stage.name not in target_names:
                continue
            destination_base = Path("runs") / context.run_id / "superseded" / stamp / stage.name
            for owned in stage.owned_dirs:
                source = context.artifact_relative(owned)
                if context.store.exists(source):
                    planned.append({"source": source.as_posix(), "destination": (destination_base / owned).as_posix(), "stage": stage.name, "kind": "tree"})
            for artifact in stage.artifacts:
                if any(Path(artifact.path).is_relative_to(Path(owned)) for owned in stage.owned_dirs):
                    continue
                source = context.artifact_relative(artifact.path)
                if context.store.exists(source):
                    planned.append({"source": source.as_posix(), "destination": (destination_base / artifact.path).as_posix(), "stage": stage.name, "kind": "file"})
        report_relative = Path("runs") / context.run_id / "superseded" / stamp / "recovery_report.json"
        report = {
            "reason": "recovery",
            "quarantined": True,
            "from_stage": from_stage,
            "refetch": refetch,
            "issues": issues,
            "planned": planned,
            "completed": False,
        }
        context.store.write_json(report_relative, report)
        state["pending_recovery"] = {
            "stamp": stamp,
            "report": report_relative.as_posix(),
            "planned": planned,
        }
        state_file.write(state)
        return self._continue_pending_recovery(context, state_file, state)

    def _continue_pending_recovery(
        self,
        context: StageContext,
        state_file: StateFile,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        pending = state["pending_recovery"]
        report = context.store.read_json(pending["report"])
        from_stage = report.get("from_stage")
        if from_stage not in self.by_name:
            raise PipelineError(f"recovery_report.json の from_stage が不正です: value={from_stage!r}")
        inventories: dict[str, list[dict[str, Any]]] = {}
        for item in pending["planned"]:
            source = Path(item["source"])
            destination = Path(item["destination"])
            source_absolute = context.store.root / source
            destination_absolute = context.store.root / destination
            source_exists = source_absolute.exists() or source_absolute.is_symlink()
            destination_exists = destination_absolute.exists() or destination_absolute.is_symlink()
            if source_exists and destination_exists:
                raise PipelineError(f"復旧の移動元と移動先が両方存在します: source={source_absolute}, destination={destination_absolute}")
            if not source_exists and not destination_exists:
                raise PipelineError(f"復旧の移動元と移動先が両方ありません: source={source_absolute}, destination={destination_absolute}")
            if source_exists:
                if item["kind"] == "tree":
                    inventory = context.store.move_tree(source, destination)
                else:
                    data = context.store.read_bytes(source)
                    inventory = [{"path": Path(item["destination"]).name, "kind": "file", "bytes": len(data), "sha256": sha256_bytes(data)}]
                    context.store.move(source, destination)
            else:
                if item["kind"] == "tree":
                    inventory = context.store.inspect_tree(destination)
                else:
                    data = context.store.read_bytes(destination)
                    inventory = [{"path": Path(item["destination"]).name, "kind": "file", "bytes": len(data), "sha256": sha256_bytes(data)}]
            inventories.setdefault(item["stage"], []).extend(inventory)
        stamp = pending["stamp"]
        targets = {from_stage} | self.descendants(from_stage)
        report_run_relative = Path(pending["report"]).relative_to(Path("runs") / context.run_id)
        for stage_name in targets:
            if stage_name in inventories:
                base = Path("runs") / context.run_id / "superseded" / stamp / stage_name
                context.store.write_json(base / "archive_note.json", {"reason": "recovery", "stage": stage_name, "inventory": inventories[stage_name]})
            record = state["stages"][stage_name]
            record["status"] = "invalidated"
            record["invalidated_by"] = "recovery"
            record["invalidated_at"] = utc_now()
            record["superseded_dir"] = (Path("superseded") / stamp / stage_name).as_posix()
            record["recovery_report"] = report_run_relative.as_posix()
            if stage_name == "S2_sources":
                record["quarantined"] = True
        report["completed"] = True
        report["inventories"] = inventories
        context.store.write_json(pending["report"], report)
        del state["pending_recovery"]
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
    def _path_has_link(path: Path, root: Path) -> bool:
        try:
            relative = path.relative_to(root)
        except ValueError:
            return True
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink() or bool(getattr(os.path, "isjunction", lambda _p: False)(current)):
                return True
        return False

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
    from .acquire import STAGE_VERSION as ACQUIRE_STAGE_VERSION, run_acquire
    from .intake import prepare_intake
    from .plan_manual import prepare_plan

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

    def s1_inputs(context: StageContext, state: dict[str, Any]) -> Mapping[str, Any]:
        topic = context.store.read_json(context.artifact_relative("topic.json"))
        prepared = prepare_plan(state=state, config=context.config, topic=topic)
        context.cache["S1_plan"] = prepared
        return prepared["input_parts"]

    def s1_run(context: StageContext, state: dict[str, Any]) -> None:
        prepared = context.cache.get("S1_plan")
        if prepared is None:
            topic = context.store.read_json(context.artifact_relative("topic.json"))
            prepared = prepare_plan(state=state, config=context.config, topic=topic)
        context.write_json("research_plan.json", prepared["plan"])

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
            config_keys=("plan",),
            artifacts=(ArtifactSpec("research_plan.json"),),
            input_provider=s1_inputs,
            runner=s1_run,
        ),
        StageSpec(
            "S2_sources",
            ACQUIRE_STAGE_VERSION,
            dependencies=("S1_plan",),
            config_keys=("acquire",),
            artifacts=(ArtifactSpec("sources/index.json", manifest=True),),
            owned_dirs=("sources", "sources.staging"),
            runner=run_acquire,
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
