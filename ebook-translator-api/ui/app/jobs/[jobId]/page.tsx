"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRequireAuth } from "../../auth";

type SqlValue = string | number | null | Uint8Array;

type QueryExecResult = {
  columns: string[];
  values: SqlValue[][];
};

type Database = {
  exec(sql: string, params?: SqlValue[]): QueryExecResult[];
  run(sql: string, params?: SqlValue[]): void;
  export(): Uint8Array;
  close(): void;
};

type SqlJsStatic = {
  Database: new (data?: Uint8Array | ArrayLike<number>) => Database;
};

type SqlJsConfig = {
  locateFile?: (file: string) => string;
};

type InitSqlJs = (config?: SqlJsConfig) => Promise<SqlJsStatic>;

type SqlJsWindow = Window & typeof globalThis & {
  initSqlJs?: InitSqlJs;
};

type Job = {
  job_id: string;
  status: string;
  progress: number;
  engine?: string;
  input_key: string;
  output_key?: string;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  expires_at: string;
  error_message?: string;
};

type ArtifactUrlResponse = {
  job_id: string;
  url: string;
  expires_in_seconds: number;
};

type ReviewStatus = "all" | "translated" | "untranslated" | "error";

type ReviewRow = {
  id: string;
  index: number;
  status: Exclude<ReviewStatus, "all">;
  originalText: string;
  translatedText: string;
  errorMessage: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const TERMINAL_STATUSES = new Set(["succeeded", "failed", "canceled", "expired"]);
const SQLITE_CONTENT_TYPE = "application/vnd.sqlite3";

function isUnauthorizedStatus(status: number): boolean {
  return status === 401 || status === 403;
}

let sqlJsPromise: Promise<SqlJsStatic> | null = null;

function normalizeCell(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value == null) {
    return "";
  }
  return String(value);
}

function classifyReviewRow(translatedText: string, errorMessage: string): ReviewRow["status"] {
  if (errorMessage) {
    return "error";
  }
  if (translatedText.trim()) {
    return "translated";
  }
  return "untranslated";
}

function extractReviewRows(database: Database): ReviewRow[] {
  const result = database.exec(`
    SELECT
      cache.id,
      cache.original,
      COALESCE(cache.translation, '') AS translation,
      COALESCE(review_status.error_message, '') AS error_message
    FROM cache
    LEFT JOIN review_status ON review_status.id = cache.id
    WHERE NOT cache.ignored
    ORDER BY cache.rowid ASC
  `);
  const values = result[0]?.values || [];
  return values.map((row, index) => {
    const id = normalizeCell(row[0]);
    const originalText = normalizeCell(row[1]);
    const translatedText = normalizeCell(row[2]);
    const errorMessage = normalizeCell(row[3]);
    return {
      id,
      index: index + 1,
      status: classifyReviewRow(translatedText, errorMessage),
      originalText,
      translatedText,
      errorMessage,
    };
  });
}

async function loadSqlJs(): Promise<SqlJsStatic> {
  if (!sqlJsPromise) {
    sqlJsPromise = new Promise<SqlJsStatic>((resolve, reject) => {
      const sqlWindow = window as SqlJsWindow;
      const initialize = () => {
        if (!sqlWindow.initSqlJs) {
          reject(new Error("sql.js runtime did not expose initSqlJs."));
          return;
        }
        sqlWindow
          .initSqlJs({
            locateFile: () => "/sqljs/sql-wasm.wasm",
          })
          .then(resolve)
          .catch(reject);
      };

      if (sqlWindow.initSqlJs) {
        initialize();
        return;
      }

      const existing = document.getElementById("sqljs-runtime") as HTMLScriptElement | null;
      if (existing) {
        existing.addEventListener("load", initialize, { once: true });
        existing.addEventListener("error", () => reject(new Error("Failed to load /sqljs/sql-wasm.js.")), {
          once: true,
        });
        return;
      }

      const script = document.createElement("script");
      script.id = "sqljs-runtime";
      script.src = "/sqljs/sql-wasm.js";
      script.async = true;
      script.onload = initialize;
      script.onerror = () => reject(new Error("Failed to load /sqljs/sql-wasm.js."));
      document.head.appendChild(script);
    }).catch((error) => {
      sqlJsPromise = null;
      throw error;
    });
  }
  return sqlJsPromise;
}

