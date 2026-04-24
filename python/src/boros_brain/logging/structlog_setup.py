"""structlog configuration with contextvars-bound run_id (INFRA-07, PROTO-01).

`merge_contextvars` pulls `run_id + tier + pid` into every log record. Because
`bind_contextvars` operates on Python `contextvars.ContextVar`, the binding is
inherited automatically by `asyncio.create_task` and `asyncio.gather` (Python 3.7+
semantics — verified in test_structlog_contextvars).

Log files live under `logs/<YYYY-MM-DD>/<run_id>.<tier>.log.jsonl`. Opened in
line-buffered text-append mode (`"a", buffering=1`) so each `log.info(...)`
call flushes at the trailing newline — critical for the RUN_MANIFEST-first
invariant (a crash between `configure_logging()` and the next log call must
not lose the manifest line). Text mode is required because `structlog.WriteLogger`
concatenates `message + "\n"` as strings; `_orjson_dumps` therefore returns `str`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars


def _orjson_dumps(obj: Any, default: Callable[[Any], Any] | None = None) -> str:
    """Serialize to str — structlog WriteLoggerFactory writes text, not bytes.

    orjson returns bytes by design; decode to utf-8 here so the JSONRenderer
    output line-concatenates cleanly with the newline inside WriteLogger.msg().
    """
    result: str = orjson.dumps(obj, default=default).decode("utf-8")
    return result


def configure_logging(
    run_id: str,
    tier: str,
    logs_dir: Path | str,
    first_manifest_line: dict[str, Any] | None = None,
) -> None:
    """Bind contextvars + configure structlog JSON writer.

    If `first_manifest_line` is provided, emit a single `RUN_MANIFEST` record as
    the first log line. This enforces the MANIFEST-FIRST invariant: every
    `<run_id>.brain.log.jsonl` opens with a self-describing manifest record.
    """
    logs_dir = Path(logs_dir)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    date_dir = logs_dir / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    log_path = date_dir / f"{run_id}.{tier}.log.jsonl"
    # Line-buffered text append — every log.info() flushes at its trailing newline.
    # Binary mode (`"ab"`) does NOT work here: WriteLogger.msg() does `msg + "\n"`
    # with a str, so the underlying file must accept str writes.
    log_file = open(log_path, "a", buffering=1, encoding="utf-8")  # noqa: SIM115 (long-lived file handle)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.PROCESS,
                ]
            ),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(serializer=_orjson_dumps),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(file=log_file),
        cache_logger_on_first_use=False,
    )
    # Reset contextvars so test isolation is clean, then bind the active run.
    clear_contextvars()
    bind_contextvars(run_id=run_id, tier=tier, pid=os.getpid())

    if first_manifest_line is not None:
        # MANIFEST-FIRST invariant: the first log line IS the manifest, same as
        # the sidecar JSON content. Downstream log readers split on the first
        # record and load it as the run's knob inventory.
        get_logger("boros_brain.manifest.writer").info("RUN_MANIFEST", **first_manifest_line)


def get_logger(name: str) -> Any:
    """Return a bound structlog logger. Thin wrapper; exported for test imports.

    Returns Any because structlog.get_logger() returns a FilteringBoundLogger whose
    exact type depends on the wrapper_class configured at runtime — impossible to
    statically type without a mypy plugin. Callers use it as a duck-typed logger.
    """
    return structlog.get_logger(name)
