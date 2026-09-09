# core/rankers/r0_lexical.py — SDD §3 / BUILD_PROMPTS M10
import re
from core.ranking import rank
from core.scoring import score_candidate
from core.types import (
    AsOfDate,
    Bp,
    CandidateScore,
    ParseOutcome,
    RankerId,
    Ranking,
    Requirement,
    RequirementJudgement,
    ResumeText,
)


def _stem(token: str) -> str:
    """Pure, deterministic suffix stemming for English words."""
    t = token.lower().strip()
    if len(t) <= 3:
        return t
    suffixes = (
        "sses", "ies", "ting", "ling", "ning", "ing", "eed", "ed",
        "es", "s", "ment", "tion", "ational", "able", "ive", "ity",
    )
    for s in suffixes:
        if t.endswith(s) and len(t) - len(s) >= 3:
            return t[:-len(s)]
    return t


def rank_lexical(
    resumes: tuple[ResumeText, ...],
    requirements: tuple[Requirement, ...],
    idf_table: dict[str, int],
    unparsed: tuple[ParseOutcome, ...],
    k: int,
    as_of: AsOfDate,
) -> Ranking:
    """R0 Lexical Ranker: IDF-weighted token match over extracted requirements.

    Uses injected IDF table and suffix stemming on the exact requirement list R2 receives.
    Assembles CandidateScore and ranks candidates via core.ranking.rank.
    """
    candidate_scores: list[CandidateScore] = []

    for resume in resumes:
        # Tokenize and stem resume words
        tokens = re.findall(r"\b[a-zA-Z0-9]+\b", resume.text)
        stemmed_tokens = {_stem(t) for t in tokens}

        judgements: list[RequirementJudgement] = []
        for req in requirements:
            req_stems = [_stem(t) for t in req.tokens]
            if not req_stems:
                req_stems = [_stem(w) for w in re.findall(r"\b[a-zA-Z0-9]+\b", req.text)]

            matched_stems = [st for st in req_stems if st in stemmed_tokens]

            total_idf = sum(idf_table.get(st, 1000) for st in req_stems)
            matched_idf = sum(idf_table.get(st, 1000) for st in matched_stems)

            if total_idf > 0 and matched_idf > 0:
                confidence_val = (matched_idf * 10000) // total_idf
                is_met = True
                conf_bp = Bp(confidence_val)
            else:
                is_met = False
                conf_bp = Bp(0)

            judgements.append(
                RequirementJudgement(
                    candidate_id=resume.candidate_id,
                    requirement_id=req.id,
                    met=is_met,
                    confidence_bp=conf_bp,
                    evidence=None,
                )
            )

        cand_score = score_candidate(
            judgements=tuple(judgements),
            requirements=requirements,
            as_of=as_of,
        )
        candidate_scores.append(cand_score)

    return rank(
        scores=tuple(candidate_scores),
        unparsed=unparsed,
        k=k,
        ranker=RankerId.R0_LEXICAL,
        as_of=as_of,
    )
