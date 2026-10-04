"""Constrained, atomic storage for article pipeline runs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path, PurePath
from typing import Any

from . import PipelineError


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise PipelineError(
            f"ファイルのハッシュを計算できません: path={path}, error={exc}"
        ) from exc


class RunStore:
    """The only write boundary for ``run/article_pipeline``."""

    def __init__(self, repo_root: Path, root: Path | None = None) -> None:
        self.repo_root = repo_root.resolve(strict=True)
        configured = root if root is not None else Path("run/article_pipeline")
        if configured.is_absolute():
            candidate = configured
        else:
            candidate = self.repo_root / configured
        self.root = candidate.resolve(strict=False)
        required_root = (self.repo_root / "run/article_pipeline").resolve(strict=False)
        if self.root != required_root:
            raise PipelineError(
                "パイプラインの保存先が固定ディレクトリではありません: "
                f"configured={candidate}, required={required_root}"
            )
        self._reject_links(candidate)

    def ensure_gitignored(self) -> None:
        probe = Path("run/article_pipeline/.probe")
        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", probe.as_posix()],
                cwd=self.repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise PipelineError(
                f"git check-ignore を実行できません: repo={self.repo_root}, error={exc}"
            ) from exc
        if result.returncode == 1:
            raise PipelineError(
                "保存先が gitignore の対象ではありません: "
                f"path={probe.as_posix()}, repo={self.repo_root}"
            )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "出力なし"
            raise PipelineError(
                "git check-ignore が失敗しました: "
                f"path={probe.as_posix()}, returncode={result.returncode}, detail={detail}"
            )

    def path(self, relative: str | Path) -> Path:
        rel = Path(relative)
        if rel.is_absolute() or PurePath(rel).anchor:
            raise PipelineError(f"絶対パスには書き込めません: path={relative}")
        if not rel.parts or any(part in ("", ".", "..") for part in rel.parts):
            raise PipelineError(f"不正な相対パスです: path={relative}")
        candidate = self.root.joinpath(*rel.parts)
        self._reject_links(candidate)
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise PipelineError(
                f"保存先の外には書き込めません: path={relative}, resolved={resolved}, root={self.root}"
            ) from exc
        return candidate

    def exists(self, relative: str | Path) -> bool:
        return self.path(relative).exists()

    def mkdir(self, relative: str | Path, *, exclusive: bool = False) -> Path:
        target = self.path(relative)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.mkdir(exist_ok=not exclusive)
        except FileExistsError as exc:
            raise PipelineError(f"ディレクトリが既に存在します: path={target}") from exc
        except OSError as exc:
            raise PipelineError(
                f"ディレクトリを作成できません: path={target}, error={exc}"
            ) from exc
        return target

    def read_bytes(self, relative: str | Path) -> bytes:
        target = self.path(relative)
        try:
            return target.read_bytes()
        except OSError as exc:
            raise PipelineError(f"ファイルを読めません: path={target}, error={exc}") from exc

    def read_text(self, relative: str | Path) -> str:
        target = self.path(relative)
        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PipelineError(f"UTF-8 ファイルを読めません: path={target}, error={exc}") from exc

    def read_json(self, relative: str | Path) -> Any:
        target = self.path(relative)
        try:
            return json.loads(self.read_text(relative))
        except json.JSONDecodeError as exc:
            raise PipelineError(
                f"JSON を解析できません: path={target}, line={exc.lineno}, column={exc.colno}, error={exc.msg}"
            ) from exc

    def write_bytes(self, relative: str | Path, data: bytes) -> Path:
        target = self.path(relative)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            self._reject_links(temp)
            with temp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except OSError as exc:
            cleanup_error: OSError | None = None
            if "temp" in locals() and temp.exists():
                try:
                    temp.unlink()
                except OSError as cleanup_exc:
                    cleanup_error = cleanup_exc
            cleanup_detail = (
                f", temporary_cleanup_error={cleanup_error}" if cleanup_error is not None else ""
            )
            raise PipelineError(
                f"ファイルを原子的に書き込めません: path={target}, error={exc}{cleanup_detail}"
            ) from exc
        return target

    def write_text(self, relative: str | Path, text: str) -> Path:
        return self.write_bytes(relative, text.encode("utf-8"))

    def write_json(self, relative: str | Path, value: Any) -> Path:
        try:
            data = canonical_json_bytes(value)
        except (TypeError, ValueError) as exc:
            raise PipelineError(
                f"正規形 JSON に変換できません: path={relative}, error={exc}"
            ) from exc
        return self.write_bytes(relative, data)

    def create_exclusive_json(self, relative: str | Path, value: Any) -> Path:
        target = self.path(relative)
        try:
            data = canonical_json_bytes(value)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise PipelineError(
                f"ファイルを排他作成できません: path={target}, error={exc}"
            ) from exc
        return target

    def remove(self, relative: str | Path) -> None:
        target = self.path(relative)
        try:
            target.unlink()
        except FileNotFoundError as exc:
            raise PipelineError(f"削除対象がありません: path={target}") from exc
        except OSError as exc:
            raise PipelineError(f"ファイルを削除できません: path={target}, error={exc}") from exc

    def move(self, source: str | Path, destination: str | Path) -> None:
        src = self.path(source)
        dst = self.path(destination)
        if not src.exists():
            raise PipelineError(f"移動元がありません: path={src}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
        except OSError as exc:
            raise PipelineError(
                f"ファイルを退避できません: source={src}, destination={dst}, error={exc}"
            ) from exc

    def copy_bytes(self, source: str | Path, destination: str | Path) -> None:
        self.write_bytes(destination, self.read_bytes(source))

    def hash(self, relative: str | Path) -> str:
        return sha256_bytes(self.read_bytes(relative))

    def _reject_links(self, candidate: Path) -> None:
        absolute = candidate if candidate.is_absolute() else self.repo_root / candidate
        try:
            relative = absolute.relative_to(self.repo_root)
        except ValueError as exc:
            raise PipelineError(
                f"リポジトリ外のパスは使用できません: path={absolute}, repo={self.repo_root}"
            ) from exc
        current = self.repo_root
        for part in relative.parts:
            current = current / part
            if not current.exists() and not current.is_symlink():
                continue
            try:
                is_junction = bool(getattr(os.path, "isjunction", lambda _p: False)(current))
            except OSError as exc:
                raise PipelineError(
                    f"ジャンクションを検査できません: path={current}, error={exc}"
                ) from exc
            if current.is_symlink() or is_junction:
                kind = "symbolic link" if current.is_symlink() else "junction"
                raise PipelineError(
                    f"リンク経由の保存先は使用できません: path={current}, kind={kind}"
                )
