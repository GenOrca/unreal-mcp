# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Action coverage enforcement (offline, no Unreal needed).

Every catalog action must be exercised by an in-editor unittest
(Plugins/.../tests/test_<domain>.py references "ue_<action>"), OR be listed
in KNOWN_UNTESTED below as acknowledged technical debt.

Why: the dispatcher auto-exposes any ue_* function. Without this gate, a new
action could ship with zero behavior test and all other gates stay green.
This makes "add an action without a test" a conscious, reviewable choice
(you must edit KNOWN_UNTESTED) rather than a silent gap.

KNOWN_UNTESTED is debt to shrink, not to grow. The stale-entry check fails if
an allowlisted action becomes tested or disappears, so the list self-cleans.
"""

import re
from pathlib import Path

import pytest

from unreal_mcp.dispatchers._catalog import CATALOG

PLUGIN_TESTS = (
    Path(__file__).resolve().parents[2]
    / "Plugins" / "UnrealMCPython" / "Content" / "Python" / "UnrealMCPython" / "tests"
)

# Actions not routed as ue_<action> over TCP — covered by mcp-server pytest instead.
SPECIAL = {"util": {"execute_python", "livecoding_compile"}}

# ── Technical debt: actions with no in-editor behavior test yet. SHRINK over time. ──
# Adding a new action? Write a test in test_<domain>.py instead of adding it here.
KNOWN_UNTESTED: dict[str, set[str]] = {
    # PIE start/stop change the editor play mode asynchronously; running them in the
    # headless suite (which never ticks between calls) would leave the editor in PIE.
    # Verified manually through the MCP chain instead.
    "util": {"start_pie", "stop_pie"},
    # save_current_level can raise a modal Save-As dialog on an untitled level,
    # which would hang the headless suite; save_all_levels is grouped with it.
    # Verified manually instead.
    "level": {"save_current_level", "save_all_levels"},
}


def _referenced(domain: str) -> set[str]:
    tf = PLUGIN_TESTS / f"test_{domain}.py"
    if not tf.exists():
        return set()
    return set(re.findall(r"ue_(\w+)", tf.read_text(encoding="utf-8")))


def _allowed(domain: str) -> set[str]:
    return SPECIAL.get(domain, set()) | KNOWN_UNTESTED.get(domain, set())


@pytest.mark.parametrize("domain", sorted(CATALOG))
def test_every_action_is_tested_or_allowlisted(domain):
    referenced = _referenced(domain)
    untested = [
        a for a in CATALOG[domain]
        if a not in referenced and a not in _allowed(domain)
    ]
    assert not untested, (
        f"{domain}: these actions have no in-editor test and are not allowlisted: "
        f"{untested}. Add a test in test_{domain}.py, or (consciously) add them to "
        f"KNOWN_UNTESTED in test_coverage.py."
    )


def test_no_stale_allowlist_entries():
    """KNOWN_UNTESTED must not contain actions that are now tested or no longer exist."""
    stale = []
    for domain, actions in KNOWN_UNTESTED.items():
        referenced = _referenced(domain)
        for a in actions:
            if a not in CATALOG.get(domain, {}):
                stale.append(f"{domain}.{a} (not in catalog)")
            elif a in referenced:
                stale.append(f"{domain}.{a} (now tested — remove from allowlist)")
    assert not stale, f"Stale KNOWN_UNTESTED entries: {stale}"


def test_plugin_tests_dir_exists():
    """Guard: if the layout moves, fail loudly instead of silently passing coverage."""
    assert PLUGIN_TESTS.is_dir(), f"Plugin tests dir not found: {PLUGIN_TESTS}"
