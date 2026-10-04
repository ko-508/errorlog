"""Local-only article pipeline foundations for P1."""

from __future__ import annotations


class PipelineError(RuntimeError):
    """An expected, actionable pipeline failure."""


SCHEMA_VERSION = 1
