"""structlog processor that redacts sensitive keys before JSON render.

Phase 1 / INFRA-12 / ASVS V7. Injected via configure_logging via the
extra_processors mechanism in structlog_setup.py.

Usage:
    from boros_brain.logging.redaction import redact_sensitive
    configure_logging(run_id, tier, logs_dir, extra_processors=[redact_sensitive])
"""

from __future__ import annotations

import re
from typing import Any

# Matches keys whose names indicate sensitive values (case-insensitive).
# Pattern covers: api_key, api-key, apikey, token, secret, private_key,
# private-key, password, and any key containing DOTENV_PRIVATE_KEY anywhere.
_SENSITIVE = re.compile(
    r"^(api[-_]?key|token|secret|private[-_]?key|password|.*dotenv_private_key.*)$",
    re.IGNORECASE,
)


def redact_sensitive(logger: Any, method_name: Any, event_dict: dict[str, Any]) -> dict[str, Any]:  # type: ignore[misc]
    """structlog processor: replace values of sensitive keys with '***'.

    Signature matches structlog's processor protocol:
        processor(logger, method_name, event_dict) -> event_dict

    Operates in-place on event_dict (structlog convention); also returns it
    so the processor chain can continue.
    """
    for k in list(event_dict.keys()):
        if _SENSITIVE.match(str(k)):
            event_dict[k] = "***"
    return event_dict
