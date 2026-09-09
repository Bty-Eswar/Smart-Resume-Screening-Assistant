# tests/test_m4_metrics.py — Tests for M4: core/metrics.py
from fractions import Fraction
import pytest

from core.types import (
    AsOfDate,
    Bp,
    CandidateId,
    CandidateScore,
    RankedEntry,
    RankerId,
    Ranking,
    RunId,
    Verdict,
)
from core.metrics import (
    EmptyGoldSet,
    cohens_kappa,
    jaccard_top_k,
    precision_at_k,
    rank_delta,
)


def _make_candidate_score(cand_id: str, score_bp: int = 5000) -> CandidateScore:
    return CandidateScore(
        candidate_id=CandidateId(cand_id),
        score_bp=Bp(score_bp),
        met_count=1,
        high_weight_met_count=0,
        judgements=(),
    )


def _make_ranking(
    ranked_ids: list[str],
    abstain_ids: list[str] = None,
    abstain_straddled_k: bool = False,
) -> Ranking:
    abstain_ids = abstain_ids or []
    ranked_entries = tuple(
        RankedEntry(rank=idx + 1, score=_make_candidate_score(cid), verdict=Verdict.ACCEPT)
        for idx, cid in enumerate(ranked_ids)
    )
    abstain_entries = tuple(
        RankedEntry(rank=len(ranked_ids) + 1, score=_make_candidate_score(cid), verdict=Verdict.UNREVIEWED)
        for cid in abstain_ids
    )
    return Ranking(
        run_id=RunId("run_test"),
        ranker=RankerId.R0_LEXICAL,
        as_of=AsOfDate("2026-09-09"),
        ranked=ranked_entries,
        abstain_band=abstain_entries,
        abstain_straddled_k=abstain_straddled_k,
        unparsed=(),
    )


def test_1_wrong_fix_precision_denominator_is_k():
    """1. Wrong-fix test: 8 ranked entries with 4 gold, k=10 -> Fraction(4, 10), NOT Fraction(4, 8)."""
    ranking = _make_ranking([f"cand_{i}" for i in range(1, 9)])
    gold = frozenset(CandidateId(f"cand_{i}") for i in range(1, 5))

    p = precision_at_k(ranking, gold, 10)

    print(f"\n[M4.1] Evaluated precision_at_k with 8 ranked, 4 gold, k=10:")
    print(f"  Result: {p.numerator}/{p.denominator}")
    print(f"  Explicit Fraction: {p}")

    assert p == Fraction(4, 10), f"Expected Fraction(4, 10), got {p}"
    assert p != Fraction(4, 8), "Wrong-fix check failed: denominator was incorrectly len(ranked)=8 instead of k=10"
    print(f"  [VERIFY] Explicit fraction: {p} equals 4/10 (differs from 4/8={Fraction(4, 8)})")


def test_2_abstain_band_straddling_k():
    """2. Abstain band straddling k: 7 ranked + 6 abstained, 3 gold in abstained set count as misses."""
    ranked_ids = [f"r_{i}" for i in range(1, 8)]  # 7 ranked
    abstain_ids = [f"a_{i}" for i in range(1, 7)]  # 6 abstained
    ranking = _make_ranking(ranked_ids, abstain_ids=abstain_ids, abstain_straddled_k=True)

    # Gold set: 2 in ranked, 3 in abstained
    gold = frozenset(
        [
            CandidateId("r_1"),
            CandidateId("r_2"),
            CandidateId("a_1"),
            CandidateId("a_2"),
            CandidateId("a_3"),
        ]
    )

    # With k=10, the 3 gold in the abstain band are NOT in ranked[:10], so they count as misses
    p = precision_at_k(ranking, gold, 10)

    print(f"\n[M4.2] Straddling abstain band test:")
    print(f"  precision_at_k: {p} ({p.numerator}/{p.denominator})")
    print(f"  abstain_straddled_k flag: {ranking.abstain_straddled_k}")

    assert ranking.abstain_straddled_k is True, "Precondition failed: abstain_straddled_k flag did not fire"
    assert p == Fraction(2, 10), f"Expected Fraction(2, 10), got {p}"


def test_3_cohens_kappa_skewed_negative():
    """3. Two labelers both mark 36/40 negative and agree on all: raw agreement 0.90 but kappa < 1/5."""
    # Labeler A marks 4 positive and 36 negative
    # Labeler B marks 0 positive and 40 negative
    # Both agree on all 36 negatives
    a = tuple([True] * 4 + [False] * 36)
    b = tuple([False] * 40)

    raw_agreement = Fraction(sum(1 for x, y in zip(a, b) if x == y), len(a))
    kappa = cohens_kappa(a, b)

    print(f"\n[M4.3] Cohen's Kappa Skewed Fixture:")
    print(f"  Raw Agreement: {raw_agreement} ({float(raw_agreement):.2f})")
    print(f"  Cohen's Kappa: {kappa} ({float(kappa):.4f})")

    assert raw_agreement == Fraction(36, 40)
    assert raw_agreement == Fraction(9, 10)
    assert kappa < Fraction(1, 5), f"Expected kappa < 1/5, got {kappa}"


