# tests/test_m8_scoring_ranking.py — Tests for M8: core/scoring.py and core/ranking.py
from dataclasses import fields, is_dataclass
from fractions import Fraction
import random
import pytest

from core.metrics import precision_at_k
from core.ranking import rank
from core.scoring import score_candidate
from core.types import (
    AsOfDate,
    Bp,
    CandidateId,
    CandidateScore,
    EvidenceSpan,
    ParseOutcome,
    ParseStatus,
    RankerId,
    Requirement,
    RequirementId,
    RequirementJudgement,
    Verdict,
)


def _make_candidate_score(
    cid: str,
    score_bp: int,
    met_count: int = 1,
    high_weight_met_count: int = 0,
) -> CandidateScore:
    return CandidateScore(
        candidate_id=CandidateId(cid),
        score_bp=Bp(score_bp),
        met_count=met_count,
        high_weight_met_count=high_weight_met_count,
        judgements=(),
    )


def test_1_known_judgement_set_hand_computed_score():
    """1. Known judgement set -> hand-computed score_bp.

    Expected value computed strictly by hand in test, meeting scoring logic in one place.
    Req 1: weight 4000 bp, met=True,  conf=8500 bp -> (4000 * 8500) // 10000 = 3400 bp
    Req 2: weight 3500 bp, met=True,  conf=6000 bp -> (3500 * 6000) // 10000 = 2100 bp
    Req 3: weight 2500 bp, met=False, conf=9000 bp -> 0 bp (not met)
    Sum: 3400 + 2100 + 0 = 5500 bp
    Met count: 2, High weight met count: 2 (both weights >= 1000)
    """
    reqs = (
        Requirement(RequirementId("r1"), "Req 1", ("r1",), Bp(4000)),
        Requirement(RequirementId("r2"), "Req 2", ("r2",), Bp(3500)),
        Requirement(RequirementId("r3"), "Req 3", ("r3",), Bp(2500)),
    )

    cid = CandidateId("cand_hand_calc")
    js = (
        RequirementJudgement(cid, RequirementId("r1"), True, Bp(8500), None),
        RequirementJudgement(cid, RequirementId("r2"), True, Bp(6000), None),
        RequirementJudgement(cid, RequirementId("r3"), False, Bp(9000), None),
    )

    # Hand-computed expected values:
    EXPECTED_SCORE_BP = 5500
    EXPECTED_MET_COUNT = 2
    EXPECTED_HIGH_WEIGHT_MET = 2

    score = score_candidate(js, reqs, AsOfDate("2026-01-01"))

    print(f"\n[M8.1] Hand-computed expected: {EXPECTED_SCORE_BP}, realised: {score.score_bp}")
    assert score.score_bp == EXPECTED_SCORE_BP
    assert score.met_count == EXPECTED_MET_COUNT
    assert score.high_weight_met_count == EXPECTED_HIGH_WEIGHT_MET
    assert [j.requirement_id for j in score.judgements] == ["r1", "r2", "r3"]


def test_2_rate_amplification_12_tied_candidates():
    """2. Rate amplification: construct fixture with 12 deliberately tied candidates. Print realised tie count."""
    tied_scores = tuple(
        _make_candidate_score(f"cand_tied_{i:02d}", score_bp=7500, met_count=3, high_weight_met_count=2)
        for i in range(12)
    )

    ranking = rank(
        scores=tied_scores,
        unparsed=(),
        k=10,
        ranker=RankerId.R0_LEXICAL,
        as_of=AsOfDate("2026-01-01"),
    )

    realised_tie_count = len(ranking.abstain_band)
    print(f"\n[M8.2] Realised tie count in abstain_band: {realised_tie_count}")

    assert realised_tie_count == 12
    assert len(ranking.ranked) == 0


