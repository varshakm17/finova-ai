"""Global pytest fixtures and test configuration for Finova AI.

Configures markers and command-line options for selective live network testing,
ensuring normal CI and developer test runs remain 100% offline and deterministic.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line options to pytest."""
    parser.addoption(
        "--run-live-sec",
        action="store_true",
        default=False,
        help="Run live SEC EDGAR integration tests (requires network and compliant User-Agent)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Conditionally skip tests marked with live_sec unless explicitly requested."""
    run_live = config.getoption("--run-live-sec", default=False)
    markexpr = config.option.markexpr

    # If --run-live-sec is passed, or -m live_sec is specified, do not skip
    if run_live or "live_sec" in markexpr:
        return

    skip_live_sec = pytest.mark.skip(
        reason="Live SEC EDGAR test skipped by default. Run with --run-live-sec or -m live_sec to execute."
    )
    for item in items:
        if "live_sec" in item.keywords:
            item.add_marker(skip_live_sec)
