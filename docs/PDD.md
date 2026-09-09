# PRODUCT DEFINITION DOCUMENT — `shortlist`

**Repo:** `shortlist/`
**Doc path:** `docs/PDD.md`
**Status:** frozen at commit before hackathon start. Amendments require a new commit with a dated changelog entry at the bottom of this file. No silent edits.

---

## 1. ONE-LINE DEFINITION

`shortlist` takes one job description and a folder of resumes and returns a ranked top-10 in which every candidate carries a quoted line from their own resume for each requirement they were credited with — and it measures whether the LLM doing that ranking actually beats keyword search.

---

## 2. THE PROBLEM

A recruiter posts one mid-level backend engineering role. The posting stays open 14 days and collects **340 applications**.

Screening one resume properly — open the file, read past the summary block, find the evidence, decide — takes about **45 seconds**. That is **4 hours 15 minutes** of continuous reading for a single req. A recruiter carrying 8 open reqs cannot spend 34 hours a fortnight on first-pass screening, so what actually happens is one of three things:

1. **Keyword filter in the ATS.** Query is `Java AND Kubernetes AND "REST"`. It returns 41 resumes. It drops the candidate who wrote "containerised the deployment on EKS" because the literal token `Kubernetes` never appears. It keeps the candidate who listed `Kubernetes` in a 60-item skills wall with no project attached.
2. **First-40-then-stop.** Applications are read in submission order until the recruiter's patience runs out, typically around 40. The other 300 are rejected by timeout, not by assessment. Application #287 was never read.
3. **Proxy heuristics.** University tier, employer brand, resume formatting quality. Fast, defensible-sounding, and the least correlated with job performance of the three.

The measurable consequence: two recruiters screening the same 340 resumes for the same req produce shortlists that overlap by **roughly half**. The process is not just slow, it is not reproducible.

`shortlist` targets exactly the 4h15m and exactly the inconsistency — and refuses to claim it solves either until the numbers say so.

---

## 3. WHAT IT DOES — THE LOOP

One loop. Beginning: a JD arrives. End: an accept/reject decision is recorded against every shortlisted candidate.

1. **Recruiter pastes a job description** into a single textarea and clicks Extract.
2. **System decomposes the JD into 8–15 atomic requirements**, each a single testable claim ("has shipped production Java", "has worked with a managed container orchestrator"), displayed for the recruiter to delete or edit. This edited list is the contract for everything downstream.
3. **Recruiter uploads a folder of resumes** (`.pdf` with a text layer, `.docx`). Files that yield under 200 characters of extracted text are surfaced immediately in a **Failed to parse** list, with filenames, and are counted as failures — never silently dropped.
4. **System scores every parsed resume against every requirement**, producing per-requirement `{met: bool, confidence: 0–1, evidence: verbatim span}`. Evidence spans are validated as exact substrings of the source resume text; a span that fails validation is discarded and the requirement drops to `met: false`.
5. **System ranks candidates** by weighted requirement coverage and returns the top 10, alongside the same corpus ranked by two baselines.
6. **Recruiter opens a candidate, sees each requirement with its quoted evidence line**, and clicks Accept or Reject.
7. **Decisions and the full ranked run are written to Postgres and exported as `runs/<run_id>.json`** — the file that every claim in section 7 is computed from.

Step 6 is not a UI flourish. It is the instrument. A ranker with no recorded human verdict produces no measurement.

---

## 4. THE THESIS — NON-NEGOTIABLE

> **Measure where per-requirement LLM matching with evidence extraction beats keyword and embedding retrieval on recruiter-labeled relevance, and characterise the disagreements.**

This is a measurement, not a capability. If the LLM loses, the document reports that the LLM loses and the project still has a result.

### Rules that follow from it

**R1.** The gold labels are created and committed to `eval/gold.csv` **before** any ranker output exists on the labeled corpus. The commit hash is recorded in section 7 and quoted in the demo.

