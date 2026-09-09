# core/rankers/r1_embedding.py — SDD §3 / BUILD_PROMPTS M10
import math
from typing import Mapping, Sequence
from core.quantize import quantize
from core.ranking import rank
from core.types import (
    AsOfDate,
    Bp,
    CandidateId,
    CandidateScore,
    ParseOutcome,
    RankerId,
    Ranking,
    ResumeText,
)


def _cosine_similarity_bp(
    u: Sequence[int],
    v: Sequence[int],
) -> Bp:
    """Compute cosine similarity between two numeric vectors, returning quantized basis points (0..10000)."""
    if not u or not v or len(u) != len(v):
        return Bp(0)

    dot = sum(x * y for x, y in zip(u, v))
    norm_u = math.sqrt(sum(x * x for x in u))
    norm_v = math.sqrt(sum(y * y for y in v))

    if norm_u <= 0 or norm_v <= 0:
        return Bp(0)

    cos_val = dot / (norm_u * norm_v)
    clamped = max(0.0, min(1.0, cos_val))
    return quantize(clamped)


def rank_embedding(
    resumes: tuple[ResumeText, ...],
    jd_vector: Sequence[int],
    resume_vectors: Mapping[CandidateId, Sequence[int]],
    unparsed: tuple[ParseOutcome, ...],
    k: int,
    as_of: AsOfDate,
    min_confidence_bp: int = 5000,
) -> Ranking:
    """R1 Embedding Ranker: Cosine similarity over pre-injected dense vectors.

    Pure function: does not fetch or compute embeddings.
    """
    candidate_scores: list[CandidateScore] = []

    for resume in resumes:
        vec = resume_vectors.get(resume.candidate_id)
        if vec is not None:
            score_bp = _cosine_similarity_bp(jd_vector, vec)
        else:
            score_bp = Bp(0)

        met = 1 if score_bp >= min_confidence_bp else 0
        cand_score = CandidateScore(
            candidate_id=resume.candidate_id,
            score_bp=score_bp,
            met_count=met,
            high_weight_met_count=met,
            judgements=(),
        )
        candidate_scores.append(cand_score)

    return rank(
        scores=tuple(candidate_scores),
        unparsed=unparsed,
        k=k,
        ranker=RankerId.R1_EMBEDDING,
        as_of=as_of,
    )
