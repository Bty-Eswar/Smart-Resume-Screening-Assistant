# core/scoring.py — SDD §3 / BUILD_PROMPTS M8
from dataclasses import replace
import re
from core.types import (
    AsOfDate,
    Bp,
    CandidateId,
    CandidateScore,
    Requirement,
    RequirementJudgement,
)


def _check_duration_satisfied(
    req_text: str,
    evidence_text: str,
    as_of: AsOfDate,
) -> bool:
    """Check if an experience-duration requirement is satisfied as of as_of.

    Looks for patterns like 'N+ years' in req_text and start years in evidence_text.
    """
    req_match = re.search(r"(\d+)\+?\s*years?", req_text, re.IGNORECASE)
    if not req_match:
        return True

    required_years = int(req_match.group(1))

    # Search for start year: '2020 to present', '2020 - present', 'since 2020', 'from 2020'
    ev_match = re.search(
        r"(?:since|from)\s*(20\d\d|19\d\d)\b|(20\d\d|19\d\d)\s*(?:-|to|–)\s*present",
        evidence_text,
        re.IGNORECASE,
    )
    if not ev_match:
        return True

    year_str = ev_match.group(1) or ev_match.group(2)
    start_year = int(year_str)

    as_of_year = int(str(as_of).split("-")[0])
    years_accrued = as_of_year - start_year

    return years_accrued >= required_years


def score_candidate(
    judgements: tuple[RequirementJudgement, ...],
    requirements: tuple[Requirement, ...],
    as_of: AsOfDate,
    high_weight_threshold_bp: int = 1000,
) -> CandidateScore:
    """Score a candidate based on requirement judgements and weights.

    Uses integer arithmetic only:
        score_bp = sum(weight_bp * confidence_bp // 10000 for met judgements)

    Judgements attached to CandidateScore are sorted strictly by requirement_id.
    as_of is required and load-bearing for duration reasoning (D2).
    """
    if not as_of:
        raise ValueError("as_of date is required")

    if not judgements:
        return CandidateScore(
            candidate_id=CandidateId(""),
            score_bp=Bp(0),
            met_count=0,
            high_weight_met_count=0,
            judgements=(),
        )

    cand_id = judgements[0].candidate_id
    for j in judgements:
        if j.candidate_id != cand_id:
            raise ValueError(f"Mismatched candidate_id in judgements: {j.candidate_id} != {cand_id}")

    req_map = {r.id: r for r in requirements}

    sorted_js: list[RequirementJudgement] = []
    score_bp_total = 0
    met_count = 0
    high_weight_met_count = 0

    # Sort judgements by requirement_id
    for j in sorted(judgements, key=lambda item: item.requirement_id):
        final_j = j
        if j.met:
            req = req_map.get(j.requirement_id)
            if req:
                # Check experience-duration sensitivity against as_of (D2)
                ev_text = j.evidence.text if j.evidence else ""
                if not _check_duration_satisfied(req.text, ev_text, as_of):
                    final_j = replace(j, met=False, evidence=None)

        if final_j.met:
            req = req_map.get(final_j.requirement_id)
            if req:
                weight = int(req.weight_bp)
                conf = int(final_j.confidence_bp)
                term = (weight * conf) // 10000
                score_bp_total += term
                met_count += 1
                if weight >= high_weight_threshold_bp:
                    high_weight_met_count += 1

        sorted_js.append(final_j)

    return CandidateScore(
        candidate_id=cand_id,
        score_bp=Bp(score_bp_total),
        met_count=met_count,
        high_weight_met_count=high_weight_met_count,
        judgements=tuple(sorted_js),
    )
