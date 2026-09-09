# BUILD PROMPTS — `shortlist`

**Doc path:** `docs/BUILD_PROMPTS.md`
**Derives from:** `docs/PDD.md`, `docs/SDD.md`
**Convention:** every number below is marked `[H]` — a **hypothesis to verify by measurement**, not a fact. If a measured value contradicts an `[H]`, the measured value wins and the doc gets a changelog row.

**Order is measurement-first.** Guards before code they guard. Generator before harness. Harness before engine. The engine is built last because it is the thing under test, and a thing under test cannot also be the thing that decides whether it passed.

---

## SESSION OPENER

> Paste once at the start of every build session, before the module prompt.

---

You are building `shortlist`, a resume-screening measurement system. Two documents govern this work: `docs/PDD.md` (what is being measured and what would falsify it) and `docs/SDD.md` (how the code is shaped). Read both before writing anything. Where this prompt and those documents disagree, **stop and say so** — do not reconcile them yourself.

### DETERMINISM CHARTER — binding on every line you write

- **D1** No `float` in `core/`. Scores are `int` basis points, `0..10000`. Floats exist only in `adapters/`, before `quantize()`.
- **D2** No clock reads in `core/`. The date is an injected `as_of: AsOfDate` parameter.
- **D3** Every ID is `blake2b(canonical_tuple, digest_size=16).hexdigest()`. Never `uuid4()`, never a counter, never object identity.
- **D4** Every returned sequence is a sorted `tuple` with an explicitly named key function. Never a `set`, never insertion-ordered `dict`, never an unsorted comprehension.
- **D5** Tie-break chain is `(score_bp desc, met_count desc, high_weight_met_count desc)`. Entries still tied after all three **ABSTAIN** into `abstain_band`. Candidate ID never breaks a tie.
- **D6** Identical inputs produce byte-identical output files.
- **D7** The suite makes zero network calls. `BedrockJudge.__init__` raises `RuntimeError` when `PYTEST_CURRENT_TEST` is in `os.environ`.
- **D8** Every `EvidenceSpan.text` equals `resume.text[span.start:span.end]` exactly. A span failing this is dropped and its judgement forced `met=False`.
- **D9** `JudgementCache` key is `blake2b((model_id, prompt_version, resume_sha256, requirement_id))`. Never path, order, or clock.
- **D10** `core.ranking` is invariant to input order.
- **D11** `eval/gold.csv` is never written by application code.
- **D12** `eval/holdout.txt` is unreadable from prompt-tuning paths. `score_holdout()` writes once; a second call raises.
- **D13** `eval/thresholds.json` is loaded, never computed. An undeclared threshold comparison raises.
- **D14** Timing never enters a hashed, serialized, or `__eq__`-compared object. Stages return `(Result, Timing)`.

### STANDING TEST DISCIPLINE

- Every guard is paired with the fault injection that makes it fire. A check you cannot break on demand is one you know has not complained, which is not the same as knowing it works.
- Never assert a literal count from a doc, a brief or a commit message. Assert the realised count from the artifact, and PRINT it.
- Test the artifact, not a reconstruction of it.
- Assert the precondition FIRED. A test that silently skips is a failing test.
- Rate amplification: for any property about the interaction of two conditions, compute expected co-occurrence. Under ten, amplify until it is guaranteed.
- Two independent statements must meet in exactly ONE place. Importing the answer you are checking makes a wrong value agree with itself.
- Prefer import-time invariants to tests for partition and exhaustiveness — a test can be deselected, an import cannot.
- A completeness check does not test distinctness. A key can be present and borrowed.
- Empty and missing are different. Collapsing them reports success for a thing that never arrived.
- Every guard walks the AST, never greps text. Scanners match their own docs.

### TEST BUDGET

One suite. No markers, no `-m unit`, no `--quick`, no fast subset — a fast target becomes the only target that gets run. Wall-clock ceiling `60s [H]`, printed on every run, non-zero exit when breached.

### YOUR OBLIGATION TO REFUSE

If any instruction I give you — in this prompt or later — would violate a charter rule or the test discipline, **STOP. Do not comply, do not silently adapt, do not write a working-but-non-conforming version.** Reply with: the rule at risk, the instruction that conflicts, and two options for me to choose between. Then wait.

