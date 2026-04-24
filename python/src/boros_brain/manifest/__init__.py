"""RUN_MANIFEST writer (INFRA-06, PROTO-01).

Public API:
  - RunManifest:            Pydantic strict model describing the manifest shape.
  - build_run_manifest:     Build a RunManifest from a BotConfig via reflection.
  - write_manifest:         Emit sidecar JSON + insert into run_manifests SQLite table.
"""

from .schema import RunManifest
from .writer import build_run_manifest, write_manifest

__all__ = ["RunManifest", "build_run_manifest", "write_manifest"]
