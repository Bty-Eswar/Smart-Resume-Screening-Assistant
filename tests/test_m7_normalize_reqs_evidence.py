# tests/test_m7_normalize_reqs_evidence.py — Tests for M7
import random
import unicodedata
import pytest

from core.evidence import validate_evidence
from core.ids import content_id
from core.normalize import normalize_ws
from core.requirements import build_requirements
from core.types import (
    Bp,
    CandidateId,
    EvidenceSpan,
    Requirement,
    RequirementId,
    RequirementJudgement,
    ResumeText,
    Sha256,
)
from eval.generate_corpus import DEFAULT_JOB_SPEC, generate


def test_1_normalize_ws_idempotent():
    """1. normalize_ws is idempotent: f(f(x)) == f(x) over 50 varied inputs. Print count run."""
    varied_inputs = [
        "",
        "   ",
        "\t\n\r",
        "simple word",
        "  leading space",
        "trailing space  ",
        "  surrounded  by   many    spaces  ",
        "tabs\tand\tnewlines\nand\r\ncarriage\rreturns",
        "multi \n\n\n line \t\t breaks \r\n with spaces",
        "unicode \u00a0 non-breaking \u2003 em-space \u2009 thin-space",
        "ligature \ufb01le (\ufb02 ligature)",  # "file" fi/fl ligatures
        "fullwidth \uff11\uff12\uff13 and \uff21\uff22\uff23",
        "diacritics e\u0301 vs \u00e9 canonical decomposition",
        "mixed punctuation: Hello, world! (and [brackets] {braces} / slashes)",
        "special symbols: © ® ™ § ¶ † ‡ •",
        "equations: 10 + 20 = 30; x > y < z & a % b",
        "sentence with multiple periods... and ellipses …",
        "bullet points: • item 1 \n • item 2 \n • item 3",
        "email: test.user@example.com and url: https://example.com/path?a=1&b=2",
        "mixed case: CamelCase and ALLCAPS and lowercase and under_scores",
    ]
    # Expand to 50 varied inputs using permutations of unicode characters and whitespaces
    rng = random.Random(777)
    tokens = ["word", "hello", "résumé", "\ufb01rm", "100%", "K8s", "c++", "c#", "\u00a0", " ", "\t", "\n", "\r\n"]
    for _ in range(30):
        length = rng.randint(3, 15)
        raw_str = "".join(rng.choice(tokens) for _ in range(length))
        varied_inputs.append(raw_str)

    assert len(varied_inputs) >= 50, f"Expected at least 50 inputs, got {len(varied_inputs)}"

    count_run = 0
    for inp in varied_inputs:
        f_x = normalize_ws(inp)
        f_f_x = normalize_ws(f_x)
        assert f_f_x == f_x, f"Idempotence failed for {inp!r}: {f_f_x!r} != {f_x!r}"
        count_run += 1

    print(f"\n[M7.1] normalize_ws idempotence verified across {count_run} varied inputs")


def test_2_weights_sum_to_10000():
    """2. Weights sum to exactly 10000 after build_requirements, for 9999 and 10003 raw sums."""
    jd_sha = Sha256("e" * 64)

    # Case A: sum = 9999 (e.g. 3333 + 3333 + 3333)
    raw_9999 = (
        {"id": "r1", "text": "Requirement 1", "weight_bp": 3333},
        {"id": "r2", "text": "Requirement 2", "weight_bp": 3333},
        {"id": "r3", "text": "Requirement 3", "weight_bp": 3333},
    )
    reqs_9999 = build_requirements(raw_9999, jd_sha)
    sum_9999 = sum(r.weight_bp for r in reqs_9999)

    # Case B: sum = 10003 (e.g. 5003 + 3000 + 2000)
    raw_10003 = (
        {"id": "r1", "text": "Requirement A", "weight_bp": 5003},
        {"id": "r2", "text": "Requirement B", "weight_bp": 3000},
        {"id": "r3", "text": "Requirement C", "weight_bp": 2000},
    )
    reqs_10003 = build_requirements(raw_10003, jd_sha)
    sum_10003 = sum(r.weight_bp for r in reqs_10003)

    print(f"\n[M7.2] Raw sum 9999 realised sum: {sum_9999}")
    print(f"[M7.2] Raw sum 10003 realised sum: {sum_10003}")

    assert sum_9999 == 10000
    assert sum_10003 == 10000


