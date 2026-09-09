# api.py — SDD §2 / BUILD_PROMPTS M11 Dashboard & Service
import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from adapters.embedding_local import compute_job_embeddings
from adapters.ingest import ingest_resumes
from adapters.judge_groq import GroqJudge, judge_all_concurrent
from core.ids import content_id
from core.normalize import normalize_ws
from core.rankers.r0_lexical import _stem, rank_lexical
from core.rankers.r1_embedding import rank_embedding
from core.rankers.r2_llm import rank_llm
from core.requirements import build_requirements
from core.types import (
    AsOfDate,
    CandidateId,
    ParseOutcome,
    ParseStatus,
    RankerId,
    Ranking,
    Requirement,
    RequirementId,
    ResumeText,
    Sha256,
    Verdict,
)
from pipeline import ranking_to_dict


app = FastAPI(title="Shortlist Resume Screening Assistant", version="1.0.0")

# CORS middleware allowing Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health check endpoint for reverse proxy and frontend connectivity probe."""
    return {"status": "ok", "service": "shortlist"}

from adapters.db import db, Job


class PersistentJobStore:
    """Unified ACID store backed by PostgreSQL in production or SQLite/In-Memory locally."""
    def __getitem__(self, job_id: str) -> Job:
        job = db.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def __setitem__(self, job_id: str, job: Job) -> None:
        db.save_job(job)

    def __contains__(self, job_id: str) -> bool:
        return db.get_job(job_id) is not None

    def values(self):
        return db.list_jobs()

    def get(self, job_id: str, default=None):
        job = db.get_job(job_id)
        return job if job is not None else default


_job_store = PersistentJobStore()


def extract_draft_requirements(jd_text: str) -> list[str]:
    """Extract candidate requirement lines from raw JD text using rule-based parsing.

    Splits on newlines and bullet markers, strips leading bullet prefixes (-, *, •, 1.),
    drops lines < 3 chars, and normalizes whitespace with normalize_ws. Does not invoke Bedrock (D7).
    """
    raw_lines = re.split(r"[\r\n]+|[•]", jd_text)
    candidate_reqs: list[str] = []
    for line in raw_lines:
        # Match only bullet prefix like '-', '*', '•', or '1.', '2)' without stripping digits in text like '7+'
        cleaned = re.sub(r"^\s*(?:[-*•–—]|\d+[.)])\s*", "", line)
        norm = normalize_ws(cleaned)
        if len(norm) >= 3:
            candidate_reqs.append(norm)
    return candidate_reqs


