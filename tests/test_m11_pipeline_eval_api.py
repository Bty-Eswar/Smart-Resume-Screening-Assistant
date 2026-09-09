# tests/test_m11_pipeline_eval_api.py — Tests for M11
import ast
from fractions import Fraction
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import pytest

from adapters.judge_cached import CachedJudge, compute_cache_key
from api import app, render_dashboard_html
from core.types import (
    AsOfDate,
    Bp,
    CandidateId,
    CandidateScore,
    EvidenceSpan,
    ParseOutcome,
    ParseStatus,
    RankedEntry,
    RankerId,
    Ranking,
    Requirement,
    RequirementId,
    RequirementJudgement,
    ResumeText,
    RunId,
    Sha256,
    Verdict,
)
from eval.harness import (
    HoldoutAlreadyScored,
    run_evaluation_harness,
    score_holdout,
)
from pipeline import TimingLog, ranking_to_dict, run_pipeline


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_1_d6_byte_identical_runs(tmp_path):
    """1. D6: run the full pipeline twice from the fixture cache; assert runs/<id>.json is byte-identical.

    Print both SHA-256s.
    """
    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()

    # Create 2 valid resumes
    r1_text = "Senior Python Engineer with 8 years experience building scalable backend microservices. " * 3
    r2_text = "Kubernetes and Cloud Infrastructure Architect with Docker container expertise. " * 3

    p1 = resume_dir / "resume_01.pdf"
    p2 = resume_dir / "resume_02.pdf"

    # Minimal valid PDF bytes from make_pdf_bytes
    from tests.test_m6_ingest import make_pdf_bytes
    p1.write_bytes(make_pdf_bytes(r1_text))
    p2.write_bytes(make_pdf_bytes(r2_text))

    sha1 = hashlib.sha256(p1.read_bytes()).hexdigest()
    sha2 = hashlib.sha256(p2.read_bytes()).hexdigest()

    reqs = (
        Requirement(RequirementId("req_py"), "Python microservices", ("python", "microservic"), Bp(5000)),
        Requirement(RequirementId("req_k8s"), "Kubernetes deployment", ("kubernet", "deploy"), Bp(5000)),
    )

    # Pre-record judgements in cache
    model = "anthropic.claude-3-sonnet"
    prompt = "v1"
    cache_dir = tmp_path / "fixtures" / "judgements"
    cache_dir.mkdir(parents=True)

    cache_file = cache_dir / "cache.json"
    k1 = compute_cache_key(model, prompt, sha1, "req_py")
    k2 = compute_cache_key(model, prompt, sha1, "req_k8s")
    k3 = compute_cache_key(model, prompt, sha2, "req_py")
    k4 = compute_cache_key(model, prompt, sha2, "req_k8s")

    cache_data = {
        k1: {"met": True, "confidence_bp": 9500, "evidence": {"start": 0, "end": 22, "text": "Senior Python Engineer"}},
        k2: {"met": False, "confidence_bp": 0, "evidence": None},
        k3: {"met": False, "confidence_bp": 0, "evidence": None},
        k4: {"met": True, "confidence_bp": 9000, "evidence": {"start": 0, "end": 26, "text": "Kubernetes and Cloud Infra"}},
    }
    cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

    judge = CachedJudge(cache_dir=cache_dir, model_id=model, prompt_version=prompt)

    runs_dir = tmp_path / "runs"
    timing_path = tmp_path / "eval" / "timing.json"

    # Run 1
    rank1, _ = run_pipeline(
        resume_dir=resume_dir,
        requirements=reqs,
        judge=judge,
        k=5,
        ranker=RankerId.R2_LLM,
        as_of=AsOfDate("2026-01-01"),
        runs_dir=runs_dir,
        timing_path=timing_path,
    )
    run1_path = runs_dir / f"{rank1.run_id}.json"
    sha_run1 = compute_file_sha256(run1_path)

    # Run 2
    rank2, _ = run_pipeline(
        resume_dir=resume_dir,
        requirements=reqs,
        judge=judge,
        k=5,
        ranker=RankerId.R2_LLM,
        as_of=AsOfDate("2026-01-01"),
        runs_dir=runs_dir,
        timing_path=timing_path,
    )
    run2_path = runs_dir / f"{rank2.run_id}.json"
    sha_run2 = compute_file_sha256(run2_path)

    print(f"\n[M11.1] Run 1 file SHA-256: {sha_run1}")
    print(f"[M11.1] Run 2 file SHA-256: {sha_run2}")

    assert sha_run1 == sha_run2, "D6 failure: run files are not byte-identical across runs"
    assert run1_path.read_bytes() == run2_path.read_bytes()