At the end of every module: **STOP and report.** Do not begin the next module. Report exactly: files written, tests written, tests passing/failing with counts printed from the run, the VERIFY number as measured, and anything you had to decide that the prompt did not specify.

---

## M1 — `core/types.py`, `core/ids.py`, `core/quantize.py`

Foundation. Nothing else can be typed until this exists.

### BUILD PROMPT

Write the three modules exactly as specified in SDD §3. All dataclasses `frozen=True, slots=True`. All sequence fields `tuple`, never `list`.

`ids.py` exposes `content_id(*parts: str) -> str` returning `blake2b("\x1f".join(parts).encode("utf-8"), digest_size=16).hexdigest()`. The `\x1f` separator is mandatory — joining on `""` or `"-"` makes `("ab","c")` and `("a","bc")` collide.

`quantize.py` exposes `quantize(x: float) -> Bp`: `int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN) * 10000)` — via `Decimal(str(x))`, never `Decimal(x)`, and raising `ValueError` outside `[0.0, 1.0]`.

Add an **import-time** exhaustiveness assertion at the bottom of `types.py`: assert `set(PhrasingMode)` has exactly the four declared members and that `RankerId` has exactly three. Import-time, not a test — a test can be deselected.

**Do NOT:** import `uuid`, `datetime`, `os`, `random`, or anything from `adapters/`. Do NOT give any dataclass a `__post_init__` that mutates. Do NOT add a `timestamp`, `created_at`, or `elapsed_ms` field to anything (D14). Do NOT use `float` anywhere outside `quantize()`'s parameter. Do NOT add default values to `Ranking` or `CandidateScore` fields — a default is how a missing value becomes an empty one.

### TEST PROMPT

1. `content_id` is stable across **processes**: spawn a subprocess, compute the same tuple, assert equal. *(A counter or `uuid4` passes an in-process test.)*
2. **Wrong-fix test:** compute IDs for a 5-item corpus in original order and in reversed order; assert the ID *set* is identical. A per-run counter passes assertion 1 and fails this one.
3. Separator collision: `content_id("ab","c") != content_id("a","bc")`. Print both.
4. `quantize(0.5) == 5000`, `quantize(0.0) == 0`, `quantize(1.0) == 10000`. Print each.
5. **Wrong-fix test:** `quantize(0.12345)`. Truncation via `int(x*10000)` gives `1234`; correct half-even gives `1234` too — so instead use `quantize(0.99995)`: truncation gives `9999`, half-even gives `10000` `[H — verify by running both implementations]`. Assert the correct value and print it.
6. `quantize(-0.01)` and `quantize(1.01)` each raise `ValueError`. Assert the exception fired; a test that passes because nothing raised is a failing test.
7. Every dataclass in `types.py` raises `FrozenInstanceError` on attribute assignment. Loop over them via `__subclasses__`-free explicit list and **print the count checked** — do not assert a literal from this document.
8. **Fault injection:** in a temp module, define a `PhrasingMode` with three members and assert the import-time exhaustiveness check raises.

### VERIFY

`content_id` produces identical output across two OS processes and across input reordering. **Property, binary.** Do not proceed if it is order-dependent.

### CUT LINE

Nothing. This module is never cut. If it is late, everything downstream is wrong-shaped.

**STOP and report.**

---

## M2 — `tests/guards/` — the AST charter enforcers

Built second, before any logic, so every later module is born under enforcement.

### BUILD PROMPT

Write `tests/guards/ast_guards.py` implementing, as `ast.NodeVisitor` walks over every `.py` file under `core/`:

- `find_float_annotations(tree) -> tuple[Violation, ...]` — D1
- `find_clock_reads(tree) -> tuple[Violation, ...]` — D2, matching `datetime.now`, `date.today`, `time.time`, `time.monotonic`
- `find_uuid_usage(tree) -> tuple[Violation, ...]` — D3
- `find_set_returns(tree) -> tuple[Violation, ...]` — D4
- `find_io_imports(tree) -> tuple[Violation, ...]` — layering: `adapters`, `os`, `pathlib`, `requests`, `boto3`, `open`
- `find_timing_fields(tree) -> tuple[Violation, ...]` — D14, field names in `{elapsed_ms, started_at, ended_at, duration, latency, call_count}`

