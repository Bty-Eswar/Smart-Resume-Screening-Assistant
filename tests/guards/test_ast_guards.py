# tests/guards/test_ast_guards.py — Tests for M2: AST Charter Enforcers
import ast
from pathlib import Path
import pytest

from tests.guards.ast_guards import (
    Violation,
    GuardTargetMissing,
    GuardTargetEmpty,
    find_float_annotations,
    find_clock_reads,
    find_uuid_usage,
    find_set_returns,
    find_io_imports,
    find_timing_fields,
    scan_directory,
    ALL_GUARDS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORE_DIR = REPO_ROOT / "core"


def test_guard_1_fault_injection_d1_float(tmp_path):
    """1. Fault injection D1: float variable annotation triggers D1 violation."""
    code = "bad_score: float = 0.95\n"
    tree = ast.parse(code, filename="bad_float.py")
    violations = find_float_annotations(tree, file_path="bad_float.py")

    print(f"\n[M2.1] D1 Fault Injection: found {len(violations)} violation(s)")
    for v in violations:
        print(f"  {v.rule} at {v.file}:{v.lineno} — {v.detail}")

    assert len(violations) == 1, f"Expected exactly 1 violation, got {len(violations)}"
    assert violations[0].rule == "D1"


def test_guard_2_fault_injection_d2_clock(tmp_path):
    """1. Fault injection D2: clock read (datetime.now) triggers D2 violation."""
    code = "import datetime\ncurrent_time = datetime.now()\n"
    tree = ast.parse(code, filename="bad_clock.py")
    violations = find_clock_reads(tree, file_path="bad_clock.py")

    print(f"\n[M2.2] D2 Fault Injection: found {len(violations)} violation(s)")
    for v in violations:
        print(f"  {v.rule} at {v.file}:{v.lineno} — {v.detail}")

    assert len(violations) == 1, f"Expected exactly 1 violation, got {len(violations)}"
    assert violations[0].rule == "D2"


def test_guard_3_fault_injection_d3_uuid(tmp_path):
    """1. Fault injection D3: UUID usage triggers D3 violation."""
    code = "import uuid\nnew_id = uuid.uuid4()\n"
    tree = ast.parse(code, filename="bad_uuid.py")
    violations = find_uuid_usage(tree, file_path="bad_uuid.py")

    print(f"\n[M2.3] D3 Fault Injection: found {len(violations)} violation(s)")
    for v in violations:
        print(f"  {v.rule} at {v.file}:{v.lineno} — {v.detail}")

    assert len(violations) >= 1, "Expected violation for UUID import"
    assert any(v.rule == "D3" for v in violations)


def test_guard_4_fault_injection_d4_set_returns(tmp_path):
    """1. Fault injection D4: returning a set literal triggers D4 violation."""
    code = "def get_items():\n    return {'item_a', 'item_b'}\n"
    tree = ast.parse(code, filename="bad_set.py")
    violations = find_set_returns(tree, file_path="bad_set.py")

    print(f"\n[M2.4] D4 Fault Injection: found {len(violations)} violation(s)")
    for v in violations:
        print(f"  {v.rule} at {v.file}:{v.lineno} — {v.detail}")

    assert len(violations) == 1, f"Expected exactly 1 violation, got {len(violations)}"
    assert violations[0].rule == "D4"


def test_guard_5_fault_injection_layering_io_imports(tmp_path):
    """1. Fault injection layering: importing os in core triggers layering violation."""
    code = "import os\n"
    tree = ast.parse(code, filename="bad_layering.py")
    violations = find_io_imports(tree, file_path="bad_layering.py")

    print(f"\n[M2.5] Layering Fault Injection: found {len(violations)} violation(s)")
    for v in violations:
        print(f"  {v.rule} at {v.file}:{v.lineno} — {v.detail}")

    assert len(violations) == 1, f"Expected exactly 1 violation, got {len(violations)}"
    assert violations[0].rule == "layering"


def test_guard_6_fault_injection_d14_timing_fields(tmp_path):
    """1. Fault injection D14: timing field on a non-Timing dataclass triggers D14 violation."""
    code = "from dataclasses import dataclass\n@dataclass\nclass ResultRecord:\n    elapsed_ms: int\n"
    tree = ast.parse(code, filename="bad_timing.py")
    violations = find_timing_fields(tree, file_path="bad_timing.py")

    print(f"\n[M2.6] D14 Fault Injection: found {len(violations)} violation(s)")
    for v in violations:
        print(f"  {v.rule} at {v.file}:{v.lineno} — {v.detail}")

    assert len(violations) == 1, f"Expected exactly 1 violation, got {len(violations)}"
    assert violations[0].rule == "D14"


def test_wrong_fix_grep_decoy():
    """2. Wrong-fix test: string literal 'float' and comment '# float' yield ZERO violations."""
    code = '''# float comment here
def describe():
    """Docstring containing float."""
    label = "float"
    return label
'''
    tree = ast.parse(code, filename="decoy.py")
    violations = find_float_annotations(tree, file_path="decoy.py")

    print(f"\n[M2.Decoy] Grep decoy violations: {len(violations)}")
    assert len(violations) == 0, (
        f"AST scanner must not match comments or string literals; found {len(violations)} false positive(s)"
    )


def test_scanned_file_count_is_nonzero():
    """3. Assert guard suite scans a nonzero number of files in core/ and print the count."""
    scanned_files, _ = scan_directory(CORE_DIR)
    file_count = len(scanned_files)

    print(f"\n[M2.Count] Realised files scanned in core/: {file_count}")
    for p in scanned_files:
        print(f"  - {Path(p).name}")

    assert file_count > 0, "No files found to scan in core/"


def test_empty_vs_missing_directory_exceptions(tmp_path):
    """4. Empty-vs-missing: nonexistent dir raises GuardTargetMissing; empty dir raises GuardTargetEmpty."""
    nonexistent = tmp_path / "non_existent_folder_xyz"
    empty_folder = tmp_path / "empty_folder"
    empty_folder.mkdir()

    with pytest.raises(GuardTargetMissing) as excinfo_missing:
        scan_directory(nonexistent)
    print(f"\n[M2.EmptyVsMissing] Caught missing target: {excinfo_missing.value}")

    with pytest.raises(GuardTargetEmpty) as excinfo_empty:
        scan_directory(empty_folder)
    print(f"[M2.EmptyVsMissing] Caught empty target:   {excinfo_empty.value}")


def test_real_core_passes_all_guards():
    """5. Run all six guards against real core/ and assert zero violations, printing per-rule counts."""
    scanned_files, violations = scan_directory(CORE_DIR)

    # Compute per-rule violations
    counts_by_rule = {rule_name: 0 for rule_name, _ in ALL_GUARDS}
    for v in violations:
        counts_by_rule[v.rule] = counts_by_rule.get(v.rule, 0) + 1

    print(f"\n[M2.RealCore] Scanned {len(scanned_files)} files in core/. Violations per rule:")
    for rule, count in sorted(counts_by_rule.items()):
        print(f"  Rule {rule:8s}: {count} violation(s)")

    if violations:
        for v in violations:
            print(f"  VIOLATION: {v.rule} in {v.file}:{v.lineno} — {v.detail}")

    assert len(violations) == 0, f"Found {len(violations)} violation(s) in core/"
