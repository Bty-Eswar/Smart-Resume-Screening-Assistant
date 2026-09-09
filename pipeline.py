# pipeline.py — SDD §2, §8 / BUILD_PROMPTS M11
from dataclasses import dataclass, field
import json
from pathlib import Path
import time

from adapters.ingest import ingest_resumes
from adapters.judge_bedrock import Judge
from adapters.judge_cached import judge_all
from core.evidence import validate_evidence
from core.rankers.r0_lexical import rank_lexical
from core.rankers.r1_embedding import rank_embedding
from core.rankers.r2_llm import rank_llm
from core.ranking import rank
from core.requirements import build_requirements
from core.types import (
    AsOfDate,
    ParseOutcome,
    ParseStatus,
    RankedEntry,
    RankerId,
    Ranking,
    Requirement,
    RequirementJudgement,
    ResumeText,
    Sha256,
    Timing,
)


@dataclass
class TimingLog:
    """Accumulates stage execution telemetry (never mixed with ranking results per D14)."""
    timings: list[Timing] = field(default_factory=list)

    def record(self, stage: str, elapsed_ms: int, call_count: int = 1) -> Timing:
        t = Timing(stage=stage, elapsed_ms=elapsed_ms, call_count=call_count)
        self.timings.append(t)
        return t

    def to_dict(self) -> dict:
        return {
            "timings": [
                {
                    "stage": t.stage,
                    "elapsed_ms": t.elapsed_ms,
                    "call_count": t.call_count,
                }
                for t in self.timings
            ]
        }

    def write(self, path: str | Path = "eval/timing.json") -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def ranking_to_dict(ranking: Ranking) -> dict:
    """Convert a Ranking object to a pure JSON-serializable dictionary with zero telemetry."""
    def entry_to_dict(entry: RankedEntry) -> dict:
        return {
            "rank": entry.rank,
            "candidate_id": str(entry.score.candidate_id),
            "score_bp": int(entry.score.score_bp),
            "met_count": entry.score.met_count,
            "high_weight_met_count": entry.score.high_weight_met_count,
            "verdict": entry.verdict.value,
            "judgements": [
                {
                    "requirement_id": str(j.requirement_id),
                    "met": j.met,
                    "confidence_bp": int(j.confidence_bp),
                    "evidence": {
                        "start": j.evidence.start,
                        "end": j.evidence.end,
                        "text": j.evidence.text,
                    } if j.evidence else None,
                }
                for j in entry.score.judgements
            ],
        }

    return {
        "run_id": str(ranking.run_id),
        "ranker": ranking.ranker.value,
        "as_of": str(ranking.as_of),
        "abstain_straddled_k": ranking.abstain_straddled_k,
        "ranked": [entry_to_dict(e) for e in ranking.ranked],
        "abstain_band": [entry_to_dict(e) for e in ranking.abstain_band],
        "unparsed": [
            {
                "filename": o.filename,
                "status": o.status.value,
            }
            for o in ranking.unparsed
        ],
    }


def ingest_stage(
    resume_dir: str | Path,
    min_text_chars: int = 200,
) -> tuple[tuple[ParseOutcome, ...], Timing]:
    """Stage 1: Ingest resumes from directory."""
    t0 = time.monotonic()
    outcomes = ingest_resumes(resume_dir, min_text_chars=min_text_chars)
    elapsed = int((time.monotonic() - t0) * 1000)
    timing = Timing(stage="ingest", elapsed_ms=elapsed, call_count=len(outcomes))
    return outcomes, timing


def requirements_stage(
    raw_requirements: tuple[dict, ...],
    jd_sha: Sha256,
) -> tuple[tuple[Requirement, ...], Timing]:
    """Stage 2: Build and normalize requirements."""
    t0 = time.monotonic()
    reqs = build_requirements(raw_requirements, jd_sha)
    elapsed = int((time.monotonic() - t0) * 1000)
    timing = Timing(stage="requirements", elapsed_ms=elapsed, call_count=len(reqs))
    return reqs, timing