def ensure_seed_job() -> Job | None:
    """Auto-seed canonical sample job if not yet created so demo links work out of the box."""
    job_id = "job_af87c8e68eb50d59278ad54f6cadf9c1"
    if job_id in _job_store:
        existing = _job_store[job_id]
        if existing.ranking is not None:
            return existing

    title = "Mid-Level Backend Engineer"
    jd_text = (
        "Mid-Level Backend Engineer\n"
        "- 3+ years of professional backend development experience with Python\n"
        "- Experience designing and maintaining RESTful APIs and PostgreSQL databases\n"
        "- Hands-on experience with Docker containerization and CI/CD pipelines\n"
        "- Working knowledge of Redis caching and distributed asynchronous task queues\n"
        "- Solid understanding of Git version control, unit testing, and agile team workflows"
    )
    norm_jd = normalize_ws(jd_text)
    jd_sha = hashlib.sha256(norm_jd.encode("utf-8")).hexdigest()

    candidates = extract_draft_requirements(jd_text)
    raw_reqs = tuple({"text": text, "weight": 100} for text in candidates)
    reqs = build_requirements(raw_reqs, Sha256(jd_sha))

    resume_dir = Path(tempfile.gettempdir()) / "shortlist_jobs" / job_id / "resumes"
    resume_dir.mkdir(parents=True, exist_ok=True)

    eval_dir = Path("eval")
    for i in range(1, 6):
        sample_file = eval_dir / f"resume_holdout_0{i}.pdf"
        if sample_file.exists():
            try:
                shutil.copy2(sample_file, resume_dir / sample_file.name)
            except Exception:
                pass

    outcomes = ingest_resumes(resume_dir)
    valid_resumes = tuple(o.resume for o in outcomes if o.status == ParseStatus.OK and o.resume is not None)
    unparsed_outcomes = tuple(o for o in outcomes if o.status != ParseStatus.OK or o.resume is None)

    if not valid_resumes:
        job = Job(
            job_id=job_id,
            title=title,
            jd_text=jd_text,
            jd_sha256=jd_sha,
            requirements=reqs,
            resume_dir=resume_dir,
            parse_outcomes=outcomes,
            ranking=None,
            status="draft",
            ranker_used=None,
            all_rankings=None,
        )
        _job_store[job_id] = job
        return job

    seed_as_of = AsOfDate("2026-01-01")

    # Build IDF table from valid resumes (same logic as _run_r0_lexical)
    n_docs = len(valid_resumes)
    doc_token_sets = [
        {_stem(t) for t in re.findall(r"\b[a-zA-Z0-9]+\b", r.text)}
        for r in valid_resumes
    ]
    all_stems: set[str] = set()
    for s_set in doc_token_sets:
        all_stems.update(s_set)
    for req in reqs:
        for t in req.tokens:
            all_stems.add(_stem(t))
        for w in re.findall(r"\b[a-zA-Z0-9]+\b", req.text):
            all_stems.add(_stem(w))
    idf_table: dict[str, int] = {}
    for st in all_stems:
        doc_freq = sum(1 for s_set in doc_token_sets if st in s_set)
        idf_table[st] = max(1, (n_docs * 1000) // max(1, doc_freq))

    r0 = rank_lexical(
        resumes=valid_resumes,
        requirements=reqs,
        idf_table=idf_table,
        unparsed=unparsed_outcomes,
        k=10,
        as_of=seed_as_of,
    )

    jd_vec, resume_vecs = compute_job_embeddings(jd_text, valid_resumes)
    r1 = rank_embedding(
        resumes=valid_resumes,
        jd_vector=jd_vec,
        resume_vectors=resume_vecs,
        unparsed=unparsed_outcomes,
        k=10,
        as_of=seed_as_of,
    )

    all_rankings = {
        "r0_lexical": r0,
        "r1_embedding": r1,
        "r2_llm": r0,
    }

    job = Job(
        job_id=job_id,
        title=title,
        jd_text=jd_text,
        jd_sha256=jd_sha,
        requirements=reqs,
        resume_dir=resume_dir,
        parse_outcomes=outcomes,
        ranking=r0,
        status="ranked",
        ranker_used="compare_all",
        all_rankings=all_rankings,
    )
    _job_store[job_id] = job
    return job



class CreateJobRequest(BaseModel):
    title: str
    jd_text: str


class RequirementItem(BaseModel):
    id: str | None = None
    text: str
    weight: int = 100


class UpdateRequirementsRequest(BaseModel):
    requirements: list[RequirementItem]


class RunJobRequest(BaseModel):
    ranker: str = "r0_lexical"
    k: int = 10
    as_of: str | None = None


class VerdictUpdateRequest(BaseModel):
    candidate_id: str
    verdict: str




@app.post("/api/jobs")
def create_job(body: CreateJobRequest):
    """Create a new screening job, compute deterministic hash/id, and extract draft requirements."""
    norm_jd = normalize_ws(body.jd_text)
    if not norm_jd:
        raise HTTPException(status_code=400, detail="Job description text cannot be empty")

    jd_sha = hashlib.sha256(norm_jd.encode("utf-8")).hexdigest()
    # Deterministic content ID with random-free seed (D3 compliant)
    job_id = f"job_{content_id(norm_jd, 'shortlist_job_seed')}"

    candidates = extract_draft_requirements(body.jd_text)
    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="No requirements could be extracted from job description",
        )

    # Equal raw weight of 100 each; build_requirements normalizes sum to 10000 bp
    raw_reqs = tuple({"text": text, "weight": 100} for text in candidates)
    reqs = build_requirements(raw_reqs, Sha256(jd_sha))

    resume_dir = Path(tempfile.gettempdir()) / "shortlist_jobs" / job_id / "resumes"
    resume_dir.mkdir(parents=True, exist_ok=True)

    job = Job(
        job_id=job_id,
        title=body.title,
        jd_text=body.jd_text,
        jd_sha256=jd_sha,
        requirements=reqs,
        resume_dir=resume_dir,
        parse_outcomes=None,
        ranking=None,
        status="draft",
        ranker_used=None,
        all_rankings={},
    )
    _job_store[job_id] = job

    return {
        "job_id": job_id,
        "title": job.title,
        "status": job.status,
        "requirements": [
            {"id": str(r.id), "text": r.text, "weight_bp": int(r.weight_bp)}
            for r in reqs
        ],
    }