def test_3_wrong_fix_tied_candidates_swap_ids():
    """3. Wrong-fix test, the critical one: two candidates tied on all three keys.

    Swap their candidate_id values and re-rank.
    Assert:
      (a) both appear in abstain_band
      (b) neither appears in ranked
      (c) the ranked tuple is byte-identical across the swap.
    """
    c_clear_high = _make_candidate_score("c_winner", score_bp=9000, met_count=4, high_weight_met_count=3)
    c_clear_low = _make_candidate_score("c_loser", score_bp=4000, met_count=1, high_weight_met_count=0)

    c_tie_1 = _make_candidate_score("c_tie_alpha", score_bp=7000, met_count=2, high_weight_met_count=1)
    c_tie_2 = _make_candidate_score("c_tie_beta", score_bp=7000, met_count=2, high_weight_met_count=1)

    # Run 1: original order
    run1 = rank(
        scores=(c_clear_high, c_tie_1, c_tie_2, c_clear_low),
        unparsed=(),
        k=10,
        ranker=RankerId.R0_LEXICAL,
        as_of=AsOfDate("2026-01-01"),
    )

    # Run 2: swapped candidate_ids for the two tied candidates
    c_tie_1_swapped = _make_candidate_score("c_tie_beta", score_bp=7000, met_count=2, high_weight_met_count=1)
    c_tie_2_swapped = _make_candidate_score("c_tie_alpha", score_bp=7000, met_count=2, high_weight_met_count=1)

    run2 = rank(
        scores=(c_clear_high, c_tie_1_swapped, c_tie_2_swapped, c_clear_low),
        unparsed=(),
        k=10,
        ranker=RankerId.R0_LEXICAL,
        as_of=AsOfDate("2026-01-01"),
    )

    abstain_ids_1 = {e.score.candidate_id for e in run1.abstain_band}
    ranked_ids_1 = {e.score.candidate_id for e in run1.ranked}

    print(f"\n[M8.3] Run1 ranked IDs: {[e.score.candidate_id for e in run1.ranked]}")
    print(f"[M8.3] Run1 abstain IDs: {sorted(abstain_ids_1)}")

    # (a) both appear in abstain_band
    assert "c_tie_alpha" in abstain_ids_1
    assert "c_tie_beta" in abstain_ids_1

    # (b) neither appears in ranked
    assert "c_tie_alpha" not in ranked_ids_1
    assert "c_tie_beta" not in ranked_ids_1

    # (c) ranked tuple is byte-identical across the swap
    assert run1.ranked == run2.ranked


def test_4_d10_input_order_invariance_20_shuffles():
    """4. D10: 20 shuffles of the input scores -> identical Ranking. Print shuffle count run."""
    cands = [
        _make_candidate_score("c01", score_bp=9500, met_count=5, high_weight_met_count=4),
        _make_candidate_score("c02", score_bp=8800, met_count=4, high_weight_met_count=3),
        _make_candidate_score("c03", score_bp=8800, met_count=4, high_weight_met_count=2),  # differs on high_weight
        _make_candidate_score("c04", score_bp=7200, met_count=3, high_weight_met_count=2),  # tied with c05
        _make_candidate_score("c05", score_bp=7200, met_count=3, high_weight_met_count=2),  # tied with c04
        _make_candidate_score("c06", score_bp=6000, met_count=2, high_weight_met_count=1),
        _make_candidate_score("c07", score_bp=4500, met_count=1, high_weight_met_count=1),
        _make_candidate_score("c08", score_bp=3000, met_count=1, high_weight_met_count=0),
    ]

    unparsed = (
        ParseOutcome("res_b.pdf", ParseStatus.CORRUPT, None),
        ParseOutcome("res_a.pdf", ParseStatus.NO_TEXT_LAYER, None),
    )

    baseline = rank(tuple(cands), unparsed, k=5, ranker=RankerId.R0_LEXICAL, as_of=AsOfDate("2026-01-01"))

    rng = random.Random(4242)
    shuffle_count = 0
    for _ in range(20):
        shuffled = list(cands)
        rng.shuffle(shuffled)
        result = rank(tuple(shuffled), unparsed, k=5, ranker=RankerId.R0_LEXICAL, as_of=AsOfDate("2026-01-01"))
        assert result == baseline, f"Shuffle {shuffle_count} produced different Ranking!"
        shuffle_count += 1

    print(f"\n[M8.4] D10 verified: {shuffle_count} shuffles produced identical Ranking byte-for-byte")


def test_5_tie_straddling_k():
    """5. Tie straddling k: 7 clear entries then a 6-way tie.

    Assert abstain_straddled_k is True and precision_at_k treats the abstained as misses.
    """
    clear_entries = [
        _make_candidate_score(f"cand_clear_{i:02d}", score_bp=9000 - i * 100, met_count=5, high_weight_met_count=4)
        for i in range(7)
    ]
    tied_entries = [
        _make_candidate_score(f"cand_tie_{i:02d}", score_bp=8000, met_count=3, high_weight_met_count=2)
        for i in range(6)
    ]

    all_scores = tuple(clear_entries + tied_entries)
    ranking = rank(all_scores, unparsed=(), k=10, ranker=RankerId.R0_LEXICAL, as_of=AsOfDate("2026-01-01"))

    print(f"\n[M8.5] Ranked count: {len(ranking.ranked)}, Abstain count: {len(ranking.abstain_band)}")
    print(f"[M8.5] abstain_straddled_k: {ranking.abstain_straddled_k}")

    assert len(ranking.ranked) == 7
    assert len(ranking.abstain_band) == 6
    assert ranking.abstain_straddled_k is True

    # Gold set: 4 from ranked clear entries, 3 from abstain band
    gold_set = frozenset([
        CandidateId("cand_clear_00"),
        CandidateId("cand_clear_01"),
        CandidateId("cand_clear_02"),
        CandidateId("cand_clear_03"),
        CandidateId("cand_tie_00"),
        CandidateId("cand_tie_01"),
        CandidateId("cand_tie_02"),
    ])

    # Precision at k=10 must equal Fraction(4, 10) because abstained candidates count as misses
    p_at_10 = precision_at_k(ranking, gold_set, k=10)
    print(f"[M8.5] precision_at_k realised: {p_at_10}")
    assert p_at_10 == Fraction(4, 10)