def judge_stage(
    resumes: tuple[ResumeText, ...],
    requirements: tuple[Requirement, ...],
    judge: Judge,
) -> tuple[tuple[RequirementJudgement, ...], Timing]:
    """Stage 3: Judge all resumes against requirements and validate evidence spans (D8)."""
    t0 = time.monotonic()
    raw_judgements = judge_all(resumes, requirements, judge)

    # Validate evidence spans verbatim (D8)
    resume_map = {r.candidate_id: r for r in resumes}
    validated_judgements = []
    for j in raw_judgements:
        res = resume_map[j.candidate_id]
        val_j = validate_evidence(j, res)
        validated_judgements.append(val_j)

    elapsed = int((time.monotonic() - t0) * 1000)
    timing = Timing(stage="judge", elapsed_ms=elapsed, call_count=len(validated_judgements))
    return tuple(validated_judgements), timing


def rank_stage(
    resumes: tuple[ResumeText, ...],
    requirements: tuple[Requirement, ...],
    judgements: tuple[RequirementJudgement, ...],
    unparsed: tuple[ParseOutcome, ...],
    k: int,
    ranker: RankerId,
    as_of: AsOfDate,
    idf_table: dict[str, int] | None = None,
    resume_vectors: dict | None = None,
    jd_vector: tuple[int, ...] | None = None,
) -> tuple[Ranking, Timing]:
    """Stage 4: Rank candidates using designated ranker."""
    t0 = time.monotonic()

    if ranker == RankerId.R0_LEXICAL:
        ranking = rank_lexical(
            resumes=resumes,
            requirements=requirements,
            idf_table=idf_table or {},
            unparsed=unparsed,
            k=k,
            as_of=as_of,
        )
    elif ranker == RankerId.R1_EMBEDDING:
        ranking = rank_embedding(
            resumes=resumes,
            jd_vector=jd_vector or (1, 1, 1),
            resume_vectors=resume_vectors or {},
            unparsed=unparsed,
            k=k,
            as_of=as_of,
        )
    else:
        # Default / R2_LLM
        ranking = rank_llm(
            resumes=resumes,
            requirements=requirements,
            judgements=judgements,
            unparsed=unparsed,
            k=k,
            as_of=as_of,
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    timing = Timing(stage="rank", elapsed_ms=elapsed, call_count=len(resumes))
    return ranking, timing


def run_pipeline(
    resume_dir: str | Path,
    requirements: tuple[Requirement, ...],
    judge: Judge,
    k: int = 10,
    ranker: RankerId = RankerId.R2_LLM,
    as_of: AsOfDate = AsOfDate("2026-01-01"),
    runs_dir: str | Path = "runs",
    timing_path: str | Path = "eval/timing.json",
    idf_table: dict[str, int] | None = None,
    resume_vectors: dict | None = None,
    jd_vector: tuple[int, ...] | None = None,
) -> tuple[Ranking, TimingLog]:
    """Execute end-to-end resume screening pipeline.

    Writes runs/<run_id>.json (D6 byte-identical) and eval/timing.json (D14 telemetry separation).
    Returns (Ranking, TimingLog).
    """
    timing_log = TimingLog()

    # 1. Ingest
    outcomes, t_ingest = ingest_stage(resume_dir)
    timing_log.timings.append(t_ingest)

    valid_resumes = tuple(o.resume for o in outcomes if o.status == ParseStatus.OK and o.resume is not None)
    unparsed = tuple(o for o in outcomes if o.status != ParseStatus.OK)

    # 2. Judge (if LLM ranker or judgements needed)
    judgements, t_judge = judge_stage(valid_resumes, requirements, judge)
    timing_log.timings.append(t_judge)

    # 3. Rank
    ranking, t_rank = rank_stage(
        resumes=valid_resumes,
        requirements=requirements,
        judgements=judgements,
        unparsed=unparsed,
        k=k,
        ranker=ranker,
        as_of=as_of,
        idf_table=idf_table,
        resume_vectors=resume_vectors,
        jd_vector=jd_vector,
    )
    timing_log.timings.append(t_rank)

    # 4. Persistence: write runs/<run_id>.json (D6)
    runs_path = Path(runs_dir)
    runs_path.mkdir(parents=True, exist_ok=True)
    run_file = runs_path / f"{ranking.run_id}.json"
    ranking_json = json.dumps(ranking_to_dict(ranking), indent=2, sort_keys=True)
    run_file.write_text(ranking_json, encoding="utf-8")

    # 5. Telemetry: write eval/timing.json (D14)
    timing_log.write(timing_path)

    return ranking, timing_log
