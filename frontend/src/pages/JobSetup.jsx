// frontend/src/pages/JobSetup.jsx — Screen 1: Skill Extraction & Requirement Tuning
import React, { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Sparkles,
  ArrowRight,
  Plus,
  Trash2,
  AlertCircle,
  CheckCircle2,
  Sliders,
  FileText,
  RotateCcw,
  Zap,
} from "lucide-react";
import { createJob, getJob, updateRequirements } from "../api/client";

const SAMPLE_JD = `Mid-Level Backend Engineer
- 3+ years of professional backend development experience with Python
- Experience designing and maintaining RESTful APIs and PostgreSQL databases
- Hands-on experience with Docker containerization and CI/CD pipelines
- Working knowledge of Redis caching and distributed asynchronous task queues
- Solid understanding of Git version control, unit testing, and agile team workflows`;


export default function JobSetup() {
  const navigate = useNavigate();
  const { jobId: routeJobId } = useParams();

  const [title, setTitle] = useState("");
  const [jdText, setJdText] = useState("");
  const [activeJobId, setActiveJobId] = useState(routeJobId || null);
  const [requirements, setRequirements] = useState([]);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);
  const [reqError, setReqError] = useState(null);

  // New requirement inputs
  const [newText, setNewText] = useState("");
  const [newWeight, setNewWeight] = useState(15);

  // If jobId is present in URL, load the existing job
  useEffect(() => {
    if (routeJobId) {
      setLoading(true);
      getJob(routeJobId)
        .then((job) => {
          setTitle(job.title);
          setJdText(job.jd_text || "");
          setActiveJobId(job.job_id);
          if (job.requirements && job.requirements.length > 0) {
            setRequirements(
              job.requirements.map((r) => ({
                id: r.id,
                text: r.text,
                weight: Math.round(r.weight_bp / 100), // convert basis points to %
              }))
            );
          }
          setLoading(false);
        })
        .catch((err) => {
          setError(err.response?.data?.detail || "Failed to load job details");
          setLoading(false);
        });
    }
  }, [routeJobId]);

  const handleLoadSample = () => {
    setTitle("Mid-Level Backend Engineer");
    setJdText(SAMPLE_JD);
    setError(null);
  };


  const handleExtract = async (e) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Please enter a job title");
      return;
    }
    if (!jdText.trim()) {
      setError("Please enter or paste a job description");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const data = await createJob(title.trim(), jdText.trim());
      setActiveJobId(data.job_id);
      setRequirements(
        data.requirements.map((r) => ({
          id: r.id,
          text: r.text,
          weight: Math.round(r.weight_bp / 100), // bp to %
        }))
      );
      setLoading(false);
    } catch (err) {
      setError(
        err.response?.data?.detail || "Failed to extract requirements. Ensure JD contains bullet points or distinct lines."
      );
      setLoading(false);
    }
  };

  const handleUpdateReqText = (index, text) => {
    const updated = [...requirements];
    updated[index].text = text;
    setRequirements(updated);
  };

  const handleUpdateReqWeight = (index, weight) => {
    const updated = [...requirements];
    const num = parseInt(weight, 10);
    updated[index].weight = isNaN(num) ? 0 : Math.max(0, num);
    setRequirements(updated);
  };

  const handleDeleteReq = (index) => {
    const updated = requirements.filter((_, i) => i !== index);
    setRequirements(updated);
  };

  const handleAddRequirement = (e) => {
    e.preventDefault();
    if (!newText.trim()) return;
    setRequirements([
      ...requirements,
      {
        id: `custom_${Date.now()}`,
        text: newText.trim(),
        weight: newWeight > 0 ? newWeight : 10,
      },
    ]);
    setNewText("");
    setNewWeight(15);
  };

  const handleConfirmAndContinue = async () => {
    if (requirements.length === 0) {
      setReqError("At least one requirement is required before proceeding to upload");
      return;
    }

    setReqError(null);
    setConfirming(true);

    try {
      const payload = requirements.map((r) => ({
        text: r.text,
        weight: r.weight,
      }));
      const res = await updateRequirements(activeJobId, payload);
      setConfirming(false);
      navigate(`/jobs/${res.job_id}/upload`);
    } catch (err) {
      setReqError(
        err.response?.data?.detail || "Failed to confirm requirements. Check that weights are positive numbers."
      );
      setConfirming(false);
    }
  };

  const totalWeight = requirements.reduce((sum, r) => sum + (r.weight || 0), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* Page Header */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
          <Sparkles size={24} color="#6366f1" />
          <h2 style={{ fontSize: "24px" }}>Skill Extraction Engine</h2>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
          Paste a Job Description to automatically extract and weight core skills and qualification criteria.
        </p>
      </div>

      {/* Extraction Form Card */}
      <div className="glass-card">
        <form onSubmit={handleExtract} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <label style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>
              Job Title
            </label>
            <button
              type="button"
              onClick={handleLoadSample}
              className="btn btn-secondary"
              style={{ padding: "4px 10px", fontSize: "12px", gap: "6px" }}
            >
              <Zap size={13} color="#a855f7" />
              <span>Load sample data</span>
            </button>

          </div>

          <input
            type="text"
            placeholder="e.g. Senior Backend Engineer (Python / Distributed Systems)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={loading || confirming}
            style={{
              padding: "12px 16px",
              borderRadius: "var(--radius-sm)",
              background: "rgba(255, 255, 255, 0.04)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
              fontSize: "15px",
              outline: "none",
              transition: "border-color 0.2s ease",
            }}
          />

          <div>
            <label style={{ display: "block", fontSize: "14px", fontWeight: 600, marginBottom: "8px" }}>
              Job Description / Requirements
            </label>
            <textarea
              rows={8}
              placeholder="Paste job description with bullet points or qualification lines..."
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              disabled={loading || confirming}
              style={{
                width: "100%",
                padding: "14px 16px",
                borderRadius: "var(--radius-sm)",
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                fontSize: "14px",
                fontFamily: "monospace",
                lineHeight: "1.6",
                outline: "none",
                resize: "vertical",
              }}
            />
          </div>

          {error && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                padding: "12px 16px",
                background: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "var(--radius-sm)",
                color: "#fca5a5",
                fontSize: "14px",
              }}
            >
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          )}

          <div>
            <button
              type="submit"
              disabled={loading || confirming}
              className="btn btn-primary"
              style={{ width: "100%", padding: "14px 20px", fontSize: "15px" }}
            >
              {loading ? (
                <span>Extracting Skills & Requirements...</span>
              ) : (
                <>
                  <Sparkles size={17} />
                  <span>Extract Skills & Build Requirements</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Requirement Tuning Section (Rendered on success) */}
      {requirements.length > 0 && (
        <div className="glass-card" style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Sliders size={20} color="#6366f1" />
                <h3 style={{ fontSize: "18px" }}>Extracted Skills & Tuning</h3>
                <span className="badge badge-success">{requirements.length} Skills</span>
              </div>
              <p style={{ color: "var(--text-muted)", fontSize: "13px", marginTop: "4px" }}>
                Review, edit, add, or re-weight criteria. Weights are automatically normalized to sum to 100% (10,000 bp) by the backend.
              </p>
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-end",
                padding: "8px 14px",
                background: "rgba(255, 255, 255, 0.03)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
              }}
            >
              <span style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-muted)", fontWeight: 600 }}>
                Raw Weight Sum
              </span>
              <span style={{ fontSize: "18px", fontWeight: 700, color: "var(--accent)" }}>
                {totalWeight}%
              </span>
            </div>
          </div>

          {/* Table */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "14px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
                  <th style={{ padding: "10px 12px", width: "40px" }}>#</th>
                  <th style={{ padding: "10px 12px" }}>Extracted Requirement / Skill</th>
                  <th style={{ padding: "10px 12px", width: "140px" }}>Weight (%)</th>
                  <th style={{ padding: "10px 12px", width: "50px", textAlign: "center" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {requirements.map((req, idx) => (
                  <tr
                    key={req.id || idx}
                    style={{
                      borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                      transition: "background 0.15s ease",
                    }}
                  >
                    <td style={{ padding: "12px", color: "var(--text-muted)", fontWeight: 600 }}>
                      {idx + 1}
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <input
                        type="text"
                        value={req.text}
                        onChange={(e) => handleUpdateReqText(idx, e.target.value)}
                        style={{
                          width: "100%",
                          padding: "8px 12px",
                          borderRadius: "var(--radius-sm)",
                          background: "rgba(255, 255, 255, 0.03)",
                          border: "1px solid var(--border)",
                          color: "var(--text-primary)",
                          fontSize: "14px",
                          outline: "none",
                        }}
                      />
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <input
                          type="number"
                          min="0"
                          max="1000"
                          value={req.weight}
                          onChange={(e) => handleUpdateReqWeight(idx, e.target.value)}
                          style={{
                            width: "75px",
                            padding: "8px 10px",
                            borderRadius: "var(--radius-sm)",
                            background: "rgba(255, 255, 255, 0.03)",
                            border: "1px solid var(--border)",
                            color: "var(--text-primary)",
                            fontSize: "14px",
                            outline: "none",
                            textAlign: "right",
                          }}
                        />
                        <span style={{ color: "var(--text-muted)" }}>%</span>
                      </div>
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "center" }}>
                      <button
                        type="button"
                        onClick={() => handleDeleteReq(idx)}
                        title="Delete requirement"
                        style={{
                          background: "transparent",
                          color: "var(--text-muted)",
                          padding: "6px",
                          borderRadius: "4px",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--danger)")}
                        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Add Requirement Inline Row */}
          <form
            onSubmit={handleAddRequirement}
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "center",
              padding: "12px 16px",
              background: "rgba(255, 255, 255, 0.02)",
              borderRadius: "var(--radius-sm)",
              border: "1px dashed var(--border)",
            }}
          >
            <input
              type="text"
              placeholder="+ Add missing requirement or skill criteria..."
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              style={{
                flex: 1,
                padding: "8px 12px",
                borderRadius: "var(--radius-sm)",
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                fontSize: "13px",
                outline: "none",
              }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <input
                type="number"
                min="1"
                max="1000"
                value={newWeight}
                onChange={(e) => setNewWeight(parseInt(e.target.value, 10) || 10)}
                style={{
                  width: "65px",
                  padding: "8px 8px",
                  borderRadius: "var(--radius-sm)",
                  background: "rgba(255, 255, 255, 0.04)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                  outline: "none",
                  textAlign: "right",
                }}
              />
              <span style={{ color: "var(--text-muted)", fontSize: "13px" }}>%</span>
            </div>
            <button
              type="submit"
              disabled={!newText.trim()}
              className="btn btn-secondary"
              style={{ padding: "8px 14px", fontSize: "13px" }}
            >
              <Plus size={14} />
              <span>Add</span>
            </button>
          </form>

          {reqError && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                padding: "12px 16px",
                background: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "var(--radius-sm)",
                color: "#fca5a5",
                fontSize: "14px",
              }}
            >
              <AlertCircle size={18} />
              <span>{reqError}</span>
            </div>
          )}

          {/* Action Footer */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              paddingTop: "16px",
              borderTop: "1px solid var(--border)",
            }}
          >
            <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>
              Weights are automatically renormalized to sum to 100% (10,000 basis points).
            </span>

            <button
              type="button"
              onClick={handleConfirmAndContinue}
              disabled={confirming || requirements.length === 0}
              className="btn btn-primary"
              style={{ padding: "12px 24px", fontSize: "15px" }}
            >
              {confirming ? (
                <span>Confirming...</span>
              ) : (
                <>
                  <span>Confirm & Continue to Upload</span>
                  <ArrowRight size={17} />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