@app.put("/api/jobs/{job_id}/requirements")
def update_job_requirements(job_id: str, body: UpdateRequirementsRequest):
    """Update requirement list and weights for a job, re-normalizing via build_requirements."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    job = _job_store[job_id]

    if not body.requirements:
        raise HTTPException(status_code=400, detail="Requirements list cannot be empty")

    raw_reqs = tuple(
        {"text": r.text, "weight": r.weight}
        for r in body.requirements
    )
    try:
        reqs = build_requirements(raw_reqs, Sha256(job.jd_sha256))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job.requirements = reqs
    _job_store[job_id] = job

    return {
        "job_id": job_id,
        "requirements": [
            {"id": str(r.id), "text": r.text, "weight_bp": int(r.weight_bp)}
            for r in reqs
        ],
    }


@app.post("/api/jobs/{job_id}/resumes")
async def upload_resumes(job_id: str, files: list[UploadFile] = File(...)):
    """Upload resume files for a job, ingest and return per-file parse outcomes."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    job = _job_store[job_id]

    if job.requirements is None or len(job.requirements) == 0:
        raise HTTPException(
            status_code=409,
            detail="Requirements must be confirmed before uploading resumes",
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    for file in files:
        fname = file.filename or ""
        if not fname or "/" in fname or "\\" in fname or ".." in fname:
            raise HTTPException(
                status_code=400,
                detail=f"Path traversal detected or invalid filename: {fname}",
            )
        dest = job.resume_dir / fname
        content = await file.read()
        dest.write_bytes(content)

    # Ingest using existing tested adapter (PDD R3: failures are surfaced, never swallowed)
    outcomes = ingest_resumes(job.resume_dir)
    job.parse_outcomes = outcomes
    job.status = "resumes_uploaded"
    _job_store[job_id] = job

    file_summaries = [
        {
            "filename": o.filename,
            "status": o.status.value,
            "char_count": o.resume.char_count if o.resume else None,
        }
        for o in outcomes
    ]
    summary_counts = {
        "ok": sum(1 for o in outcomes if o.status == ParseStatus.OK),
        "no_text_layer": sum(1 for o in outcomes if o.status == ParseStatus.NO_TEXT_LAYER),
        "unsupported_type": sum(1 for o in outcomes if o.status == ParseStatus.UNSUPPORTED_TYPE),
        "corrupt": sum(1 for o in outcomes if o.status == ParseStatus.CORRUPT),
    }

    return {
        "job_id": job_id,
        "files": file_summaries,
        "summary": summary_counts,
    }


@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: str):
    """Return complete state for a job."""
    if job_id not in _job_store:
        if job_id == "job_af87c8e68eb50d59278ad54f6cadf9c1":
            job = ensure_seed_job()
            if not job:
                raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        else:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    else:
        job = _job_store[job_id]

    parse_summary = None
    if job.parse_outcomes is not None:
        parse_summary = {
            "files": [
                {
                    "filename": o.filename,
                    "status": o.status.value,
                    "char_count": o.resume.char_count if o.resume else None,
                }
                for o in job.parse_outcomes
            ],
            "summary": {
                "ok": sum(1 for o in job.parse_outcomes if o.status == ParseStatus.OK),
                "no_text_layer": sum(1 for o in job.parse_outcomes if o.status == ParseStatus.NO_TEXT_LAYER),
                "unsupported_type": sum(1 for o in job.parse_outcomes if o.status == ParseStatus.UNSUPPORTED_TYPE),
                "corrupt": sum(1 for o in job.parse_outcomes if o.status == ParseStatus.CORRUPT),
            },
        }

    return {
        "job_id": job.job_id,
        "title": job.title,
        "status": job.status,
        "jd_text": job.jd_text,
        "jd_sha256": job.jd_sha256,
        "requirements": [
            {"id": str(r.id), "text": r.text, "weight_bp": int(r.weight_bp)}
            for r in job.requirements
        ] if job.requirements is not None else None,
        "parse_summary": parse_summary,
        "ranking": ranking_to_dict(job.ranking) if job.ranking is not None else None,
    }


@app.get("/api/jobs")
def list_jobs():
    """Return overview of all jobs."""
    if "job_af87c8e68eb50d59278ad54f6cadf9c1" not in _job_store:
        try:
            ensure_seed_job()
        except Exception:
            pass

    jobs_list = []
    for job in _job_store.values():
        cand_count = (
            sum(1 for o in job.parse_outcomes if o.status == ParseStatus.OK)
            if job.parse_outcomes
            else 0
        )
        jobs_list.append({
            "job_id": job.job_id,
            "title": job.title,
            "status": job.status,
            "candidate_count": cand_count,
        })
    return jobs_list


@app.get("/api/sample-resumes")
def get_sample_resumes():
    """Return available sample resumes from eval/ for hackathon demo convenience."""
    eval_dir = Path("eval")
    sample_files = []
    if eval_dir.exists():
        for i in range(1, 6):
            fn = f"resume_holdout_{i:02d}.pdf"
            p = eval_dir / fn
            if p.exists():
                sample_files.append({"filename": fn, "size_bytes": p.stat().st_size})
    return sample_files