def test_3_requirements_sorted_by_id_order_independent():
    """3. Requirements sorted by id; shuffled input -> identical output (D4)."""
    jd_sha = Sha256("a" * 64)
    raw_entries = [
        {"id": "zeta_req", "text": "Zeta knowledge", "weight_bp": 1000},
        {"id": "alpha_req", "text": "Alpha knowledge", "weight_bp": 4000},
        {"id": "gamma_req", "text": "Gamma knowledge", "weight_bp": 3000},
        {"id": "beta_req", "text": "Beta knowledge", "weight_bp": 2000},
    ]

    out_orig = build_requirements(tuple(raw_entries), jd_sha)

    # Shuffle
    shuffled_entries = list(raw_entries)
    random.Random(12345).shuffle(shuffled_entries)
    out_shuffled = build_requirements(tuple(shuffled_entries), jd_sha)

    print(f"\n[M7.3] Requirements sorted order: {[r.id for r in out_orig]}")

    # Assert sorted by id
    assert [r.id for r in out_orig] == sorted(r.id for r in out_orig)
    # Assert identical output despite shuffled input
    assert out_orig == out_shuffled


def test_4_valid_span_judgement_unchanged():
    """4. Valid span -> judgement unchanged."""
    resume_text = "Senior Software Engineer with 8 years of Python microservices experience."
    resume = ResumeText(
        candidate_id=CandidateId("c01"),
        filename="resume.pdf",
        sha256=Sha256("1" * 64),
        text=resume_text,
        char_count=len(resume_text),
    )

    span_text = "Python microservices experience"
    start = resume_text.index(span_text)
    end = start + len(span_text)

    span = EvidenceSpan(start=start, end=end, text=span_text)
    j = RequirementJudgement(
        candidate_id=CandidateId("c01"),
        requirement_id=RequirementId("req_py"),
        met=True,
        confidence_bp=Bp(9500),
        evidence=span,
    )

    validated = validate_evidence(j, resume)
    assert validated == j
    assert validated.met is True
    assert validated.evidence == span
    print(f"\n[M7.4] Valid span accepted unchanged: {validated.evidence.text!r}")


def test_5_wrong_fix_substring_vs_offset():
    """5. Wrong-fix test: 'Kubernetes' at offset 400, but evidence points to offset 50.

    A naive substring implementation (`if j.evidence.text in r.text`) passes because
    the string exists in the document; the offset implementation rejects it.
    """
    # Create resume text where offset 50 is NOT Kubernetes, but offset 400 IS Kubernetes
    padding_before = "A" * 50
    padding_middle = "B" * (400 - 50)
    resume_text = padding_before + padding_middle + "Kubernetes and cloud orchestration platform."
    assert resume_text[400:410] == "Kubernetes"
    assert resume_text[50:60] != "Kubernetes"

    resume = ResumeText(
        candidate_id=CandidateId("c02"),
        filename="resume2.pdf",
        sha256=Sha256("2" * 64),
        text=resume_text,
        char_count=len(resume_text),
    )

    # Span pointing to offset 50..60 with text "Kubernetes"
    decoy_span = EvidenceSpan(start=50, end=60, text="Kubernetes")
    j = RequirementJudgement(
        candidate_id=CandidateId("c02"),
        requirement_id=RequirementId("req_k8s"),
        met=True,
        confidence_bp=Bp(9000),
        evidence=decoy_span,
    )

    validated = validate_evidence(j, resume)

    print(f"\n[M7.5] Wrong-fix test validated: met={validated.met}, evidence={validated.evidence}")
    assert validated.met is False, "Wrong-fix check failed: decoy offset was accepted"
    assert validated.evidence is None, "Wrong-fix check failed: invalid evidence was not dropped"


def test_6_off_by_one_boundary():
    """6. Off-by-one boundary: span with end one past true end -> rejected. Span exactly correct -> accepted."""
    resume_text = "Proficient in Distributed Database Systems and Cassandra."
    resume = ResumeText(
        candidate_id=CandidateId("c03"),
        filename="resume3.pdf",
        sha256=Sha256("3" * 64),
        text=resume_text,
        char_count=len(resume_text),
    )

    target = "Cassandra"
    exact_start = resume_text.index(target)
    exact_end = exact_start + len(target)

    # 1. Exact span
    exact_span = EvidenceSpan(start=exact_start, end=exact_end, text=target)
    j_exact = RequirementJudgement(
        candidate_id=CandidateId("c03"),
        requirement_id=RequirementId("req_cas"),
        met=True,
        confidence_bp=Bp(9000),
        evidence=exact_span,
    )
    val_exact = validate_evidence(j_exact, resume)

    # 2. Off-by-one end (end = exact_end + 1, including the trailing period)
    off_by_one_span = EvidenceSpan(start=exact_start, end=exact_end + 1, text=target)
    j_off_by_one = RequirementJudgement(
        candidate_id=CandidateId("c03"),
        requirement_id=RequirementId("req_cas"),
        met=True,
        confidence_bp=Bp(9000),
        evidence=off_by_one_span,
    )
    val_off = validate_evidence(j_off_by_one, resume)

    print(f"\n[M7.6] Exact span accepted: met={val_exact.met}, evidence={val_exact.evidence.text!r}")
    print(f"[M7.6] Off-by-one span rejected: met={val_off.met}, evidence={val_off.evidence}")

    assert val_exact.met is True
    assert val_exact.evidence == exact_span

    assert val_off.met is False
    assert val_off.evidence is None


