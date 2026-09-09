# conftest.py — Determinism Charter D7 Network Guard & SDD §7 Wall Clock Budget Enforcer
import os
import socket
import stat
import time
from pathlib import Path
import pytest


class NetworkForbiddenError(RuntimeError):
    """Raised when any code under test attempts to open a network socket (D7)."""
    pass


_original_connect = socket.socket.connect
_original_create_connection = socket.create_connection


def _forbidden_connect(self, address, *args, **kwargs):
    raise NetworkForbiddenError(
        f"Network connection to {address} forbidden during test execution (Charter D7)"
    )


def _forbidden_create_connection(address, *args, **kwargs):
    raise NetworkForbiddenError(
        f"Network connection to {address} forbidden during test execution (Charter D7)"
    )


# Active across all pytest runs
socket.socket.connect = _forbidden_connect
socket.create_connection = _forbidden_create_connection

# SDD §7 Wall Clock Budget
BUDGET_SECONDS = 60.0


def pytest_sessionstart(session):
    session.start_time = time.monotonic()


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session, "start_time"):
        elapsed = time.monotonic() - session.start_time
        pct = (elapsed / BUDGET_SECONDS) * 100
        print(f"\n============ SUITE WALL CLOCK: {elapsed:.1f}s / {BUDGET_SECONDS:.1f}s BUDGET ({pct:.0f}%) ============")

        budget_limit = float(os.environ.get("PYTEST_BUDGET_SECONDS", BUDGET_SECONDS))
        if elapsed > budget_limit:
            print(f"ERROR: Suite wall clock {elapsed:.2f}s exceeded budget {budget_limit:.2f}s!")
            session.exitstatus = 1


@pytest.fixture(scope="session", autouse=True)
def protect_gold_csv():
    """Ensure eval/gold.csv is strictly read-only per D11."""
    gold_path = Path("eval/gold.csv")
    gold_path.parent.mkdir(parents=True, exist_ok=True)
    if not gold_path.exists():
        gold_path.write_text("candidate_id,gold_label\ncand_01,1\n", encoding="utf-8")

    # Set read-only (0o444)
    gold_path.chmod(stat.S_IREAD)
    yield
    # Restore write permission for cleanup if needed
    try:
        gold_path.chmod(stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass

