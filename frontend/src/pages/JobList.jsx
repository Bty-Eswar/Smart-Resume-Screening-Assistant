// frontend/src/pages/JobList.jsx — Home screen with Recent Jobs list and + New Job action
import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Briefcase,
  Plus,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  RefreshCw,
  Users,
  CheckCircle2,
  Clock,
  Layers,
} from "lucide-react";
import { listJobs } from "../api/client";
import JobSetup from "./JobSetup";

export default function JobList() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);

  const fetchJobs = () => {
    setLoading(true);
    listJobs()
      .then((data) => {
        setJobs(data);
        setLoading(false);
        // If no jobs exist yet, default to showing create form
        if (data.length === 0) {
          setShowCreateForm(true);
        }
      })
      .catch(() => {
        setLoading(false);
        setShowCreateForm(true);
      });
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  const getTargetRoute = (job) => {
    if (job.status === "ranked") return `/jobs/${job.job_id}/dashboard`;
    if (job.status === "resumes_uploaded") return `/jobs/${job.job_id}/upload`;
    return `/jobs/${job.job_id}/requirements`;
  };

  const getStatusBadge = (status) => {
    if (status === "ranked") {
      return (
        <span className="badge badge-success">
          <CheckCircle2 size={12} style={{ marginRight: "4px" }} />
          RANKED & READY
        </span>
      );
    }
    if (status === "resumes_uploaded") {
      return (
        <span className="badge badge-warning">
          <Layers size={12} style={{ marginRight: "4px" }} />
          RESUMES UPLOADED
        </span>
      );
    }
    return (
      <span className="badge badge-neutral">
        <Clock size={12} style={{ marginRight: "4px" }} />
        DRAFT REQUIREMENTS
      </span>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* Top Banner & Action */}
      <div
        className="glass-card"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "20px",
          padding: "28px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
            <Briefcase size={26} color="#6366f1" />
            <h2 style={{ fontSize: "22px" }}>Screening Jobs & Candidate Runs</h2>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
            Resume screening pipeline powered by strict determinism and evidence justification.
          </p>
        </div>

        <div style={{ display: "flex", gap: "12px" }}>
          {jobs.length > 0 && (
            <button
              type="button"
              onClick={() => setShowCreateForm(!showCreateForm)}
              className={showCreateForm ? "btn btn-secondary" : "btn btn-primary"}
              style={{ gap: "8px", padding: "10px 20px" }}
            >
              <Plus size={16} />
              <span>{showCreateForm ? "View Existing Jobs" : "+ New Job"}</span>
            </button>
          )}
        </div>
      </div>

      {/* Render Create Job Setup Form if toggled or if no jobs */}
      {showCreateForm ? (
        <JobSetup />
      ) : (
        /* Recent Jobs List */
        <div className="glass-card">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "20px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Sparkles size={18} color="#a855f7" />
              <h3 style={{ fontSize: "18px" }}>Recent Screening Jobs</h3>
            </div>
            <span className="badge badge-neutral">{jobs.length} Active Runs</span>
          </div>

          {loading ? (
            <div style={{ textAlign: "center", padding: "30px", color: "var(--text-muted)" }}>
              <RefreshCw size={20} className="spin-animation" style={{ animation: "spin 1s linear infinite" }} />
              <div style={{ marginTop: "8px" }}>Loading jobs...</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              {jobs.map((job) => (
                <div
                  key={job.job_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: "16px",
                    padding: "16px 20px",
                    background: "rgba(255, 255, 255, 0.02)",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border)",
                    transition: "all 0.2s ease",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                      <span style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-primary)" }}>
                        {job.title}
                      </span>
                      {getStatusBadge(job.status)}
                    </div>

                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "16px",
                        fontSize: "13px",
                        color: "var(--text-muted)",
                        marginTop: "6px",
                      }}
                    >
                      <span>
                        Job ID: <code style={{ color: "#a5b4fc" }}>{job.job_id}</code>
                      </span>
                      <span>•</span>
                      <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                        <Users size={14} />
                        <strong>{job.candidate_count}</strong> candidates
                      </span>
                    </div>
                  </div>

                  <Link
                    to={getTargetRoute(job)}
                    className={job.status === "ranked" ? "btn btn-primary" : "btn btn-secondary"}
                    style={{ padding: "8px 18px", fontSize: "13px", gap: "8px" }}
                  >
                    <span>{job.status === "ranked" ? "Open Dashboard" : "Continue Workflow"}</span>
                    <ArrowRight size={15} />
                  </Link>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
