# core/types.py — SDD §3 Domain Model
from dataclasses import dataclass
from enum import Enum
from typing import NewType

Bp = NewType("Bp", int)  # basis points, 0..10000 inclusive. The ONLY numeric score type.
RunId = NewType("RunId", str)  # 32-hex blake2b
CandidateId = NewType("CandidateId", str)
RequirementId = NewType("RequirementId", str)
Sha256 = NewType("Sha256", str)
AsOfDate = NewType("AsOfDate", str)  # "YYYY-MM-DD". String, not date — no arithmetic in core.


class RankerId(str, Enum):
    R0_LEXICAL = "r0_lexical"
    R1_EMBEDDING = "r1_embedding"
    R2_LLM = "r2_llm"


class ParseStatus(str, Enum):
    OK = "ok"
    NO_TEXT_LAYER = "no_text_layer"  # < 200 chars extracted
    UNSUPPORTED_TYPE = "unsupported_type"
    CORRUPT = "corrupt"


class Verdict(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    UNREVIEWED = "unreviewed"


class PhrasingMode(str, Enum):  # used by ground truth (§4) and disagreement coding
    EXPLICIT_TOKEN = "explicit_token"  # requirement's own vocabulary appears
    IMPLICIT_PARAPHRASE = "implicit_paraphrase"
    SKILLS_WALL = "skills_wall"  # named in a list, no supporting narrative
    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class Requirement:
    id: RequirementId  # hash of (jd_sha256, normalized_text)
    text: str
    tokens: tuple[str, ...]  # stemmed, sorted, deduplicated
    weight_bp: Bp  # weights across one JD sum to exactly 10000


@dataclass(frozen=True, slots=True)
class ResumeText:
    candidate_id: CandidateId  # hash of (file_sha256,)
    filename: str
    sha256: Sha256
    text: str  # whitespace-normalized
    char_count: int


@dataclass(frozen=True, slots=True)
class ParseOutcome:
    filename: str
    status: ParseStatus
    resume: ResumeText | None  # None iff status != OK


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    start: int  # char offset into ResumeText.text
    end: int
    text: str  # MUST equal resume.text[start:end] (D8)


@dataclass(frozen=True, slots=True)
class RequirementJudgement:
    candidate_id: CandidateId
    requirement_id: RequirementId
    met: bool
    confidence_bp: Bp  # quantized at the adapter boundary (C2)
    evidence: EvidenceSpan | None  # None iff met is False


@dataclass(frozen=True, slots=True)
class CandidateScore:
    candidate_id: CandidateId
    score_bp: Bp  # sum over met requirements of weight_bp * confidence_bp // 10000
    met_count: int
    high_weight_met_count: int  # met requirements whose weight_bp >= 1000
    judgements: tuple[RequirementJudgement, ...]  # sorted by requirement_id


@dataclass(frozen=True, slots=True)
class RankedEntry:
    rank: int  # 1-based; equal for tied entries inside abstain_band
    score: CandidateScore
    verdict: Verdict


@dataclass(frozen=True, slots=True)
class Ranking:
    run_id: RunId
    ranker: RankerId
    as_of: AsOfDate
    ranked: tuple[RankedEntry, ...]
    abstain_band: tuple[RankedEntry, ...]  # sorted by candidate_id — display order only, NOT rank (D5)
    abstain_straddled_k: bool
    unparsed: tuple[ParseOutcome, ...]  # sorted by filename; counted in denominators (§3.1)


@dataclass(frozen=True, slots=True)
class Timing:  # NEVER a field of anything above (D14)
    stage: str
    elapsed_ms: int
    call_count: int


# Import-time exhaustiveness assertions (cannot be deselected)
assert set(PhrasingMode) == {
    PhrasingMode.EXPLICIT_TOKEN,
    PhrasingMode.IMPLICIT_PARAPHRASE,
    PhrasingMode.SKILLS_WALL,
    PhrasingMode.ABSENT,
} and len(PhrasingMode) == 4, "PhrasingMode exhaustiveness violation"

assert set(RankerId) == {
    RankerId.R0_LEXICAL,
    RankerId.R1_EMBEDDING,
    RankerId.R2_LLM,
} and len(RankerId) == 3, "RankerId exhaustiveness violation"
