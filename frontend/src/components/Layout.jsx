import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Briefcase, FileText, CheckCircle2, ShieldCheck, Activity, Plus } from "lucide-react";
import { checkHealth, getJob } from "../api/client";

export default function Layout({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const pathMatch = location.pathname.match(/\/jobs\/([^/]+)/);
  const jobId = pathMatch && pathMatch[1] !== "new" ? pathMatch[1] : null;

  const [activeJob, setActiveJob] = useState(null);
  const [healthStatus, setHealthStatus] = useState("checking"); // "connected" | "disconnected" | "checking"

  // Probe API connection on mount and every 5 seconds (Requirement 4)
  useEffect(() => {
    let isMounted = true;
    const probe = () => {
      checkHealth()
        .then(() => {
          if (isMounted) setHealthStatus("connected");
        })
        .catch(() => {
          if (isMounted) setHealthStatus("disconnected");
        });
    };
    probe();
    const timer = setInterval(probe, 5000);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, []);

  // Fetch job state if jobId is in URL
  useEffect(() => {
    if (!jobId) {
      setActiveJob(null);
      return;
    }
    getJob(jobId)
      .then((data) => {
        setActiveJob(data);
        // Automatic status-driven navigation jump
        if (data.status === "ranked" && location.pathname.endsWith("/requirements")) {
          navigate(`/jobs/${jobId}/dashboard`, { replace: true });
        } else if (data.status === "resumes_uploaded" && location.pathname.endsWith("/requirements")) {
          navigate(`/jobs/${jobId}/upload`, { replace: true });
        }
      })
      .catch(() => {
        setActiveJob(null);
      });
  }, [jobId, location.pathname, navigate]);

  // Determine active step (1, 2, or 3)
  const getStepNumber = () => {
    if (location.pathname.includes("/dashboard")) return 3;
    if (location.pathname.includes("/upload")) return 2;
    return 1;
  };

  const currentStep = getStepNumber();

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <Link to="/" className="brand-title">
            <ShieldCheck size={28} color="#6366f1" />
            <span>Shortlist</span>
          </Link>
          <span className="brand-badge">Audit-Grade Screening</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {/* Top-Right API Connection Indicator (Requirement 4) */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "6px 14px",
              borderRadius: "9999px",
              fontSize: "12px",
              fontWeight: 600,
              background:
                healthStatus === "connected"
                  ? "rgba(16, 185, 129, 0.12)"
                  : "rgba(239, 68, 68, 0.15)",
              border: `1px solid ${
                healthStatus === "connected"
                  ? "rgba(16, 185, 129, 0.35)"
                  : "rgba(239, 68, 68, 0.4)"
              }`,
              color: healthStatus === "connected" ? "#34d399" : "#f87171",
            }}
          >
            <span
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                backgroundColor: healthStatus === "connected" ? "#10b981" : "#ef4444",
                boxShadow: healthStatus === "connected" ? "0 0 8px #10b981" : "0 0 8px #ef4444",
                display: "inline-block",
              }}
            />
            <span>
              {healthStatus === "connected"
                ? "Backend Connected"
                : "Backend Offline (Start uvicorn api:app --port 8000)"}
            </span>
          </div>

          <Link to="/" className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: "13px" }}>
            <Briefcase size={15} />
            <span>Jobs</span>
          </Link>
        </div>
      </header>


      {/* 3-Step Indicator */}
      <nav className="stepper-nav" aria-label="Screening workflow steps">
        <ol className="stepper-list">
          {/* Step 1 */}
          <li
            className={`step-item ${currentStep === 1 ? "active" : ""} ${
              currentStep > 1 || (activeJob && activeJob.requirements) ? "completed" : ""
            }`}
          >
            <span className="step-badge">1</span>
            <span>Job & Requirements</span>
          </li>

          <div className={`step-connector ${currentStep > 1 ? "completed" : ""}`} />

          {/* Step 2 */}
          <li
            className={`step-item ${currentStep === 2 ? "active" : ""} ${
              currentStep > 2 || (activeJob && activeJob.status === "ranked") ? "completed" : ""
            }`}
          >
            <span className="step-badge">2</span>
            <span>Upload Resumes</span>
          </li>

          <div className={`step-connector ${currentStep > 2 ? "completed" : ""}`} />

          {/* Step 3 */}
          <li className={`step-item ${currentStep === 3 ? "active" : ""}`}>
            <span className="step-badge">3</span>
            <span>Screening Dashboard</span>
          </li>
        </ol>
      </nav>

      {/* Main Content Area */}
      <main>{children}</main>
    </div>
  );
}
