# adapters/db.py — Unified PostgreSQL & SQLite Persistent Job Store
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.types import (
    AsOfDate,
    Bp,
    CandidateId,
    CandidateScore,
    EvidenceSpan,
    ParseOutcome,
    ParseStatus,
    RankedEntry,
    RankerId,
    Ranking,
    Requirement,
    RequirementId,
    RequirementJudgement,
    ResumeText,
    RunId,
    Sha256,
    Verdict,
)
from pipeline import ranking_to_dict


@dataclass
class Job:
    job_id: str
    title: str
    jd_text: str
    jd_sha256: str
    requirements: tuple[Requirement, ...] | None
    resume_dir: Path
    parse_outcomes: tuple[ParseOutcome, ...] | None
    ranking: Ranking | None
    status: str  # "draft" | "resumes_uploaded" | "ranked"
    ranker_used: str | None = None
    all_rankings: dict[str, Ranking] | None = None


# Serialization helpers
def dict_to_ranking(d: dict) -> Ranking:
    """Reconstruct frozen Ranking dataclass hierarchy from dictionary."""
    def dict_to_entry(ed: dict) -> RankedEntry:
        judgements = []
        for jd in ed.get("judgements", []):
            ev = None
            if jd.get("evidence"):
                ev = EvidenceSpan(
                    start=int(jd["evidence"]["start"]),
                    end=int(jd["evidence"]["end"]),
                    text=str(jd["evidence"]["text"]),
                )
            judgements.append(
                RequirementJudgement(
                    candidate_id=CandidateId(ed["candidate_id"]),
                    requirement_id=RequirementId(jd["requirement_id"]),
                    met=bool(jd["met"]),
                    confidence_bp=Bp(int(jd.get("confidence_bp", 0))),
                    evidence=ev,
                )
            )
        score = CandidateScore(
            candidate_id=CandidateId(ed["candidate_id"]),
            score_bp=Bp(int(ed["score_bp"])),
            met_count=int(ed["met_count"]),
            high_weight_met_count=int(ed["high_weight_met_count"]),
            judgements=tuple(judgements),
        )
        return RankedEntry(
            rank=int(ed["rank"]),
            score=score,
            verdict=Verdict(ed.get("verdict", "unreviewed")),
        )

    unparsed = []
    for ud in d.get("unparsed", []):
        unparsed.append(
            ParseOutcome(
                filename=ud["filename"],
                status=ParseStatus(ud["status"]),
                resume=None,
            )
        )

    return Ranking(
        run_id=RunId(d["run_id"]),
        ranker=RankerId(d["ranker"]),
        as_of=AsOfDate(d["as_of"]),
        ranked=tuple(dict_to_entry(e) for e in d.get("ranked", [])),
        abstain_band=tuple(dict_to_entry(e) for e in d.get("abstain_band", [])),
        abstain_straddled_k=bool(d.get("abstain_straddled_k", False)),
        unparsed=tuple(unparsed),
    )


def serialize_requirements(reqs: tuple[Requirement, ...] | None) -> str:
    if not reqs:
        return "[]"
    return json.dumps([
        {
            "id": str(r.id),
            "text": r.text,
            "tokens": list(r.tokens),
            "weight_bp": int(r.weight_bp),
        }
        for r in reqs
    ])


def deserialize_requirements(raw: str | None) -> tuple[Requirement, ...] | None:
    if not raw or raw == "[]":
        return None
    data = json.loads(raw)
    return tuple(
        Requirement(
            id=RequirementId(r["id"]),
            text=r["text"],
            tokens=tuple(r.get("tokens", ())),
            weight_bp=Bp(int(r["weight_bp"])),
        )
        for r in data
    )


def serialize_parse_outcomes(outcomes: tuple[ParseOutcome, ...] | None) -> str:
    if not outcomes:
        return "[]"
    res = []
    for o in outcomes:
        res.append({
            "filename": o.filename,
            "status": o.status.value,
            "char_count": o.resume.char_count if o.resume else 0,
            "candidate_id": str(o.resume.candidate_id) if o.resume else "",
            "sha256": str(o.resume.sha256) if o.resume else "",
            "text": o.resume.text if o.resume else "",
        })
    return json.dumps(res)


def deserialize_parse_outcomes(raw: str | None) -> tuple[ParseOutcome, ...] | None:
    if not raw or raw == "[]":
        return None
    data = json.loads(raw)
    res = []
    for item in data:
        status = ParseStatus(item["status"])
        resume = None
        if status == ParseStatus.OK:
            resume = ResumeText(
                candidate_id=CandidateId(item["candidate_id"]),
                filename=item["filename"],
                sha256=Sha256(item["sha256"]),
                text=item.get("text", ""),
                char_count=item.get("char_count", len(item.get("text", ""))),
            )
        res.append(ParseOutcome(filename=item["filename"], status=status, resume=resume))
    return tuple(res)