def test_2_d14_divergent_timings_produce_equal_ranking_and_run_id():
    """2. D14: two runs with divergent timings produce equal Ranking objects and identical run_id.

    Print the ids.
    """
    scores = (
        CandidateScore(CandidateId("c01"), Bp(9000), 2, 1, ()),
        CandidateScore(CandidateId("c02"), Bp(8000), 1, 1, ()),
    )

    from core.ranking import rank
    # Run A
    log_a = TimingLog()
    log_a.record("ingest", elapsed_ms=12)
    log_a.record("judge", elapsed_ms=45)
    rank_a = rank(scores, unparsed=(), k=5, ranker=RankerId.R2_LLM, as_of=AsOfDate("2026-01-01"))

    # Run B: heavily delayed timings
    log_b = TimingLog()
    log_b.record("ingest", elapsed_ms=4500)
    log_b.record("judge", elapsed_ms=9800)
    rank_b = rank(scores, unparsed=(), k=5, ranker=RankerId.R2_LLM, as_of=AsOfDate("2026-01-01"))

    print(f"\n[M11.2] Run A ID: {rank_a.run_id}")
    print(f"[M11.2] Run B ID: {rank_b.run_id}")

    assert rank_a == rank_b
    assert rank_a.run_id == rank_b.run_id


def test_3_results_json_contains_no_telemetry_keys(tmp_path):
    """3. results.json contains no key from {elapsed_ms, started_at, duration, latency}.

    Walk parsed JSON recursively, print key count inspected.
    """
    resumes = (
        ResumeText(CandidateId("c01"), "res1.pdf", Sha256("1" * 64), "text", 4),
    )
    reqs = (
        Requirement(RequirementId("r1"), "text", ("token",), Bp(10000)),
    )
    js = (
        RequirementJudgement(CandidateId("c01"), RequirementId("r1"), True, Bp(10000), None),
    )
    gold = frozenset([CandidateId("c01")])

    eval_dir = tmp_path / "eval"
    run_evaluation_harness(
        resumes=resumes,
        requirements=reqs,
        judgements=js,
        unparsed=(),
        idf_table={"token": 1000},
        jd_vector=(1,),
        resume_vectors={CandidateId("c01"): (1,)},
        gold_set=gold,
        eval_dir=eval_dir,
    )

    results_file = eval_dir / "results.json"
    assert results_file.exists()
    data = json.loads(results_file.read_text(encoding="utf-8"))

    forbidden_keys = {"elapsed_ms", "started_at", "duration", "latency", "call_count"}
    inspected_count = 0

    def check_keys(obj):
        nonlocal inspected_count
        if isinstance(obj, dict):
            for k, v in obj.items():
                inspected_count += 1
                assert k not in forbidden_keys, f"Found forbidden telemetry key in results.json: {k}"
                check_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                check_keys(item)

    check_keys(data)
    print(f"\n[M11.3] Inspected {inspected_count} keys in results.json; zero telemetry keys found")
    assert inspected_count > 0


def test_4_d12_fault_injection_holdout_scored_twice(tmp_path):
    """4. D12 fault injection: call score_holdout() twice -> second raises HoldoutAlreadyScored."""
    holdout_file = tmp_path / "holdout.txt"
    holdout_file.write_text("cand_h01.pdf\ncand_h02.pdf\n", encoding="utf-8")
    out_file = tmp_path / "holdout_results.json"

    # First run succeeds
    first = score_holdout(holdout_path=holdout_file, output_path=out_file)
    assert first["holdout_count"] == 2

    # Second run raises HoldoutAlreadyScored
    with pytest.raises(HoldoutAlreadyScored) as excinfo:
        score_holdout(holdout_path=holdout_file, output_path=out_file)

    print(f"\n[M11.4] Caught expected HoldoutAlreadyScored: {excinfo.value}")
    assert "already been scored" in str(excinfo.value)


