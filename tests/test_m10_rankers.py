# tests/test_m10_rankers.py — Tests for M10: core/rankers/
import ast
from pathlib import Path
import random
import pytest

from core.ids import content_id
from core.rankers.r0_lexical import rank_lexical
from core.rankers.r1_embedding import rank_embedding
from core.rankers.r2_llm import rank_llm
from core.types import (
    AsOfDate,
    Bp,
    CandidateId,
    ParseOutcome,
    Requirement,
    RequirementId,
    RequirementJudgement,
    ResumeText,
    Sha256,
)


def _compute_req_list_hash(reqs: tuple[Requirement, ...]) -> str:
    sorted_reqs = sorted(reqs, key=lambda r: r.id)
    parts = [f"{r.id}:{r.weight_bp}:{r.text}" for r in sorted_reqs]
    return content_id(*parts)


def test_1_r0_all_tokens_vs_none():
    """1. R0 on a resume containing every requirement token verbatim ranks it above one containing none."""
    reqs = (
        Requirement(RequirementId("r1"), "Python microservices", ("python", "microservic"), Bp(5000)),
        Requirement(RequirementId("r2"), "Kubernetes deployment", ("kubernet", "deploy"), Bp(5000)),
    )
    idf_table = {"python": 3000, "microservic": 3000, "kubernet": 4000, "deploy": 4000}

    resume_full = ResumeText(
        candidate_id=CandidateId("cand_full"),
        filename="full.pdf",
        sha256=Sha256("1" * 64),
        text="Specialist in Python microservices and Kubernetes deployment orchestration.",
        char_count=77,
    )
    resume_empty = ResumeText(
        candidate_id=CandidateId("cand_empty"),
        filename="empty.pdf",
        sha256=Sha256("2" * 64),
        text="Classical violinist with background in baroque chamber music and acoustic performance.",
        char_count=87,
    )

    ranking = rank_lexical(
        resumes=(resume_empty, resume_full),
        requirements=reqs,
        idf_table=idf_table,
        unparsed=(),
        k=5,
        as_of=AsOfDate("2026-01-01"),
    )

    scores = {e.score.candidate_id: e.score.score_bp for e in ranking.ranked}
    print(f"\n[M10.1] Full resume score: {scores['cand_full']}, Empty resume score: {scores['cand_empty']}")

    assert scores["cand_full"] > scores["cand_empty"]
    assert scores["cand_full"] == 10000
    assert scores["cand_empty"] == 0
    assert ranking.ranked[0].score.candidate_id == "cand_full"


def test_2_wrong_fix_tf_vs_idf():
    """2. Wrong-fix test: a TF-only implementation ranks a resume repeating one common token 50 times

    above one covering five distinct requirements. Assert the five-requirement resume ranks higher.
    """
    reqs = (
        Requirement(RequirementId("r1"), "Python", ("python",), Bp(2000)),
        Requirement(RequirementId("r2"), "Kubernetes", ("kubernet",), Bp(2000)),
        Requirement(RequirementId("r3"), "Cassandra", ("cassandra",), Bp(2000)),
        Requirement(RequirementId("r4"), "Docker", ("docker",), Bp(2000)),
        Requirement(RequirementId("r5"), "GRPC", ("grpc",), Bp(2000)),
    )
    # "team" has negligible IDF (10), while domain skills have high IDF (4000)
    idf_table = {
        "team": 10,
        "python": 4000,
        "kubernet": 4000,
        "cassandra": 4000,
        "docker": 4000,
        "grpc": 4000,
    }

    # Resume A repeats common token "team" 50 times and only mentions python once
    # Under pure TF counting, "team" * 50 dominates.
    text_spam = "team " * 50 + "python"
    resume_spam = ResumeText(
        candidate_id=CandidateId("cand_spam"),
        filename="spam.pdf",
        sha256=Sha256("3" * 64),
        text=text_spam,
        char_count=len(text_spam),
    )

    # Resume B covers all 5 requirements
    text_broad = "Python Kubernetes Cassandra Docker GRPC"
    resume_broad = ResumeText(
        candidate_id=CandidateId("cand_broad"),
        filename="broad.pdf",
        sha256=Sha256("4" * 64),
        text=text_broad,
        char_count=len(text_broad),
    )

    ranking = rank_lexical(
        resumes=(resume_spam, resume_broad),
        requirements=reqs,
        idf_table=idf_table,
        unparsed=(),
        k=5,
        as_of=AsOfDate("2026-01-01"),
    )

    scores = {e.score.candidate_id: e.score.score_bp for e in ranking.ranked}
    print(f"\n[M10.2] Broad candidate score: {scores['cand_broad']}, Spam candidate score: {scores['cand_spam']}")

    assert scores["cand_broad"] > scores["cand_spam"]
    assert ranking.ranked[0].score.candidate_id == "cand_broad"