class DatabaseAdapter:
    """Unified database interface supporting PostgreSQL and SQLite."""

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL", "")
        self.is_postgres = False
        self._pg_conn = None
        self._sqlite_path = None

        # Check if running under pytest (strictly socket-free per D7)
        in_test = "pytest" in sys.modules

        if not in_test and (self.db_url.startswith("postgresql://") or self.db_url.startswith("postgres://")):
            try:
                import psycopg2
                self._pg_conn = psycopg2.connect(self.db_url)
                self._pg_conn.autocommit = True
                self.is_postgres = True
            except Exception as e:
                print(f"[DB] Could not connect to PostgreSQL ({e}), falling back to SQLite.")
                self.is_postgres = False

        if not self.is_postgres:
            if in_test or self.db_url == ":memory:" or os.environ.get("SHORTLIST_IN_MEMORY"):
                self._sqlite_path = ":memory:"
            else:
                db_dir = Path("data")
                db_dir.mkdir(parents=True, exist_ok=True)
                self._sqlite_path = str(db_dir / "shortlist.db")

        self.init_schema()

    def _get_connection(self):
        if self.is_postgres:
            return self._pg_conn
        # Open separate connection for thread-safety in SQLite
        conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _execute(self, query: str, params: tuple = ()):
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.is_postgres:
                # Replace SQLite parameter placeholders '?' with PostgreSQL '%s'
                pg_query = query.replace("?", "%s")
                cur.execute(pg_query, params)
                return cur
            else:
                cur.execute(query, params)
                conn.commit()
                return cur
        except Exception:
            if not self.is_postgres:
                conn.rollback()
            raise

    def init_schema(self):
        """Create tables if they do not already exist."""
        ddl_jobs = """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            jd_text TEXT NOT NULL,
            jd_sha256 TEXT NOT NULL,
            requirements_json TEXT,
            resume_dir TEXT NOT NULL,
            parse_outcomes_json TEXT,
            status TEXT NOT NULL,
            ranker_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        ddl_rankings = """
        CREATE TABLE IF NOT EXISTS rankings (
            job_id TEXT NOT NULL,
            ranker_id TEXT NOT NULL,
            ranking_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (job_id, ranker_id)
        );
        """
        ddl_verdicts = """
        CREATE TABLE IF NOT EXISTS verdicts (
            job_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (job_id, candidate_id)
        );
        """
        self._execute(ddl_jobs)
        self._execute(ddl_rankings)
        self._execute(ddl_verdicts)

    def save_job(self, job: Job) -> None:
        """Upsert a Job entity and its rankings/verdicts."""
        reqs_json = serialize_requirements(job.requirements)
        outcomes_json = serialize_parse_outcomes(job.parse_outcomes)

        # Upsert job record
        sql = """
        INSERT INTO jobs (job_id, title, jd_text, jd_sha256, requirements_json, resume_dir, parse_outcomes_json, status, ranker_used)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            title=excluded.title,
            jd_text=excluded.jd_text,
            jd_sha256=excluded.jd_sha256,
            requirements_json=excluded.requirements_json,
            resume_dir=excluded.resume_dir,
            parse_outcomes_json=excluded.parse_outcomes_json,
            status=excluded.status,
            ranker_used=excluded.ranker_used;
        """
        self._execute(sql, (
            job.job_id,
            job.title,
            job.jd_text,
            job.jd_sha256,
            reqs_json,
            str(job.resume_dir),
            outcomes_json,
            job.status,
            job.ranker_used,
        ))

        # Save rankings if present
        if job.all_rankings:
            for ranker_key, rk in job.all_rankings.items():
                self.save_ranking(job.job_id, ranker_key, rk)
        elif job.ranking and job.ranker_used:
            self.save_ranking(job.job_id, job.ranker_used, job.ranking)

    def save_ranking(self, job_id: str, ranker_id: str, ranking: Ranking) -> None:
        """Upsert a ranking run for a job."""
        ranking_dict = ranking_to_dict(ranking)
        sql = """
        INSERT INTO rankings (job_id, ranker_id, ranking_json)
        VALUES (?, ?, ?)
        ON CONFLICT(job_id, ranker_id) DO UPDATE SET
            ranking_json=excluded.ranking_json,
            created_at=CURRENT_TIMESTAMP;
        """
        self._execute(sql, (job_id, ranker_id, json.dumps(ranking_dict)))

    def get_job(self, job_id: str) -> Job | None:
        """Retrieve a Job by id, hydrating its rankings and verdicts."""
        cur = self._execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        if not row:
            return None

        # Load rankings
        cur_rankings = self._execute("SELECT ranker_id, ranking_json FROM rankings WHERE job_id = ?", (job_id,))
        all_rankings = {}
        for r_row in cur_rankings.fetchall():
            r_key = r_row[0] if isinstance(r_row, tuple) else r_row["ranker_id"]
            r_json = r_row[1] if isinstance(r_row, tuple) else r_row["ranking_json"]
            all_rankings[r_key] = dict_to_ranking(json.loads(r_json))

        # Load verdicts and apply overrides
        verdicts = self.get_verdicts(job_id)
        if verdicts and all_rankings:
            # Synchronize verdicts onto all loaded rankings
            for r_key, rk in list(all_rankings.items()):
                new_ranked = []
                for entry in rk.ranked:
                    v_override = verdicts.get(str(entry.score.candidate_id))
                    if v_override and v_override != entry.verdict.value:
                        new_ranked.append(RankedEntry(rank=entry.rank, score=entry.score, verdict=Verdict(v_override)))
                    else:
                        new_ranked.append(entry)
                new_abstain = []
                for entry in rk.abstain_band:
                    v_override = verdicts.get(str(entry.score.candidate_id))
                    if v_override and v_override != entry.verdict.value:
                        new_abstain.append(RankedEntry(rank=entry.rank, score=entry.score, verdict=Verdict(v_override)))
                    else:
                        new_abstain.append(entry)
                all_rankings[r_key] = Ranking(
                    run_id=rk.run_id,
                    ranker=rk.ranker,
                    as_of=rk.as_of,
                    ranked=tuple(new_ranked),
                    abstain_band=tuple(new_abstain),
                    abstain_straddled_k=rk.abstain_straddled_k,
                    unparsed=rk.unparsed,
                )

        ranker_used = row[8] if isinstance(row, tuple) else row["ranker_used"]
        main_ranking = None
        if all_rankings:
            if ranker_used and ranker_used in all_rankings:
                main_ranking = all_rankings[ranker_used]
            elif "r0_lexical" in all_rankings:
                main_ranking = all_rankings["r0_lexical"]
            else:
                main_ranking = next(iter(all_rankings.values()))

        return Job(
            job_id=row[0] if isinstance(row, tuple) else row["job_id"],
            title=row[1] if isinstance(row, tuple) else row["title"],
            jd_text=row[2] if isinstance(row, tuple) else row["jd_text"],
            jd_sha256=row[3] if isinstance(row, tuple) else row["jd_sha256"],
            requirements=deserialize_requirements(row[4] if isinstance(row, tuple) else row["requirements_json"]),
            resume_dir=Path(row[5] if isinstance(row, tuple) else row["resume_dir"]),
            parse_outcomes=deserialize_parse_outcomes(row[6] if isinstance(row, tuple) else row["parse_outcomes_json"]),
            ranking=main_ranking,
            status=row[7] if isinstance(row, tuple) else row["status"],
            ranker_used=ranker_used,
            all_rankings=all_rankings if all_rankings else None,
        )

    def list_jobs(self) -> list[Job]:
        """List all jobs ordered by creation."""
        cur = self._execute("SELECT job_id FROM jobs ORDER BY created_at DESC")
        jobs = []
        for row in cur.fetchall():
            jid = row[0] if isinstance(row, tuple) else row["job_id"]
            j = self.get_job(jid)
            if j:
                jobs.append(j)
        return jobs

    def update_verdict(self, job_id: str, candidate_id: str, verdict: str) -> None:
        """Persist a candidate verdict decision."""
        sql = """
        INSERT INTO verdicts (job_id, candidate_id, verdict)
        VALUES (?, ?, ?)
        ON CONFLICT(job_id, candidate_id) DO UPDATE SET
            verdict=excluded.verdict,
            updated_at=CURRENT_TIMESTAMP;
        """
        self._execute(sql, (job_id, candidate_id, verdict))

    def get_verdicts(self, job_id: str) -> dict[str, str]:
        """Fetch all custom candidate verdicts for a job."""
        cur = self._execute("SELECT candidate_id, verdict FROM verdicts WHERE job_id = ?", (job_id,))
        result = {}
        for row in cur.fetchall():
            cid = row[0] if isinstance(row, tuple) else row["candidate_id"]
            verdict = row[1] if isinstance(row, tuple) else row["verdict"]
            result[cid] = verdict
        return result


# Global default database instance
db = DatabaseAdapter()
