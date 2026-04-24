"""Shared structlog setup + log-record schema (INFRA-07).

Public API:
  - configure_logging:  bind contextvars + configure JSON writer; optionally emit RUN_MANIFEST.
  - get_logger:         get a bound structlog logger.
  - LogRecord:          Pydantic schema of the minimum shared record shape.
  - MIN_FIELDS:         set of minimum field names every log record must carry.
"""

from .schema import MIN_FIELDS, LogRecord
from .structlog_setup import configure_logging, get_logger

__all__ = ["LogRecord", "MIN_FIELDS", "configure_logging", "get_logger"]
