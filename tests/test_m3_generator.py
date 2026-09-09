# tests/test_m3_generator.py — Tests for M3: eval/generate_corpus.py & Ground Truth Model
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
import pytest

from eval.generate_corpus import (
    DEFAULT_JOB_SPEC,
    CardinalityViolation,
    PhrasingMode,
    RequirementId,
    TruthRecord,
    generate,
    validate_cardinality,
)


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_1a_truth_partitions_requirements():
    """1a. Partition: every requirement appears exactly once across planted ∪ omitted."""
    resumes, truths = generate(jd=DEFAULT_JOB_SPEC, n=30, seed=42)
    all_req_ids = {r.id for r in DEFAULT_JOB_SPEC.requirements}

    checked_candidates = 0
    for cand_resume, truth in zip(resumes, truths):
        planted_ids = {p.requirement_id for p in truth.planted}
        omitted_ids = set(truth.omitted)

        # Disjoint: no requirement in both
        assert planted_ids.isdisjoint(omitted_ids), (
            f"Candidate {truth.candidate_id}: overlap between planted and omitted: {planted_ids & omitted_ids}"
        )
        # Exhaustive: union covers all requirements
        assert (planted_ids | omitted_ids) == all_req_ids, (
            f"Candidate {truth.candidate_id}: missing requirements: {all_req_ids - (planted_ids | omitted_ids)}"
        )
        checked_candidates += 1

    print(f"\n[M3.1a] Partition verified across {checked_candidates} candidates (100% exact partition)")


def test_1b_planted_evidence_is_findable():
    """1b. Each planted item yields exactly 1 locatable span in the generated text."""
    resumes, truths = generate(jd=DEFAULT_JOB_SPEC, n=30, seed=42)

    total_planted_checked = 0
    for cand_resume, truth in zip(resumes, truths):
        for planted in truth.planted:
            occurrences = cand_resume.text.count(planted.surface_form)
            assert occurrences == 1, (
                f"Candidate {truth.candidate_id}: Planted '{planted.surface_form}' found {occurrences} times"
            )
            total_planted_checked += 1

    print(f"\n[M3.1b] Verified {total_planted_checked} planted evidence spans (each found exactly once)")


def test_1c_omitted_requirements_have_no_tokens():
    """1c. Omitted requirements have zero token occurrences in the resume text."""
    resumes, truths = generate(jd=DEFAULT_JOB_SPEC, n=30, seed=42)
    req_map = {r.id: r for r in DEFAULT_JOB_SPEC.requirements}

    total_omitted_checked = 0
    for cand_resume, truth in zip(resumes, truths):
        lower_text = cand_resume.text.lower()
        for o_id in truth.omitted:
            req = req_map[o_id]
            for token in req.tokens:
                pattern = rf"\b{re.escape(token.lower())}\b"
                match = re.search(pattern, lower_text)
                assert match is None, (
                    f"Candidate {truth.candidate_id}: Omitted requirement {o_id} "
                    f"token '{token}' appeared in text: '{match.group(0)}'"
                )
            total_omitted_checked += 1

    print(f"\n[M3.1c] Verified {total_omitted_checked} omitted requirement checks (0 forbidden tokens found)")


def test_1d_distractors_disjoint_from_planted():
    """1d. Distractor tokens are strictly disjoint from planted requirement tokens."""
    resumes, truths = generate(jd=DEFAULT_JOB_SPEC, n=30, seed=42)
    req_map = {r.id: r for r in DEFAULT_JOB_SPEC.requirements}

    total_distractors_checked = 0
    for cand_resume, truth in zip(resumes, truths):
        planted_tokens = set()
        for p in truth.planted:
            planted_tokens.update(t.lower() for t in req_map[p.requirement_id].tokens)

        for d in truth.distractors:
            assert d.lower() not in planted_tokens, (
                f"Candidate {truth.candidate_id}: Distractor '{d}' collides with planted tokens {planted_tokens}"
            )
            total_distractors_checked += 1

    print(f"\n[M3.1d] Verified {total_distractors_checked} distractor tokens (0 collisions with planted tokens)")


def test_2_two_statements_meet_once_hand_corrupt_raises():
    """2. Hand-corrupt a TruthRecord by deleting one entry from omitted and assert check raises."""
    resumes, truths = generate(jd=DEFAULT_JOB_SPEC, n=1, seed=42)
    sample_resume = resumes[0]
    sample_truth = truths[0]

    # Ensure there is an omitted requirement to drop
    assert len(sample_truth.omitted) > 0, "Precondition failed: candidate has no omitted requirements"
    corrupted_omitted = sample_truth.omitted[:-1]

    corrupted_truth = TruthRecord(
        candidate_id=sample_truth.candidate_id,
        jd_sha256=sample_truth.jd_sha256,
        planted=sample_truth.planted,
        omitted=corrupted_omitted,
        distractors=sample_truth.distractors,
        generator_version=sample_truth.generator_version,
        seed=sample_truth.seed,
    )

    with pytest.raises(CardinalityViolation) as excinfo:
        validate_cardinality(corrupted_truth, sample_resume.text, DEFAULT_JOB_SPEC)

    print(f"\n[M3.2] Caught expected CardinalityViolation on corrupted omitted set: {excinfo.value}")