**R2.** All three rankers (R0, R1, R2) run over the identical corpus, the identical requirement list, and the identical top-k. No ranker gets a preprocessing step the others do not.

**R3.** Parse failures count against the ranker that failed to parse them. They are not excluded from the denominator.

**R4.** The headline metric and `k` are fixed in section 7 before any run. `k = 10`.

### What I will NOT do to make the result look better

- **Not relabel the gold set after seeing model output.** Not one row. If a label looks wrong post-hoc, it stays, and the disagreement is discussed in prose.
- **Not tune prompts against the held-out 15.** Prompt iteration happens on the 25-resume dev split only. The held-out split is scored once, at H+4:15, and that score is the reported score.
- **Not weaken the baselines.** R0 gets the same extracted requirement list R2 gets, proper stemming, and IDF weighting. A strawman TF-IDF over raw JD text is not a baseline, it is a prop.
- **Not re-roll for a good seed.** The self-consistency run is three shuffles; whichever three come out are the three reported.
- **Not drop hard resumes from the corpus** because they hurt the numbers. Corpus is frozen at H+0:00.
- **Not change `k` after seeing results.** If R2 wins at k=5 and loses at k=10, the report says exactly that, with k=10 as headline.
- **Not present a cherry-picked demo candidate.** The demo walks the #1 candidate from the held-out run, whoever that turns out to be, plus one candidate the system got wrong.
- **Not claim a win below the section 6 threshold.** Parity is a result and will be reported as parity.

---

## 5. TAXONOMY

Every category the system assigns, split by what actually computes it. I expected this to come out roughly even. It does not — and three categories I assumed were mechanical are not.

### 5A. Rules can compute (deterministic, testable with `assert`)

| Category | Rule | Test file |
|---|---|---|
| File type accepted | extension in `{.pdf, .docx}` | `tests/test_ingest.py` |
| Text-layer present | extracted chars ≥ 200 | `tests/test_ingest.py` |
| Contact block present | regex email OR 10-digit phone | `tests/test_ingest.py` |
| Explicit skill token present | case-folded exact/stem match against requirement token list | `tests/test_r0.py` |
| Degree name present | match against `data/degrees.txt` | `tests/test_rules.py` |
| Certification name present | match against `data/certs.txt` | `tests/test_rules.py` |
| Evidence span validity | span is exact substring of source text after whitespace normalisation | `tests/test_evidence.py` |
| Document section headers | regex on known header vocabulary | `tests/test_rules.py` |

Eight categories. All of them are string presence. Not one of them is a judgement about the candidate.

### 5B. Genuinely needs judgement (no rule I can write in 6 hours is correct)

| Category | Why the rule fails |
|---|---|
| **Requirement satisfaction** | "Has worked with a managed container orchestrator" is met by "deployed on EKS", "wrote Helm charts", "migrated services to GKE" — an open set. |
| **Years of experience** | Overlapping roles, contract gaps, "2019–present" resolved against what date, part-time weighting. *I assumed this was arithmetic. It is not.* |
| **Seniority level** | Title inflation is unbounded. "Lead Engineer" at a 4-person startup ≠ "Lead Engineer" at a bank. |
| **Skill depth vs. skill mention** | A 60-item skills wall and a paragraph describing one system are both "Python". |
| **Project substance** | Distinguishing a shipped system from a tutorial follow-along requires reading the description. |
| **Internship vs. employment** | Titles frequently omit the distinction; dates and company context imply it. |
| **Education equivalence** | Bootcamp, diploma, self-taught with shipped work, foreign degree naming. *I assumed the degree list handled this. The list only handles the name.* |
| **Domain transfer** | Whether payments experience counts toward a fintech requirement. |
| **Recency weighting** | Java used daily until 2018, none since — met or not met? |
| **Career-gap interpretation** | Not scored, but affects any experience-duration calculation. *I assumed I could ignore it. Ignoring it silently is itself a judgement.* |