`Violation` is a frozen dataclass of `(file: str, lineno: int, rule: str, detail: str)`.

**Do NOT** implement any of these with `str.find`, regex, or `in source_text`. A text scanner matches the string `"float"` inside its own docstring and inside `docs/SDD.md`, and it matches `# no floats here` in a comment. Walk the AST.

**Do NOT** let a guard pass by finding zero files. If the file list is empty, raise.

### TEST PROMPT

1. For each of the six guards, **fault injection**: write a temp module under a scanned path containing exactly that violation, run the guard, assert exactly 1 violation and assert its `rule` matches. Six separate tests, not one loop that could pass on five.
2. **Wrong-fix test:** a temp module containing the *string literal* `"float"` and a comment `# float`. Assert the D1 guard returns **zero** violations. A grep-based implementation fails here — which is the entire point of the rule.
3. Assert the guard suite scans a nonzero number of files and **print the count**. Do not assert `== 12` from this doc.
4. Empty-vs-missing: point the scanner at a nonexistent directory → raises `GuardTargetMissing`. Point it at an existing but empty directory → raises `GuardTargetEmpty`. Two distinct exceptions; assert both fired.
5. Run all six guards against the real `core/` and assert zero violations. Print the per-rule counts.

### VERIFY

**Six of six** fault injections fire, and the grep-decoy test passes. Print the fired count. If any guard cannot be made to fire on demand, it does not work — it has merely not complained.

### CUT LINE

If late: cut `find_set_returns` and `find_timing_fields` (order 2 then 1 — timing is cut last of the two, because D14 protects the run hash). **Never cut** `find_clock_reads` or `find_io_imports` — those two are what keep `core/` pure enough for D6 to hold.

**STOP and report.**

---

## M3 — `eval/generate_corpus.py` and the truth model

The data generator, built before anything that consumes data.

### BUILD PROMPT

Write `generate(jd: JobSpec, n: int, seed: int) -> tuple[tuple[SyntheticResume, ...], tuple[TruthRecord, ...]]`, pure given an injected `random.Random(seed)`.

For each synthetic candidate, decide **first** which requirements to plant, in which `PhrasingMode`, and which to omit — then render text from those decisions. Truth records the decisions. Truth must **never** be produced by inspecting the rendered text (SDD §4).

Write `truth.jsonl`, one `TruthRecord` per line, sorted by `candidate_id`.

Implement the four cardinality checks from SDD §4 as an **import-time** validator function called at the end of `generate()`, raising on violation — partition and exhaustiveness belong at import/construction, not in a deselectable test.

**Do NOT** compute `omitted` as `all_requirements - planted` at read time. Store it explicitly. If both come from one expression, the partition check is checking a value against itself and will agree with any bug.

**Do NOT** plant a distractor token that belongs to any planted requirement's token set. **Do NOT** call `random` at module level. **Do NOT** write `gold.csv` (D11).

### TEST PROMPT

1. **Partition, per relationship type** (four separate tests, not one blanket loop): every requirement appears exactly once across `planted ∪ omitted`; each planted item is locatable in the text; omitted requirements have zero token occurrences; distractors are disjoint from planted tokens.
2. **Two-statements-meet-once:** hand-corrupt a `TruthRecord` by deleting one entry from `omitted` and assert the partition check raises. If it passes, `omitted` is being re-derived and the check is circular.
3. Same seed → byte-identical `truth.jsonl` across two processes. Print both SHA-256s.
4. Different seed → different output. Assert the precondition fired (i.e. that the files actually differ), don't let a broken generator pass by producing identical files both times.
5. **Rate amplification:** the property "a candidate has an implicit-paraphrase plant AND a skills-wall distractor for the same requirement" has an expected co-occurrence near zero under natural generation. Add a `force_modes` parameter and generate ≥ `20 [H]` such candidates deliberately. Print the realised co-occurrence count from the artifact.
6. **Wrong-fix test:** a generator that satisfies "omitted has zero tokens" by post-hoc deleting the token from rendered text. Assert every omitted requirement's *sentence region* is well-formed — no double spaces, no orphaned punctuation, no zero-length sections. Print the malformation count.
7. Assert `len(resumes)` equals the realised line count of `truth.jsonl` read back from disk, and print it. Do not assert `n`.

