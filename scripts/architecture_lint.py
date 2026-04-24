#!/usr/bin/env python3
"""Architecture drift lint (INFRA-09, PROTO-02).

Walks python/src/ via AST + ts/src/ via regex; diffs against docs/architecture.yml.
Exit 0 on clean, exit 1 with violation list on drift.

Granularity (per RESEARCH §Pattern 5 granularity rule):
  - Declare: modules + public top-level functions + CLI commands + config knobs + external deps
  - Do NOT declare: private helpers, dataclass fields, methods on non-public classes

Usage:
  python scripts/architecture_lint.py                        # defaults: docs/architecture.yml, python/src, ts/src
  python scripts/architecture_lint.py --yml docs/architecture.yml --src python/src --ts-src ts/src
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

import yaml


def extract_python_inventory(src_root: Path) -> dict:
    """Walk src_root, extract module IDs and public top-level function names.

    Module ID convention:
      python/src/boros_brain/config/schema.py -> brain.config.schema
      (package root = process name: boros_brain -> brain)
    """
    modules: set[str] = set()
    functions: set[tuple[str, str]] = set()  # (module_id, function_name)

    for py in sorted(src_root.rglob("*.py")):
        # Skip __init__.py entirely — they are namespace/package markers, not module nodes.
        # Skip private modules and test files.
        if py.name.startswith("_"):
            continue
        if "test" in py.name.lower():
            continue

        rel = py.relative_to(src_root)
        rel_parts = rel.with_suffix("").parts

        # Skip migration directories (Alembic internals — not architecture nodes)
        if "migrations" in rel_parts:
            continue

        if not rel_parts:
            continue

        # Map package root to process name
        package_root = rel_parts[0]
        if package_root == "boros_brain":
            process_name = "brain"
        elif package_root == "boros_hands":
            process_name = "hands"
        else:
            # Unknown package root: use as-is (supports fixture trees)
            process_name = package_root

        sub_parts = list(rel_parts[1:])
        if not sub_parts:
            continue  # e.g. boros_brain/__init__.py — not a module node

        mod_id = ".".join([process_name] + sub_parts)
        modules.add(mod_id)

        # Extract public top-level functions
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    functions.add((mod_id, node.name))

    return {"modules": modules, "functions": functions}


def extract_ts_inventory(src_root: Path) -> dict:
    """Walk src_root, extract TS module IDs (no function extraction — regex-lite)."""
    modules: set[str] = set()

    for ts in sorted(src_root.rglob("*.ts")):
        if ts.name.endswith(".test.ts") or ts.name.endswith(".spec.ts"):
            continue

        rel = ts.relative_to(src_root)
        rel_parts = rel.with_suffix("").parts

        if not rel_parts:
            continue

        package_root = rel_parts[0]
        if package_root == "boros_hands":
            process_name = "hands"
        elif package_root == "boros_brain":
            process_name = "brain"
        else:
            process_name = package_root

        sub_parts = list(rel_parts[1:])
        if not sub_parts:
            continue

        mod_id = ".".join([process_name] + sub_parts)
        modules.add(mod_id)

    return {"modules": modules}


def compare(yml: dict, py_inv: dict, ts_inv: dict) -> list[str]:
    """Diff the code inventory against the YAML manifest; return list of violations."""
    violations: list[str] = []

    declared_modules = {
        n["id"]
        for n in yml.get("nodes", [])
        if n.get("type") == "module"
    }
    code_modules = py_inv["modules"] | ts_inv["modules"]

    # Code defines a module not declared in architecture.yml
    undeclared = code_modules - declared_modules
    for m in sorted(undeclared):
        violations.append(f"Code defines module `{m}` not declared in architecture.yml")

    # architecture.yml declares a module that doesn't exist in source
    orphaned = declared_modules - code_modules
    for m in sorted(orphaned):
        violations.append(
            f"architecture.yml declares module `{m}` not found in source tree"
        )

    # Verify every declared path actually exists on disk
    for n in yml.get("nodes", []):
        if n.get("type") != "module":
            continue
        p = n.get("path")
        if p and not Path(p).exists():
            violations.append(
                f"architecture.yml node `{n['id']}` points at missing path `{p}`"
            )

    # Python module public_function reconciliation (TS function discovery is regex-lite and not checked)
    declared_module_ids = {
        n["id"]
        for n in yml.get("nodes", [])
        if n.get("type") == "module" and n.get("path", "").endswith(".py")
    }
    # Build a map: module_id -> declared_functions (from yml)
    yml_fn_map: dict[str, set[str]] = {}
    for n in yml.get("nodes", []):
        if n.get("type") != "module" or not n.get("path", "").endswith(".py"):
            continue
        yml_fn_map[n["id"]] = set(n.get("public_functions") or [])

    # Build a map: module_id -> actual_functions (from code)
    code_fn_map: dict[str, set[str]] = {}
    for mod_id, fn_name in py_inv["functions"]:
        code_fn_map.setdefault(mod_id, set()).add(fn_name)

    for mod_id in sorted(declared_module_ids):
        declared_fns = yml_fn_map.get(mod_id, set())
        actual_fns = code_fn_map.get(mod_id, set())

        # yml declares fn not found in code
        for fn in sorted(declared_fns - actual_fns):
            violations.append(
                f"architecture.yml declares public fn `{mod_id}.{fn}` not found in code"
            )

        # code defines public fn not declared in yml (for declared modules only — drift)
        for fn in sorted(actual_fns - declared_fns):
            violations.append(
                f"Code defines public fn `{mod_id}.{fn}` not declared in architecture.yml"
            )

    return violations


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Architecture drift lint — diffs code tree against docs/architecture.yml"
    )
    ap.add_argument(
        "--yml",
        default="docs/architecture.yml",
        type=Path,
        help="Path to architecture.yml manifest (default: docs/architecture.yml)",
    )
    ap.add_argument(
        "--src",
        default="python/src",
        type=Path,
        help="Python source root (default: python/src)",
    )
    ap.add_argument(
        "--ts-src",
        default="ts/src",
        type=Path,
        help="TypeScript source root (default: ts/src)",
    )
    args = ap.parse_args()

    if not args.yml.exists():
        print(
            f"ERROR: architecture manifest not found at `{args.yml}`. "
            "Run plan 01-04 Task 1 to create it.",
            file=sys.stderr,
        )
        return 1

    yml = yaml.safe_load(args.yml.read_text(encoding="utf-8"))

    py_inv = (
        extract_python_inventory(args.src)
        if args.src.exists()
        else {"modules": set(), "functions": set()}
    )
    ts_inv = (
        extract_ts_inventory(args.ts_src)
        if args.ts_src.exists()
        else {"modules": set()}
    )

    violations = compare(yml, py_inv, ts_inv)

    if violations:
        print("\n".join(violations), file=sys.stderr)
        print(
            f"\n{len(violations)} architecture-lint violation(s) — update docs/architecture.yml",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