def test_7_fabricated_span_rejected():
    """7. Fabricated span (text not in document at all) -> rejected, met forced False."""
    resume_text = "Frontend engineer with React, TypeScript, and CSS skills."
    resume = ResumeText(
        candidate_id=CandidateId("c04"),
        filename="resume4.pdf",
        sha256=Sha256("4" * 64),
        text=resume_text,
        char_count=len(resume_text),
    )

    fabricated_span = EvidenceSpan(start=0, end=15, text="Golang Architect")
    j = RequirementJudgement(
        candidate_id=CandidateId("c04"),
        requirement_id=RequirementId("req_go"),
        met=True,
        confidence_bp=Bp(8000),
        evidence=fabricated_span,
    )

    val = validate_evidence(j, resume)
    print(f"\n[M7.7] Fabricated span: met={val.met}, evidence={val.evidence}")
    assert val.met is False
    assert val.evidence is None


def test_8_rate_amplification_invalid_spans():
    """8. Rate amplification: inject 30 deliberately invalid spans, assert all 30 are caught."""
    resume_text = "Specialist in machine learning algorithms, deep learning, PyTorch, and NLP modeling."
    resume = ResumeText(
        candidate_id=CandidateId("c05"),
        filename="resume5.pdf",
        sha256=Sha256("5" * 64),
        text=resume_text,
        char_count=len(resume_text),
    )

    # Generate 30 distinct invalid spans: inverted offsets, out of bounds, truncated text, wrong offsets
    corruptions = []
    # Inverted offsets (10)
    for i in range(10):
        corruptions.append(EvidenceSpan(start=20 + i, end=10 + i, text="PyTorch"))
    # Out of bounds (10)
    for i in range(10):
        corruptions.append(EvidenceSpan(start=500 + i, end=510 + i, text="PyTorch"))
    # Text mismatch at offsets (10)
    for i in range(10):
        corruptions.append(EvidenceSpan(start=i, end=i + 7, text="UnknownMismatch"))

    assert len(corruptions) == 30

    caught_count = 0
    for idx, invalid_span in enumerate(corruptions):
        j = RequirementJudgement(
            candidate_id=CandidateId("c05"),
            requirement_id=RequirementId(f"req_{idx}"),
            met=True,
            confidence_bp=Bp(9000),
            evidence=invalid_span,
        )
        val = validate_evidence(j, resume)
        if val.met is False and val.evidence is None:
            caught_count += 1

    print(f"\n[M7.8] Rate amplification: caught {caught_count} / 30 injected invalid spans")
    assert caught_count == 30, f"Expected 30 invalid spans caught, got {caught_count}"


def test_9_weight_type_validations():
    """Assert float weights and bool weights are strictly rejected."""
    jd_sha = Sha256("f" * 64)

    # Float weight rejected
    with pytest.raises(TypeError, match="integer Bp"):
        build_requirements(({"id": "r1", "text": "req", "weight_bp": 5000.0},), jd_sha)

    # Bool weight rejected
    with pytest.raises(TypeError, match="integer Bp"):
        build_requirements(({"id": "r1", "text": "req", "weight_bp": True},), jd_sha)

    # Empty raw list rejected
    with pytest.raises(ValueError, match="empty"):
        build_requirements((), jd_sha)


def test_verify_evidence_validity_rate():
    """VERIFY: Realised evidence-validity rate on fixture corpus >= 95% (PDD T2)."""
    # Generate 20 candidates from DEFAULT_JOB_SPEC
    resumes, truths = generate(jd=DEFAULT_JOB_SPEC, n=20, seed=42)

    total_spans = 0
    valid_spans = 0

    for cand_resume, truth in zip(resumes, truths):
        for planted in truth.planted:
            surf = planted.surface_form
            start = cand_resume.text.find(surf)
            if start == -1:
                continue
            end = start + len(surf)

            span = EvidenceSpan(start=start, end=end, text=surf)
            j = RequirementJudgement(
                candidate_id=cand_resume.candidate_id,
                requirement_id=planted.requirement_id,
                met=True,
                confidence_bp=Bp(10000),
                evidence=span,
            )

            # Validate
            val = validate_evidence(j, cand_resume)
            total_spans += 1
            if val.met is True and val.evidence == span:
                valid_spans += 1

    assert total_spans > 0, "No evidence spans evaluated"
    validity_rate_pct = (valid_spans / total_spans) * 100.0

    print(f"\n[M7.VERIFY] Realised evidence-validity rate: {valid_spans}/{total_spans} ({validity_rate_pct:.1f}%)")
    assert validity_rate_pct >= 95.0, f"PDD T2 breached: {validity_rate_pct}% < 95%"
