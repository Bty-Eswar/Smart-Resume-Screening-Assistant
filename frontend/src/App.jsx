import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import JobList from "./pages/JobList";
import JobSetup from "./pages/JobSetup";
import ResumeUpload from "./pages/ResumeUpload";
import Dashboard from "./pages/Dashboard";

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<JobList />} />
          <Route path="/jobs/new" element={<JobSetup />} />
          <Route path="/jobs/:jobId/requirements" element={<JobSetup />} />
          <Route path="/jobs/:jobId/upload" element={<ResumeUpload />} />
          <Route path="/jobs/:jobId/dashboard" element={<Dashboard />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

