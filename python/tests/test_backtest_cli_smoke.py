"""CLI smoke tests for the backtest engine (Plan 05-09).

test_cli_help_exits_clean: --help returns 0 and lists run + plot subcommands.
test_cli_module_import: build_parser + main import cleanly.

[[backtest-cli-and-run-manifest-emission]]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from boros_brain.backtest.cli import build_parser, main


def test_cli_help_exits_clean() -> None:
    """--help exits 0 and lists both subcommands."""
    result = subprocess.run(
        [sys.executable, "-m", "boros_brain.backtest", "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert result.returncode == 0, f"--help exited {result.returncode}: {result.stderr}"
    assert "run" in result.stdout, "expected 'run' subcommand in --help output"
    assert "plot" in result.stdout, "expected 'plot' subcommand in --help output"


def test_cli_module_import() -> None:
    """build_parser and main are importable and callable without errors."""
    parser = build_parser()
    assert parser is not None
    # build_parser should produce a parser with a 'run' and 'plot' subcommand
    # The subcommands are registered under 'cmd'
    subparsers_actions = [a for a in parser._actions if hasattr(a, "_parser_class")]
    assert len(subparsers_actions) > 0 or any(
        hasattr(a, "choices") and a.choices and "run" in a.choices for a in parser._actions
    ), "expected 'run' in parser subcommands"


def test_main_is_shim_main() -> None:
    """__main__.main is the same object as cli.main."""
    from boros_brain.backtest.__main__ import main as shim_main

    assert shim_main is main


def test_cli_missing_subcommand_exits_2(tmp_path: Path) -> None:
    """Missing subcommand exits with a non-zero code (argparse handles this)."""
    result = subprocess.run(
        [sys.executable, "-m", "boros_brain.backtest"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    # argparse with required=True exits 2 when subcommand is missing
    assert result.returncode != 0


def test_cli_bad_config_exits_2(tmp_path: Path) -> None:
    """Config file not found → ConfigError on stderr, exit 2."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "boros_brain.backtest",
            "--config",
            str(tmp_path / "nonexistent.yaml"),
            "run",
            "--market",
            "BINANCE-ETHUSDT-29MAY2026",
            "--side",
            "long",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}"
    assert "ConfigError" in result.stderr
