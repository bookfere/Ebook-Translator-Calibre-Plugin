"use client";

import { useEffect, useState } from "react";
import { useRequireAuth } from "../auth";

type Job = {
  job_id: string;
  status: string;
  progress: number;
  engine?: string;
  input_key: string;
  output_key?: string;
  created_at: string;
  finished_at?: string;
  error_message?: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function isUnauthorizedStatus(status: number): boolean {
  return status === 401 || status === 403;
}

export default function JobsPage() {
  const { status, accessToken, signOut } = useRequireAuth({ redirectTo: "/login" });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [message, setMessage] = useState("Loading...");

  useEffect(() => {
    if (status !== "authenticated" || !accessToken) {
      return;
    }

    async function loadJobs() {
      setMessage("Loading...");

      const response = await fetch(`${API_BASE_URL}/v1/jobs?limit=20&offset=0`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (isUnauthorizedStatus(response.status)) {
        await signOut();
        return;
      }

      if (!response.ok) {
        setMessage(`Failed to load jobs: ${response.status}`);
        return;
      }

      const payload = await response.json();
      setJobs(payload.items || []);
      setMessage("");
    }

    loadJobs().catch((error) => setMessage(String(error)));
  }, [accessToken, signOut, status]);

  if (status === "loading") {
    return (
      <main>
        <div className="card">
          <h1>Jobs</h1>
          <p className="hint">Checking your session...</p>
        </div>
      </main>
    );
  }

  if (status === "unauthenticated") {
    return (
      <main>
        <div className="card">
          <h1>Jobs</h1>
          <p className="hint">Redirecting to login...</p>
        </div>
      </main>
    );
  }

  return (
    <main>
      <div className="card">
        <h1>Jobs</h1>
        <p style={{ marginTop: 0 }}>
          Create a new translation job from <a href="/new-job">/new-job</a>.
        </p>
        {message && <p>{message}</p>}
        {!message && (
          <table className="table">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Created</th>
                <th>Finished</th>
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.job_id}>
                  <td>
                    <a href={`/jobs/${job.job_id}`}>{job.job_id}</a>
                  </td>
                  <td>{job.status}</td>
                  <td>{job.progress}%</td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                  <td>{job.finished_at ? new Date(job.finished_at).toLocaleString() : "-"}</td>
                  <td>
                    <a href={`/jobs/${job.job_id}`}>Open</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
