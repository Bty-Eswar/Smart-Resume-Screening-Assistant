# adapters/judge_cached.py — SDD §5 / D9 / BUILD_PROMPTS M9
import json
from pathlib import Path
from core.ids import content_id
from core.quantize import quantize
from core.types import (
    Bp,
    EvidenceSpan,
    Requirement,
    RequirementJudgement,
    ResumeText,
)
from adapters.judge_bedrock import Judge


class CacheMiss(Exception):
    """Raised when a requested judgement is not present in the cache."""
    pass


class CacheDirectoryNotFound(FileNotFoundError):
    """Raised when the cache directory does not exist."""
    pass


class CacheEmptyError(ValueError):
    """Raised when a cache file or directory is empty."""
    pass


def compute_cache_key(
    model_id: str,
    prompt_version: str,
    resume_sha256: str,
    requirement_id: str,
) -> str:
    """Compute D9 cache key using blake2b over (model_id, prompt_version, resume_sha256, requirement_id)."""
    return content_id(str(model_id), str(prompt_version), str(resume_sha256), str(requirement_id))


class CachedJudge:
    """Replays judgements from fixtures/judgements/ keyed per D9.

    Never falls back to BedrockJudge.
    Never keys on filename, index, or insertion order.
    """

    def __init__(
        self,
        cache_dir: str | Path = "fixtures/judgements",
        model_id: str = "anthropic.claude-3-sonnet",
        prompt_version: str = "v1",
    ) -> None:
        self.model_id = model_id
        self.prompt_version = prompt_version
        self.cache_dir = Path(cache_dir)
        self._cache: dict[str, dict] = {}

        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_dir.exists():
            raise CacheDirectoryNotFound(f"Cache directory does not exist: {self.cache_dir}")

        if self.cache_dir.is_file():
            if self.cache_dir.stat().st_size == 0:
                raise CacheEmptyError(f"Cache file is empty (0 bytes): {self.cache_dir}")
            with open(self.cache_dir, "r", encoding="utf-8") as f:
                content = json.load(f)
                if not content:
                    raise CacheEmptyError(f"Cache content is empty: {self.cache_dir}")
                self._cache.update(content)
            return

        # Path is a directory
        json_files = sorted(self.cache_dir.glob("*.json"))
        if not json_files:
            raise CacheEmptyError(f"No cache files found in directory: {self.cache_dir}")

        for jf in json_files:
            if jf.stat().st_size == 0:
                raise CacheEmptyError(f"Cache file is empty (0 bytes): {jf}")
            with open(jf, "r", encoding="utf-8") as f:
                content = json.load(f)
                if not content:
                    raise CacheEmptyError(f"Cache file content is empty: {jf}")
                self._cache.update(content)

    def judge(self, resume: ResumeText, req: Requirement) -> RequirementJudgement:
        """Look up requirement judgement in cache per D9 key."""
        key = compute_cache_key(
            model_id=self.model_id,
            prompt_version=self.prompt_version,
            resume_sha256=str(resume.sha256),
            requirement_id=str(req.id),
        )

        if key not in self._cache:
            raise CacheMiss(
                f"Cache miss for key={key} (resume_sha256={resume.sha256}, req_id={req.id})"
            )

        data = self._cache[key]
        met = bool(data["met"])

        conf_raw = data.get("confidence_bp", data.get("confidence", 0))
        if isinstance(conf_raw, float):
            confidence_bp = quantize(conf_raw)
        elif isinstance(conf_raw, int) and not isinstance(conf_raw, bool):
            confidence_bp = Bp(conf_raw)
        else:
            raise TypeError(f"Invalid confidence type in cache: {type(conf_raw)}")

        evidence_span = None
        if data.get("evidence"):
            ev = data["evidence"]
            evidence_span = EvidenceSpan(
                start=int(ev["start"]),
                end=int(ev["end"]),
                text=str(ev["text"]),
            )

        return RequirementJudgement(
            candidate_id=resume.candidate_id,
            requirement_id=req.id,
            met=met,
            confidence_bp=confidence_bp,
            evidence=evidence_span,
        )


def judge_all(
    resumes: tuple[ResumeText, ...],
    reqs: tuple[Requirement, ...],
    client: Judge,
) -> tuple[RequirementJudgement, ...]:
    """Judge all candidate resumes against all requirements.

    Returns tuple of RequirementJudgements.
    """
    judgements: list[RequirementJudgement] = []
    for resume in resumes:
        for req in reqs:
            j = client.judge(resume, req)
            judgements.append(j)
    return tuple(judgements)