### VERIFY

**Realised co-occurrence count for the amplified property is ≥ 20 `[H]`, printed.** Below that, the disagreement cause-coding in PDD §7 has too few cases to validate against.

### CUT LINE

If late: drop `SKILLS_WALL` mode and generate only `EXPLICIT_TOKEN` / `IMPLICIT_PARAPHRASE` / `ABSENT`. This weakens the "skills-wall-inflation" disagreement category to hand-coding only. **Never cut** the truth-records-decisions rule — a generator that re-derives truth is worse than no generator.

**STOP and report.**

---

## M4 — `core/metrics.py`

The measuring instruments, before the thing they measure.

### BUILD PROMPT

Pure. Returns `Fraction`, never `float` (D1 reaches the eval layer).

```python
def precision_at_k(ranking: Ranking, gold: frozenset[CandidateId], k: int) -> Fraction
def jaccard_top_k(a: Ranking, b: Ranking, k: int) -> Fraction
def cohens_kappa(a: tuple[bool, ...], b: tuple[bool, ...]) -> Fraction
def rank_delta(a: Ranking, b: Ranking) -> tuple[tuple[CandidateId, int], ...]
```

Every function takes its denominator explicitly. `k` has **no default**. Per SDD C3, `precision_at_k` uses denominator `k` even when `len(ranked) < k`, and counts abstained entries as misses.

**Do NOT** default `k` to `10`. **Do NOT** use `len(ranking.ranked)` as a denominator anywhere. **Do NOT** import `statistics`, `sklearn`, or `numpy` — importing an implementation of the thing you are checking means a wrong value agrees with itself. **Do NOT** silently accept mismatched-length inputs to `cohens_kappa`; raise.

### TEST PROMPT

1. **Wrong-fix test, the important one:** a `Ranking` with 8 ranked entries of which 4 are gold. `precision_at_k(r, gold, 10)` must equal `Fraction(4,10)`, not `Fraction(4,8)`. Print both the numerator and denominator. The `len(ranked)` implementation passes every other precision test and fails only this one.
2. Abstain band straddling k: 7 ranked + 6 abstained, 3 gold in the abstained set. Assert those 3 count as misses and `abstain_straddled_k` is `True`. Assert the flag fired — a `False` here means the fixture didn't exercise the case.
3. `cohens_kappa` with two labelers who both mark 36/40 negative and agree on all: raw agreement is `0.90 [H]` but κ must be near `0` — assert `κ < Fraction(1,5) [H]`. Print κ and raw agreement side by side. An accuracy-based wrong implementation passes a naive test and fails this.
4. `cohens_kappa` on perfect agreement → exactly `Fraction(1)`. On perfect disagreement → negative. Print both.
5. Mismatched-length inputs raise. Assert the exception fired.
6. Empty vs missing: `precision_at_k` on an empty `ranked` tuple returns `Fraction(0,k)`; on `gold=frozenset()` raises `EmptyGoldSet`. These are different and must not collapse.
7. `jaccard_top_k` of a ranking with itself is `Fraction(1)`; of two disjoint top-10s is `Fraction(0)`.
8. No function returns a `float` — assert `isinstance(result, Fraction)` for all four. Print the count checked.

### VERIFY

**Assertion 1 passes: `4/10`, not `4/8`, printed as an explicit fraction.** This single number decides whether PDD T5 means anything.

### CUT LINE

If late: cut `rank_delta` (T4 falls back to comparing top-10 membership instead of positions — weaker, but still a bias signal). **Never cut** `precision_at_k` or `cohens_kappa`.

**STOP and report.**

---

## M5 — `config.py` and `eval/checks.py`

### BUILD PROMPT

`config.py` loads `config.toml` per SDD §6 and raises on three distinct axes: `UnknownConfigKey`, `ConfigTypeError`, `ConfigRangeError`. Reject `bool` where `int` is expected — `isinstance(True, int)` is `True` in Python and a naive loader accepts `k = true`.

`eval/checks.py` loads `eval/thresholds.json` and exposes `check(name: str, measured) -> CheckResult`. An unknown `name` raises `UndeclaredThreshold` (D13). `checks.py` never writes the file.