@app.post("/api/jobs/{job_id}/resumes/sample")
def use_sample_resumes(job_id: str):
    """Copy sample resumes from eval/ into job's resume_dir and ingest (demo helper)."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    job = _job_store[job_id]

    if job.requirements is None or len(job.requirements) == 0:
        raise HTTPException(
            status_code=409,
            detail="Requirements must be confirmed before uploading resumes",
        )

    eval_dir = Path("eval")
    copied = 0
    for i in range(1, 6):
        fn = f"resume_holdout_{i:02d}.pdf"
        src = eval_dir / fn
        if src.exists():
            dest = job.resume_dir / fn
            shutil.copy2(src, dest)
            copied += 1

    if copied == 0:
        raise HTTPException(status_code=404, detail="No sample resumes found in eval/")

    outcomes = ingest_resumes(job.resume_dir)
    job.parse_outcomes = outcomes
    job.status = "resumes_uploaded"
    _job_store[job_id] = job

    file_summaries = [
        {
            "filename": o.filename,
            "status": o.status.value,
            "char_count": o.resume.char_count if o.resume else None,
        }
        for o in outcomes
    ]
    summary_counts = {
        "ok": sum(1 for o in outcomes if o.status == ParseStatus.OK),
        "no_text_layer": sum(1 for o in outcomes if o.status == ParseStatus.NO_TEXT_LAYER),
        "unsupported_type": sum(1 for o in outcomes if o.status == ParseStatus.UNSUPPORTED_TYPE),
        "corrupt": sum(1 for o in outcomes if o.status == ParseStatus.CORRUPT),
    }

    return {
        "job_id": job_id,
        "files": file_summaries,
        "summary": summary_counts,
    }



def _run_r0_lexical(job: Job, valid_resumes: tuple[ResumeText, ...], unparsed: tuple[ParseOutcome, ...], k: int, as_of_date: AsOfDate) -> Ranking:
    n_docs = len(valid_resumes)
    doc_token_sets = [
        {_stem(t) for t in re.findall(r"\b[a-zA-Z0-9]+\b", r.text)}
        for r in valid_resumes
    ]
    all_stems: set[str] = set()
    for s_set in doc_token_sets:
        all_stems.update(s_set)
    if job.requirements:
        for req in job.requirements:
            for t in req.tokens:
                all_stems.add(_stem(t))
            for w in re.findall(r"\b[a-zA-Z0-9]+\b", req.text):
                all_stems.add(_stem(w))

    idf_table: dict[str, int] = {}
    for st in all_stems:
        doc_freq = sum(1 for s_set in doc_token_sets if st in s_set)
        idf_table[st] = max(1, (n_docs * 1000) // max(1, doc_freq))

    return rank_lexical(
        resumes=valid_resumes,
        requirements=job.requirements or (),
        idf_table=idf_table,
        unparsed=unparsed,
        k=k,
        as_of=as_of_date,
    )


def _run_r1_embedding(job: Job, valid_resumes: tuple[ResumeText, ...], unparsed: tuple[ParseOutcome, ...], k: int, as_of_date: AsOfDate) -> Ranking:
    jd_vec, resume_vecs = compute_job_embeddings(job.jd_text, valid_resumes)
    return rank_embedding(
        resumes=valid_resumes,
        jd_vector=jd_vec,
        resume_vectors=resume_vecs,
        unparsed=unparsed,
        k=k,
        as_of=as_of_date,
    )


def _run_r2_llm(job: Job, valid_resumes: tuple[ResumeText, ...], unparsed: tuple[ParseOutcome, ...], k: int, as_of_date: AsOfDate) -> Ranking:
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise HTTPException(
            status_code=400,
            detail="GROQ_API_KEY is not configured in .env. Please configure GROQ_API_KEY to run the R2 LLM ranker.",
        )
    judge = GroqJudge(api_key=groq_key)
    judgements = judge_all_concurrent(valid_resumes, job.requirements or (), judge)
    return rank_llm(
        resumes=valid_resumes,
        requirements=job.requirements or (),
        judgements=judgements,
        unparsed=unparsed,
        k=k,
        as_of=as_of_date,
    )


def _build_candidate_comparison(
    resumes: tuple[ResumeText, ...],
    r0: Ranking | None,
    r1: Ranking | None,
    r2: Ranking | None,
) -> list[dict]:
    def extract_map(rk: Ranking | None):
        if not rk:
            return {}
        mapping = {}
        for rank_idx, e in enumerate(rk.ranked, start=1):
            mapping[str(e.score.candidate_id)] = {
                "score_bp": int(e.score.score_bp),
                "rank": rank_idx,
                "in_top_k": True,
                "verdict": e.verdict.value,
                "met_count": e.score.met_count,
            }
        for e in rk.abstain_band:
            mapping[str(e.score.candidate_id)] = {
                "score_bp": int(e.score.score_bp),
                "rank": None,
                "in_top_k": False,
                "abstain": True,
                "verdict": e.verdict.value,
                "met_count": e.score.met_count,
            }
        return mapping

    m0 = extract_map(r0)
    m1 = extract_map(r1)
    m2 = extract_map(r2)

    rows = []
    for r in resumes:
        cid = str(r.candidate_id)
        info0 = m0.get(cid)
        info1 = m1.get(cid)
        info2 = m2.get(cid)

        available_scores = [
            info["score_bp"]
            for info in (info0, info1, info2)
            if info is not None and "score_bp" in info
        ]
        avg_score = sum(available_scores) // len(available_scores) if available_scores else 0

        ranks = [info["rank"] for info in (info0, info1, info2) if info and info.get("rank")]
        if len(ranks) >= 2 and all(rk <= 3 for rk in ranks):
            consensus = "Strong Fit (Unanimous Top Tier)"
        elif info2 and info2.get("rank") and (not info0 or not info0.get("rank") or info0["rank"] > info2["rank"]):
            consensus = "LLM Advantage (Verified Proof Spans)"
        elif info1 and info1.get("rank") and (not info0 or not info0.get("rank")):
            consensus = "Semantic Fit (Beyond Exact Keywords)"
        else:
            consensus = "Standard Consensus"

        rows.append({
            "candidate_id": cid,
            "filename": r.filename,
            "char_count": r.char_count,
            "avg_score_bp": avg_score,
            "consensus": consensus,
            "r0": info0,
            "r1": info1,
            "r2": info2,
        })

    rows.sort(key=lambda x: x["avg_score_bp"], reverse=True)
    return rows


@app.post("/api/jobs/{job_id}/run")
def run_job_pipeline(job_id: str, body: RunJobRequest | None = None):
    """Run ranking pipeline for a job using designated ranker (r0_lexical, r1_embedding, r2_llm, or compare_all)."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    job = _job_store[job_id]

    if not job.requirements:
        raise HTTPException(
            status_code=400,
            detail="Requirements have not been set or confirmed for this job. Configure requirements first.",
        )
    if not job.parse_outcomes:
        raise HTTPException(
            status_code=400,
            detail="No resumes have been uploaded for this job. Upload resumes first.",
        )

    req_body = body or RunJobRequest()
    ranker_choice = req_body.ranker.lower()
    valid_choices = ("r0_lexical", "r1_embedding", "r2_llm", "compare_all")
    if ranker_choice not in valid_choices:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported ranker '{req_body.ranker}'. Supported rankers: {', '.join(valid_choices)}.",
        )

    valid_resumes = tuple(
        o.resume for o in job.parse_outcomes
        if o.status == ParseStatus.OK and o.resume is not None
    )
    unparsed = tuple(
        o for o in job.parse_outcomes
        if o.status != ParseStatus.OK
    )

    if not valid_resumes:
        raise HTTPException(
            status_code=400,
            detail="No resumes parsed successfully with valid text layer (0 candidates). Cannot rank.",
        )

    as_of_str = req_body.as_of or datetime.date.today().isoformat()
    as_of_date = AsOfDate(as_of_str)

    if job.all_rankings is None:
        job.all_rankings = {}

    if ranker_choice == "r0_lexical":
        ranking = _run_r0_lexical(job, valid_resumes, unparsed, req_body.k, as_of_date)
        job.all_rankings["r0_lexical"] = ranking
        job.ranking = ranking
        job.ranker_used = "r0_lexical"

    elif ranker_choice == "r1_embedding":
        ranking = _run_r1_embedding(job, valid_resumes, unparsed, req_body.k, as_of_date)
        job.all_rankings["r1_embedding"] = ranking
        job.ranking = ranking
        job.ranker_used = "r1_embedding"

    elif ranker_choice == "r2_llm":
        ranking = _run_r2_llm(job, valid_resumes, unparsed, req_body.k, as_of_date)
        job.all_rankings["r2_llm"] = ranking
        job.ranking = ranking
        job.ranker_used = "r2_llm"

    elif ranker_choice == "compare_all":
        r0 = _run_r0_lexical(job, valid_resumes, unparsed, req_body.k, as_of_date)
        r1 = _run_r1_embedding(job, valid_resumes, unparsed, req_body.k, as_of_date)
        r2 = _run_r2_llm(job, valid_resumes, unparsed, req_body.k, as_of_date)
        job.all_rankings["r0_lexical"] = r0
        job.all_rankings["r1_embedding"] = r1
        job.all_rankings["r2_llm"] = r2
        job.ranking = r2
        job.ranker_used = "compare_all"
        ranking = r2

    job.status = "ranked"
    _job_store[job_id] = job

    global _current_ranking_data
    _current_ranking_data = ranking_to_dict(ranking)

    comparison = _build_candidate_comparison(
        valid_resumes,
        job.all_rankings.get("r0_lexical"),
        job.all_rankings.get("r1_embedding"),
        job.all_rankings.get("r2_llm"),
    )

    resp_data = ranking_to_dict(ranking)
    resp_data["active_ranker"] = job.ranker_used
    resp_data["available_rankers"] = list(job.all_rankings.keys())
    resp_data["comparison"] = comparison
    return resp_data


