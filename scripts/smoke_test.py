# scripts/smoke_test.py — Manual smoke test for Shortlist API endpoints
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import httpx

BASE_URL = "http://127.0.0.1:8000"


def ensure_sample_pdfs():
    """Ensure sample PDFs (resume_holdout_01 through 05) exist in eval/ for smoke testing."""
    eval_dir = REPO_ROOT / "eval"
    eval_dir.mkdir(exist_ok=True)
    from tests.test_m6_ingest import make_pdf_bytes

    pdf_definitions = [
        (
            "resume_holdout_01.pdf",
            "Senior Backend Engineer with 8+ years experience in Python microservices, "
            "distributed cloud architecture, Docker, Kubernetes, and PostgreSQL systems. "
            "Led platform engineering and high-availability API deployment on AWS infrastructure. "
            * 2,
        ),
        (
            "resume_holdout_02.pdf",
            "Cloud Infrastructure Architect with 6+ years specializing in Kubernetes orchestration, "
            "Terraform automation, CI/CD pipelines, and Python backend tooling. "
            "Led migration of monolithic services to cloud-native containerized microservices. "
            * 2,
        ),
        (
            "resume_holdout_03.pdf",
            "Distributed Systems Specialist with 7+ years developing low-latency Python services, "
            "Kafka message streaming, and distributed consensus mechanisms. Expert in PostgreSQL and Redis caching layers. "
            * 2,
        ),
        (
            "resume_holdout_04.pdf",
            "Senior Site Reliability and DevOps Engineer. 5 years managing large-scale Kubernetes production clusters, "
            "CI/CD automation, and Terraform infrastructure-as-code deployments on AWS. "
            * 2,
        ),
        (
            "resume_holdout_05.pdf",
            "Frontend Specialist and UI Developer with React, TypeScript, and CSS experience. "
            "Built modern responsive dashboards and interactive web applications with REST API integration. "
            * 2,
        ),
    ]

    pdf_paths = []
    for fname, text in pdf_definitions:
        p = eval_dir / fname
        if not p.exists():
            p.write_bytes(make_pdf_bytes(text))
            print(f"Created sample PDF: {p}")
        pdf_paths.append(p)

    return pdf_paths


