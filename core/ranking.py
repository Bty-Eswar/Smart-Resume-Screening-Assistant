# core/ranking.py — SDD §3 / D4, D5, D10 / BUILD_PROMPTS M8
from core.ids import content_id
from core.types import (
    AsOfDate,
    CandidateScore,
    ParseOutcome,
    RankedEntry,
    RankerId,
    Ranking,
    RunId,
    Verdict,
)


def rank(
    scores: tuple[CandidateScore, ...],
    unparsed: tuple[ParseOutcome, ...],
    k: int,
    ranker: RankerId,
    as_of: AsOfDate,
) -> Ranking:
    """Rank candidates according to the tie-break chain:
        (score_bp desc, met_count desc, high_weight_met_count desc)

    Candidates tied after all three keys are placed in abstain_band, sorted by
    candidate_id for display only (D5). Candidate ID is NEVER used as a tie-break key.
    Sets abstain_straddled_k when the abstain band crosses index k.
    Input-order invariant (D10).
    """
    if k <= 0:
        raise ValueError(f"k must be a positive integer, got {k}")
    if not as_of:
        raise ValueError("as_of is required")

    # Tie-break key extraction function (D5)
    def tie_key(s: CandidateScore) -> tuple[int, int, int]:
        return (int(s.score_bp), int(s.met_count), int(s.high_weight_met_count))

    # Collect all unique keys sorted descending
    unique_keys = sorted({tie_key(s) for s in scores}, reverse=True)

    ranked_entries: list[RankedEntry] = []
    abstain_entries: list[RankedEntry] = []
    straddled_k = False

    cursor = 1
    for key in unique_keys:
        # Collect candidates sharing this exact key
        group = [s for s in scores if tie_key(s) == key]
        group_len = len(group)

        if group_len == 1:
            cand_score = group[0]
            current_rank = cursor
            verdict = Verdict.ACCEPT if current_rank <= k else Verdict.REJECT
            ranked_entries.append(
                RankedEntry(rank=current_rank, score=cand_score, verdict=verdict)
            )
            cursor += 1
        else:
            # Tie detected across all three tie-break keys (D5)
            # All tied entries go to abstain_band, with equal rank
            tie_rank = cursor
            start_pos = cursor
            end_pos = cursor + group_len - 1

            if start_pos <= k <= end_pos:
                straddled_k = True

            for cand_score in group:
                abstain_entries.append(
                    RankedEntry(rank=tie_rank, score=cand_score, verdict=Verdict.UNREVIEWED)
                )

            cursor += group_len

    # Sort abstain_band strictly by candidate_id for display only (D5)
    sorted_abstain = tuple(sorted(abstain_entries, key=lambda e: e.score.candidate_id))
    sorted_ranked = tuple(ranked_entries)
    sorted_unparsed = tuple(sorted(unparsed, key=lambda o: o.filename))

    # Compute deterministic run_id independent of input order (D3, D10)
    canonical_cand_ids = sorted(s.candidate_id for s in scores)
    run_id_str = content_id(str(ranker), str(as_of), str(k), *canonical_cand_ids)
    run_id = RunId(run_id_str)

    return Ranking(
        run_id=run_id,
        ranker=ranker,
        as_of=as_of,
        ranked=sorted_ranked,
        abstain_band=sorted_abstain,
        abstain_straddled_k=straddled_k,
        unparsed=sorted_unparsed,
    )