**Do NOT** put thresholds in `config.toml`. **Do NOT** let `check()` fall back to a hardcoded default when a key is missing — that is exactly how a threshold gets invented at hour four.

### TEST PROMPT

1. Unknown key → `UnknownConfigKey` fired.
2. Wrong type → `ConfigTypeError` fired.
3. `k = true` → `ConfigTypeError` fired. Separate test; the bool-is-int case is the one that slips through.
4. `weight_bp = 10001` → `ConfigRangeError` fired.
5. **Fault injection for D13:** call `check("t99_not_declared", 0)` → `UndeclaredThreshold` fired.
6. **Completeness is not distinctness:** assert every threshold key referenced anywhere in `eval/` (found by AST walk of string constants passed to `check`) exists in `thresholds.json`, **and** that `thresholds.json` has no duplicate keys after parsing, **and** that no two thresholds share an identical value-and-comparator pair borrowed from each other. Print the key count from the file.
7. Attempt to open `thresholds.json` for writing during a run → assert it raises (chmod `0o444` in the fixture).

### VERIFY

**The realised threshold key count in `thresholds.json`, printed, equals the count of distinct `check()` call sites found by AST walk.** Print both numbers.

### CUT LINE

If late: cut the three-axis config validation down to type-only (drop range and unknown-key). **Never cut** `UndeclaredThreshold` — it is the mechanical form of the PDD's entire pre-declaration promise.

**STOP and report.**

---

## M6 — `adapters/ingest.py`

### BUILD PROMPT

`ingest_resumes(dir: str) -> tuple[ParseOutcome, ...]`, sorted by filename. PDF via `pdfplumber`, DOCX via `python-docx`. Text normalized through `core.normalize.normalize_ws` before length check.

Four distinct `ParseStatus` outcomes: `OK`, `NO_TEXT_LAYER` (< `min_text_chars`), `UNSUPPORTED_TYPE`, `CORRUPT`. `resume` is `None` iff status is not `OK`.

**Do NOT** collapse "file produced zero characters" and "file does not exist" — the first is `NO_TEXT_LAYER` on a real file, the second is a caller error and raises. **Do NOT** drop failures from the returned tuple; PDD R3 counts them. **Do NOT** catch bare `Exception` and return `CORRUPT` for everything — that hides a bug in your own code as a bad input file.

### TEST PROMPT

1. A valid text-layer PDF → `OK`, `char_count > 0` printed.
2. A scanned/image-only PDF → `NO_TEXT_LAYER`. Assert `resume is None`.
3. A `.txt` file → `UNSUPPORTED_TYPE`.
4. A truncated/corrupt PDF → `CORRUPT`.
5. **Empty vs missing:** a zero-byte `.pdf` → `NO_TEXT_LAYER`; a filename that does not exist → raises. Assert both, separately.
6. **Boundary:** files with exactly `199`, `200`, `201` characters after normalization → `NO_TEXT_LAYER`, `OK`, `OK` `[H — 200 is from config, read it, don't hardcode]`. Print the three char counts.
7. Output is sorted by filename and is a `tuple` — shuffle the directory listing (monkeypatch `os.listdir`) and assert identical output. D4.
8. **Wrong-fix test:** an implementation that filters failures out of the return value passes 1–4. Assert `len(outcomes)` equals the realised file count on disk, printed, including all failures.

### VERIFY

**Realised parse-success rate on the frozen corpus, printed as `n/40`.** PDD T1 requires `≥ 36/40 [H]`. If breached, drop the failing format now — do not spend a second hour here.

### CUT LINE

If late: drop `.docx` and accept PDF only, recording the exclusion in the report. **Never cut** the failure list — an invisible failure is a silently shrunk denominator.

**STOP and report.**

---

## M7 — `core/normalize.py`, `core/requirements.py`, `core/evidence.py`

### BUILD PROMPT

`normalize_ws(s: str) -> str` — collapse runs of whitespace to single spaces, strip, NFKC-normalize. Deterministic, no locale dependence.

`build_requirements(raw: tuple[dict, ...], jd_sha: Sha256) -> tuple[Requirement, ...]` — sorted by `id`. Assert weights sum to exactly `10000`; if the model returned weights that don't, normalize them with integer arithmetic and put the remainder on the highest-weight requirement so the sum is exact.