def main():
    sample_pdfs = ensure_sample_pdfs()

    server_process = None
    probe_client = httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(connect=0.3, read=1.0, write=1.0, pool=1.0))
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)

    # Check if server is already running, else start it
    try:
        r = probe_client.get("/health")
        if r.status_code == 200:
            print(f"[OK] Existing server detected at {BASE_URL}", flush=True)
    except Exception:
        print(f"[INFO] Starting FastAPI server on {BASE_URL}...", flush=True)
        log_path = REPO_ROOT / "uvicorn_smoke.log"
        log_file = open(log_path, "w", encoding="utf-8")
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=log_file,
        )
        # Wait for server to boot
        booted = False
        for _ in range(40):
            time.sleep(0.2)
            try:
                if probe_client.get("/health").status_code == 200:
                    booted = True
                    break
            except Exception:
                pass
        if not booted:
            print("[ERROR] Failed to connect to server within 8s.", flush=True)
            if server_process:
                server_process.kill()
            sys.exit(1)
        print(f"[OK] Server booted successfully at {BASE_URL}", flush=True)


    try:
        print("\n" + "=" * 70)
        print("1. POST /api/jobs — Submit Job Description & Extract Requirements")
        print("=" * 70)
        jd_payload = {
            "title": "Staff Platform & Distributed Systems Engineer",
            "jd_text": """Staff Platform & Distributed Systems Engineer
- 7+ years building high-throughput Python backend microservices
- Production Kubernetes cluster administration and Docker container orchestration
- Deep expertise in relational database architecture and PostgreSQL performance tuning
- Proven track record designing distributed consensus and caching systems
- Excellent cross-functional technical leadership and mentoring capabilities""",
        }
        res = client.post("/api/jobs", json=jd_payload)
        print(f"Status Code: {res.status_code}")
        data = res.json()
        print(f"Response Body:\n{json.dumps(data, indent=2)}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        job_id = data["job_id"]
        reqs = data["requirements"]
        assert len(reqs) > 0, "Expected extracted requirements"
        total_bp = sum(r["weight_bp"] for r in reqs)
        print(f"-> Verified total requirement weight sums to exactly: {total_bp} bp")
        assert total_bp == 10000

        print("\n" + "=" * 70)
        print("2. PUT /api/jobs/{job_id}/requirements — Edit / Reweight Requirements")
        print("=" * 70)
        updated_reqs_payload = {
            "requirements": [
                {"text": reqs[0]["text"], "weight": 300},
                {"text": reqs[1]["text"], "weight": 200},
                {"text": reqs[2]["text"], "weight": 100},
            ]
        }
        res = client.put(f"/api/jobs/{job_id}/requirements", json=updated_reqs_payload)
        print(f"Status Code: {res.status_code}")
        updated_data = res.json()
        print(f"Response Body:\n{json.dumps(updated_data, indent=2)}")
        assert res.status_code == 200
        new_total_bp = sum(r["weight_bp"] for r in updated_data["requirements"])
        print(f"-> Verified re-weighted requirements sum to exactly: {new_total_bp} bp")
        assert new_total_bp == 10000

        print("\n" + "=" * 70)
        print("3. POST /api/jobs/{job_id}/resumes — Upload 5 Resumes (01 through 05)")
        print("=" * 70)
        files_to_upload = []
        open_handles = []
        for p in sample_pdfs:
            f = open(p, "rb")
            open_handles.append(f)
            files_to_upload.append(("files", (p.name, f, "application/pdf")))

        try:
            res = client.post(f"/api/jobs/{job_id}/resumes", files=files_to_upload)
        finally:
            for h in open_handles:
                h.close()

        print(f"Status Code: {res.status_code}")
        upload_data = res.json()
        print(f"Response Body:\n{json.dumps(upload_data, indent=2)}")
        assert res.status_code == 200
        assert upload_data["summary"]["ok"] == 5
        print(f"-> Parsed {upload_data['summary']['ok']} resumes with status OK (PDD R3 preserved)")

        print("\n" + "=" * 70)
        print("4. POST /api/jobs/{job_id}/run — Execute Ranking Pipeline (R0 Lexical)")
        print("=" * 70)
        run_payload = {
            "ranker": "r0_lexical",
            "k": 10,
            "as_of": "2026-01-01",
        }
        res = client.post(f"/api/jobs/{job_id}/run", json=run_payload)
        print(f"Status Code: {res.status_code}")
        run_data = res.json()
        print(f"Run Response (Summary): run_id={run_data['run_id']}, ranked_count={len(run_data['ranked'])}, abstain_count={len(run_data['abstain_band'])}")
        assert res.status_code == 200
        assert len(run_data["ranked"]) > 0

        print("\n" + "=" * 70)
        print("5. GET /api/jobs/{job_id}/ranking — Retrieve Scoped Ranking")
        print("=" * 70)
        res = client.get(f"/api/jobs/{job_id}/ranking")
        print(f"Status Code: {res.status_code}")
        ranking_data = res.json()
        assert res.status_code == 200
        first_cand_id = ranking_data["ranked"][0]["candidate_id"]
        initial_verdict = ranking_data["ranked"][0]["verdict"]
        print(f"Top Candidate: {first_cand_id} (Initial Verdict: {initial_verdict}, Score: {ranking_data['ranked'][0]['score_bp']} bp)")

        print("\n" + "=" * 70)
        print("6. POST /api/jobs/{job_id}/verdict — Update Candidate Verdict")
        print("=" * 70)
        verdict_payload = {
            "candidate_id": first_cand_id,
            "verdict": "accept",
        }
        res = client.post(f"/api/jobs/{job_id}/verdict", json=verdict_payload)
        print(f"Status Code: {res.status_code}")
        verdict_res = res.json()
        print(f"Verdict Response: {json.dumps(verdict_res, indent=2)}")
        assert res.status_code == 200
        assert verdict_res["verdict"] == "accept"

        # Verify ranking now reflects the accepted verdict
        res = client.get(f"/api/jobs/{job_id}/ranking")
        updated_ranking_data = res.json()
        assert updated_ranking_data["ranked"][0]["verdict"] == "accept"
        print(f"-> Verified Candidate {first_cand_id} verdict updated to 'accept' in job ranking")

        print("\n" + "=" * 70)
        print("7. GET /dashboard — Verify HTML Dashboard Reflects Active Job")
        print("=" * 70)
        res = client.get("/dashboard")
        assert res.status_code == 200
        assert first_cand_id in res.text
        print(f"-> HTML Dashboard successfully rendered candidate {first_cand_id}")

        print("\n" + "=" * 70)
        print("FINAL RANKING JSON (Complete Object):")
        print("=" * 70)
        print(json.dumps(updated_ranking_data, indent=2))

        print("\n======================================================================")
        print("[SUCCESS] ALL END-TO-END SMOKE TEST ASSERTIONS PASSED")
        print("======================================================================")

    finally:
        client.close()
        if server_process:
            server_process.terminate()
            server_process.wait()


if __name__ == "__main__":
    main()