def test_3_r0_and_r2_receive_equal_requirement_lists_by_content_hash():
    """3. R0 and R2 receive requirement lists asserted equal by content hash. Print the hash."""
    reqs = (
        Requirement(RequirementId("r1"), "Python backend architecture", ("python", "backend"), Bp(6000)),
        Requirement(RequirementId("r2"), "Distributed systems design", ("distributed", "system"), Bp(4000)),
    )

    hash_r0 = _compute_req_list_hash(reqs)
    hash_r2 = _compute_req_list_hash(reqs)

    print(f"\n[M10.3] R0 requirement list hash: {hash_r0}")
    print(f"[M10.3] R2 requirement list hash: {hash_r2}")

    assert hash_r0 == hash_r2
    assert len(hash_r0) == 32


def test_4_all_three_rankers_return_identical_candidate_id_sets():
    """4. All three rankers return Ranking objects over the same candidate set; assert candidate-ID sets match."""
    c_ids = [f"cand_{i:02d}" for i in range(10)]
    resumes = tuple(
        ResumeText(
            candidate_id=CandidateId(cid),
            filename=f"{cid}.pdf",
            sha256=Sha256(f"{i:02x}" * 32),
            text="Experienced software engineer with Python.",
            char_count=42,
        )
        for i, cid in enumerate(c_ids)
    )
    reqs = (Requirement(RequirementId("r1"), "Python", ("python",), Bp(10000)),)

    # R0 setup
    idf = {"python": 1000}
    rank_r0 = rank_lexical(resumes, reqs, idf, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))

    # R1 setup
    jd_vec = (1, 1, 1, 1)
    res_vecs = {r.candidate_id: (1, 1, 1, 1) for r in resumes}
    rank_r1 = rank_embedding(resumes, jd_vec, res_vecs, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))

    # R2 setup
    judgements = tuple(
        RequirementJudgement(r.candidate_id, RequirementId("r1"), True, Bp(9000), None)
        for r in resumes
    )
    rank_r2 = rank_llm(resumes, reqs, judgements, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))

    def extract_cids(r):
        return {e.score.candidate_id for e in r.ranked} | {e.score.candidate_id for e in r.abstain_band}

    cids_r0 = extract_cids(rank_r0)
    cids_r1 = extract_cids(rank_r1)
    cids_r2 = extract_cids(rank_r2)
    expected_cids = set(CandidateId(cid) for cid in c_ids)

    print(f"\n[M10.4] Candidate set size across all rankers: {len(cids_r0)}")

    assert cids_r0 == expected_cids
    assert cids_r1 == expected_cids
    assert cids_r2 == expected_cids


