// frontend/src/pages/Dashboard.jsx — Screen 3: Deterministic Screening Dashboard & Multi-Ranker Comparison
import React, { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import {
  Award,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  FileText,
  Calendar,
  Layers,
  Cpu,
  Hash,
  ShieldCheck,
  Check,
  X,
  ExternalLink,
  Sparkles,
  Info,
  RefreshCw,
  BarChart3,
  TrendingUp,
  BrainCircuit,
  Binary,
} from "lucide-react";
import { getJob, getRanking, postVerdict, runPipeline } from "../api/client";

export default function Dashboard() {
  const { jobId } = useParams();

  const [job, setJob] = useState(null);
  const [ranking, setRanking] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedCandidates, setExpandedCandidates] = useState(new Set());
  const [updatingCandidate, setUpdatingCandidate] = useState({});
  const [activeTab, setActiveTab] = useState("compare_all");
  const [switchingTab, setSwitchingTab] = useState(false);

  const loadData = async (preferredRanker = null) => {
    if (!jobId) return;
    try {
      setLoading(true);
      const [jobData, rankingData] = await Promise.all([
        getJob(jobId),
        getRanking(jobId, preferredRanker),
      ]);
      setJob(jobData);
      setRanking(rankingData);
      if (!preferredRanker && rankingData.active_ranker) {
        setActiveTab(rankingData.active_ranker === "compare_all" ? "compare_all" : rankingData.active_ranker);
      }
      setLoading(false);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load screening results");
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [jobId]);

  const handleTabChange = async (tabName) => {
    setActiveTab(tabName);
    if (tabName === "compare_all") {
      return;
    }
    // Check if this ranker exists or if we should fetch its ranking
    try {
      setSwitchingTab(true);
      const data = await getRanking(jobId, tabName);
      setRanking(data);
      setSwitchingTab(false);
    } catch (err) {
      setSwitchingTab(false);
    }
  };

  const handleTriggerRanker = async (rankerName) => {
    setSwitchingTab(true);
    try {
      const data = await runPipeline(jobId, rankerName, 10);
      setRanking(data);
      setActiveTab(rankerName);
      setSwitchingTab(false);
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to run ${rankerName}`);
      setSwitchingTab(false);
    }
  };

  const toggleEvidence = (candidateId) => {
    setExpandedCandidates((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) {
        next.delete(candidateId);
      } else {
        next.add(candidateId);
      }
      return next;
    });
  };

  const handleVerdictChange = async (candidateId, newVerdict) => {
    if (!ranking) return;

    // Snapshot for optimistic rollback
    const previousRanking = { ...ranking };

    const updateEntries = (entries) =>
      entries.map((entry) =>
        entry.candidate_id === candidateId ? { ...entry, verdict: newVerdict } : entry
      );

    setRanking((prev) => ({
      ...prev,
      ranked: updateEntries(prev.ranked || []),
      abstain_band: updateEntries(prev.abstain_band || []),
      comparison: (prev.comparison || []).map((row) =>
        row.candidate_id === candidateId
          ? {
              ...row,
              r0: row.r0 ? { ...row.r0, verdict: newVerdict } : null,
              r1: row.r1 ? { ...row.r1, verdict: newVerdict } : null,
              r2: row.r2 ? { ...row.r2, verdict: newVerdict } : null,
            }
          : row
      ),
    }));

    setUpdatingCandidate((prev) => ({ ...prev, [candidateId]: true }));

    try {
      await postVerdict(jobId, candidateId, newVerdict);
      setUpdatingCandidate((prev) => ({ ...prev, [candidateId]: false }));
    } catch (err) {
      setRanking(previousRanking);
      setUpdatingCandidate((prev) => ({ ...prev, [candidateId]: false }));
      setError(`Failed to update verdict for candidate ${candidateId}`);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "80px 20px" }}>
        <RefreshCw size={36} className="spin-animation" style={{ color: "#6366f1", margin: "0 auto 16px" }} />
        <h3 style={{ fontSize: "20px", marginBottom: "8px" }}>Loading Deterministic Screening Results...</h3>
        <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
          Retrieving IDF tables, dense vector projections, and verifiable evidence spans...
        </p>
      </div>
    );
  }

  if (error && !ranking) {
    return (
      <div className="glass-card" style={{ padding: "40px", textAlign: "center", maxWidth: "600px", margin: "40px auto" }}>
        <AlertTriangle size={48} color="#ef4444" style={{ margin: "0 auto 16px" }} />
        <h3 style={{ fontSize: "22px", color: "#f87171", marginBottom: "8px" }}>Screening Not Found</h3>
        <p style={{ color: "var(--text-secondary)", marginBottom: "24px" }}>
          {error.includes("not found") ? "This job has not been created or screened yet on this server." : error}
        </p>
        <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
          <Link to="/" className="btn btn-secondary">
            Browse Jobs
          </Link>
          <Link to="/jobs/new" className="btn btn-primary">
            + Create New Job
          </Link>
        </div>
      </div>
    );
  }

  const totalReqCount = job?.requirements?.length || 0;
  const rankedList = ranking?.ranked || [];
  const abstainList = ranking?.abstain_band || [];
  const unparsedList = ranking?.unparsed || [];
  const comparisonList = ranking?.comparison || [];

  const reqMap = (job?.requirements || []).reduce((acc, r) => {
    acc[r.id] = r.text;
    return acc;
  }, {});

  const renderCandidateCard = (candidate, isAbstain = false) => {
    const isExpanded = expandedCandidates.has(candidate.candidate_id);
    const scorePct = (candidate.score_bp / 100).toFixed(1);
    const isUpdating = updatingCandidate[candidate.candidate_id];

    return (
      <div
        key={candidate.candidate_id}
        className="glass-card"
        style={{
          padding: "20px 24px",
          background: isAbstain ? "rgba(245, 158, 11, 0.04)" : "var(--bg-card)",
          border: isAbstain
            ? "1px solid rgba(245, 158, 11, 0.25)"
            : "1px solid var(--border)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "14px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "10px",
                background: isAbstain
                  ? "rgba(245, 158, 11, 0.2)"
                  : candidate.rank === 1
                  ? "var(--accent-gradient)"
                  : "rgba(255, 255, 255, 0.06)",
                color: isAbstain ? "#fbbf24" : "white",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 800,
                fontSize: "15px",
                fontFamily: "Outfit, sans-serif",
              }}
            >
              {isAbstain ? "TIED" : `#${candidate.rank}`}
            </div>

            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span
                  style={{
                    fontFamily: "monospace",
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                  }}
                >
                  {candidate.candidate_id}
                </span>

                <span
                  className={`badge ${
                    candidate.verdict === "accept"
                      ? "badge-success"
                      : candidate.verdict === "reject"
                      ? "badge-danger"
                      : "badge-neutral"
                  }`}
                >
                  {candidate.verdict === "accept" && <Check size={12} style={{ marginRight: "4px" }} />}
                  {candidate.verdict === "reject" && <X size={12} style={{ marginRight: "4px" }} />}
                  {candidate.verdict.toUpperCase()}
                </span>
              </div>

              <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "4px" }}>
                Criteria Met: <strong>{candidate.met_count}</strong> of {totalReqCount} (High-Weight Met: {candidate.high_weight_met_count || 0})
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "18px", flexWrap: "wrap" }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "24px", fontWeight: 800, fontFamily: "Outfit", color: "var(--text-primary)" }}>
                {scorePct}%
              </div>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                Match Score
              </div>
            </div>

            <div style={{ display: "flex", gap: "8px" }}>
              <button
                type="button"
                onClick={() => handleVerdictChange(candidate.candidate_id, "accept")}
                disabled={isUpdating}
                className="btn"
                style={{
                  padding: "6px 12px",
                  fontSize: "12px",
                  background: candidate.verdict === "accept" ? "var(--success)" : "rgba(16, 185, 129, 0.15)",
                  color: candidate.verdict === "accept" ? "#064e3b" : "#34d399",
                  border: "1px solid rgba(16, 185, 129, 0.4)",
                  fontWeight: 600,
                }}
              >
                <Check size={14} />
                <span>Accept</span>
              </button>

              <button
                type="button"
                onClick={() => handleVerdictChange(candidate.candidate_id, "reject")}
                disabled={isUpdating}
                className="btn"
                style={{
                  padding: "6px 12px",
                  fontSize: "12px",
                  background: candidate.verdict === "reject" ? "var(--danger)" : "rgba(239, 68, 68, 0.15)",
                  color: candidate.verdict === "reject" ? "#7f1d1d" : "#f87171",
                  border: "1px solid rgba(239, 68, 68, 0.4)",
                  fontWeight: 600,
                }}
              >
                <X size={14} />
                <span>Reject</span>
              </button>
            </div>

            <button
              type="button"
              onClick={() => toggleEvidence(candidate.candidate_id)}
              className="btn btn-secondary"
              style={{ padding: "6px 12px", fontSize: "12px", gap: "6px" }}
            >
              <span>Evidence ({candidate.judgements?.length || 0})</span>
              {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>
        </div>

        {isExpanded && (
          <div
            style={{
              marginTop: "18px",
              paddingTop: "18px",
              borderTop: "1px solid var(--border)",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
              <ShieldCheck size={16} color="#6366f1" />
              <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)" }}>
                Auditable Verification Evidence (Charter D8 Verbatim Invariant)
              </span>
            </div>

            {candidate.judgements?.map((j, jIdx) => {
              const reqText = reqMap[j.requirement_id] || j.requirement_id;
              const confPct = (j.confidence_bp / 100).toFixed(1);

              return (
                <div
                  key={`${j.requirement_id}-${jIdx}`}
                  style={{
                    padding: "12px 14px",
                    background: "rgba(255, 255, 255, 0.02)",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      {j.met ? (
                        <CheckCircle2 size={16} color="#10b981" />
                      ) : (
                        <XCircle size={16} color="#64748b" />
                      )}
                      <span style={{ fontWeight: 600, fontSize: "14px", color: "var(--text-primary)" }}>
                        {reqText}
                      </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span className={`badge ${j.met ? "badge-success" : "badge-neutral"}`}>
                        {j.met ? "CRITERIA MET" : "NOT MET"}
                      </span>
                      <span style={{ fontSize: "12px", color: "var(--text-muted)", fontFamily: "monospace" }}>
                        Conf: {confPct}%
                      </span>
                    </div>
                  </div>

                  {j.evidence ? (
                    <div
                      style={{
                        marginTop: "10px",
                        padding: "10px 12px",
                        background: "rgba(99, 102, 241, 0.08)",
                        borderRadius: "var(--radius-sm)",
                        borderLeft: "3px solid #6366f1",
                      }}
                    >
                      <div style={{ fontSize: "11px", color: "#818cf8", fontWeight: 600, marginBottom: "4px" }}>
                        VERBATIM RESUME EVIDENCE (Chars {j.evidence.start}–{j.evidence.end}):
                      </div>
                      <div style={{ fontSize: "13px", color: "var(--text-primary)", fontStyle: "italic", lineHeight: "1.4" }}>
                        "{j.evidence.text}"
                      </div>
                    </div>
                  ) : (
                    <div style={{ marginTop: "6px", fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic" }}>
                      {j.met
                        ? "Evaluated and satisfied by candidate resume profile"
                        : "No corresponding requirement verification found in resume text"}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* Header Info Card */}
      <div className="glass-card" style={{ padding: "24px 28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
              <Award size={26} color="#6366f1" />
              <h2 style={{ fontSize: "24px" }}>{job?.title || "Screening Evaluation Dashboard"}</h2>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
              Deterministic, Evidence-Backed Candidate Recommendation Engine • Multi-Method Ranking Analysis
            </p>
          </div>

          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
            <span className="badge badge-neutral" style={{ padding: "6px 12px", gap: "6px" }}>
              <Cpu size={13} color="#6366f1" />
              <span>Active Engine: <strong>{activeTab.toUpperCase()}</strong></span>
            </span>
            <span className="badge badge-neutral" style={{ padding: "6px 12px", gap: "6px" }}>
              <Calendar size={13} color="#a855f7" />
              <span>As Of: <strong>{ranking?.as_of}</strong></span>
            </span>
            <button
              onClick={() => handleTriggerRanker("compare_all")}
              disabled={switchingTab}
              className="btn btn-secondary"
              style={{ fontSize: "12px", padding: "6px 12px", gap: "6px" }}
            >
              <RefreshCw size={13} className={switchingTab ? "spin-animation" : ""} />
              <span>Re-run All 3</span>
            </button>
          </div>
        </div>

        {/* Methodology Selection Tabs */}
        <div
          style={{
            display: "flex",
            gap: "8px",
            marginTop: "24px",
            paddingTop: "20px",
            borderTop: "1px solid var(--border)",
            overflowX: "auto",
            paddingBottom: "4px",
          }}
        >
          <button
            type="button"
            onClick={() => handleTabChange("compare_all")}
            className="btn"
            style={{
              padding: "8px 16px",
              fontSize: "13px",
              fontWeight: 600,
              gap: "8px",
              background: activeTab === "compare_all" ? "var(--accent-gradient)" : "rgba(255, 255, 255, 0.04)",
              color: activeTab === "compare_all" ? "white" : "var(--text-secondary)",
              border: activeTab === "compare_all" ? "none" : "1px solid var(--border)",
            }}
          >
            <BarChart3 size={16} />
            <span>📊 All-3 Comparison Matrix</span>
          </button>

          <button
            type="button"
            onClick={() => handleTabChange("r2_llm")}
            className="btn"
            style={{
              padding: "8px 16px",
              fontSize: "13px",
              fontWeight: 600,
              gap: "8px",
              background: activeTab === "r2_llm" ? "linear-gradient(135deg, #a855f7, #6366f1)" : "rgba(255, 255, 255, 0.04)",
              color: activeTab === "r2_llm" ? "white" : "var(--text-secondary)",
              border: activeTab === "r2_llm" ? "none" : "1px solid var(--border)",
            }}
          >
            <BrainCircuit size={16} />
            <span>🤖 R2 LLM (Groq Llama 3.3)</span>
          </button>

          <button
            type="button"
            onClick={() => handleTabChange("r1_embedding")}
            className="btn"
            style={{
              padding: "8px 16px",
              fontSize: "13px",
              fontWeight: 600,
              gap: "8px",
              background: activeTab === "r1_embedding" ? "linear-gradient(135deg, #0ea5e9, #6366f1)" : "rgba(255, 255, 255, 0.04)",
              color: activeTab === "r1_embedding" ? "white" : "var(--text-secondary)",
              border: activeTab === "r1_embedding" ? "none" : "1px solid var(--border)",
            }}
          >
            <TrendingUp size={16} />
            <span>🧠 R1 Semantic Embedding</span>
          </button>

          <button
            type="button"
            onClick={() => handleTabChange("r0_lexical")}
            className="btn"
            style={{
              padding: "8px 16px",
              fontSize: "13px",
              fontWeight: 600,
              gap: "8px",
              background: activeTab === "r0_lexical" ? "linear-gradient(135deg, #10b981, #059669)" : "rgba(255, 255, 255, 0.04)",
              color: activeTab === "r0_lexical" ? "white" : "var(--text-secondary)",
              border: activeTab === "r0_lexical" ? "none" : "1px solid var(--border)",
            }}
          >
            <Binary size={16} />
            <span>⚡ R0 Lexical Matcher</span>
          </button>
        </div>
      </div>

      {/* VIEW 1: COMPARISON MATRIX */}
      {activeTab === "compare_all" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <div className="glass-card" style={{ padding: "24px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
              <div>
                <h3 style={{ fontSize: "18px", display: "flex", alignItems: "center", gap: "8px" }}>
                  <Sparkles size={20} color="#6366f1" />
                  <span>Tri-Model Consensus & Comparison Matrix</span>
                </h3>
                <p style={{ color: "var(--text-muted)", fontSize: "13px", marginTop: "4px" }}>
                  Side-by-side evaluation of every candidate across R0 Lexical (TF-IDF), R1 Semantic Embedding (Vector Cosine), and R2 LLM (Groq Llama 3.3).
                </p>
              </div>

              <div style={{ display: "flex", gap: "8px" }}>
                <span className="badge badge-success" style={{ fontSize: "11px" }}>Unbiased Consensus</span>
                <span className="badge badge-info" style={{ fontSize: "11px" }}>Verifiable Proof Spans</span>
              </div>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)", fontSize: "12px", textTransform: "uppercase" }}>
                    <th style={{ padding: "12px 14px" }}>Candidate / Resume</th>
                    <th style={{ padding: "12px 14px" }}>Consensus Verdict</th>
                    <th style={{ padding: "12px 14px" }}>Avg Match</th>
                    <th style={{ padding: "12px 14px" }}>⚡ R0 Lexical</th>
                    <th style={{ padding: "12px 14px" }}>🧠 R1 Embedding</th>
                    <th style={{ padding: "12px 14px" }}>🤖 R2 Groq LLM</th>
                    <th style={{ padding: "12px 14px", textAlign: "right" }}>Recruiter Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisonList.map((row) => {
                    const r0Score = row.r0?.score_bp != null ? (row.r0.score_bp / 100).toFixed(1) + "%" : "—";
                    const r1Score = row.r1?.score_bp != null ? (row.r1.score_bp / 100).toFixed(1) + "%" : "—";
                    const r2Score = row.r2?.score_bp != null ? (row.r2.score_bp / 100).toFixed(1) + "%" : "—";
                    const avgScore = (row.avg_score_bp / 100).toFixed(1);
                    const verdict = row.r2?.verdict || row.r0?.verdict || "unreviewed";

                    return (
                      <tr
                        key={row.candidate_id}
                        style={{
                          borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
                          transition: "background 0.2s ease",
                        }}
                      >
                        <td style={{ padding: "14px" }}>
                          <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{row.filename}</div>
                          <div style={{ fontFamily: "monospace", fontSize: "12px", color: "var(--text-muted)" }}>
                            {row.candidate_id.substring(0, 16)}...
                          </div>
                        </td>

                        <td style={{ padding: "14px" }}>
                          <span
                            className={`badge ${
                              row.consensus.includes("Strong")
                                ? "badge-success"
                                : row.consensus.includes("Advantage")
                                ? "badge-info"
                                : "badge-neutral"
                            }`}
                            style={{ fontSize: "12px" }}
                          >
                            {row.consensus}
                          </span>
                        </td>

                        <td style={{ padding: "14px" }}>
                          <div style={{ fontWeight: 800, fontSize: "16px", color: "var(--text-primary)" }}>
                            {avgScore}%
                          </div>
                          <div
                            style={{
                              width: "70px",
                              height: "4px",
                              background: "rgba(255,255,255,0.1)",
                              borderRadius: "2px",
                              marginTop: "4px",
                              overflow: "hidden",
                            }}
                          >
                            <div
                              style={{
                                width: `${avgScore}%`,
                                height: "100%",
                                background: "var(--accent-gradient)",
                              }}
                            />
                          </div>
                        </td>

                        <td style={{ padding: "14px" }}>
                          <div style={{ fontWeight: 600 }}>{r0Score}</div>
                          <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                            {row.r0?.rank ? `Rank #${row.r0.rank}` : row.r0?.abstain ? "Abstain" : "—"}
                          </div>
                        </td>

                        <td style={{ padding: "14px" }}>
                          <div style={{ fontWeight: 600 }}>{r1Score}</div>
                          <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                            {row.r1?.rank ? `Rank #${row.r1.rank}` : row.r1?.abstain ? "Abstain" : "—"}
                          </div>
                        </td>

                        <td style={{ padding: "14px" }}>
                          <div style={{ fontWeight: 600, color: "#a855f7" }}>{r2Score}</div>
                          <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                            {row.r2?.rank ? `Rank #${row.r2.rank}` : row.r2?.abstain ? "Abstain" : "—"}
                          </div>
                        </td>

                        <td style={{ padding: "14px", textAlign: "right" }}>
                          <div style={{ display: "inline-flex", gap: "6px" }}>
                            <button
                              type="button"
                              onClick={() => handleVerdictChange(row.candidate_id, "accept")}
                              className="btn"
                              style={{
                                padding: "4px 10px",
                                fontSize: "11px",
                                background: verdict === "accept" ? "var(--success)" : "rgba(16, 185, 129, 0.12)",
                                color: verdict === "accept" ? "#064e3b" : "#34d399",
                                border: "1px solid rgba(16, 185, 129, 0.3)",
                              }}
                            >
                              <Check size={12} />
                              <span>Accept</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => handleVerdictChange(row.candidate_id, "reject")}
                              className="btn"
                              style={{
                                padding: "4px 10px",
                                fontSize: "11px",
                                background: verdict === "reject" ? "var(--danger)" : "rgba(239, 68, 68, 0.12)",
                                color: verdict === "reject" ? "#7f1d1d" : "#f87171",
                                border: "1px solid rgba(239, 68, 68, 0.3)",
                              }}
                            >
                              <X size={12} />
                              <span>Reject</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        /* VIEW 2: INDIVIDUAL METHOD RANKED CARDS & EVIDENCE */
        <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
          {/* Metrics Strip */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: "16px",
            }}
          >
            <div className="glass-card" style={{ padding: "16px 20px" }}>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                Ranked Candidates
              </div>
              <div style={{ fontSize: "26px", fontWeight: 800, fontFamily: "Outfit", color: "var(--text-primary)", marginTop: "4px" }}>
                {rankedList.length}
              </div>
            </div>

            <div className="glass-card" style={{ padding: "16px 20px", background: "rgba(245, 158, 11, 0.04)", border: "1px solid rgba(245, 158, 11, 0.25)" }}>
              <div style={{ fontSize: "12px", color: "#fbbf24", textTransform: "uppercase", fontWeight: 600 }}>
                Abstain Band (Tied)
              </div>
              <div id="abstain-count" style={{ fontSize: "26px", fontWeight: 800, fontFamily: "Outfit", color: "#fbbf24", marginTop: "4px" }}>
                Band Size: {abstainList.length}
              </div>
            </div>

            <div className="glass-card" style={{ padding: "16px 20px" }}>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                Unparsed Resumes
              </div>
              <div style={{ fontSize: "26px", fontWeight: 800, fontFamily: "Outfit", color: "var(--text-secondary)", marginTop: "4px" }}>
                {unparsedList.length}
              </div>
            </div>
          </div>

          {/* Visually Distinct Abstain Band Section (Determinism Charter D5) */}
          <div
            className="glass-card"
            style={{
              border: "1px solid rgba(245, 158, 11, 0.3)",
              background: "rgba(245, 158, 11, 0.03)",
              boxShadow: "0 0 25px rgba(245, 158, 11, 0.08)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <AlertTriangle size={22} color="#f59e0b" />
                <h3 style={{ fontSize: "18px", color: "#fef3c7" }}>
                  Abstain Band ({abstainList.length} Candidates)
                </h3>
                <span className="badge badge-warning">Charter D5</span>
              </div>
              <span style={{ fontSize: "12px", color: "#fcd34d", fontWeight: 600 }}>
                Manual Review Mandated
              </span>
            </div>

            <p style={{ color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.5" }}>
              Candidates tied across all tie-break keys are placed in the Abstain Band. Shortlist strictly refuses to invent random tie-breakers.
            </p>

            {abstainList.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "16px" }}>
                {abstainList.map((cand) => renderCandidateCard(cand, true))}
              </div>
            ) : (
              <div
                style={{
                  marginTop: "16px",
                  padding: "14px 18px",
                  background: "rgba(245, 158, 11, 0.06)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  color: "#fbbf24",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                <CheckCircle2 size={16} />
                <span>Zero tied candidates straddling rank boundary K={ranking?.k || 10}. All candidate rankings are strictly resolved.</span>
              </div>
            )}
          </div>

          {/* Ranked Candidates */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <div>
                <h3 style={{ fontSize: "18px" }}>Ranked Candidate Recommendations ({rankedList.length})</h3>
                <p style={{ color: "var(--text-muted)", fontSize: "13px", marginTop: "2px" }}>
                  Evaluated using {activeTab.toUpperCase()} with auditable verification evidence.
                </p>
              </div>
            </div>

            {rankedList.length === 0 ? (
              <div className="glass-card" style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                No candidates ranked yet for this method.
                <div style={{ marginTop: "14px" }}>
                  <button onClick={() => handleTriggerRanker(activeTab)} className="btn btn-primary">
                    Run {activeTab.toUpperCase()} Now
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                {rankedList.map((cand) => renderCandidateCard(cand, false))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