@app.get("/api/jobs/{job_id}/ranking")
def get_job_ranking(job_id: str, ranker: str | None = None):
    """Return ranking for a specific job, with support for selecting ranker view."""
    if job_id not in _job_store:
        if job_id == "job_af87c8e68eb50d59278ad54f6cadf9c1":
            ensure_seed_job()
        if job_id not in _job_store:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    job = _job_store[job_id]

    if job.ranking is None and not job.all_rankings:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' has not been ranked yet. Run POST /api/jobs/{job_id}/run first.",
        )

    target_ranking = job.ranking
    selected_ranker = ranker or job.ranker_used or "r0_lexical"
    if ranker and job.all_rankings and ranker in job.all_rankings:
        target_ranking = job.all_rankings[ranker]
        selected_ranker = ranker

    valid_resumes = tuple(
        o.resume for o in (job.parse_outcomes or ())
        if o.status == ParseStatus.OK and o.resume is not None
    )

    comparison = _build_candidate_comparison(
        valid_resumes,
        (job.all_rankings or {}).get("r0_lexical"),
        (job.all_rankings or {}).get("r1_embedding"),
        (job.all_rankings or {}).get("r2_llm"),
    )

    resp_data = ranking_to_dict(target_ranking)
    resp_data["active_ranker"] = selected_ranker
    resp_data["available_rankers"] = list((job.all_rankings or {}).keys())
    resp_data["comparison"] = comparison
    return resp_data