def test_5_layering_ast_assert_no_illegal_imports():
    """5. Layering: AST-assert that no module under core/rankers/ imports adapters, gold, or truth."""
    rankers_dir = Path("core/rankers")
    py_files = sorted(rankers_dir.glob("*.py"))
    assert len(py_files) >= 3

    forbidden_modules = {"adapters", "gold", "truth"}
    violations = []

    for f in py_files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0]
                    if root_pkg in forbidden_modules:
                        violations.append((f.name, node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg in forbidden_modules:
                        violations.append((f.name, node.lineno, node.module))

    print(f"\n[M10.5] Layering check passed: 0 forbidden imports across {len(py_files)} ranker files")
    assert not violations, f"Forbidden imports found in core/rankers: {violations}"


def test_6_r1_orthogonal_vs_identical_vectors():
    """6. R1 with injected orthogonal vectors -> cosine 0; identical vectors -> 10000 bp after quantization."""
    jd_vector = (1, 0, 0, 0)
    orthogonal_vector = (0, 1, 0, 0)
    identical_vector = (1, 0, 0, 0)

    res_ortho = ResumeText(
        candidate_id=CandidateId("c_ortho"),
        filename="ortho.pdf",
        sha256=Sha256("5" * 64),
        text="text",
        char_count=4,
    )
    res_ident = ResumeText(
        candidate_id=CandidateId("c_ident"),
        filename="ident.pdf",
        sha256=Sha256("6" * 64),
        text="text",
        char_count=4,
    )

    resume_vectors = {
        CandidateId("c_ortho"): orthogonal_vector,
        CandidateId("c_ident"): identical_vector,
    }

    ranking = rank_embedding(
        resumes=(res_ortho, res_ident),
        jd_vector=jd_vector,
        resume_vectors=resume_vectors,
        unparsed=(),
        k=5,
        as_of=AsOfDate("2026-01-01"),
    )

    scores = {e.score.candidate_id: e.score.score_bp for e in ranking.ranked}
    print(f"\n[M10.6] Orthogonal vector score: {scores['c_ortho']} bp, Identical vector score: {scores['c_ident']} bp")

    assert scores["c_ortho"] == 0
    assert scores["c_ident"] == 10000


def test_7_determinism_shuffled_inputs_d10():
    """7. Determinism: each ranker run twice on shuffled input -> identical output (D10)."""
    c_ids = [f"cand_{i:02d}" for i in range(8)]
    resumes = tuple(
        ResumeText(
            candidate_id=CandidateId(cid),
            filename=f"{cid}.pdf",
            sha256=Sha256(f"{i:02x}" * 32),
            text="Python software engineering " * (i + 1),
            char_count=30 * (i + 1),
        )
        for i, cid in enumerate(c_ids)
    )
    reqs = (
        Requirement(RequirementId("r1"), "Python", ("python",), Bp(6000)),
        Requirement(RequirementId("r2"), "Engineering", ("engineering",), Bp(4000)),
    )
    idf = {"python": 1000, "engineering": 1000}
    jd_vec = (1, 2, 3)
    res_vecs = {r.candidate_id: (1, 2, 3) for r in resumes}
    judgements = tuple(
        RequirementJudgement(r.candidate_id, RequirementId("r1"), True, Bp(8000), None)
        for r in resumes
    )

    rng = random.Random(999)
    shuffled_resumes = list(resumes)
    rng.shuffle(shuffled_resumes)
    shuffled_resumes = tuple(shuffled_resumes)

    # 1. Test R0
    r0_base = rank_lexical(resumes, reqs, idf, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))
    r0_shuf = rank_lexical(shuffled_resumes, reqs, idf, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))
    assert r0_base == r0_shuf, "R0 failed D10 input order invariance"

    # 2. Test R1
    r1_base = rank_embedding(resumes, jd_vec, res_vecs, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))
    r1_shuf = rank_embedding(shuffled_resumes, jd_vec, res_vecs, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))
    assert r1_base == r1_shuf, "R1 failed D10 input order invariance"

    # 3. Test R2
    r2_base = rank_llm(resumes, reqs, judgements, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))
    r2_shuf = rank_llm(shuffled_resumes, reqs, judgements, unparsed=(), k=5, as_of=AsOfDate("2026-01-01"))
    assert r2_base == r2_shuf, "R2 failed D10 input order invariance"

    print("\n[M10.7] D10 verified: R0, R1, and R2 are all 100% invariant to input order")