def test_6_as_of_is_load_bearing_duration_reasoning():
    """6. as_of is load-bearing: two calls differing only in as_of produce different scores.

    Fixture with a duration-sensitive requirement ('5+ years') and start year 2020.
    as_of='2022-01-01' -> 2 years accrued < 5 -> not satisfied -> score 0
    as_of='2026-01-01' -> 6 years accrued >= 5 -> satisfied -> score 10000
    """
    reqs = (
        Requirement(
            id=RequirementId("req_py_dur"),
            text="5+ years of Python software development experience",
            tokens=("python",),
            weight_bp=Bp(10000),
        ),
    )

    ev_span = EvidenceSpan(start=0, end=35, text="Python engineer from 2020 to present")
    cid = CandidateId("cand_dur_test")
    js = (
        RequirementJudgement(
            candidate_id=cid,
            requirement_id=RequirementId("req_py_dur"),
            met=True,
            confidence_bp=Bp(10000),
            evidence=ev_span,
        ),
    )

    score_2022 = score_candidate(js, reqs, as_of=AsOfDate("2022-01-01"))
    score_2026 = score_candidate(js, reqs, as_of=AsOfDate("2026-01-01"))

    print(f"\n[M8.6] Score as of 2022-01-01: {score_2022.score_bp}")
    print(f"[M8.6] Score as of 2026-01-01: {score_2026.score_bp}")

    assert score_2022.score_bp != score_2026.score_bp
    assert score_2022.score_bp == 0
    assert score_2026.score_bp == 10000


def test_7_no_float_in_any_returned_object():
    """7. No float in any returned object: walk dataclass fields and assert. Print field count checked."""
    reqs = (
        Requirement(RequirementId("r1"), "Req 1", ("r1",), Bp(5000)),
        Requirement(RequirementId("r2"), "Req 2", ("r2",), Bp(5000)),
    )
    cid = CandidateId("c_test")
    js = (
        RequirementJudgement(cid, RequirementId("r1"), True, Bp(10000), None),
        RequirementJudgement(cid, RequirementId("r2"), False, Bp(0), None),
    )
    cand_score = score_candidate(js, reqs, as_of=AsOfDate("2026-01-01"))

    unparsed = (
        ParseOutcome("failed.pdf", ParseStatus.CORRUPT, None),
    )
    ranking = rank((cand_score,), unparsed, k=10, ranker=RankerId.R0_LEXICAL, as_of=AsOfDate("2026-01-01"))

    checked_field_count = 0

    def assert_no_floats(obj):
        nonlocal checked_field_count
        if is_dataclass(obj) and not isinstance(obj, type):
            for f in fields(obj):
                val = getattr(obj, f.name)
                checked_field_count += 1
                assert not isinstance(val, float), f"Found float in field {f.name}: {val}"
                assert_no_floats(val)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                checked_field_count += 1
                assert not isinstance(item, float), f"Found float in sequence: {item}"
                assert_no_floats(item)
        elif isinstance(obj, dict):
            for k_v, v in obj.items():
                checked_field_count += 1
                assert not isinstance(v, float), f"Found float in dict val: {v}"
                assert_no_floats(v)

    assert_no_floats(cand_score)
    assert_no_floats(ranking)

    print(f"\n[M8.7] Checked {checked_field_count} fields across CandidateScore and Ranking; zero floats found")
    assert checked_field_count > 0


def test_8_unparsed_candidates_sorted_by_filename():
    """8. Unparsed candidates appear in Ranking.unparsed, sorted by filename, matching input count."""
    unparsed_inputs = (
        ParseOutcome("zebra.pdf", ParseStatus.CORRUPT, None),
        ParseOutcome("alpha.pdf", ParseStatus.NO_TEXT_LAYER, None),
        ParseOutcome("mango.txt", ParseStatus.UNSUPPORTED_TYPE, None),
    )

    ranking = rank(
        scores=(),
        unparsed=unparsed_inputs,
        k=10,
        ranker=RankerId.R0_LEXICAL,
        as_of=AsOfDate("2026-01-01"),
    )

    print(f"\n[M8.8] Realised unparsed count: {len(ranking.unparsed)}")
    print(f"[M8.8] Sorted filenames: {[o.filename for o in ranking.unparsed]}")

    assert len(ranking.unparsed) == len(unparsed_inputs)
    assert [o.filename for o in ranking.unparsed] == ["alpha.pdf", "mango.txt", "zebra.pdf"]