`validate_evidence(j: RequirementJudgement, r: ResumeText) -> RequirementJudgement` — D8. Returns `j` unchanged if `r.text[j.evidence.start:j.evidence.end] == j.evidence.text`; otherwise returns a copy with `met=False, evidence=None`.

**Do NOT** implement validation as `if j.evidence.text in r.text`. That accepts a span whose offsets point somewhere else entirely, which is the failure mode this rule exists for. **Do NOT** let float weights in. **Do NOT** read a clock.

### TEST PROMPT

1. `normalize_ws` idempotent: `f(f(x)) == f(x)` over `50 [H]` varied inputs. Print the count run.
2. Weights sum to exactly `10000` after `build_requirements`, for a raw input summing to `9999` and one summing to `10003`. Print both realised sums.
3. Requirements sorted by `id`; shuffled input → identical output (D4).
4. Valid span → judgement unchanged.
5. **Wrong-fix test, the important one:** a resume containing the string `"Kubernetes"` at offset 400, and a judgement whose `evidence.text` is `"Kubernetes"` but whose `start/end` point at offset 50. The substring implementation accepts it; the offset implementation rejects it. Assert `met is False` and `evidence is None`.
6. Off-by-one boundary: span with `end` one past the true end → rejected. Span exactly correct → accepted. Print both.
7. Fabricated span (text not in document at all) → rejected, `met` forced `False`.
8. **Rate amplification:** natural invalid-span rate from a good model may be near zero. Inject `30 [H]` deliberately invalid spans into the fixture set and assert all 30 are caught. Print the caught count — this is PDD T2's instrument and it must be exercised, not merely available.

### VERIFY

**Realised evidence-validity rate on the fixture corpus, printed as a percentage.** PDD T2 requires `≥ 95% [H]`. Below it, the UI column is renamed to "Model paraphrase" and PDD §1's one-line definition changes.

### CUT LINE

If late: drop NFKC normalization (keep whitespace collapse). **Never cut** offset-based validation — substring validation is the plausible wrong fix and it makes the evidence claim false.

**STOP and report.**

---

## M8 — `core/scoring.py` and `core/ranking.py`

The engine core. Built after everything that measures it.

### BUILD PROMPT

`score_candidate(judgements, requirements, as_of) -> CandidateScore`. Integer arithmetic only: `score_bp = sum(weight_bp * confidence_bp // 10000 for met judgements)`. Judgements sorted by `requirement_id`. `as_of` is required and load-bearing for any experience-duration reasoning (D2).

`rank(scores, unparsed, k, ranker, as_of) -> Ranking`. Tie-break chain `(score_bp desc, met_count desc, high_weight_met_count desc)`. Entries tied after all three go to `abstain_band`, sorted by `candidate_id` for **display only** — that sort must not determine rank. Set `abstain_straddled_k` when the band crosses index `k`.

**Do NOT** add `candidate_id` as a fourth tie-break key. **Do NOT** rely on Python's stable sort to resolve ties — a stable sort produces byte-identical output and therefore *passes D6*, while silently ranking by input order and violating D5 and D10. This is the single most likely bug in the project. **Do NOT** read a clock. **Do NOT** use `/` on any score.

### TEST PROMPT

1. Known judgement set → hand-computed `score_bp`. Compute the expected value **by hand in the test**, not by importing `scoring` — two statements must meet in exactly one place.
2. **Rate amplification:** exact ties among continuous scores over 40 candidates have expected co-occurrence well under 10. Construct a fixture with `12 [H]` deliberately tied candidates. Print the realised tie count.
3. **Wrong-fix test, the critical one:** two candidates tied on all three keys. Swap their `candidate_id` values and re-rank. Assert (a) both appear in `abstain_band`, (b) neither appears in `ranked`, (c) the `ranked` tuple is byte-identical across the swap. A stable-sort implementation passes D6's byte test and fails (a).
4. **D10:** 20 shuffles of the input scores → identical `Ranking`. Print the shuffle count run.
5. Tie straddling `k`: 7 clear entries then a 6-way tie. Assert `abstain_straddled_k is True` and that `precision_at_k` treats the abstained as misses. Assert the flag fired.
6. `as_of` is load-bearing: two calls differing only in `as_of` produce different scores for a fixture with a duration-sensitive requirement. If they're identical, `as_of` is decorative and D2 is cosmetic. Print both scores.
7. No `float` in any returned object — walk the dataclass fields and assert. Print the field count checked.
8. Unparsed candidates appear in `Ranking.unparsed`, sorted by filename, and the realised count matches the input. Print it.

