// frontend/src/api/client.js — Shortlist API client
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL !== undefined
  ? import.meta.env.VITE_API_BASE_URL
  : (import.meta.env.PROD ? "" : "http://127.0.0.1:8000");

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

export const createJob = async (title, jdText) => {
  const response = await api.post("/api/jobs", { title, jd_text: jdText });
  return response.data;
};

export const updateRequirements = async (jobId, requirements) => {
  const response = await api.put(`/api/jobs/${jobId}/requirements`, {
    requirements,
  });
  return response.data;
};

export const uploadResumes = async (jobId, files) => {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const response = await api.post(`/api/jobs/${jobId}/resumes`, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
};

export const runPipeline = async (jobId, ranker = "r0_lexical", k = 10, asOf = null) => {
  const payload = { ranker, k };
  if (asOf) payload.as_of = asOf;
  const response = await api.post(`/api/jobs/${jobId}/run`, payload);
  return response.data;
};

export const getJob = async (jobId) => {
  const response = await api.get(`/api/jobs/${jobId}`);
  return response.data;
};

export const getRanking = async (jobId, ranker = null) => {
  const params = ranker ? { ranker } : {};
  const response = await api.get(`/api/jobs/${jobId}/ranking`, { params });
  return response.data;
};

export const postVerdict = async (jobId, candidateId, verdict) => {
  const response = await api.post(`/api/jobs/${jobId}/verdict`, {
    candidate_id: candidateId,
    verdict,
  });
  return response.data;
};

export const listJobs = async () => {
  const response = await api.get("/api/jobs");
  return response.data;
};

export const getSampleResumes = async () => {
  const response = await api.get("/api/sample-resumes");
  return response.data;
};

export const useSampleResumes = async (jobId) => {
  const response = await api.post(`/api/jobs/${jobId}/resumes/sample`);
  return response.data;
};

export const checkHealth = async () => {
  const response = await api.get("/health");
  return response.data;
};

export default api;

