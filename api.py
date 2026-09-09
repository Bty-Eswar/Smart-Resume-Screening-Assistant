# api.py — SDD §2 / BUILD_PROMPTS M11 Dashboard & Service
import json
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.types import Ranking, Verdict
from pipeline import ranking_to_dict

app = FastAPI(title="Shortlist Resume Screening Assistant", version="1.0.0")

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


class VerdictUpdateRequest(BaseModel):
    candidate_id: str
    verdict: str


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