**Ten judgement categories to eight rule categories — and the eight rules only ever answer "is this string here", never "is this candidate suitable."** The entire product value sits in 5B. That is precisely why R2 must be measured against R0: if string presence gets you the same shortlist, section 5B was a rationalisation.

---

## 6. PRE-DECLARED THRESHOLDS

Committed before any result exists. `eval/thresholds.json` holds these as machine-readable values; the harness reads that file and fails loudly on breach.

| # | Component | Threshold | Measured in | On breach |
|---|---|---|---|---|
| T1 | Resume parsing | ≥ **36 of 40** files (90%) yield ≥ 200 chars | `eval/parse_report.json` | Drop the failing format from scope, state the exclusion in the report, re-run. Do not hand-fix files. |
| T2 | Evidence validity | ≥ **95%** of returned spans are exact substrings of source | `eval/evidence_report.json` | Relabel the UI column from "Evidence" to "Model paraphrase — not verbatim". The claim in section 1 changes. |
| T3 | Self-consistency | Jaccard of top-10 across 3 shuffled runs ≥ **0.80** | `eval/consistency.json` | Ship, but the measured Jaccard is printed on the dashboard and stated in the demo's first 30 seconds. |
| T4 | Name-swap invariance | Max per-candidate score delta ≤ **0.05** (0–1 scale) AND mean rank shift ≤ **1.0** position across 3 name variants | `eval/bias.json` | This becomes the headline result. Ranking claim is demoted to secondary. |
| T5 | Win claim | P@10(R2) − P@10(R0) ≥ **+0.10** | `eval/results.json` | Below +0.10 and above +0.05: "modest lift". At or below +0.05: **parity** — reported as parity, no win language anywhere. |
| T6 | Latency | 40 resumes scored in ≤ **90 s** wall clock at concurrency 8 | `eval/timing.json` | Enable the embedding prefilter (top 25 → LLM). If still breached, drop corpus display to 25 and say so. |
| T7 | Cost | ≤ **$2.00** per 40-resume run | `eval/timing.json` | Switch to the smaller model for R2 and re-run all of section 7. Mixed-model results are not reported. |
| T8 | Label agreement | Cohen's κ between the two labelers ≥ **0.60** | `eval/agreement.json` | Report κ as the measurement ceiling. All P@10 figures are stated relative to it. Below 0.40, the gold set is called unreliable and the disagreement analysis becomes the headline. |

A breached threshold is never grounds for changing the threshold. It is grounds for changing the claim.

---

## 7. EVALUATION DESIGN

**Corpus.** 40 resumes, one job description. Sources: public resume datasets plus LLM-generated synthetic resumes; the synthetic fraction is stated in the report. Frozen at H+0:00, hash recorded in `eval/corpus.sha256`.

**Labels.** Two labelers independently mark each of the 40 as `shortlist` / `no-shortlist` against the JD, before any model runs. Disagreements resolved by discussion into `eval/gold.csv`. Cohen's κ on the pre-discussion labels goes to `eval/agreement.json`. Gold commit hash recorded here on the day: `________________`.

**Splits.** 25 dev (prompt iteration allowed), 15 held-out (scored exactly once, at H+4:15). The held-out filenames live in `eval/holdout.txt` and are not opened during development.

**Baselines.**
- **R0 — lexical.** IDF-weighted token match of the extracted requirement list against resume text, with stemming. Same requirement list R2 sees.
- **R1 — embedding.** Cosine similarity, JD text vs. whole resume, single vector each.
- **R2 — system.** Per-requirement LLM scoring with evidence extraction, weighted coverage ranking.

**Headline metric.** Precision@10 against the consensus gold set, on the held-out split, R2 vs. R0, with R1 reported alongside.

