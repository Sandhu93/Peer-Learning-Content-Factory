"""
Root pytest configuration.

Each test run writes a timestamped log file to logs/test_YYYYMMDD_HHMMSS.log
so results are persisted without needing to copy terminal output.

The console also shows live log output with timestamps.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


# ── Timestamped log file per run ─────────────────────────────────────────────

def pytest_configure(config) -> None:
    """Create a fresh timestamped log file before the session starts."""
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"test_{timestamp}.log"

    # Attach path to config so hooks below can reference it
    config._run_log_path = log_path

    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s:%(lineno)d  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)

    # Write a header so the file is self-describing
    logging.getLogger("pytest.session").info(
        "Test session started — log: %s", log_path
    )


# ── Per-test timestamp markers ────────────────────────────────────────────────

_logger = logging.getLogger("pytest.run")


def pytest_runtest_logstart(nodeid: str, location: tuple) -> None:
    _logger.info("START  %s", nodeid)


def pytest_runtest_logreport(report) -> None:
    if report.when != "call":
        # 'setup' and 'teardown' phases are logged at debug level
        if report.failed:
            _logger.debug("SETUP/TEARDOWN FAILED  %s", report.nodeid)
        return

    outcome = report.outcome.upper()   # PASSED / FAILED / SKIPPED
    duration = f"{report.duration:.3f}s"

    if report.outcome == "passed":
        _logger.info("  %-8s  %s  (%s)", outcome, report.nodeid, duration)
    elif report.outcome == "skipped":
        reason = ""
        if hasattr(report, "wasxfail"):
            reason = report.wasxfail
        elif report.longrepr:
            reason = str(report.longrepr[-1]) if isinstance(report.longrepr, tuple) else str(report.longrepr)
        _logger.info("  %-8s  %s  — %s", outcome, report.nodeid, reason)
    else:
        _logger.error("  %-8s  %s  (%s)", outcome, report.nodeid, duration)


def pytest_sessionfinish(session, exitstatus: int) -> None:
    log = logging.getLogger("pytest.session")
    # session.testscollected is an int (count), not iterable
    log.info(
        "Session finished — exit code %d  |  collected %d items",
        exitstatus,
        session.testscollected,
    )
    log_path = getattr(session.config, "_run_log_path", None)
    if log_path:
        log.info("Full log written to: %s", log_path)