### VERIFY

**Assertion 3 passes in full: tied candidates land in `abstain_band`, not in `ranked`.** Property, binary. If a stable sort is silently resolving ties, PDD T3's Jaccard number becomes unattributable and the headline result cannot be defended.

### CUT LINE

Nothing in this module is cuttable. If it is late, cut the dashboard (M11) instead.

**STOP and report.**

---

## M9 — `adapters/judge_bedrock.py`, `adapters/judge_cached.py`

### BUILD PROMPT

`Judge` protocol: `judge(resume: ResumeText, req: Requirement) -> RequirementJudgement`.

`BedrockJudge.__init__` raises `RuntimeError` if `"PYTEST_CURRENT_TEST" in os.environ` (D7). It quantizes the model's float confidence at the boundary and never returns a float into core.

`CachedJudge` replays `fixtures/judgements/`, keyed per D9 on `blake2b((model_id, prompt_version, resume_sha256, requirement_id))`. A cache miss raises `CacheMiss` — it does not fall through to the network.

Add a `socket.socket` guard in `conftest.py` that raises on any connect attempt.

**Do NOT** key the cache on filename, index, or insertion order. **Do NOT** let `CachedJudge` fall back to `BedrockJudge`. **Do NOT** retry on failure inside `core/`.

### TEST PROMPT

1. `BedrockJudge()` under pytest → `RuntimeError` fired. Assert the exception, not just truthiness.
2. **Fault injection for the socket guard:** deliberately attempt `socket.create_connection(("example.com", 80))` in a test and assert the guard raises. A guard you cannot make fire is a guard you have not tested.
3. Cache key stability across processes; changing each of the four tuple elements independently changes the key. Four separate assertions, printed.
4. **Wrong-fix test:** two resumes with identical text but different filenames must produce the **same** cache key (key is on `sha256`, not path). Assert equality and print both keys.
5. Cache miss raises `CacheMiss` — assert fired. Assert no socket was opened during the attempt.
6. Empty vs missing: an empty cache *file* and an absent cache *directory* produce different exceptions.
7. Confidence returned by `CachedJudge` is `int` basis points, never float. Print the type.

### VERIFY

**Full suite runs with the socket guard armed and zero connect attempts, with assertion 2 proving the guard fires.** Binary.

### CUT LINE

If late: hand-write the fixture cache for `10 [H]` resumes instead of recording `40`, and note the reduced fixture corpus in the report. **Never cut** the pytest refusal or the socket guard — a suite that can reach the network is a suite whose results depend on the day.

**STOP and report.**

---

## M10 — `core/rankers/r0_lexical.py`, `r1_embedding.py`, `r2_llm.py`

### BUILD PROMPT

All three pure. R0: IDF-weighted token match using an injected IDF table — same requirement list R2 receives, stemming applied, per PDD "not weaken the baselines". R1: cosine over injected vectors; it does not fetch them. R2: assembles validated judgements into `CandidateScore`.

**Do NOT** give R0 a smaller requirement list, raw JD text instead of extracted requirements, or no stemming. A strawman baseline is a prop and PDD §4 forbids it explicitly. **Do NOT** let R1 compute embeddings. **Do NOT** let any ranker see `gold.csv` or `truth.jsonl`.

### TEST PROMPT

1. R0 on a resume containing every requirement token verbatim ranks it above one containing none. Print both scores.
2. **Wrong-fix test:** a TF-only implementation ranks a resume repeating one common token 50 times above one covering five distinct requirements. Assert the five-requirement resume ranks higher — this is what separates IDF from TF.
3. R0 and R2 receive requirement lists asserted **equal by content hash**. Print the hash. This mechanically enforces the no-strawman rule.
4. All three rankers return `Ranking` objects over the same candidate set; assert the candidate-ID sets are identical across rankers. Print the set size.
5. **Layering:** AST-assert that no module under `core/rankers/` imports `adapters`, `gold`, or `truth`.
6. R1 with injected orthogonal vectors → cosine `0`; identical vectors → `10000` bp after quantization. Print both.
7. Determinism: each ranker run twice on shuffled input → identical output (D10).