**Secondary, and the part that is actually interesting.** The **disagreement set**: resumes in R2's top-10 but not R0's, and vice versa. Each disagreement is hand-inspected and assigned one cause from `{implicit-phrasing, skills-wall-inflation, domain-transfer, format-artifact, unexplained}`. Counts go to `eval/disagreement.json`.

**The single sentence that carries the result** — fill the blanks, publish whatever they say:

> On 15 held-out resumes labeled by two recruiters at κ = ____, per-requirement LLM matching scored P@10 = ____ against IDF-keyword P@10 = ____, and of the ____ candidates the two methods disagreed on, ____ were cases where the resume described a skill without naming it.

---

## 8. RESULT LANGUAGE, PRE-WRITTEN

Drafted before any data exists so that the null result has a home to go to.

**Good outcome (T5 met, ≥ +0.10):**
> Per-requirement LLM matching with evidence extraction improved precision@10 from 0.__ to 0.__ over IDF-keyword retrieval on a 15-resume held-out set (κ = 0.__). The lift concentrates in a single failure mode: __ of __ disagreements were candidates who described a required capability without using the requirement's vocabulary. Keyword retrieval's misses were not random — they were systematically the candidates who wrote about systems rather than listing tools. Ranking was stable across input-order shuffles (Jaccard 0.__) and invariant to name substitution (max score delta 0.__).

**Mediocre outcome (+0.05 to +0.10):**
> LLM matching produced a modest precision@10 improvement (0.__ → 0.__), below our pre-declared +0.10 threshold for claiming a win. At roughly __× the latency and $__ per run, the ranking improvement alone does not justify the LLM. What it does provide that keyword retrieval cannot is per-requirement evidence spans, validated verbatim against source text at __% — a reviewability property, not an accuracy one. We report this as the honest value proposition.

**Null result (≤ +0.05, or T3/T4 breached):**
> **LLM matching did not beat keyword retrieval on this task.** Precision@10 was 0.__ for the LLM ranker and 0.__ for IDF-keyword — a difference of __, inside our pre-declared parity band and inside the noise implied by inter-rater agreement of κ = 0.__. Two findings follow. First, on resumes of this kind, requirement vocabulary is repeated closely enough that lexical matching captures most of the signal; the semantic gap we assumed exists was __ of 40 candidates. Second, our labelers agreed on only __% of cases before discussion, which places a hard ceiling on any measured precision — a ranker cannot be shown to beat a target that is itself unstable. We would not deploy the LLM ranker for ranking. [If T3 breached:] Additionally, top-10 membership changed by __% under input-order shuffling alone, meaning the ranking was partly measuring position rather than fit. [If T4 breached:] Name substitution moved scores by up to 0.__, which is a disqualifying result and the most important thing we measured today.

---

## 9. SCOPE IN THREE LEVELS

### CORE — never cut. If these are not done, the project failed.
- JD → editable requirement list
- PDF/DOCX text extraction with a visible failure list
- R2: per-requirement scoring + verbatim evidence spans
- R0 baseline (IDF-keyword)
- Ranked top-10 with expandable per-requirement evidence
- Accept/Reject recorded per candidate
- Gold set of 40, dual-labeled, committed before any run
- The four numbers: P@10 R2, P@10 R0, Jaccard, name-swap delta
- `runs/<run_id>.json` export

### CONDITIONAL — fixed cut order. Cut from the bottom up, in this order, no renegotiation.

| Cut order | Item |
|---|---|
| 1 (cut first) | Dark mode, styling beyond legibility |
| 2 | AWS deployment — fall back to localhost demo |
| 3 | Postgres persistence — fall back to JSON files on disk |
| 4 | R1 embedding baseline (R0 is the baseline that matters) |
| 5 | Disagreement cause-coding automation — do it by hand on paper |
| 6 | Embedding prefilter for latency |
| 7 (cut last) | Requirement-weight editing in the UI — hardcode equal weights |