export default function JobReviewPage({ params }: { params: { jobId: string } }) {
  const { status, accessToken, signOut } = useRequireAuth({ redirectTo: "/login" });
  const jobId = params.jobId;
  const databaseRef = useRef<Database | null>(null);

  const [job, setJob] = useState<Job | null>(null);
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [filter, setFilter] = useState<ReviewStatus>("all");
  const [message, setMessage] = useState("Loading job...");
  const [actionMessage, setActionMessage] = useState("");
  const [pollKey, setPollKey] = useState(0);
  const [loadingSqlite, setLoadingSqlite] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloadingOutput, setDownloadingOutput] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    return () => {
      databaseRef.current?.close();
      databaseRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (status !== "authenticated" || !accessToken) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | null = null;

    async function loadJob() {
      try {
        const response = await fetch(`${API_BASE_URL}/v1/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (isUnauthorizedStatus(response.status)) {
          await signOut();
          return;
        }
        if (!response.ok) {
          throw new Error(`Failed to load job: ${response.status}`);
        }
        const payload = (await response.json()) as Job;
        if (cancelled) {
          return;
        }
        setJob(payload);

        if (!TERMINAL_STATUSES.has(payload.status)) {
          setMessage(`Job is ${payload.status}. Waiting for completion...`);
          timeoutId = window.setTimeout(loadJob, 5000);
        } else if (databaseRef.current) {
          setMessage("");
          setRebuilding(false);
        } else if (payload.status === "expired") {
          setMessage("Job artifacts have expired.");
        } else {
          setMessage("Loading review database...");
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(String(error));
        }
      }
    }

    loadJob();
    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [accessToken, jobId, pollKey, signOut, status]);

  useEffect(() => {
    if (
      status !== "authenticated" ||
      !accessToken ||
      !job ||
      !TERMINAL_STATUSES.has(job.status) ||
      job.status === "expired" ||
      databaseRef.current
    ) {
      return;
    }

    let cancelled = false;

    async function loadSqlite() {
      setLoadingSqlite(true);
      try {
        const response = await fetch(`${API_BASE_URL}/v1/jobs/${jobId}/sqlite-download-url`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (isUnauthorizedStatus(response.status)) {
          await signOut();
          return;
        }
        if (!response.ok) {
          throw new Error(`Failed to get SQLite download URL: ${response.status}`);
        }
        const artifact = (await response.json()) as ArtifactUrlResponse;
        const binaryResponse = await fetch(artifact.url);
        if (!binaryResponse.ok) {
          throw new Error(`Failed to download SQLite artifact: ${binaryResponse.status}`);
        }
        const buffer = await binaryResponse.arrayBuffer();
        const sqlJs = await loadSqlJs();
        if (cancelled) {
          return;
        }
        databaseRef.current?.close();
        databaseRef.current = new sqlJs.Database(new Uint8Array(buffer));
        setRows(extractReviewRows(databaseRef.current));
        setDirty(false);
        setMessage("");
      } catch (error) {
        if (!cancelled) {
          setMessage(String(error));
        }
      } finally {
        if (!cancelled) {
          setLoadingSqlite(false);
        }
      }
    }

    loadSqlite();
    return () => {
      cancelled = true;
    };
  }, [accessToken, job, jobId, signOut, status]);

  const summary = useMemo(() => {
    const translated = rows.filter((row) => row.status === "translated").length;
    const untranslated = rows.filter((row) => row.status === "untranslated").length;
    const error = rows.filter((row) => row.status === "error").length;
    return { translated, untranslated, error, total: rows.length };
  }, [rows]);

  const filteredRows = useMemo(() => {
    if (filter === "all") {
      return rows;
    }
    return rows.filter((row) => row.status === filter);
  }, [filter, rows]);

  const editingLocked =
    status !== "authenticated" || saving || rebuilding || !job || !TERMINAL_STATUSES.has(job.status) || job.status === "expired";

  function updateRowTranslation(rowId: string, translatedText: string) {
    const database = databaseRef.current;
    if (!database || editingLocked) {
      return;
    }
    const editedAt = new Date().toISOString();
    database.run("UPDATE cache SET translation = ? WHERE id = ?", [translatedText, rowId]);
    database.run(
      `
        INSERT INTO review_status (id, error_message, edited_at)
        VALUES (?, NULL, ?)
        ON CONFLICT(id) DO UPDATE SET
          error_message = NULL,
          edited_at = excluded.edited_at
      `,
      [rowId, editedAt],
    );

    setRows((currentRows) =>
      currentRows.map((row) =>
        row.id === rowId
          ? {
              ...row,
              translatedText,
              errorMessage: "",
              status: classifyReviewRow(translatedText, ""),
            }
          : row,
      ),
    );
    setDirty(true);
    setActionMessage("Unsaved review changes.");
  }

  async function saveSqlite(): Promise<boolean> {
    const database = databaseRef.current;
    if (!database || editingLocked || !accessToken) {
      return false;
    }

    setSaving(true);
    setActionMessage("");
    try {
      const urlResponse = await fetch(`${API_BASE_URL}/v1/jobs/${jobId}/sqlite-upload-url`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (isUnauthorizedStatus(urlResponse.status)) {
        await signOut();
        return false;
      }
      if (!urlResponse.ok) {
        throw new Error(`Failed to get SQLite upload URL: ${urlResponse.status}`);
      }
      const artifact = (await urlResponse.json()) as ArtifactUrlResponse;
      const exportBytes = Uint8Array.from(database.export());
      const body = new Blob([exportBytes], { type: SQLITE_CONTENT_TYPE });
      const uploadResponse = await fetch(artifact.url, {
        method: "PUT",
        headers: { "Content-Type": SQLITE_CONTENT_TYPE },
        body,
      });
      if (!uploadResponse.ok) {
        throw new Error(`Failed to upload SQLite artifact: ${uploadResponse.status}`);
      }
      setDirty(false);
      setActionMessage("SQLite review database saved.");
      return true;
    } catch (error) {
      setActionMessage(String(error));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handleRebuild() {
    if (!job || !accessToken || rebuilding || !TERMINAL_STATUSES.has(job.status) || job.status === "expired") {
      return;
    }

    if (dirty) {
      const saved = await saveSqlite();
      if (!saved) {
        return;
      }
    }

    setRebuilding(true);
    setActionMessage("");
    try {
      const response = await fetch(`${API_BASE_URL}/v1/jobs/${jobId}:rebuild`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (isUnauthorizedStatus(response.status)) {
        await signOut();
        return;
      }
      if (!response.ok) {
        throw new Error(`Failed to enqueue rebuild: ${response.status}`);
      }
      setActionMessage("Rebuild started.");
      setPollKey((current) => current + 1);
    } catch (error) {
      setActionMessage(String(error));
      setRebuilding(false);
    }
  }

  async function handleDownloadOutput() {
    if (!job || !accessToken || job.status !== "succeeded") {
      return;
    }
    setDownloadingOutput(true);
    setActionMessage("");
    try {
      const response = await fetch(`${API_BASE_URL}/v1/jobs/${jobId}/download-url`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (isUnauthorizedStatus(response.status)) {
        await signOut();
        return;
      }
      if (!response.ok) {
        throw new Error(`Failed to get output download URL: ${response.status}`);
      }
      const payload = (await response.json()) as { download_url: string };
      window.open(payload.download_url, "_blank", "noopener,noreferrer");
    } catch (error) {
      setActionMessage(String(error));
    } finally {
      setDownloadingOutput(false);
    }
  }

  if (status === "loading") {
    return (
      <main>
        <div className="card">
          <h1>Job Review</h1>
          <p className="hint">Checking your session...</p>
        </div>
      </main>
    );
  }

  if (status === "unauthenticated") {
    return (
      <main>
        <div className="card">
          <h1>Job Review</h1>
          <p className="hint">Redirecting to login...</p>
        </div>
      </main>
    );
  }

  return (
    <main>
      <div className="card">
        <div className="page-title-row">
          <div>
            <h1>Job Review</h1>
            <p className="hint">Review and edit the SQLite artifact used for rebuild-only output generation.</p>
          </div>
          <div className="toolbar-row">
            <button type="button" onClick={() => void saveSqlite()} disabled={!dirty || editingLocked}>
              {saving ? "Saving..." : "Save SQLite"}
            </button>
            <button
              type="button"
              className="button-secondary"
              onClick={() => void handleRebuild()}
              disabled={editingLocked || loadingSqlite || !databaseRef.current}
            >
              {rebuilding || (job && !TERMINAL_STATUSES.has(job.status)) ? "Rebuilding..." : "Rebuild Output"}
            </button>
            <button
              type="button"
              className="button-muted"
              onClick={() => void handleDownloadOutput()}
              disabled={downloadingOutput || job?.status !== "succeeded"}
            >
              {downloadingOutput ? "Preparing..." : "Download Output"}
            </button>
          </div>
        </div>

        {job && (
          <div className="job-meta-grid">
            <div className="meta-card">
              <span className="meta-label">Job ID</span>
              <span>{job.job_id}</span>
            </div>
            <div className="meta-card">
              <span className="meta-label">Status</span>
              <span className={`status-chip status-${job.status}`}>{job.status}</span>
            </div>
            <div className="meta-card">
              <span className="meta-label">Progress</span>
              <span>{job.progress}%</span>
            </div>
            <div className="meta-card">
              <span className="meta-label">Created</span>
              <span>{new Date(job.created_at).toLocaleString()}</span>
            </div>
            <div className="meta-card">
              <span className="meta-label">Finished</span>
              <span>{job.finished_at ? new Date(job.finished_at).toLocaleString() : "-"}</span>
            </div>
            <div className="meta-card">
              <span className="meta-label">Expires</span>
              <span>{new Date(job.expires_at).toLocaleString()}</span>
            </div>
          </div>
        )}

        {job?.error_message && <p className="review-message error-message">{job.error_message}</p>}
        {message && <p className="review-message">{message}</p>}
        {actionMessage && <p className="review-message">{actionMessage}</p>}

        <div className="stats-grid">
          <div className="stat-card">
            <span className="meta-label">Translated</span>
            <strong>{summary.translated}</strong>
          </div>
          <div className="stat-card">
            <span className="meta-label">Untranslated</span>
            <strong>{summary.untranslated}</strong>
          </div>
          <div className="stat-card">
            <span className="meta-label">Error</span>
            <strong>{summary.error}</strong>
          </div>
          <div className="stat-card">
            <span className="meta-label">Total</span>
            <strong>{summary.total}</strong>
          </div>
        </div>

        <div className="filter-row">
          {(["all", "translated", "untranslated", "error"] as ReviewStatus[]).map((value) => (
            <button
              key={value}
              type="button"
              className={value === filter ? "pill-tab active" : "pill-tab"}
              onClick={() => setFilter(value)}
            >
              {value}
            </button>
          ))}
        </div>

        <div className="review-list">
          {loadingSqlite && <p className="hint">Opening SQLite artifact...</p>}
          {!loadingSqlite && filteredRows.length === 0 && <p className="hint">No review rows to display.</p>}
          {filteredRows.map((row) => (
            <article className="review-row" key={row.id}>
              <div className="review-row-header">
                <strong>#{row.index}</strong>
                <span className={`status-chip status-${row.status}`}>{row.status}</span>
              </div>
              <div className="review-grid">
                <div>
                  <label className="meta-label" htmlFor={`original-${row.id}`}>
                    Original
                  </label>
                  <textarea id={`original-${row.id}`} className="review-textarea" value={row.originalText} readOnly />
                </div>
                <div>
                  <label className="meta-label" htmlFor={`translation-${row.id}`}>
                    Translation
                  </label>
                  <textarea
                    id={`translation-${row.id}`}
                    className="review-textarea"
                    value={row.translatedText}
                    onChange={(event) => updateRowTranslation(row.id, event.target.value)}
                    readOnly={editingLocked}
                  />
                </div>
              </div>
              {row.errorMessage && <p className="error-message">{row.errorMessage}</p>}
            </article>
          ))}
        </div>
      </div>
    </main>
  );
}
