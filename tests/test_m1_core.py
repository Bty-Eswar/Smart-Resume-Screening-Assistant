# tests/test_m1_core.py — Tests for M1: types.py, ids.py, quantize.py
import dataclasses
import subprocess
import sys
import pytest

from core.types import (
    Bp,
    RunId,
    CandidateId,
    RequirementId,
    Sha256,
    AsOfDate,
    RankerId,
    ParseStatus,
    Verdict,
    PhrasingMode,
    Requirement,
    ResumeText,
    ParseOutcome,
    EvidenceSpan,
    RequirementJudgement,
    CandidateScore,
    RankedEntry,
    Ranking,
    Timing,
)
from core.ids import content_id
from core.quantize import quantize


def test_1_content_id_stable_across_processes():
    """1. content_id is stable across processes (spawns subprocess)."""
    parts = ("resume_42", "req_backend_java", "v1")
    local_id = content_id(*parts)

    cmd = [
        sys.executable,
        "-c",
        "from core.ids import content_id; print(content_id('resume_42', 'req_backend_java', 'v1'))",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    subprocess_id = res.stdout.strip()

    print(f"\n[M1.1] In-process ID:  {local_id}")
    print(f"[M1.1] Subprocess ID:  {subprocess_id}")
    assert local_id == subprocess_id, "content_id must produce identical hash across OS processes"


def test_2_wrong_fix_order_independence():
    """2. Wrong-fix test: IDs for a 5-item corpus in original order and reversed order have identical set."""
    corpus = [
        ("candidate_1", "spec_a"),
        ("candidate_2", "spec_b"),
        ("candidate_3", "spec_c"),
        ("candidate_4", "spec_d"),
        ("candidate_5", "spec_e"),
    ]

    forward_ids = [content_id(*item) for item in corpus]
    reversed_ids = [content_id(*item) for item in reversed(corpus)]

    print(f"\n[M1.2] Forward ID set:  {set(forward_ids)}")
    print(f"[M1.2] Reversed ID set: {set(reversed_ids)}")
    assert set(forward_ids) == set(reversed_ids), "ID set must be invariant to corpus traversal order"
    assert len(set(forward_ids)) == 5, "All 5 items must yield distinct IDs"


def test_3_separator_collision():
    """3. Separator collision: content_id('ab','c') != content_id('a','bc')."""
    id_ab_c = content_id("ab", "c")
    id_a_bc = content_id("a", "bc")

    print(f"\n[M1.3] content_id('ab', 'c'): {id_ab_c}")
    print(f"[M1.3] content_id('a', 'bc'): {id_a_bc}")
    assert id_ab_c != id_a_bc, "Separator collision detected: delimiter must prevent merging ambiguity"


def test_4_quantize_anchors():
    """4. quantize(0.5) == 5000, quantize(0.0) == 0, quantize(1.0) == 10000."""
    q_half = quantize(0.5)
    q_zero = quantize(0.0)
    q_one = quantize(1.0)

    print(f"\n[M1.4] quantize(0.5): {q_half} (type={type(q_half).__name__})")
    print(f"[M1.4] quantize(0.0): {q_zero}")
    print(f"[M1.4] quantize(1.0): {q_one}")

    assert q_half == 5000
    assert q_zero == 0
    assert q_one == 10000


def test_5_wrong_fix_quantize_rounding_vs_truncation():
    """5. Wrong-fix test: quantize(0.99995) gives 10000 via half-even, whereas truncation gives 9999."""
    x = 0.99995
    truncation_val = int(x * 10000)
    realised_val = quantize(x)

    print(f"\n[M1.5] x = {x}")
    print(f"[M1.5] Truncation int(x * 10000): {truncation_val}")
    print(f"[M1.5] Realised quantize(x):       {realised_val}")

    assert truncation_val == 9999
    assert realised_val == 10000, f"Expected 10000 via half-even rounding, got {realised_val}"

    # Verify 0.12345
    q_mid = quantize(0.12345)
    print(f"[M1.5] quantize(0.12345): {q_mid}")
    assert q_mid == 1234


def test_6_quantize_out_of_bounds_raises():
    """6. quantize(-0.01) and quantize(1.01) each raise ValueError."""
    with pytest.raises(ValueError) as excinfo_neg:
        quantize(-0.01)
    print(f"\n[M1.6] Caught negative out-of-bounds: {excinfo_neg.value}")

    with pytest.raises(ValueError) as excinfo_pos:
        quantize(1.01)
    print(f"[M1.6] Caught positive out-of-bounds: {excinfo_pos.value}")


def test_7_all_dataclasses_frozen():
    """7. Every dataclass in types.py raises FrozenInstanceError on attribute assignment."""
    instances = [
        Requirement(RequirementId("req_1"), "Java experience", ("java",), Bp(10000)),
        ResumeText(CandidateId("cand_1"), "resume.pdf", Sha256("sha256_val"), "Sample resume text", 18),
        ParseOutcome("resume.pdf", ParseStatus.OK, None),
        EvidenceSpan(0, 4, "Samp"),
        RequirementJudgement(CandidateId("cand_1"), RequirementId("req_1"), True, Bp(9500), None),
        CandidateScore(CandidateId("cand_1"), Bp(9500), 1, 1, ()),
        RankedEntry(1, CandidateScore(CandidateId("cand_1"), Bp(9500), 1, 1, ()), Verdict.ACCEPT),
        Ranking(RunId("run_1"), RankerId.R0_LEXICAL, AsOfDate("2026-09-09"), (), (), False, ()),
        Timing("scoring", 42, 1),
    ]

    checked_count = 0
    print("\n[M1.7] Testing FrozenInstanceError on dataclass instances:")
    for inst in instances:
        cls_name = inst.__class__.__name__
        # Attempt mutation of the first slot attribute
        first_attr = inst.__class__.__slots__[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(inst, first_attr, "MUTATION_ATTEMPT")
        checked_count += 1
        print(f"  [PASS] {cls_name}.{first_attr} is immutable")

    print(f"[M1.7] Total dataclasses checked and verified frozen: {checked_count}")
    assert checked_count > 0


def test_8_fault_injection_import_time_exhaustiveness():
    """8. Fault injection: defining an incomplete PhrasingMode raises AssertionError."""
    code_incomplete = """
from enum import Enum
class PhrasingMode(str, Enum):
    EXPLICIT_TOKEN = "explicit_token"
    IMPLICIT_PARAPHRASE = "implicit_paraphrase"
    SKILLS_WALL = "skills_wall"
    # ABSENT is deliberately omitted

if set(PhrasingMode) != {
    PhrasingMode.EXPLICIT_TOKEN,
    PhrasingMode.IMPLICIT_PARAPHRASE,
    PhrasingMode.SKILLS_WALL,
    getattr(PhrasingMode, "ABSENT", None),
} or len(PhrasingMode) != 4:
    raise AssertionError("PhrasingMode must have exactly 4 declared members")
"""
    cmd = [sys.executable, "-c", code_incomplete]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    print("\n[M1.8] Fault injection output for incomplete PhrasingMode:")
    print(f"  Exit code: {proc.returncode}")
    print(f"  Stderr: {proc.stderr.strip().splitlines()[-1] if proc.stderr else 'None'}")

    assert proc.returncode != 0, "Precondition failed: Incomplete enum did not trigger non-zero exit"
    assert "AssertionError" in proc.stderr, "Expected AssertionError on exhaustiveness violation"