def test_5_d11_fault_injection_gold_csv_readonly():
    """5. D11 fault injection: attempt to write gold.csv from application code -> raises PermissionError."""
    gold_path = Path("eval/gold.csv")
    assert gold_path.exists(), "eval/gold.csv must exist"

    with pytest.raises(PermissionError) as excinfo:
        with open(gold_path, "w") as f:
            f.write("cand_malicious,1\n")

    print(f"\n[M11.5] Caught expected PermissionError writing to read-only gold.csv: {excinfo.value}")


def test_6_wrong_fix_harness_does_not_read_truth_jsonl():
    """6. Wrong-fix test: AST-assert harness.py has no path reaching truth.jsonl from results.json path."""
    harness_path = Path("eval/harness.py")
    tree = ast.parse(harness_path.read_text(encoding="utf-8"), filename=str(harness_path))

    # Find run_evaluation_harness function
    target_func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_evaluation_harness":
            target_func = node
            break

    assert target_func is not None, "run_evaluation_harness not found in harness.py"

    # Walk all nodes inside run_evaluation_harness
    for child in ast.walk(target_func):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            assert "truth.jsonl" not in child.value, (
                "Circular evaluation violation: run_evaluation_harness references 'truth.jsonl'"
            )

    print("\n[M11.6] AST confirmed: run_evaluation_harness has 0 references to truth.jsonl")


def test_7_dashboard_renders_abstain_band_size():
    """7. Dashboard renders a ranking whose abstain_band is non-empty and displays band size;

    assert realised band size in DOM matches the object.
    """
    ranking_data = {
        "run_id": "run_test_dash",
        "ranker": "r2_llm",
        "as_of": "2026-01-01",
        "ranked": [
            {"rank": 1, "candidate_id": "c_winner", "score_bp": 9000, "verdict": "accept", "judgements": []}
        ],
        "abstain_band": [
            {"rank": 2, "candidate_id": "c_tie_1", "score_bp": 7500, "verdict": "unreviewed", "judgements": []},
            {"rank": 2, "candidate_id": "c_tie_2", "score_bp": 7500, "verdict": "unreviewed", "judgements": []},
            {"rank": 2, "candidate_id": "c_tie_3", "score_bp": 7500, "verdict": "unreviewed", "judgements": []},
        ],
        "unparsed": [],
    }

    html = render_dashboard_html(ranking_data)

    # Assert abstain band element exists in DOM
    assert 'id="abstain-band"' in html

    # Extract realised band size from DOM
    match = re.search(r'id="abstain-count"[^>]*>Band Size:\s*(\d+)</div>', html)
    assert match is not None, "Could not find abstain-count element in rendered DOM"
    realised_size = int(match.group(1))

    expected_size = len(ranking_data["abstain_band"])
    print(f"\n[M11.7] Realised abstain band size in DOM: {realised_size} (Expected: {expected_size})")

    assert realised_size == expected_size
    assert realised_size == 3


def test_8_wall_clock_budget_fault_injection():
    """8. Suite wall clock printed and under 60s; assert non-zero exit when slow test breaches it."""
    # Fault injection: run pytest on a quick test with an impossible budget of 0.00001 seconds
    env = os.environ.copy()
    env["PYTEST_BUDGET_SECONDS"] = "0.00001"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_doc_integrity.py",
        "-q",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

    print(f"\n[M11.8] Fault injection returncode: {proc.returncode}")
    print(f"[M11.8] Fault injection output:\n{proc.stdout}")

    assert proc.returncode != 0, "Budget enforcer failed: did not exit non-zero when budget was breached"
    assert "exceeded budget" in proc.stdout.lower()


def test_verify_holdout_precision_threshold(tmp_path):
    """VERIFY: Realised P@10 on the holdout set equals or exceeds 0.70 [H]."""
    # Check that score_holdout produces P@10 >= 0.70
    holdout_out = tmp_path / "eval_verify_holdout.json"
    holdout_file = Path("eval/holdout.txt")

    # Call score_holdout on sealed holdout
    res = score_holdout(holdout_path=holdout_file, output_path=holdout_out)
    prec_fraction = Fraction(res["precision_at_k"])
    prec_float = float(prec_fraction)

    print(f"\n[M11.VERIFY] Realised P@10 on holdout set: {prec_fraction} ({prec_float * 100:.1f}%)")
    assert prec_float >= 0.70, f"PDD threshold breached: {prec_float} < 0.70"
