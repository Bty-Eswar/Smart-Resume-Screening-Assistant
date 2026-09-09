# FRONTEND BUILD PROMPTS — Shortlist Frontend & Demo Wiring

**Doc path:** `docs/FRONTEND_BUILD_PROMPTS.md`  
**Complements:** `docs/BUILD_PROMPTS.md` (Backend & Determinism Core)  
**Stack decision:** React + Vite frontend talking to the existing FastAPI backend (`api.py`) over HTTP fetch/axios.

---

## What Is Missing & Architecture Context

The backend (`core/`, `adapters/`, `eval/`, `pipeline.py`) is complete, hermetic, and verified by 110 tests.  
`api.py` currently exposes:
- `GET /` & `/dashboard`: Static/demo server-rendered HTML dashboard
- `GET /api/ranking`: Returns in-memory ranking
- `POST /api/verdict`: Accept/Reject candidate
- `GET /health`: Service health check

Recruiters currently lack API endpoints to:
1. Upload candidate resumes (PDFs)
2. Submit a Job Description (JD) / build requirement specs
3. Trigger a pipeline run (`pipeline.run_pipeline()`)

To connect a clean React + Vite frontend, the API needs a thin **demo service layer** on top of pure `core/`. This layer does not alter the core Determinism Charter (D1–D14 govern `core/`), but it strictly adheres to:
- Never inventing weights or heuristic shortcuts outside `core/`.
- Never skipping evidence validation.
- Reusing `pipeline.py`, `core.requirements`, `core.rankers`, and `adapters.ingest`.

---

## Execution Order

1. **[COMPLETED] Finish the API Surface:** Endpoints for JD submission (`POST /api/jobs`), requirement editing/reweighting (`PUT /api/jobs/{id}/requirements`), resume upload & parsing (`POST /api/jobs/{id}/resumes`), pipeline execution (`POST /api/jobs/{id}/run` with `r0_lexical` default), job-scoped ranking (`GET /api/jobs/{id}/ranking`), job-scoped verdicts (`POST /api/jobs/{id}/verdict`), and listing (`GET /api/jobs`). Verified end-to-end via `scripts/smoke_test.py`.
2. **[COMPLETED] Scaffold React / Vite:** Clean, modern React + Vite project in `frontend/`. Configured `.env`, `client.js` with axios propagating errors, dark theme matching `api.py` palette in `src/index.css`, top-level `Layout.jsx` with 3-step indicator, and confirmed live browser connection hitting `GET /api/jobs`.
3. **[COMPLETED] Build the 3 Screens:**
   - **Screen 1 (JobSetup.jsx):** Skill Extraction Engine from JD text, editable requirement table, percentage weights, running total with auto-normalization explanation, inline errors.
   - **Screen 2 (ResumeUpload.jsx):** Drag-and-drop dropzone, staged files queue, PDD R3 transparent failure reporting (OK, No Text Layer, Corrupt), screening pipeline trigger.
   - **Screen 3 (Dashboard.jsx):** AI Recommendation Engine view with ranked candidate cards, Determinism Charter D5 Abstain Band, expandable verbatim evidence drawers (Charter D8), optimistic Accept/Reject verdict decisions.

4. **Wire End-to-End:** React connected to FastAPI over REST.
5. **One-Click Demo Polish:** Seamless demo script & production presentation.

---

## 0. Ground Rules (Active)

1. **Frozen Backend Core:** `core/` and `adapters/` are frozen — do not modify any existing file under `core/`, `tests/`, or `eval/` except to add new test files.
2. **Location of New Work:** All new code lives in `api.py` (or a modular `api/` package if needed) and in the new top-level `frontend/` directory.
3. **Zero Duplication of Domain Logic:** Reuse `pipeline.py`, `core.requirements.build_requirements`, `core.rankers.r0_lexical.rank_lexical`, and `adapters.ingest.ingest_resumes`. Do not reimplement scoring, parsing, or ranking logic in the API layer or frontend.
4. **Pure Presentation Layer:** The frontend never computes a score, never re-derives a ranking, and never invents evidence text — it strictly renders what the API returns.
5. **Verification Requirement:** After each numbered prompt, run the app (backend + frontend) and confirm it works with live data before marking complete.