### OUT OF SCOPE — will not be built, will not be discussed in the demo.
Authentication, user accounts, multi-tenancy. OCR for scanned PDFs. More than one job description per run. Candidate CRM, notes, email outreach, interview scheduling. Resume parsing into a normalised candidate schema beyond what ranking needs. Historical analytics or funnel charts. Kubernetes, Terraform, CI/CD pipelines. Any model training or fine-tuning. Scaling past 50 resumes. Mobile responsive layout. Salary or offer prediction. Video or portfolio ingestion.

Bias auditing is **not** out of scope. It is T4 — a measurement, not a feature.

---

## 10. CALENDAR GATES

Anchored to hackathon day as **D**, start of clock as **H+0:00**. The event date is not stated in the brief; fill it here and the pre-work dates resolve: **D = ____________**.

### Pre-event

| Gate | When | Required output (file) | Cut rule if missed |
|---|---|---|---|
| G0 | D−7 | `docs/PDD.md` committed, this document, unamended | Non-negotiable. Without it there is no pre-declaration and no publishable null result. |
| G1 | D−5 | `eval/corpus/` — 40 resumes + 1 JD, `eval/corpus.sha256` | Drop to 25 resumes. Do not drop below 25; P@10 on fewer than 25 is not a measurement. |
| G2 | D−3 | `eval/gold.csv` + `eval/agreement.json` (two labelers, κ computed) | Single labeler, κ omitted, and the report states the measurement has no agreement ceiling — a stated weakness, not a hidden one. |
| G3 | D−2 | `eval/thresholds.json`, `eval/holdout.txt` | Blocks the run. Thresholds declared after H+0:00 are not pre-declared. |
| G4 | D−1 | Repo scaffold boots: `docker compose up` → health endpoint 200; model API key verified with one live call | Fall back to localhost + SQLite. Cut #2 and #3 fire early. |

### Event day — 6 hours

| Gate | Clock | Required output | Cut rule if missed |
|---|---|---|---|
| H1 | H+0:30 | Service running, corpus hash verified against G1 | Fire cut #2. Stop attempting deployment for the rest of the day. |
| H2 | H+1:15 | `runs/req_list.json` — JD decomposed to 8–15 requirements; 40 files extracted, `eval/parse_report.json` written, **T1 checked** | If T1 breached, drop the failing format now and record the exclusion. Do not spend a second hour on extraction. |
| H3 | H+2:30 | R2 scores all 25 dev resumes with evidence; **T2 and T6 checked** | If T6 breached, fire cut #6 (enable prefilter). If T2 breached, rename the UI column and move on — do not re-engineer the prompt past H+2:30. |
| H4 | H+3:15 | R0 running, `eval/results_dev.json` has both rankers | **Hard gate.** If R0 is not running at H+3:15, stop all UI work and build R0. The project has no result without a baseline. Fire cuts #1, #4, #5 immediately. |
| H5 | H+4:15 | Dashboard renders ranked list + evidence + accept/reject; **held-out split scored once**, `eval/results.json` written | If the dashboard is not ready, score the held-out split anyway from the CLI. The numbers outrank the UI. |
| H6 | H+4:45 | `eval/consistency.json`, `eval/bias.json` — **T3 and T4 checked** | Non-negotiable. If time is short, cut demo rehearsal, not these. A ranking with no stability or bias check is a demo. |
| H7 | H+5:15 | Deployed URL, or the decision to demo on localhost, recorded | Automatic: at H+5:15 the deployment attempt ends regardless of state. |
| H8 | H+5:30 | One slide with four numbers + the section 7 sentence, blanks filled from `eval/results.json` | Non-negotiable. |
| H9 | H+6:00 | Demo delivered: gold commit hash shown, #1 held-out candidate walked, one wrong ranking walked | — |

---

**Changelog**

| Date | Change | Commit |
|---|---|---|
| ____ | Initial freeze | ______ |
