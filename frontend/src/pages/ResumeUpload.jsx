// frontend/src/pages/ResumeUpload.jsx — Screen 2: Resume Ingestion & Parse Validation
import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  AlertOctagon,
  Trash2,
  Play,
  ArrowRight,
  Sparkles,
  Layers,
  FileCheck,
  RefreshCw,
  FolderOpen,
} from "lucide-react";
import { getJob, uploadResumes, runPipeline, useSampleResumes } from "../api/client";


export default function ResumeUpload() {
  const navigate = useNavigate();
  const { jobId } = useParams();
  const fileInputRef = useRef(null);

  const [job, setJob] = useState(null);
  const [loadingJob, setLoadingJob] = useState(true);
  const [stagedFiles, setStagedFiles] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [runningPipeline, setRunningPipeline] = useState(false);
  const [parseResults, setParseResults] = useState(null);
  const [error, setError] = useState(null);

  // Load existing job details on mount
  useEffect(() => {
    if (!jobId) return;
    setLoadingJob(true);
    getJob(jobId)
      .then((data) => {
        setJob(data);
        if (data.parse_summary) {
          setParseResults(data.parse_summary);
        }
        setLoadingJob(false);
      })
      .catch((err) => {
        setError(err.response?.data?.detail || "Failed to load job details");
        setLoadingJob(false);
      });
  }, [jobId]);

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFiles = (incomingFiles) => {
    const validExts = [".pdf", ".docx"];
    const newFiles = [];
    const rejected = [];

    Array.from(incomingFiles).forEach((file) => {
      const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
      if (validExts.includes(ext)) {
        // Prevent duplicate filenames in staged list
        if (!stagedFiles.some((f) => f.name === file.name)) {
          newFiles.push(file);
        }
      } else {
        rejected.push(file.name);
      }
    });

    if (rejected.length > 0) {
      setError(`Unsupported file format rejected: ${rejected.join(", ")}. Supported formats: .pdf, .docx`);
    } else {
      setError(null);
    }

    if (newFiles.length > 0) {
      setStagedFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleRemoveStaged = (index) => {
    setStagedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // Quick helper to generate sample demo resumes directly in the browser for instant testing
  const handleLoadDemoResumes = () => {
    const sampleFiles = [
      new File(
        [
          "%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n4 0 obj << /Length 260 >> stream\nBT /F1 12 Tf 72 712 Td (Senior Backend Engineer with 8+ years experience in Python microservices, distributed cloud architecture, Docker, Kubernetes, and PostgreSQL systems. Led platform engineering and high-availability API deployment on AWS infrastructure.) Tj ET\nendstream\nendobj\n5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\nxref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000234 00000 n \n0000000300 00000 n \ntrailer << /Size 6 /Root 1 0 R >>\nstartxref\n370\n%%EOF\n",
        ],
        "resume_alex_chen_senior_backend.pdf",
        { type: "application/pdf" }
      ),
      new File(
        [
          "%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n4 0 obj << /Length 260 >> stream\nBT /F1 12 Tf 72 712 Td (Cloud Infrastructure Architect with 6+ years specializing in Kubernetes orchestration, Terraform automation, CI/CD pipelines, and Python backend tooling. Led migration of monolithic services to cloud-native microservices.) Tj ET\nendstream\nendobj\n5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\nxref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000234 00000 n \n0000000300 00000 n \ntrailer << /Size 6 /Root 1 0 R >>\nstartxref\n370\n%%EOF\n",
        ],
        "resume_maya_lin_cloud_architect.pdf",
        { type: "application/pdf" }
      ),
      new File(
        [
          "%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n4 0 obj << /Length 260 >> stream\nBT /F1 12 Tf 72 712 Td (Distributed Systems Specialist with 7+ years developing low-latency Python services, Kafka message streaming, and distributed consensus mechanisms. Expert in PostgreSQL and Redis caching layers.) Tj ET\nendstream\nendobj\n5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\nxref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000234 00000 n \n0000000300 00000 n \ntrailer << /Size 6 /Root 1 0 R >>\nstartxref\n370\n%%EOF\n",
        ],
        "resume_david_kim_distributed_systems.pdf",
        { type: "application/pdf" }
      ),
      // Scanned PDF proxy with no text layer to demonstrate PDD R3 honest failure handling
      new File(
        [
          "%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer << /Size 4 /Root 1 0 R >>\nstartxref\n200\n%%EOF\n",
        ],
        "scanned_document_no_text.pdf",
        { type: "application/pdf" }
      ),
    ];
    setStagedFiles((prev) => [...prev, ...sampleFiles]);
    setError(null);
  };

  const handleUseSampleResumes = async () => {
    setUploading(true);
    setError(null);
    try {
      const data = await useSampleResumes(jobId);
      setParseResults(data);
      setStagedFiles([]);
      setUploading(false);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load sample resumes from server");
      setUploading(false);
    }
  };

  const handleUpload = async () => {
    if (stagedFiles.length === 0) return;
    setUploading(true);
    setError(null);

    try {
      const data = await uploadResumes(jobId, stagedFiles);
      setParseResults(data);
      setStagedFiles([]);
      setUploading(false);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to upload and parse resumes");
      setUploading(false);
    }
  };

  const [selectedRanker, setSelectedRanker] = useState("compare_all");

  const handleRunScreening = async () => {
    if (!parseResults || parseResults.summary.ok === 0) return;
    setRunningPipeline(true);
    setError(null);

    try {
      await runPipeline(jobId, selectedRanker, 10);
      setRunningPipeline(false);
      navigate(`/jobs/${jobId}/dashboard`);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || "Pipeline run failed";
      setError(`Screening failed: ${detail}`);
      setRunningPipeline(false);
    }
  };

  const okCount = parseResults?.summary?.ok || 0;
  const noTextCount = parseResults?.summary?.no_text_layer || 0;
  const corruptCount = parseResults?.summary?.corrupt || 0;
  const unsupportedCount = parseResults?.summary?.unsupported_type || 0;
  const totalFiles = parseResults?.files?.length || 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
            <Layers size={24} color="#6366f1" />
            <h2 style={{ fontSize: "24px" }}>Resume Ingestion & Ingestion Status</h2>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>
            Upload candidate resumes (.pdf, .docx). Failures and missing text layers are transparently audited.
          </p>
          {job && (
            <div style={{ fontSize: "13px", color: "var(--accent)", marginTop: "6px", fontWeight: 600 }}>
              Job: {job.title} • {job.requirements?.length || 0} Criteria Defined
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
          <button
            type="button"
            onClick={handleUseSampleResumes}
            className="btn btn-primary"
            disabled={uploading || runningPipeline}
            style={{ gap: "6px", fontSize: "13px", padding: "8px 14px" }}
          >
            <Sparkles size={15} />
            <span>Use sample resumes</span>
          </button>
          <button
            type="button"
            onClick={handleLoadDemoResumes}
            className="btn btn-secondary"
            disabled={uploading || runningPipeline}
            style={{ gap: "6px", fontSize: "13px", padding: "8px 14px" }}
          >
            <FolderOpen size={15} color="#a855f7" />
            <span>Stage Local PDFs</span>
          </button>
        </div>
      </div>


      {/* Dropzone Card */}
      <div className="glass-card">
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current && fileInputRef.current.click()}
          style={{
            border: `2px dashed ${dragActive ? "var(--accent)" : "rgba(255, 255, 255, 0.15)"}`,
            borderRadius: "var(--radius-md)",
            padding: "40px 20px",
            textAlign: "center",
            cursor: "pointer",
            background: dragActive ? "rgba(99, 102, 241, 0.08)" : "rgba(255, 255, 255, 0.02)",
            transition: "all 0.2s ease",
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx"
            style={{ display: "none" }}
            onChange={(e) => handleFiles(e.target.files)}
          />

          <div
            style={{
              display: "inline-flex",
              padding: "16px",
              borderRadius: "50%",
              background: "rgba(99, 102, 241, 0.15)",
              color: "#818cf8",
              marginBottom: "16px",
            }}
          >
            <Upload size={32} />
          </div>

          <h3 style={{ fontSize: "17px", marginBottom: "6px" }}>
            Drag and drop resume files here, or click to browse
          </h3>
          <p style={{ color: "var(--text-muted)", fontSize: "13px" }}>
            Supports PDF and DOCX files. Character layers are verified per PDD R3.
          </p>
        </div>

        {error && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginTop: "16px",
              padding: "12px 16px",
              background: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "var(--radius-sm)",
              color: "#fca5a5",
              fontSize: "14px",
            }}
          >
            <XCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* Staged Files List (before upload) */}
        {stagedFiles.length > 0 && (
          <div style={{ marginTop: "24px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "12px",
              }}
            >
              <h4 style={{ fontSize: "15px", color: "var(--text-secondary)" }}>
                Staged Files ({stagedFiles.length})
              </h4>
              <button
                type="button"
                onClick={handleUpload}
                disabled={uploading}
                className="btn btn-primary"
                style={{ padding: "8px 18px", fontSize: "13px" }}
              >
                {uploading ? (
                  <span>Uploading & Ingesting...</span>
                ) : (
                  <>
                    <Upload size={14} />
                    <span>Upload {stagedFiles.length} Resumes</span>
                  </>
                )}
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {stagedFiles.map((file, idx) => (
                <div
                  key={`${file.name}-${idx}`}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 14px",
                    background: "rgba(255, 255, 255, 0.03)",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <FileText size={18} color="#94a3b8" />
                    <span style={{ fontSize: "14px", fontWeight: 500 }}>{file.name}</span>
                    <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                      ({formatFileSize(file.size)})
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleRemoveStaged(idx)}
                    disabled={uploading}
                    style={{ background: "transparent", color: "var(--text-muted)", padding: "4px" }}
                    title="Remove from upload queue"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Parse Outcome Results (Transparent Failure Reporting) */}
      {parseResults && (
        <div className="glass-card" style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* Summary Strip */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "16px",
              paddingBottom: "18px",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <FileCheck size={22} color="#10b981" />
                <h3 style={{ fontSize: "18px" }}>Ingestion Outcomes</h3>
                <span className="badge badge-success">
                  {okCount}/{totalFiles} Valid Text Layer
                </span>
              </div>
              <p style={{ color: "var(--text-muted)", fontSize: "13px", marginTop: "4px" }}>
                Every file is parsed against strict character thresholds. Corrupt and image-only files are honestly surfaced.
              </p>
            </div>

            {/* Counts Breakdown Chips */}
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <span className="badge badge-success">
                <CheckCircle2 size={12} style={{ marginRight: "4px" }} />
                {okCount} OK
              </span>
              {noTextCount > 0 && (
                <span className="badge badge-warning">
                  <AlertTriangle size={12} style={{ marginRight: "4px" }} />
                  {noTextCount} No Text Layer
                </span>
              )}
              {corruptCount > 0 && (
                <span className="badge badge-danger">
                  <XCircle size={12} style={{ marginRight: "4px" }} />
                  {corruptCount} Corrupt
                </span>
              )}
              {unsupportedCount > 0 && (
                <span className="badge badge-neutral">
                  <AlertOctagon size={12} style={{ marginRight: "4px" }} />
                  {unsupportedCount} Unsupported
                </span>
              )}
            </div>
          </div>

          {/* Per-File Status Table */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "14px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
                  <th style={{ padding: "10px 12px" }}>Filename</th>
                  <th style={{ padding: "10px 12px", width: "180px" }}>Status</th>
                  <th style={{ padding: "10px 12px", width: "130px" }}>Extracted Chars</th>
                  <th style={{ padding: "10px 12px" }}>Audit Note</th>
                </tr>
              </thead>
              <tbody>
                {parseResults.files.map((file, idx) => {
                  let statusBadge = null;
                  let note = "";

                  if (file.status === "ok") {
                    statusBadge = (
                      <span className="badge badge-success">
                        <CheckCircle2 size={13} style={{ marginRight: "4px" }} />
                        OK
                      </span>
                    );
                    note = "Clean text layer extracted";
                  } else if (file.status === "no_text_layer") {
                    statusBadge = (
                      <span className="badge badge-warning">
                        <AlertTriangle size={13} style={{ marginRight: "4px" }} />
                        No Text Layer
                      </span>
                    );
                    note = "Scanned / image-only PDF (<200 chars)";
                  } else if (file.status === "corrupt") {
                    statusBadge = (
                      <span className="badge badge-danger">
                        <XCircle size={13} style={{ marginRight: "4px" }} />
                        Corrupt
                      </span>
                    );
                    note = "Damaged header or unreadable PDF bytes";
                  } else {
                    statusBadge = (
                      <span className="badge badge-neutral">
                        <AlertOctagon size={13} style={{ marginRight: "4px" }} />
                        Unsupported
                      </span>
                    );
                    note = "Non-standard file format";
                  }

                  return (
                    <tr
                      key={`${file.filename}-${idx}`}
                      style={{
                        borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                        background: file.status !== "ok" ? "rgba(239, 68, 68, 0.03)" : "transparent",
                      }}
                    >
                      <td style={{ padding: "12px", fontWeight: 500 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <FileText size={16} color={file.status === "ok" ? "#818cf8" : "#f87171"} />
                          <span>{file.filename}</span>
                        </div>
                      </td>
                      <td style={{ padding: "12px" }}>{statusBadge}</td>
                      <td style={{ padding: "12px", fontFamily: "monospace", color: "var(--text-secondary)" }}>
                        {file.char_count != null ? `${file.char_count.toLocaleString()} chars` : "—"}
                      </td>
                      <td style={{ padding: "12px", color: "var(--text-muted)", fontSize: "13px" }}>
                        {note}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Ranking Method Selection */}
          <div style={{ marginTop: "24px", paddingTop: "20px", borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
              <Sparkles size={16} color="#6366f1" />
              <span>Select Screening & Ranking Methodology</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: "12px", marginBottom: "20px" }}>
              <div
                onClick={() => setSelectedRanker("compare_all")}
                style={{
                  padding: "14px 16px",
                  borderRadius: "var(--radius-md)",
                  border: selectedRanker === "compare_all" ? "2px solid #6366f1" : "1px solid var(--border)",
                  background: selectedRanker === "compare_all" ? "rgba(99, 102, 241, 0.12)" : "rgba(255, 255, 255, 0.02)",
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 700, fontSize: "14px", color: "var(--text-primary)" }}>📊 Compare All 3 Methods</span>
                  <span className="badge badge-success" style={{ fontSize: "10px", padding: "2px 6px" }}>Recommended</span>
                </div>
                <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "6px", lineHeight: "1.4" }}>
                  Executes Lexical, Vector Embedding, & Groq LLM simultaneously for side-by-side consensus analysis.
                </p>
              </div>

              <div
                onClick={() => setSelectedRanker("r2_llm")}
                style={{
                  padding: "14px 16px",
                  borderRadius: "var(--radius-md)",
                  border: selectedRanker === "r2_llm" ? "2px solid #a855f7" : "1px solid var(--border)",
                  background: selectedRanker === "r2_llm" ? "rgba(168, 85, 247, 0.12)" : "rgba(255, 255, 255, 0.02)",
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                <div style={{ fontWeight: 700, fontSize: "14px", color: "var(--text-primary)" }}>🤖 R2 LLM Judge (Groq)</div>
                <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "6px", lineHeight: "1.4" }}>
                  Zero-cost Llama 3.3 deep reasoning with verbatim text evidence quotes (Charter D8).
                </p>
              </div>

              <div
                onClick={() => setSelectedRanker("r1_embedding")}
                style={{
                  padding: "14px 16px",
                  borderRadius: "var(--radius-md)",
                  border: selectedRanker === "r1_embedding" ? "2px solid #0ea5e9" : "1px solid var(--border)",
                  background: selectedRanker === "r1_embedding" ? "rgba(14, 165, 233, 0.12)" : "rgba(255, 255, 255, 0.02)",
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                <div style={{ fontWeight: 700, fontSize: "14px", color: "var(--text-primary)" }}>🧠 R1 Semantic Embedding</div>
                <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "6px", lineHeight: "1.4" }}>
                  Dense vector space cosine similarity beyond exact keyword matching.
                </p>
              </div>

              <div
                onClick={() => setSelectedRanker("r0_lexical")}
                style={{
                  padding: "14px 16px",
                  borderRadius: "var(--radius-md)",
                  border: selectedRanker === "r0_lexical" ? "2px solid #10b981" : "1px solid var(--border)",
                  background: selectedRanker === "r0_lexical" ? "rgba(16, 185, 129, 0.12)" : "rgba(255, 255, 255, 0.02)",
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                <div style={{ fontWeight: 700, fontSize: "14px", color: "var(--text-primary)" }}>⚡ R0 Lexical Matcher</div>
                <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "6px", lineHeight: "1.4" }}>
                  IDF-weighted token matching with deterministic suffix stemming.
                </p>
              </div>
            </div>

            {/* Screening Run Action Footer */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "12px",
              }}
            >
              <div>
                <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                  Selected Engine: <strong>{selectedRanker === "compare_all" ? "Multi-Method Comparison (All 3)" : selectedRanker.toUpperCase()}</strong> • Top K: <strong>10</strong>
                </span>
              </div>

              <button
                type="button"
                onClick={handleRunScreening}
                disabled={runningPipeline || okCount === 0}
                className="btn btn-primary"
                style={{ padding: "12px 24px", fontSize: "15px", gap: "10px" }}
              >
                {runningPipeline ? (
                  <>
                    <RefreshCw size={17} className="spin-animation" style={{ animation: "spin 1s linear infinite" }} />
                    <span>Scoring candidates via {selectedRanker}...</span>
                  </>
                ) : (
                  <>
                    <Play size={16} fill="currentColor" />
                    <span>Execute Screening ({okCount} Candidates)</span>
                    <ArrowRight size={17} />
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
