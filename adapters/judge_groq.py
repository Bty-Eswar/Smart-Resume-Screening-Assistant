# adapters/judge_groq.py — Live Groq LLM Evaluator for R2 LLM Ranker
import concurrent.futures
import json
import os
import re
from pathlib import Path
from typing import Mapping

import httpx
from dotenv import load_dotenv

from adapters.judge_cached import compute_cache_key
from core.evidence import validate_evidence
from core.quantize import quantize
from core.types import (
    Bp,
    EvidenceSpan,
    Requirement,
    RequirementJudgement,
    ResumeText,
)

load_dotenv()


class GroqJudge:
    """Evaluates candidate resumes against job requirements using Groq LLM API.

    Adheres strictly to Determinism Charter D7 (disabled under pytest) and
    D8 (strict evidence span verification against original resume text).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = "openai/gpt-oss-120b",
        prompt_version: str = "v1_groq",
    ) -> None:
        if "PYTEST_CURRENT_TEST" in os.environ:
            raise RuntimeError("GroqJudge is disabled under pytest per Determinism Charter D7")

        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not configured in environment or .env file")

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._memory_cache: dict[str, RequirementJudgement] = {}

    def _locate_span(self, resume_text: str, raw_quote: str) -> EvidenceSpan | None:
        """Locate exact character boundaries of quote within resume text."""
        if not raw_quote:
            return None

        quote = raw_quote.strip()
        if not quote:
            return None

        # 1. Exact match
        idx = resume_text.find(quote)
        if idx >= 0:
            return EvidenceSpan(start=idx, end=idx + len(quote), text=resume_text[idx:idx + len(quote)])

        # 2. Case-insensitive match
        idx_lower = resume_text.lower().find(quote.lower())
        if idx_lower >= 0:
            matched_slice = resume_text[idx_lower:idx_lower + len(quote)]
            return EvidenceSpan(start=idx_lower, end=idx_lower + len(quote), text=matched_slice)

        # 3. Substring with normalized spaces
        words = quote.split()
        if len(words) >= 3:
            pattern = r"\s+".join(re.escape(w) for w in words[:6])
            m = re.search(pattern, resume_text, re.IGNORECASE)
            if m:
                return EvidenceSpan(start=m.start(), end=m.end(), text=resume_text[m.start():m.end()])

        return None

    def judge(self, resume: ResumeText, req: Requirement) -> RequirementJudgement:
        """Judge a single resume against a single requirement."""
        cache_key = compute_cache_key(
            model_id=self.model_id,
            prompt_version=self.prompt_version,
            resume_sha256=str(resume.sha256),
            requirement_id=str(req.id),
        )
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        prompt = f"""You are an expert technical recruiter evaluating a candidate resume against a specific requirement.

Requirement to evaluate:
"{req.text}"

Candidate Resume Text:
\"\"\"
{resume.text}
\"\"\"

Assess whether the candidate meets this requirement.
Return ONLY a valid JSON object with the following schema:
{{
  "met": true or false,
  "confidence": integer between 0 and 10000 representing confidence in basis points (e.g. 9500 for 95%),
  "quote": "verbatim text copied directly from the resume that proves they meet it, or empty string if met is false"
}}
"""

        try:
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_id,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an objective hiring evaluator. You must return only a valid JSON object with no markdown formatting.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                },
                timeout=25.0,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            met = bool(parsed.get("met", False))
            conf_raw = parsed.get("confidence", 8000 if met else 2000)
            if isinstance(conf_raw, float):
                conf_bp = quantize(conf_raw)
            else:
                conf_bp = Bp(max(0, min(10000, int(conf_raw))))

            raw_quote = str(parsed.get("quote", ""))
            span = self._locate_span(resume.text, raw_quote) if met else None

            judgement = RequirementJudgement(
                candidate_id=resume.candidate_id,
                requirement_id=req.id,
                met=met,
                confidence_bp=conf_bp,
                evidence=span,
            )
            # Strict Charter D8 validation
            validated = validate_evidence(judgement, resume)
            self._memory_cache[cache_key] = validated
            return validated

        except Exception as exc:
            # Fallback safe judgement on API failure
            fallback = RequirementJudgement(
                candidate_id=resume.candidate_id,
                requirement_id=req.id,
                met=False,
                confidence_bp=Bp(0),
                evidence=None,
            )
            return fallback


def judge_all_concurrent(
    resumes: tuple[ResumeText, ...],
    reqs: tuple[Requirement, ...],
    judge: GroqJudge,
    max_workers: int = 12,
) -> tuple[RequirementJudgement, ...]:
    """Judge all candidate resumes against all requirements in parallel using thread pool."""
    tasks: list[tuple[ResumeText, Requirement]] = []
    for r in resumes:
        for req in reqs:
            tasks.append((r, req))

    judgements: list[RequirementJudgement] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(judge.judge, r, req): (r, req)
            for (r, req) in tasks
        }
        for future in concurrent.futures.as_completed(future_map):
            try:
                j = future.result()
                judgements.append(j)
            except Exception:
                r, req = future_map[future]
                judgements.append(
                    RequirementJudgement(
                        candidate_id=r.candidate_id,
                        requirement_id=req.id,
                        met=False,
                        confidence_bp=Bp(0),
                        evidence=None,
                    )
                )

    return tuple(judgements)
