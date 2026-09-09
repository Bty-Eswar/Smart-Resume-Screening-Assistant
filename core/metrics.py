# core/metrics.py — SDD §3 / BUILD_PROMPTS M4
from fractions import Fraction
from core.types import CandidateId, Ranking


class EmptyGoldSet(Exception):
    """Raised when gold set is empty."""
    pass


def precision_at_k(ranking: Ranking, gold: frozenset[CandidateId], k: int) -> Fraction:
    """Compute precision@k with explicit denominator k.

    Per SDD C3, uses denominator k even when len(ranked) < k.
    Any entries in abstain_band are treated as misses.
    Raises:
        EmptyGoldSet: if gold is empty (empty vs missing distinction).
        ValueError: if k <= 0.
    """
    if len(gold) == 0:
        raise EmptyGoldSet("Gold set is empty; precision cannot be evaluated against an empty target")
    if k <= 0:
        raise ValueError(f"k must be a positive integer, got {k}")

    # Inspect top-k from ranked entries only
    considered = ranking.ranked[:k]
    hits = sum(1 for entry in considered if entry.score.candidate_id in gold)
    return Fraction(hits, k)


def jaccard_top_k(a: Ranking, b: Ranking, k: int) -> Fraction:
    """Compute Jaccard similarity of the top-k candidates between two rankings.

    Jaccard = |top_k(a) ∩ top_k(b)| / |top_k(a) ∪ top_k(b)|
    Raises:
        ValueError: if k <= 0.
    """
    if k <= 0:
        raise ValueError(f"k must be a positive integer, got {k}")

    cand_a = frozenset(entry.score.candidate_id for entry in a.ranked[:k])
    cand_b = frozenset(entry.score.candidate_id for entry in b.ranked[:k])

    intersection = len(cand_a & cand_b)
    union = len(cand_a | cand_b)

    if union == 0:
        return Fraction(1) if cand_a == cand_b else Fraction(0)

    return Fraction(intersection, union)


def cohens_kappa(a: tuple[bool, ...], b: tuple[bool, ...]) -> Fraction:
    """Compute Cohen's kappa for two binary label sequences using exact Fraction arithmetic.

    Raises:
        ValueError: on mismatched-length inputs or empty inputs.
    """
    if len(a) != len(b):
        raise ValueError(f"Mismatched-length inputs to cohens_kappa: len(a)={len(a)}, len(b)={len(b)}")
    if len(a) == 0:
        raise ValueError("Cannot compute cohens_kappa on empty sequences")

    n = len(a)
    a11 = sum(1 for x, y in zip(a, b) if x and y)
    a10 = sum(1 for x, y in zip(a, b) if x and not y)
    a01 = sum(1 for x, y in zip(a, b) if not x and y)
    a00 = sum(1 for x, y in zip(a, b) if not x and not y)

    # Observed agreement
    p_o = Fraction(a11 + a00, n)

    # Expected agreement by chance
    p_a1 = Fraction(a11 + a10, n)
    p_a0 = Fraction(a01 + a00, n)
    p_b1 = Fraction(a11 + a01, n)
    p_b0 = Fraction(a10 + a00, n)
    p_e = p_a1 * p_b1 + p_a0 * p_b0

    if p_e == 1:
        return Fraction(1) if p_o == 1 else Fraction(0)

    return (p_o - p_e) / (1 - p_e)


def rank_delta(a: Ranking, b: Ranking) -> tuple[tuple[CandidateId, int], ...]:
    """Compute rank delta (rank in b - rank in a) for each candidate.

    Returns a sorted tuple of (CandidateId, rank_b - rank_a) per D4.
    """
    pos_a = {entry.score.candidate_id: entry.rank for entry in a.ranked}
    pos_b = {entry.score.candidate_id: entry.rank for entry in b.ranked}

    common_cands = sorted(set(pos_a.keys()) & set(pos_b.keys()))
    deltas = tuple((cand, pos_b[cand] - pos_a[cand]) for cand in common_cands)
    return deltas
