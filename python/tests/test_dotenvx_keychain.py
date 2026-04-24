"""Operator-local smoke test: Keychain CLI round-trip (INFRA-12).

Skipped on CI (CI=true env var) and on non-macOS platforms.
Verifies that `security add-generic-password` + `security find-generic-password`
work correctly on the operator's machine — prerequisite for headless launchd boot.

Test matrix:
  test_keychain_roundtrip_marked_skip_ci — add/find/delete 'boros-bot-test-key' item
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

_SKIP_REASON = "operator-local macOS Keychain only — skipped on CI and non-macOS"
_SKIP_CONDITION = os.environ.get("CI") == "true" or sys.platform != "darwin"

SERVICE = "boros-bot-test-key"
TEST_SECRET = "test123"


@pytest.mark.skipif(_SKIP_CONDITION, reason=_SKIP_REASON)
class TestKeychainRoundtrip:
    def test_keychain_roundtrip_marked_skip_ci(self) -> None:
        """Add a test item to Keychain, retrieve it, then clean up.

        Uses -U flag on add to update-or-create so re-runs are idempotent.
        Verifies the Keychain CLI is wired correctly on this machine.
        """
        user = os.environ.get("USER", "")
        assert user, "USER env var must be set"

        # Add (or update) the test item
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s",
                SERVICE,
                "-a",
                user,
                "-w",
                TEST_SECRET,
                "-U",  # update-or-create (idempotent)
            ],
            check=True,
            capture_output=True,
        )

        # Retrieve and verify
        result = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", user, "-w"],
            check=True,
            capture_output=True,
            text=True,
        )
        retrieved = result.stdout.strip()
        assert retrieved == TEST_SECRET, f"Keychain round-trip failed: expected {TEST_SECRET!r}, got {retrieved!r}"

        # Cleanup — remove the test item
        subprocess.run(
            ["security", "delete-generic-password", "-s", SERVICE, "-a", user],
            check=True,
            capture_output=True,
        )