def test_3_cross_process_determinism_same_seed(tmp_path):
    """3. Same seed -> byte-identical truth.jsonl across two OS processes."""
    truth_file_local = tmp_path / "truth_local.jsonl"
    truth_file_subprocess = tmp_path / "truth_subprocess.jsonl"

    # Local run
    generate(jd=DEFAULT_JOB_SPEC, n=20, seed=12345, output_truth_path=truth_file_local)
    sha_local = compute_file_sha256(truth_file_local)

    # Subprocess run
    cmd = [
        sys.executable,
        "-c",
        (
            "from eval.generate_corpus import generate, DEFAULT_JOB_SPEC; "
            f"generate(jd=DEFAULT_JOB_SPEC, n=20, seed=12345, output_truth_path=r'{truth_file_subprocess}')"
        ),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    sha_subprocess = compute_file_sha256(truth_file_subprocess)

    print(f"\n[M3.3] Local SHA-256:      {sha_local}")
    print(f"[M3.3] Subprocess SHA-256: {sha_subprocess}")

    assert sha_local == sha_subprocess, "truth.jsonl must be byte-identical across OS processes"


def test_4_different_seeds_produce_different_output():
    """4. Different seed -> different output. Assert precondition fired."""
    resumes_a, truths_a = generate(jd=DEFAULT_JOB_SPEC, n=5, seed=101)
    resumes_b, truths_b = generate(jd=DEFAULT_JOB_SPEC, n=5, seed=202)

    text_a = "\n".join(r.text for r in resumes_a)
    text_b = "\n".join(r.text for r in resumes_b)

    assert text_a != text_b, "Precondition failed: Different seeds produced identical text!"
    assert truths_a != truths_b, "Precondition failed: Different seeds produced identical truth records!"

    print("\n[M3.4] Precondition fired: Seed 101 and Seed 202 produced distinct text and truth outputs")


def test_5_rate_amplification_cooccurrence():
    """5. Rate amplification: candidate has implicit-paraphrase plant AND skills-wall distractor for req >= 20."""
    target_amplified = 25
    resumes, truths = generate(
        jd=DEFAULT_JOB_SPEC,
        n=40,
        seed=42,
        force_modes={"amplified_implicit_and_skills_distractor": target_amplified},
    )

    k8s_id = RequirementId("req_k8s")
    k8s_distractor = "Docker"

    cooccurrence_count = 0
    for cand_resume, truth in zip(resumes, truths):
        has_implicit_k8s = any(
            p.requirement_id == k8s_id and p.mode == PhrasingMode.IMPLICIT_PARAPHRASE
            for p in truth.planted
        )
        has_k8s_distractor = k8s_distractor in truth.distractors
        if has_implicit_k8s and has_k8s_distractor:
            cooccurrence_count += 1

    print(f"\n[M3.5] Realised co-occurrence count for amplified property: {cooccurrence_count}")
    assert cooccurrence_count >= 20, f"Expected co-occurrence >= 20 [H], got {cooccurrence_count}"


def test_6_wrong_fix_sentence_region_well_formedness():
    """6. Wrong-fix test: assert resume text has no double spaces, orphaned punctuation, or zero-length sections."""
    resumes, truths = generate(jd=DEFAULT_JOB_SPEC, n=30, seed=42)

    malformation_count = 0
    for r in resumes:
        # Check double spaces (outside newlines)
        for line in r.text.splitlines():
            if "  " in line:
                malformation_count += 1
                print(f"  Malformation (double space) in {r.filename}: '{line}'")

        # Check orphaned punctuation e.g. ", ," or ".. " or ", ."
        if re.search(r"[,;]\s*[,;]", r.text) or re.search(r"\.\s*\.", r.text):
            malformation_count += 1
            print(f"  Malformation (orphaned punctuation) in {r.filename}")

        # Check zero-length sections
        sections = re.split(r"\n[A-Z\s]{4,}\n", r.text)
        for sec in sections:
            if len(sec.strip()) == 0:
                malformation_count += 1
                print(f"  Malformation (empty section) in {r.filename}")

    print(f"\n[M3.6] Malformation count: {malformation_count}")
    assert malformation_count == 0, f"Found {malformation_count} text malformations"


def test_7_resume_count_equals_truth_jsonl_lines(tmp_path):
    """7. Assert len(resumes) equals realised line count of truth.jsonl read back from disk."""
    truth_file = tmp_path / "truth.jsonl"
    resumes, truths = generate(jd=DEFAULT_JOB_SPEC, n=35, seed=42, output_truth_path=truth_file)

    with open(truth_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    print(f"\n[M3.7] Realised resumes returned: {len(resumes)}")
    print(f"[M3.7] Realised lines in truth.jsonl: {len(lines)}")

    assert len(resumes) == len(lines), "Resume list count does not match lines in truth.jsonl"
    assert len(lines) > 0
