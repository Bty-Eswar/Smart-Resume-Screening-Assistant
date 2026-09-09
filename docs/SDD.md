# SOFTWARE DESIGN DOCUMENT — `shortlist`

**Repo:** `shortlist/`
**Doc path:** `docs/SDD.md`
**Derives from:** `docs/PDD.md` (frozen at G0, D−7)
**Status:** committed at G0 alongside the PDD. Amendments require a changelog row.

---

## 0. THREE CONTRADICTIONS BETWEEN THIS SDD AND THE PDD

Named here rather than resolved silently. Each has a decision attached, but the decision is a choice, not a derivation.

### C1 — D6 (byte-identical output) vs. an LLM in the pipeline

The PDD's R2 ranker calls a language model. Language models are not byte-deterministic even at temperature 0. D6 as literally written cannot hold for a pipeline containing R2.

Worse, PDD threshold **T3 measures exactly the nondeterminism D6 forbids** — Jaccard of top-10 across three shuffled runs, threshold 0.80. If the code were truly byte-deterministic end to end, T3 would be trivially 1.00 and would measure nothing.

**Decision:** D6 is scoped to the **core**, defined as everything downstream of the model boundary. The model call is I/O and lives outside it. Concretely: `judge()` returns `RequirementJudgement` records; every function that consumes them is byte-deterministic given identical judgements. The suite pins judgements from a fixture cache, so `pytest` sees a deterministic system. T3 runs against the *live* boundary and is therefore a measurement of the model, not of the code — which is the only way its number means anything. **If the core were nondeterministic, T3 would be unattributable**, and that is the whole reason D6 exists here.

### C2 — D1 (exact numerics, never float) vs. cosine similarity and model confidences

R1 is embedding cosine similarity, which is float by construction. R2 returns a confidence the PDD types as `0–1`. Both are floats arriving at a decision path.