### VERIFY

**The requirement-list content hash is identical for R0 and R2, printed.** If they differ, the comparison in PDD §7 is not measuring what it claims.

### CUT LINE

If late: cut R1 entirely (this is cut order #4 in PDD §9). **Never cut** R0 — PDD gate H4 stops all UI work at H+3:15 if R0 is not running, because without a baseline there is no result.

**STOP and report.**

---

## M11 — `pipeline.py`, `eval/harness.py`, `api.py`, dashboard

### BUILD PROMPT

`pipeline.py` is the only module importing both `core/` and `adapters/`. Every stage returns `(Result, Timing)`; timings accumulate in a `TimingLog` written to `eval/timing.json`, never into `results.json` (D14).

`harness.py` runs all three rankers, writes `eval/results.json`, `consistency.json`, `bias.json`, `parse_report.json`, `timing.json`. `score_holdout()` writes once; a second call raises `HoldoutAlreadyScored` (D12).

Dashboard: ranked list, expandable per-requirement evidence, Accept/Reject buttons, and the abstain band rendered as a visually distinct band labelled with its size.

**Do NOT** put a duration, timestamp, or `run started at` into `results.json`. **Do NOT** let `harness.py` read `truth.jsonl` in any path producing `results.json` (SDD §4 — that would be circular). **Do NOT** let prompt-tuning code read `holdout.txt`.

### TEST PROMPT

1. **D6:** run the full pipeline twice from the fixture cache; assert `runs/<id>.json` is byte-identical. Print both SHA-256s.
2. **D14:** two runs with divergent timings produce equal `Ranking` objects and identical `run_id`. Print the ids.
3. `results.json` contains no key from `{elapsed_ms, started_at, duration, latency}` — walk the parsed JSON recursively, print the key count inspected.
4. **D12 fault injection:** call `score_holdout()` twice → second raises. Assert fired.
5. **D11 fault injection:** attempt to write `gold.csv` from application code → raises (file chmod `0o444` in the session fixture). Assert fired.
6. **Wrong-fix test:** AST-assert `harness.py` has no import path reaching `truth.jsonl` from the function that writes `results.json`. A comment saying it doesn't is not a test.
7. Dashboard renders a ranking whose `abstain_band` is non-empty and displays the band size; assert the realised band size in the DOM matches the object, printed.
8. Suite wall clock printed and under `60s [H]`; assert non-zero exit when a deliberately slow test breaches it (fault injection).

### VERIFY

**Two consecutive full runs produce byte-identical `runs/<run_id>.json`, both SHA-256s printed.** If they differ, find the source of variance before running anything against the held-out split — a nondeterministic core makes PDD T3 unattributable.

### CUT LINE

Cut in this fixed order if late: (1) dashboard styling, (2) deployment — demo on localhost, (3) Postgres — write JSON files instead. This matches PDD §9 cut order #1, #2, #3. **Never cut** `results.json` / `consistency.json` / `bias.json` — those three files are the deliverable. The dashboard is not.

**STOP and report.**

---

## APPENDIX — HYPOTHESES TO VERIFY

Every `[H]` in this document, gathered for one pass at the end. None is a fact until a run prints it.

| Marker | Claim | Verified by |
|---|---|---|
| 60s | Suite wall-clock ceiling is achievable | M11 assertion 8 |
| 0.99995→10000 | Half-even distinguishes from truncation at this input | M1 assertion 5 |
| ≥20 | Amplified co-occurrence count in generator | M3 VERIFY |
| 0.90 / κ<0.2 | Raw-agreement vs κ divergence fixture | M4 assertion 3 |
| 200 chars | Text-layer threshold — read from config, not hardcoded | M6 assertion 6 |
| ≥36/40 | Parse success (PDD T1) | M6 VERIFY |
| ≥95% | Evidence validity (PDD T2) | M7 VERIFY |
| 30 | Injected invalid spans for amplification | M7 assertion 8 |
| 12 | Deliberately tied candidates | M8 assertion 2 |
| 10 | Reduced fixture cache size under cut | M9 CUT LINE |
| 50 | Idempotence sample size | M7 assertion 1 |