def test_4_cohens_kappa_perfect_agreement_and_disagreement():
    """4. cohens_kappa on perfect agreement -> Fraction(1). On perfect disagreement -> negative."""
    agree_a = tuple([True] * 10 + [False] * 10)
    agree_b = tuple([True] * 10 + [False] * 10)
    k_agree = cohens_kappa(agree_a, agree_b)

    disagree_a = tuple([True] * 10 + [False] * 10)
    disagree_b = tuple([False] * 10 + [True] * 10)
    k_disagree = cohens_kappa(disagree_a, disagree_b)

    print(f"\n[M4.4] Cohen's Kappa Boundary Tests:")
    print(f"  Perfect Agreement:    {k_agree}")
    print(f"  Perfect Disagreement: {k_disagree}")

    assert k_agree == Fraction(1), f"Expected Fraction(1), got {k_agree}"
    assert k_disagree < Fraction(0), f"Expected negative kappa on perfect disagreement, got {k_disagree}"
    assert k_disagree == Fraction(-1)


def test_5_mismatched_length_inputs_raise():
    """5. Mismatched-length inputs to cohens_kappa raise ValueError."""
    with pytest.raises(ValueError) as excinfo:
        cohens_kappa((True, False, True), (True, False))
    print(f"\n[M4.5] Caught expected ValueError on mismatched lengths: {excinfo.value}")


def test_6_empty_vs_missing_distinctions():
    """6. Empty vs missing: empty ranked tuple returns Fraction(0, k); empty gold raises EmptyGoldSet."""
    empty_ranking = _make_ranking([])
    valid_gold = frozenset([CandidateId("cand_1")])

    # Empty ranked returns Fraction(0, k)
    p_empty = precision_at_k(empty_ranking, valid_gold, 10)
    print(f"\n[M4.6] Empty ranked returned: {p_empty}")
    assert p_empty == Fraction(0, 10)

    # Empty gold set raises EmptyGoldSet
    non_empty_ranking = _make_ranking(["cand_1"])
    with pytest.raises(EmptyGoldSet) as excinfo:
        precision_at_k(non_empty_ranking, frozenset(), 10)
    print(f"[M4.6] Caught expected EmptyGoldSet: {excinfo.value}")


def test_7_jaccard_top_k_properties():
    """7. jaccard_top_k with itself is Fraction(1); of two disjoint top-10s is Fraction(0)."""
    ranking_a = _make_ranking([f"a_{i}" for i in range(10)])
    ranking_b = _make_ranking([f"b_{i}" for i in range(10)])

    j_self = jaccard_top_k(ranking_a, ranking_a, 10)
    j_disjoint = jaccard_top_k(ranking_a, ranking_b, 10)

    print(f"\n[M4.7] Jaccard similarity tests:")
    print(f"  Self similarity:     {j_self}")
    print(f"  Disjoint similarity: {j_disjoint}")

    assert j_self == Fraction(1)
    assert j_disjoint == Fraction(0)


def test_8_no_float_returned_all_four_functions():
    """8. No function returns a float — scalar metrics return Fraction, rank_delta returns tuple of int deltas."""
    ranking_a = _make_ranking(["c1", "c2", "c3"])
    ranking_b = _make_ranking(["c3", "c2", "c1"])
    gold = frozenset([CandidateId("c1")])

    res_p = precision_at_k(ranking_a, gold, 3)
    res_j = jaccard_top_k(ranking_a, ranking_b, 3)
    res_k = cohens_kappa((True, False), (True, False))
    res_rd = rank_delta(ranking_a, ranking_b)

    scalar_results = [res_p, res_j, res_k]
    checked_count = 0

    print("\n[M4.8] Type assertions (no float, exact Fraction/int):")
    for res in scalar_results:
        assert isinstance(res, Fraction), f"Expected Fraction, got {type(res)}"
        assert not isinstance(res, float)
        checked_count += 1
        print(f"  Metric {checked_count}: {res} is Fraction")

    assert isinstance(res_rd, tuple), f"Expected tuple from rank_delta, got {type(res_rd)}"
    for cand_id, delta in res_rd:
        assert isinstance(cand_id, str)
        assert isinstance(delta, int), f"Expected int rank delta, got {type(delta)}"
        assert not isinstance(delta, float)
    checked_count += 1
    print(f"  Metric {checked_count}: rank_delta {res_rd} contains integer deltas (0 floats)")

    print(f"[M4.8] Total metric functions checked and verified float-free: {checked_count}")
    assert checked_count == 4