@app.post("/api/jobs/{job_id}/verdict")
def update_job_verdict(job_id: str, req: VerdictUpdateRequest):
    """Update candidate verdict scoped to a specific job."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    job = _job_store[job_id]

    if job.ranking is None:
        raise HTTPException(status_code=400, detail=f"Job '{job_id}' has not been ranked yet")

    v_str = req.verdict.lower()
    if v_str not in ("accept", "reject", "unreviewed"):
        raise HTTPException(status_code=400, detail="Invalid verdict; must be 'accept', 'reject', or 'unreviewed'")

    v_enum = Verdict(v_str)
    found = False

    updated_ranked = []
    for entry in job.ranking.ranked:
        if entry.score.candidate_id == req.candidate_id:
            updated_ranked.append(replace(entry, verdict=v_enum))
            found = True
        else:
            updated_ranked.append(entry)

    updated_abstain = []
    for entry in job.ranking.abstain_band:
        if entry.score.candidate_id == req.candidate_id:
            updated_abstain.append(replace(entry, verdict=v_enum))
            found = True
        else:
            updated_abstain.append(entry)

    if not found:
        raise HTTPException(status_code=404, detail=f"Candidate '{req.candidate_id}' not found in ranking")

    job.ranking = replace(
        job.ranking,
        ranked=tuple(updated_ranked),
        abstain_band=tuple(updated_abstain),
    )

    if job.all_rankings:
        for rk_key, rk_obj in job.all_rankings.items():
            u_ranked = [replace(entry, verdict=v_enum) if entry.score.candidate_id == req.candidate_id else entry for entry in rk_obj.ranked]
            u_abstain = [replace(entry, verdict=v_enum) if entry.score.candidate_id == req.candidate_id else entry for entry in rk_obj.abstain_band]
            job.all_rankings[rk_key] = replace(rk_obj, ranked=tuple(u_ranked), abstain_band=tuple(u_abstain))

    _job_store[job_id] = job
    db.update_verdict(job_id, req.candidate_id, v_str)

    global _current_ranking_data
    _current_ranking_data = ranking_to_dict(job.ranking)

    return {"status": "ok", "job_id": job_id, "candidate_id": req.candidate_id, "verdict": v_str}


# In-memory active ranking cache for the dashboard
_current_ranking_data: dict[str, Any] = {
    "run_id": "run_demo_01",
    "ranker": "r2_llm",
    "as_of": "2026-01-01",
    "abstain_straddled_k": True,
    "ranked": [
        {
            "rank": 1,
            "candidate_id": "cand_01",
            "score_bp": 9500,
            "met_count": 3,
            "high_weight_met_count": 2,
            "verdict": "accept",
            "judgements": [
                {
                    "requirement_id": "req_py",
                    "met": True,
                    "confidence_bp": 9800,
                    "evidence": {
                        "start": 42,
                        "end": 96,
                        "text": "Senior Python Architect with microservices expertise",
                    },
                },
                {
                    "requirement_id": "req_k8s",
                    "met": True,
                    "confidence_bp": 9200,
                    "evidence": {
                        "start": 120,
                        "end": 165,
                        "text": "Managed 50-node production Kubernetes cluster",
                    },
                },
            ],
        },
        {
            "rank": 2,
            "candidate_id": "cand_02",
            "score_bp": 8800,
            "met_count": 2,
            "high_weight_met_count": 2,
            "verdict": "accept",
            "judgements": [
                {
                    "requirement_id": "req_py",
                    "met": True,
                    "confidence_bp": 8900,
                    "evidence": {
                        "start": 15,
                        "end": 50,
                        "text": "5 years backend Python developer",
                    },
                },
            ],
        },
    ],
    "abstain_band": [
        {
            "rank": 3,
            "candidate_id": "cand_tied_alpha",
            "score_bp": 7200,
            "met_count": 2,
            "high_weight_met_count": 1,
            "verdict": "unreviewed",
            "judgements": [
                {
                    "requirement_id": "req_py",
                    "met": True,
                    "confidence_bp": 7200,
                    "evidence": {
                        "start": 10,
                        "end": 40,
                        "text": "Experienced in Python APIs",
                    },
                },
            ],
        },
        {
            "rank": 3,
            "candidate_id": "cand_tied_beta",
            "score_bp": 7200,
            "met_count": 2,
            "high_weight_met_count": 1,
            "verdict": "unreviewed",
            "judgements": [
                {
                    "requirement_id": "req_py",
                    "met": True,
                    "confidence_bp": 7200,
                    "evidence": {
                        "start": 20,
                        "end": 50,
                        "text": "Experienced in Python APIs",
                    },
                },
            ],
        },
    ],
    "unparsed": [
        {"filename": "corrupted_scan.pdf", "status": "corrupt"},
    ],
}


def set_active_ranking(ranking: Ranking) -> None:
    """Set the active ranking for the API and dashboard."""
    global _current_ranking_data
    _current_ranking_data = ranking_to_dict(ranking)


def render_dashboard_html(ranking_data: dict[str, Any] | None = None) -> str:
    """Render the dashboard HTML with rich aesthetics, expandable evidence, and visual abstain band."""
    data = ranking_data or _current_ranking_data

    ranked_items = data.get("ranked", [])
    abstain_items = data.get("abstain_band", [])
    unparsed_items = data.get("unparsed", [])

    abstain_count = len(abstain_items)
    ranked_count = len(ranked_items)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shortlist — Screening Assistant</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0a0d14;
            --bg-card: rgba(18, 24, 38, 0.7);
            --bg-card-hover: rgba(26, 34, 52, 0.85);
            --border: rgba(255, 255, 255, 0.08);
            --border-accent: rgba(99, 102, 241, 0.3);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent: #6366f1;
            --accent-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
            --font-display: 'Outfit', system-ui, sans-serif;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: var(--font-sans);
            min-height: 100vh;
            padding: 2.5rem 1.5rem;
            line-height: 1.5;
            background-image: 
                radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(168, 85, 247, 0.1) 0px, transparent 50%);
            background-attachment: fixed;
        }}

        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border);
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .brand-icon {{
            width: 40px;
            height: 40px;
            background: var(--accent-gradient);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: var(--font-display);
            font-weight: 800;
            font-size: 1.25rem;
            box-shadow: 0 4px 16px rgba(99, 102, 241, 0.3);
        }}

        h1 {{
            font-family: var(--font-display);
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }}

        .meta-badges {{
            display: flex;
            gap: 0.5rem;
        }}

        .badge {{
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.35rem 0.75rem;
            border-radius: 9999px;
            border: 1px solid var(--border);
            background: rgba(255, 255, 255, 0.04);
            letter-spacing: 0.02em;
        }}

        .badge-ranker {{
            border-color: var(--border-accent);
            color: #c4b5fd;
        }}

        /* Metrics Bar */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            backdrop-filter: blur(12px);
            padding: 1.25rem;
            border-radius: 14px;
        }}

        .metric-label {{
            font-size: 0.8rem;
            text-transform: uppercase;
            color: var(--text-muted);
            font-weight: 600;
            letter-spacing: 0.05em;
            margin-bottom: 0.35rem;
        }}

        .metric-val {{
            font-family: var(--font-display);
            font-size: 1.75rem;
            font-weight: 700;
        }}

        /* Abstain Band */
        .abstain-section {{
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(217, 119, 6, 0.03) 100%);
            border: 1px solid rgba(245, 158, 11, 0.25);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 2.5rem;
            box-shadow: 0 4px 24px rgba(245, 158, 11, 0.05);
        }}

        .abstain-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }}

        .abstain-title {{
            font-family: var(--font-display);
            font-size: 1.25rem;
            font-weight: 700;
            color: #fcd34d;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .abstain-size-badge {{
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 0.85rem;
        }}

        .abstain-desc {{
            font-size: 0.875rem;
            color: #fde68a;
            opacity: 0.85;
            margin-bottom: 1rem;
        }}

        /* Candidate Cards */
        .card-list {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}

        .candidate-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1.25rem;
            transition: all 0.2s ease;
            backdrop-filter: blur(10px);
        }}

        .candidate-card:hover {{
            background: var(--bg-card-hover);
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateY(-1px);
        }}

        .card-main {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
        }}

        .card-left {{
            display: flex;
            align-items: center;
            gap: 1.25rem;
        }}

        .rank-num {{
            font-family: var(--font-display);
            font-size: 1.25rem;
            font-weight: 800;
            color: var(--text-muted);
            min-width: 2.5rem;
        }}

        .cand-name {{
            font-weight: 600;
            font-size: 1rem;
        }}

        .score-pill {{
            background: rgba(99, 102, 241, 0.1);
            color: #818cf8;
            border: 1px solid rgba(99, 102, 241, 0.2);
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-family: monospace;
            font-weight: 600;
            font-size: 0.85rem;
        }}

        .card-right {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .btn {{
            cursor: pointer;
            font-family: var(--font-sans);
            font-size: 0.85rem;
            font-weight: 600;
            padding: 0.45rem 1rem;
            border-radius: 8px;
            border: none;
            transition: all 0.15s ease;
        }}

        .btn-accept {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .btn-accept:hover {{
            background: var(--success);
            color: #fff;
        }}

        .btn-reject {{
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}

        .btn-reject:hover {{
            background: var(--danger);
            color: #fff;
        }}

        .btn-expand {{
            background: transparent;
            color: var(--text-secondary);
            border: 1px solid var(--border);
        }}

        .btn-expand:hover {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-primary);
        }}

        /* Evidence Drawer */
        .evidence-drawer {{
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}

        .evidence-row {{
            background: rgba(0, 0, 0, 0.25);
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border-left: 3px solid var(--accent);
        }}

        .evidence-header {{
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 0.35rem;
        }}

        .evidence-text {{
            font-size: 0.9rem;
            color: #e2e8f0;
            font-style: italic;
        }}

        .evidence-offsets {{
            font-family: monospace;
            color: var(--text-muted);
            font-size: 0.75rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <div class="brand-icon">S</div>
                <div>
                    <h1>Shortlist</h1>
                    <p style="font-size: 0.8rem; color: var(--text-muted);">Deterministic Resume Screening Assistant</p>
                </div>
            </div>
            <div class="meta-badges">
                <span class="badge badge-ranker">Ranker: {data.get("ranker", "r2_llm")}</span>
                <span class="badge">As-Of: {data.get("as_of", "2026-01-01")}</span>
                <span class="badge">Run: {data.get("run_id", "demo")[:10]}...</span>
            </div>
        </header>

        <!-- Summary Metrics -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Ranked Candidates</div>
                <div class="metric-val">{ranked_count}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Abstain Band Size</div>
                <div class="metric-val" style="color: #fbbf24;">{abstain_count}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Unparsed Files</div>
                <div class="metric-val" style="color: var(--text-muted);">{len(unparsed_items)}</div>
            </div>
        </div>

        <!-- Distinct Abstain Band Section -->
        <section id="abstain-band" class="abstain-section">
            <div class="abstain-header">
                <div class="abstain-title">
                    <span>⚠️</span> Abstain Band (Manual Review Required)
                </div>
                <div id="abstain-count" class="abstain-size-badge">Band Size: {abstain_count}</div>
            </div>
            <p class="abstain-desc">
                Candidates below share identical scores across all tie-breaking keys. Per Determinism Charter D5, candidate IDs never break ties. Recruiter review required.
            </p>
            <div class="card-list">"""

    for item in abstain_items:
        cid = item.get("candidate_id", "")
        score_bp = item.get("score_bp", 0)
        html += f"""
                <div class="candidate-card" style="border-color: rgba(245, 158, 11, 0.2);">
                    <div class="card-main">
                        <div class="card-left">
                            <span class="rank-num" style="color: #f59e0b;">TIE</span>
                            <span class="cand-name">{cid}</span>
                            <span class="score-pill" style="color: #fbbf24; border-color: rgba(245, 158, 11, 0.3);">{score_bp} bp</span>
                        </div>
                        <div class="card-right">
                            <button class="btn btn-accept" onclick="updateVerdict('{cid}', 'accept')">Accept</button>
                            <button class="btn btn-reject" onclick="updateVerdict('{cid}', 'reject')">Reject</button>
                        </div>
                    </div>
                </div>"""

    html += f"""
            </div>
        </section>

        <!-- Ranked Candidates Section -->
        <section>
            <h2 style="font-family: var(--font-display); font-size: 1.25rem; margin-bottom: 1rem;">Ranked Shortlist</h2>
            <div class="card-list">"""

    for item in ranked_items:
        rank_num = item.get("rank", 1)
        cid = item.get("candidate_id", "")
        score_bp = item.get("score_bp", 0)
        verdict = item.get("verdict", "accept")
        judgements = item.get("judgements", [])

        html += f"""
                <div class="candidate-card" id="card-{cid}">
                    <div class="card-main">
                        <div class="card-left">
                            <span class="rank-num">#{rank_num}</span>
                            <span class="cand-name">{cid}</span>
                            <span class="score-pill">{score_bp} bp</span>
                            <span class="badge" style="text-transform: uppercase;">{verdict}</span>
                        </div>
                        <div class="card-right">
                            <button class="btn btn-expand" onclick="toggleEvidence('{cid}')">Evidence ({len(judgements)})</button>
                            <button class="btn btn-accept" onclick="updateVerdict('{cid}', 'accept')">Accept</button>
                            <button class="btn btn-reject" onclick="updateVerdict('{cid}', 'reject')">Reject</button>
                        </div>
                    </div>
                    <div id="evidence-{cid}" class="evidence-drawer" style="display: none;">"""

        for j in judgements:
            req_id = j.get("requirement_id", "")
            met = j.get("met", False)
            conf_bp = j.get("confidence_bp", 0)
            ev = j.get("evidence")
            ev_text = ev.get("text", "No verbatim evidence") if ev else "No evidence span"
            start = ev.get("start", 0) if ev else 0
            end = ev.get("end", 0) if ev else 0

            html += f"""
                        <div class="evidence-row" style="border-left-color: {'var(--success)' if met else 'var(--danger)'};">
                            <div class="evidence-header">
                                <span><strong>{req_id}</strong> — {'MET' if met else 'NOT MET'} ({conf_bp} bp)</span>
                                <span class="evidence-offsets">[{start}:{end}]</span>
                            </div>
                            <div class="evidence-text">"{ev_text}"</div>
                        </div>"""

        html += """
                    </div>
                </div>"""

    html += """
            </div>
        </section>
    </div>

    <script>
        function toggleEvidence(cid) {
            const drawer = document.getElementById('evidence-' + cid);
            if (drawer.style.display === 'none') {
                drawer.style.display = 'flex';
            } else {
                drawer.style.display = 'none';
            }
        }

        async function updateVerdict(cid, verdict) {
            try {
                const res = await fetch('/api/verdict', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({candidate_id: cid, verdict: verdict})
                });
                if (res.ok) {
                    alert('Updated verdict for ' + cid + ' to ' + verdict);
                }
            } catch (err) {
                console.log('Local demo verdict updated: ' + cid + ' -> ' + verdict);
            }
        }
    </script>
</body>
</html>"""
    return html


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    """Serve the interactive screening dashboard."""
    return HTMLResponse(content=render_dashboard_html(), status_code=200)


@app.get("/api/ranking")
def get_ranking():
    """Return the current active ranking."""
    return _current_ranking_data


@app.post("/api/verdict")
def update_verdict(req: VerdictUpdateRequest):
    """Update candidate verdict."""
    v = req.verdict.lower()
    if v not in ("accept", "reject", "unreviewed"):
        raise HTTPException(status_code=400, detail="Invalid verdict")

    updated = False
    for item in _current_ranking_data.get("ranked", []):
        if item.get("candidate_id") == req.candidate_id:
            item["verdict"] = v
            updated = True
            break

    if not updated:
        for item in _current_ranking_data.get("abstain_band", []):
            if item.get("candidate_id") == req.candidate_id:
                item["verdict"] = v
                updated = True
                break

    if not updated:
        raise HTTPException(status_code=404, detail="Candidate not found")

    return {"status": "ok", "candidate_id": req.candidate_id, "verdict": v}


@app.get("/health")
def health_check():
    return {"status": "ok"}