**Decision:** floats are permitted *only* in the untrusted zone before `quantize()`. Every score crossing into the core is an `int` in basis points, `0..10000`, produced by `quantize(x: float) -> int` using `round-half-even` on `Decimal(str(x))`. After quantization no float exists anywhere in `core/`. This loses resolution below 0.0001, which is below the smallest threshold in the PDD (T4's 0.05 = 500 bp) by a factor of 500.

### C3 — D5 (exhausted ties ABSTAIN) vs. "returns the top 10"

The PDD promises a top-10 and computes precision@10. D5 says a tie that exhausts the tie-break chain must abstain rather than pick. A tie straddling rank 10 therefore yields a shortlist of 8 or 13, and `P@10` has no defined denominator.

**Decision:** ranking returns `Ranking(ranked: tuple[RankedEntry, ...], abstain_band: tuple[RankedEntry, ...])`. If the abstain band straddles the k boundary, **P@10 is computed with denominator 10 and the abstained entries scored as misses.** This is the pessimistic convention and it is declared now, before any result, precisely because the optimistic convention would be tempting later. `eval/results.json` records `abstain_straddled_k: bool` on every run; if it is ever `true`, the demo says so.

---

## 1. DETERMINISM CHARTER

Fourteen rules. Each names the test that fails when it is broken. All tests live in `tests/` and run in the single suite (§7 — there is no fast subset).

| # | Rule | Enforcing test |
|---|---|---|
| **D1** | No `float` exists in `core/`. All scores are `int` basis points `0..10000`. Floats are legal only in `adapters/` before `quantize()`. | `test_d1_no_float_in_core_annotations` — AST-walks every module under `core/`, asserts no `float` annotation, no float literal, no `/` operator on score-typed names. |
| **D2** | No clock reads in `core/`. `as_of: AsOfDate` is a required parameter on every function whose result could depend on the date (all experience-duration arithmetic). | `test_d2_no_clock_reads_in_core` — AST-scans `core/` for `datetime.now`, `date.today`, `time.time`, `time.monotonic`; asserts zero. Plus `test_d2_as_of_changes_experience_scores` proves the parameter is actually load-bearing. |
| **D3** | Every ID is `blake2b(canonical_tuple, digest_size=16).hexdigest()`. No `uuid4`, no counters, no object identity. | `test_d3_ids_are_content_hashes` — constructs the same corpus twice in separate processes, asserts identical `RunId`, `CandidateId`, `RequirementId`. `test_d3_no_uuid_import` asserts `uuid` is not imported anywhere in `core/`. |
| **D4** | Every returned sequence is a `tuple` sorted by an explicitly named key function. No function returns a `set`, a `dict` relying on insertion order, or an unsorted comprehension. | `test_d4_all_outputs_sorted` — for each pipeline stage, runs it on inputs in 5 shuffled orders, asserts identical output tuples. `test_d4_no_set_returns` inspects return annotations. |
| **D5** | The tie-break chain is `(score_bp desc, met_count desc, high_weight_met_count desc)`. Entries still tied after all three go to `abstain_band`. Candidate ID **never** breaks a tie. | `test_d5_exhausted_tie_abstains` — two candidates identical on all three keys must appear in `abstain_band`, not in `ranked`. `test_d5_id_does_not_rank` — swapping two tied candidates' IDs must not change which one ranks higher, because neither does. |
| **D6** | Given identical `JudgementCache` contents, two runs produce byte-identical `runs/<run_id>.json`. | `test_d6_byte_identical_runs` — runs the full pipeline twice from the fixture cache, `assert open(a,'rb').read() == open(b,'rb').read()`. |
| **D7** | The suite makes zero network calls. `BedrockJudge.__init__` raises `RuntimeError` when `PYTEST_CURRENT_TEST` is in `os.environ`. | `test_d7_real_client_refuses_under_pytest` — asserts the `RuntimeError`. `test_d7_no_sockets` installs a `socket.socket` guard in `conftest.py` that raises on any connect attempt; a deliberate leak test proves the guard fires. |
| **D8** | Every `EvidenceSpan.text` is an exact substring of its source `ResumeText` after `normalize_ws()`. A span failing this is dropped and its judgement forced to `met=False`. | `test_d8_evidence_is_verbatim` — property test over the fixture corpus. `test_d8_invalid_span_forces_not_met` — injects a fabricated span, asserts `met is False`. This is PDD **T2**. |
| **D9** | The `JudgementCache` key is `blake2b((model_id, prompt_version, resume_sha256, requirement_id))`. Cache hits never depend on file path, ordering, or wall-clock. | `test_d9_cache_key_is_stable` — same tuple in a fresh process yields the same key; changing any one element changes it. |
| **D10** | `core.ranking` is invariant to input order. Shuffling the candidate list cannot change `ranked` or `abstain_band`. | `test_d10_ranking_order_invariant` — 20 shuffles, identical output. **Without this, PDD T3's Jaccard number is unattributable** — churn could be code or model, and we could not say which. |
| **D11** | `eval/gold.csv` is never written by application code. The only writer is a human. | `test_d11_gold_is_read_only` — asserts no `open(..., 'w')` or `to_csv` targeting `gold.csv` anywhere in the repo; `conftest.py` chmods it `0o444` for the session and asserts a write raises. This enforces the PDD's "not relabel the gold set" rule mechanically rather than by intention. |
| **D12** | Held-out filenames in `eval/holdout.txt` are unreadable by any module under `prompts/` or any dev-split code path. Scoring the held-out split writes `eval/results.json` exactly once; a second write raises. | `test_d12_holdout_scored_once` — second call to `score_holdout()` raises `HoldoutAlreadyScored`. |
| **D13** | `eval/thresholds.json` is loaded, never computed. No code writes it. A comparison against a threshold not present in the file raises `UndeclaredThreshold`. | `test_d13_all_comparisons_declared` — enumerates every threshold constant referenced in `eval/`, asserts each has a key in `thresholds.json`. |
| **D14** | Timing never enters a hashed, serialized-for-comparison, or `__eq__`-compared object. Every stage returns `(Result, Timing)`. | `test_d14_timing_absent_from_results` — asserts no field of any `core/` dataclass is named in `{elapsed_ms, started_at, duration, latency}`; asserts `Ranking.__eq__` holds across runs with different timings. |

**Rules that exist because of this project specifically, not from the baseline set:** D8, D9, D10, D11, D12, D13. D10 and D11 are the two that would most quietly destroy the result — one makes T3 meaningless, the other makes the entire pre-declaration a claim rather than a fact.

---

## 2. REPOSITORY LAYOUT

Every module is **PURE** (no I/O, no clock, no network, no randomness) or **I/O**. Never both.

```
shortlist/
├── core/                          PURE — the determinism boundary
│   ├── types.py                   Frozen dataclasses and enums (§3). No logic.
│   ├── quantize.py                float → int basis points; the only float-touching code allowed near core.
│   ├── ids.py                     blake2b content hashing for RunId / CandidateId / RequirementId.
│   ├── normalize.py               Whitespace, case-folding, stemming. Deterministic string ops only.
│   ├── requirements.py            Parses model JSON into Requirement tuples; validates weights sum.
│   ├── evidence.py                Verbatim-substring validation; drops invalid spans (D8).
│   ├── scoring.py                 RequirementJudgement tuple → CandidateScore. Integer arithmetic only.
│   ├── ranking.py                 CandidateScore tuple → Ranking. Tie-break chain and abstain band (D5, D10).
│   ├── rankers/r0_lexical.py      IDF-weighted token match. Pure given a prebuilt IDF table.
│   ├── rankers/r1_embedding.py    Cosine over injected vectors. Pure — does not fetch vectors.
│   ├── rankers/r2_llm.py          Assembles judgements into a Ranking. Pure — does not call the model.
│   └── metrics.py                 P@k, Jaccard, Cohen's κ, rank-delta. Integer/Fraction arithmetic.
│
├── adapters/                      I/O — everything that touches the world
│   ├── ingest.py                  PDF/DOCX → ResumeText. Filesystem reads.
│   ├── judge_bedrock.py           Live model client. Refuses to instantiate under pytest (D7).
│   ├── judge_cached.py            Replays JudgementCache from disk. The only judge the suite sees.
│   ├── embed.py                   Live embedding client. Same pytest refusal.
│   ├── store.py                   Postgres / JSON-file persistence. Cut #3 swaps the backend here only.
│   └── clock.py                   The single place `date.today()` may be called. Returns AsOfDate.
│
├── pipeline.py                    I/O — wires adapters to core. The only module importing both.
├── api.py                         I/O — FastAPI routes. No business logic.
├── config.py                      I/O — loads and type-validates config.toml (§6).
├── eval/
│   ├── harness.py                 I/O — runs all three rankers, writes eval/*.json.
│   ├── checks.py                  PURE — threshold comparisons against thresholds.json (D13).
│   ├── generate_corpus.py         I/O — synthetic resume generator, emits truth.jsonl (§4).
│   ├── thresholds.json            Data. Committed at G3.
│   ├── gold.csv                   Data. Human-written only (D11).
│   ├── holdout.txt                Data. 15 filenames, sealed at G3.
│   └── corpus.sha256              Data. Frozen at H+0:00.
├── fixtures/judgements/           Recorded model responses. Makes D6 and D7 possible.
├── tests/                         One suite. No markers, no subsets (§7).
└── docs/{PDD.md,SDD.md}
```

`pipeline.py` is the single module permitted to import from both `core/` and `adapters/`. A test enforces it: `test_layering_no_io_import_in_core` asserts no module under `core/` imports `adapters`, `os`, `pathlib`, `requests`, `boto3`, or `datetime`.

---

## 3. DOMAIN MODEL

All frozen, all `slots=True`, all sequences are `tuple`. Everything named below is defined below — nothing is referenced and left open.

```python
# core/types.py
from dataclasses import dataclass
from enum import Enum
from typing import NewType

Bp          = NewType("Bp", int)        # basis points, 0..10000 inclusive. The ONLY numeric score type.
RunId       = NewType("RunId", str)     # 32-hex blake2b
CandidateId = NewType("CandidateId", str)
RequirementId = NewType("RequirementId", str)
Sha256      = NewType("Sha256", str)
AsOfDate    = NewType("AsOfDate", str)  # "YYYY-MM-DD". String, not date — no arithmetic in core.

class RankerId(str, Enum):
    R0_LEXICAL = "r0_lexical"
    R1_EMBEDDING = "r1_embedding"
    R2_LLM = "r2_llm"

class ParseStatus(str, Enum):
    OK = "ok"
    NO_TEXT_LAYER = "no_text_layer"      # < 200 chars extracted
    UNSUPPORTED_TYPE = "unsupported_type"
    CORRUPT = "corrupt"

class Verdict(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    UNREVIEWED = "unreviewed"

class PhrasingMode(str, Enum):         # used by ground truth (§4) and disagreement coding
    EXPLICIT_TOKEN = "explicit_token"   # requirement's own vocabulary appears
    IMPLICIT_PARAPHRASE = "implicit_paraphrase"
    SKILLS_WALL = "skills_wall"         # named in a list, no supporting narrative
    ABSENT = "absent"

@dataclass(frozen=True, slots=True)
class Requirement:
    id: RequirementId          # hash of (jd_sha256, normalized_text)
    text: str
    tokens: tuple[str, ...]    # stemmed, sorted, deduplicated
    weight_bp: Bp              # weights across one JD sum to exactly 10000

@dataclass(frozen=True, slots=True)
class ResumeText:
    candidate_id: CandidateId  # hash of (file_sha256,)
    filename: str
    sha256: Sha256
    text: str                  # whitespace-normalized
    char_count: int

@dataclass(frozen=True, slots=True)
class ParseOutcome:
    filename: str
    status: ParseStatus
    resume: ResumeText | None  # None iff status != OK

@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    start: int                 # char offset into ResumeText.text
    end: int
    text: str                  # MUST equal resume.text[start:end] (D8)

@dataclass(frozen=True, slots=True)
class RequirementJudgement:
    candidate_id: CandidateId
    requirement_id: RequirementId
    met: bool
    confidence_bp: Bp          # quantized at the adapter boundary (C2)
    evidence: EvidenceSpan | None   # None iff met is False

@dataclass(frozen=True, slots=True)
class CandidateScore:
    candidate_id: CandidateId
    score_bp: Bp               # sum over met requirements of weight_bp * confidence_bp // 10000
    met_count: int
    high_weight_met_count: int # met requirements whose weight_bp >= 1000
    judgements: tuple[RequirementJudgement, ...]   # sorted by requirement_id

@dataclass(frozen=True, slots=True)
class RankedEntry:
    rank: int                  # 1-based; equal for tied entries inside abstain_band
    score: CandidateScore
    verdict: Verdict

@dataclass(frozen=True, slots=True)
class Ranking:
    run_id: RunId
    ranker: RankerId
    as_of: AsOfDate
    ranked: tuple[RankedEntry, ...]
    abstain_band: tuple[RankedEntry, ...]      # sorted by candidate_id — display order only, NOT rank (D5)
    abstain_straddled_k: bool
    unparsed: tuple[ParseOutcome, ...]         # sorted by filename; counted in denominators (§3.1)

@dataclass(frozen=True, slots=True)
class Timing:                  # NEVER a field of anything above (D14)
    stage: str
    elapsed_ms: int
    call_count: int
```

### 3.1 CANONICAL UNIT OF MEASUREMENT

> **The canonical unit is the `(candidate_id, requirement_id)` judgement.**

Everything the system does is a judgement about one candidate against one requirement. Both dimensions of the model's work are visible in it, and no rate in the system is computed without naming which population it divides by.

**Three populations exist. Each has its own denominator. They are never averaged together, and `metrics.py` takes the denominator as an explicit argument so it cannot be defaulted.**

| Rate | Numerator | Denominator | Population |
|---|---|---|---|
| Parse success | `ParseStatus.OK` count | **all submitted files** (40) | Files |
| Coverage (per candidate) | met requirements weighted | **`sum(weight_bp)` = 10000** | Requirements, per JD |
| Precision@k | gold-positive entries in `ranked[:k]` | **k = 10, fixed** | Ranked slots |
| Evidence validity | verbatim-valid spans | **all returned spans** | Judgements |

Parse failures reduce the pool of rankable candidates but **do not** shrink the P@10 denominator — PDD R3. A candidate who fails to parse is a miss for the ranker that could not read them.

`test_metrics_denominator_is_explicit` asserts every function in `metrics.py` requires its denominator positionally and none has a default.

---

## 4. GROUND TRUTH MODEL

Applies only to the synthetic fraction of the corpus. **Truth records what the generator constructed. It never records anything derivable from the finished text.**

Concretely: truth does **not** store "this resume contains the word Kubernetes" — a grep re-derives that, and storing it means two sources that can disagree. Truth stores the *decision*: "for requirement R7, we planted evidence in `IMPLICIT_PARAPHRASE` mode using surface form `containerised the deployment on EKS`."

```python
@dataclass(frozen=True, slots=True)
class PlantedEvidence:
    requirement_id: RequirementId
    mode: PhrasingMode         # EXPLICIT_TOKEN | IMPLICIT_PARAPHRASE | SKILLS_WALL
    surface_form: str          # the exact string inserted
    section: str               # which resume section it went into

@dataclass(frozen=True, slots=True)
class TruthRecord:
    candidate_id: CandidateId
    jd_sha256: Sha256
    planted: tuple[PlantedEvidence, ...]     # sorted by requirement_id
    omitted: tuple[RequirementId, ...]       # deliberately not satisfied; sorted
    distractors: tuple[str, ...]             # tokens present with no supporting substance; sorted
    generator_version: str
    seed: int                                # the generator's only randomness, injected
```

### Declared cardinality, checked per relationship type

Not one blanket invariant — four, each with its own check, because a blanket rule passes when three of four are broken in compensating ways.

| Relationship | Cardinality | Check |
|---|---|---|
| `TruthRecord` → `Requirement` | Every requirement in the JD appears **exactly once** across `planted ∪ omitted`. Never both, never neither. | `test_truth_partitions_requirements` |
| `PlantedEvidence` → `EvidenceSpan` | Each planted item yields **exactly 1** locatable span in the generated text. | `test_planted_evidence_is_findable` |
| `omitted` → spans | **Exactly 0** spans. A requirement marked omitted whose token appears anywhere is a generator bug. | `test_omitted_requirements_have_no_tokens` |
| `distractors` → `planted` | **0 overlap.** A distractor token may not belong to any planted requirement's token set. | `test_distractors_disjoint_from_planted` |

### The tension this creates with §7 of the PDD — stated, not resolved

Synthetic truth is **not** the gold set. The PDD's headline P@10 is measured against **recruiter labels on `gold.csv`**, and synthetic truth must never be substituted for it, because a generator that plants `IMPLICIT_PARAPHRASE` evidence has *constructed* the exact advantage R2 is being tested for. Measuring R2 against its own generator's intentions is circular.

**What synthetic truth is legitimately for:** one thing only — checking whether the *disagreement cause-coding* in PDD §7 is accurate. If R2 uniquely surfaces a candidate and we code the cause as `implicit-phrasing`, `truth.jsonl` says whether that resume actually had implicit-mode planting. That is a validation of our labeling of the mechanism, not of the ranking. `eval/harness.py` refuses to read `truth.jsonl` in any code path that produces `results.json`; `test_truth_not_used_in_precision` enforces it.

---

## 5. THE PIPELINE

Every core stage is a pure function returning `(Result, Timing)`. Adapters are marked I/O and are the only stages that may fail on the world.

```python
# --- I/O boundary in ---
def load_jd(path: str) -> tuple[str, Sha256]                                     # adapters/ingest.py
def extract_requirements(jd_text: str, client: Judge) -> tuple[dict, ...]        # adapters/judge_*.py
def ingest_resumes(dir: str) -> tuple[ParseOutcome, ...]                         # adapters/ingest.py
def judge_all(resumes, reqs, client: Judge) -> tuple[RequirementJudgement, ...]  # adapters/judge_*.py
def today() -> AsOfDate                                                          # adapters/clock.py — the only clock read

# --- PURE core, all of it byte-deterministic (D6) ---
def build_requirements(raw: tuple[dict, ...], jd_sha: Sha256) -> tuple[Requirement, ...]
def validate_evidence(j: RequirementJudgement, r: ResumeText) -> RequirementJudgement   # D8
def score_candidate(js: tuple[RequirementJudgement, ...], reqs: tuple[Requirement, ...],
                    as_of: AsOfDate) -> CandidateScore                                   # D2
def rank(scores: tuple[CandidateScore, ...], unparsed: tuple[ParseOutcome, ...],
         k: int, ranker: RankerId, as_of: AsOfDate) -> Ranking                           # D4, D5, D10
def precision_at_k(ranking: Ranking, gold: frozenset[CandidateId], k: int) -> Fraction   # denominator explicit
def jaccard_top_k(a: Ranking, b: Ranking, k: int) -> Fraction
def cohens_kappa(a: tuple[bool, ...], b: tuple[bool, ...]) -> Fraction
def rank_delta(a: Ranking, b: Ranking) -> tuple[tuple[CandidateId, int], ...]            # for T4

# --- I/O boundary out ---
def write_run(ranking: Ranking, path: str) -> None                               # adapters/store.py
def write_eval(name: str, payload: dict, path: str) -> None                      # eval/harness.py
```

`Judge` is a protocol with one method, `judge(resume: ResumeText, req: Requirement) -> RequirementJudgement`. Two implementations: `BedrockJudge` (live, refuses under pytest — D7) and `CachedJudge` (replays `fixtures/judgements/`). Nothing in `core/` imports either.

Metrics return `Fraction`, not `float` — D1 reaches the eval layer too. Rendering to a decimal string happens once, in the report writer.

---

## 6. CONFIGURATION

Single file `config.toml`. Every tunable lives here; no magic numbers in code. `test_no_numeric_literals_in_core` AST-scans `core/` and fails on any int literal outside `{0, 1, -1, 2, 10000}`.

```toml
[run]
k = 10
as_of = "2026-01-01"          # injected everywhere; never today() in core

[scoring]
high_weight_threshold_bp = 1000
min_confidence_bp = 5000       # below this, met is forced False

[ingest]
min_text_chars = 200
allowed_extensions = ["pdf", "docx"]

[model]
judge_model_id = "..."
prompt_version = "v1"
temperature = 0
max_concurrency = 8

[paths]
corpus_dir = "eval/corpus"
gold_csv = "eval/gold.csv"
holdout_txt = "eval/holdout.txt"
thresholds_json = "eval/thresholds.json"
cache_dir = "fixtures/judgements"
```

The loader is strict on **three** axes, not one:

```python
def load(path: str) -> Config:
    raw = tomllib.load(open(path,"rb"))
    # 1. unexpected KEY  -> UnknownConfigKey
    # 2. wrong TYPE      -> ConfigTypeError  (bool is rejected where int expected — bool is an int subclass in Python)
    # 3. out of RANGE    -> ConfigRangeError (all *_bp fields must be 0..10000)
```

`test_config_rejects_unknown_key`, `test_config_rejects_wrong_type`, `test_config_rejects_bool_for_int`, `test_config_rejects_out_of_range_bp`. The bool case is called out separately because `isinstance(True, int)` is `True` and a naive loader accepts `k = true`.

Thresholds are **not** in `config.toml`. They live in `eval/thresholds.json` and are immutable during a run (D13) — a tunable and a pre-declared threshold must not sit in the same editable file, or one gets adjusted while editing the other.

---

## 7. TEST BUDGET

**Ceiling: 60 seconds wall clock for the entire suite.** Measured every run and printed as the last line of output.

```
============ SUITE WALL CLOCK: 41.2s / 60.0s BUDGET (69%) ============
```

`conftest.py` records `time.monotonic()` at session start and end, prints the line in `pytest_sessionfinish`, and **exits non-zero if the ceiling is exceeded**. A slow suite is a build failure, not a note.

**There is no fast subset, no `-m unit`, no `--quick`, no markers.** This is deliberate and it is the point of the section: the moment a fast target exists, it becomes the target that gets run, and the slow tests execute only when someone remembers — which, in the last ninety minutes of a six-hour build, is never. One suite, one number, one budget.

60 seconds is achievable because `D7` guarantees no network and `CachedJudge` replays from disk. If the suite approaches the ceiling, the response is to shrink the fixture corpus used in tests — recorded in `config.toml` — not to split the suite. `test_budget_line_is_printed` asserts the line appears, so the budget cannot be quietly removed.

---

## 8. TELEMETRY IS NOT A RESULT

`Timing` is never a field of `Ranking`, `CandidateScore`, `RequirementJudgement`, or any other core dataclass. Every instrumented stage returns a 2-tuple:

```python
ranking, timing = rank(scores, unparsed, k, ranker, as_of)
```

Timings accumulate in a `TimingLog` held by `pipeline.py` and are written to `eval/timing.json` — a separate file from `eval/results.json`. Nothing in `results.json` contains a duration, and nothing in `timing.json` contains a score.

Three consequences that make this load-bearing rather than stylistic:

1. `RunId` hashes the input tuple only. Two runs of identical inputs at different speeds share a `RunId`, which is what makes D6's byte-comparison possible at all.
2. `Ranking.__eq__` (dataclass-generated) is meaningful — two rankings compare equal when the *decisions* match, regardless of how long they took.
3. PDD **T6** (90 s latency) and **T7** ($2.00 cost) are read from `timing.json`; PDD **T5** (P@10) is read from `results.json`. A threshold check can never accidentally read a duration into a score comparison.

`test_d14_timing_absent_from_results` walks every core dataclass's `__dataclass_fields__` and fails on any field named in `{elapsed_ms, started_at, ended_at, duration, latency, call_count}`. `test_d14_equal_rankings_differ_in_timing` constructs two rankings from the same inputs with divergent timings and asserts `a == b`.

---

**Changelog**

| Date | Change | Commit |
|---|---|---|
| ____ | Initial commit at G0, alongside PDD | ______ |
