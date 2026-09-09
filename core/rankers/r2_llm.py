# core/rankers/r2_llm.py — SDD §3 / BUILD_PROMPTS M10
from core.ranking import rank
from core.scoring import score_candidate
from core.types import (
    AsOfDate,
    CandidateScore,
    ParseOutcome,
    RankerId,
    Ranking,
    Requirement,
    RequirementJudgement,
    ResumeText,
)


def rank_llm(
    resumes: tuple[ResumeText, ...],
    requirements: tuple[Requirement, ...],
    judgements: tuple[RequirementJudgement, ...],
    unparsed: tuple[ParseOutcome, ...],
    k: int,
    as_of: AsOfDate,
) -> Ranking:
    """R2 LLM Ranker: Assembles pre-computed and validated judgements into a Ranking.

    Pure function: does not call external LLM clients or APIs.
    """
    # Group judgements by candidate_id
    js_by_cand: dict[str, list[RequirementJudgement]] = {}
    for j in judgements:
        js_by_cand.setdefault(str(j.candidate_id), []).append(j)

    candidate_scores: list[CandidateScore] = []

    for resume in resumes:
        cand_js = js_by_cand.get(str(resume.candidate_id), [])
        cand_score = score_candidate(
            judgements=tuple(cand_js),
            requirements=requirements,
            as_of=as_of,
        )
        candidate_scores.append(cand_score)

    return rank(
        scores=tuple(candidate_scores),
        unparsed=unparsed,
        k=k,
        ranker=RankerId.R2_LLM,
        as_of=as_of,
    )
