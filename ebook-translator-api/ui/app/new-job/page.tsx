"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRequireAuth } from "../auth";

type EngineInfo = {
  id: string;
  display_name: string;
};

type FormatInfo = {
  input_formats: string[];
  output_formats: string[];
};

type UploadInitResponse = {
  upload_key: string;
  put_url: string;
  expires_in_seconds: number;
};

type CreateJobResponse = {
  job_id: string;
  status: string;
  created_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;

const MIME_BY_FORMAT: Record<string, string> = {
  epub: "application/epub+zip",
  srt: "application/x-subrip",
  pgn: "application/x-chess-pgn",
};

function isUnauthorizedStatus(status: number): boolean {
  return status === 401 || status === 403;
}

function getErrorDetail(payload: unknown): string {
  if (typeof payload === "string") {
    return payload;
  }
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    return JSON.stringify(detail);
  }
  return "Unexpected error";
}

function uploadFileWithProgress(
  url: string,
  file: File,
  contentType: string,
  onProgress: (value: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", contentType);

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) {
        return;
      }
      onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
        resolve();
        return;
      }
      reject(new Error(`Upload failed: ${xhr.status}`));
    };

    xhr.onerror = () => reject(new Error("Upload failed: network error"));
    xhr.send(file);
  });
}

export default function NewJobPage() {
  const { status, accessToken, signOut } = useRequireAuth({ redirectTo: "/login" });

  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [formats, setFormats] = useState<FormatInfo>({ input_formats: [], output_formats: [] });

  const [inputFormat, setInputFormat] = useState("srt");
  const [sourceLang, setSourceLang] = useState("en");
  const [targetLang, setTargetLang] = useState("ja");
  const [engine, setEngine] = useState("deepinfra");
  const [file, setFile] = useState<File | null>(null);

  const [model, setModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [temperature, setTemperature] = useState("");
  const [topP, setTopP] = useState("");

  const [uploadProgress, setUploadProgress] = useState(0);
  const [message, setMessage] = useState("Load metadata...");
  const [submitting, setSubmitting] = useState(false);
  const [createdJobId, setCreatedJobId] = useState("");

  const outputFormat = useMemo(() => {
    if (formats.output_formats.includes(inputFormat)) {
      return inputFormat;
    }
    return formats.output_formats[0] || inputFormat;
  }, [formats.output_formats, inputFormat]);

  useEffect(() => {
    if (status !== "authenticated" || !accessToken) {
      return;
    }

    async function loadMetadata() {
      setMessage("Load metadata...");

      const [engineRes, formatRes] = await Promise.all([
        fetch(`${API_BASE_URL}/v1/engines`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        }),
        fetch(`${API_BASE_URL}/v1/formats`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        }),
      ]);

      if (isUnauthorizedStatus(engineRes.status) || isUnauthorizedStatus(formatRes.status)) {
        await signOut();
        return;
      }

      if (!engineRes.ok) {
        setMessage(`Failed to load engines: ${engineRes.status}`);
        return;
      }
      if (!formatRes.ok) {
        setMessage(`Failed to load formats: ${formatRes.status}`);
        return;
      }

      const enginePayload = (await engineRes.json()) as EngineInfo[];
      const formatPayload = (await formatRes.json()) as FormatInfo;
      setEngines(enginePayload);
      setFormats(formatPayload);

      setEngine((current) => {
        if (enginePayload.length === 0 || enginePayload.some((item) => item.id === current)) {
          return current;
        }
        return enginePayload[0].id;
      });
      setInputFormat((current) => {
        if (formatPayload.input_formats.length === 0 || formatPayload.input_formats.includes(current)) {
          return current;
        }
        return formatPayload.input_formats[0];
      });

      setMessage("");
    }

    loadMetadata().catch((error) => {
      setMessage(String(error));
    });
  }, [accessToken, signOut, status]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatedJobId("");
    setUploadProgress(0);

    if (status !== "authenticated" || !accessToken) {
      await signOut();
      return;
    }
    if (!file) {
      setMessage("Select a file first.");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setMessage("File is larger than 100MB limit.");
      return;
    }

    const contentType = MIME_BY_FORMAT[inputFormat] || file.type || "application/octet-stream";
    const trimmedModel = model.trim();
    const trimmedPrompt = prompt.trim();

    const engineOptions: Record<string, string | number | boolean> = {};
    if (trimmedModel) {
      engineOptions.model = trimmedModel;
    }
    if (trimmedPrompt) {
      engineOptions.prompt = trimmedPrompt;
    }
    if (temperature !== "") {
      const parsed = Number(temperature);
      if (!Number.isFinite(parsed)) {
        setMessage("Temperature must be a number.");
        return;
      }
      engineOptions.temperature = parsed;
    }
    if (topP !== "") {
      const parsed = Number(topP);
      if (!Number.isFinite(parsed)) {
        setMessage("Top P must be a number.");
        return;
      }
      engineOptions.top_p = parsed;
    }

    setSubmitting(true);
    try {
      setMessage("Creating upload URL...");
      const uploadInitRes = await fetch(`${API_BASE_URL}/v1/uploads:init`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          input_format: inputFormat,
          content_type: contentType,
        }),
      });

      if (isUnauthorizedStatus(uploadInitRes.status)) {
        await signOut();
        return;
      }

      if (!uploadInitRes.ok) {
        const payload = (await uploadInitRes.json().catch(() => ({}))) as unknown;
        throw new Error(`uploads:init failed (${uploadInitRes.status}): ${getErrorDetail(payload)}`);
      }

      const uploadInit = (await uploadInitRes.json()) as UploadInitResponse;

      setMessage("Uploading file to storage...");
      await uploadFileWithProgress(uploadInit.put_url, file, contentType, setUploadProgress);

      setMessage("Creating job...");
      const createJobRes = await fetch(`${API_BASE_URL}/v1/jobs`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          upload_key: uploadInit.upload_key,
          input_format: inputFormat,
          output_format: outputFormat,
          source_lang: sourceLang,
          target_lang: targetLang,
          engine,
          engine_options: engineOptions,
        }),
      });

      if (isUnauthorizedStatus(createJobRes.status)) {
        await signOut();
        return;
      }

      if (!createJobRes.ok) {
        const payload = (await createJobRes.json().catch(() => ({}))) as unknown;
        throw new Error(`jobs failed (${createJobRes.status}): ${getErrorDetail(payload)}`);
      }

      const job = (await createJobRes.json()) as CreateJobResponse;
      setCreatedJobId(job.job_id);
      setMessage(`Job created: ${job.job_id}`);
    } catch (error) {
      setMessage(String(error));
    } finally {
      setSubmitting(false);
    }
  }

  if (status === "loading") {
    return (
      <main>
        <div className="card">
          <h1>New Job</h1>
          <p className="hint">Checking your session...</p>
        </div>
      </main>
    );
  }

  if (status === "unauthenticated") {
    return (
      <main>
        <div className="card">
          <h1>New Job</h1>
          <p className="hint">Redirecting to login...</p>
        </div>
      </main>
    );
  }

  return (
    <main>
      <div className="card">
        <h1>New Job</h1>
        <p>Create a translation job in one screen (EPUB/SRT/PGN).</p>

        <form onSubmit={onSubmit}>
          <div className="form-grid-two">
            <div>
              <label htmlFor="input-format">Format</label>
              <select
                id="input-format"
                value={inputFormat}
                onChange={(event) => setInputFormat(event.target.value)}
                disabled={submitting}
              >
                {formats.input_formats.map((format) => (
                  <option key={format} value={format}>
                    {format.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="engine">Engine</label>
              <select
                id="engine"
                value={engine}
                onChange={(event) => setEngine(event.target.value)}
                disabled={submitting}
              >
                {engines.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-grid-two">
            <div>
              <label htmlFor="source-lang">Source Language</label>
              <input
                id="source-lang"
                value={sourceLang}
                onChange={(event) => setSourceLang(event.target.value)}
                placeholder="en"
                disabled={submitting}
                required
              />
            </div>
            <div>
              <label htmlFor="target-lang">Target Language</label>
              <input
                id="target-lang"
                value={targetLang}
                onChange={(event) => setTargetLang(event.target.value)}
                placeholder="ja"
                disabled={submitting}
                required
              />
            </div>
          </div>

          <div>
            <label htmlFor="file">File</label>
            <input
              id="file"
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
              disabled={submitting}
              required
            />
            <p className="hint">Max 100MB. Output format is fixed to {outputFormat.toUpperCase()} for this job.</p>
          </div>

          <h2 style={{ marginTop: 22 }}>Advanced Options</h2>
          <div className="form-grid-two">
            <div>
              <label htmlFor="model">Model (optional)</label>
              <input
                id="model"
                value={model}
                onChange={(event) => setModel(event.target.value)}
                placeholder="deepseek-ai/DeepSeek-V3.2"
                disabled={submitting}
              />
            </div>
            <div>
              <label htmlFor="temperature">Temperature (optional)</label>
              <input
                id="temperature"
                type="number"
                step="0.1"
                value={temperature}
                onChange={(event) => setTemperature(event.target.value)}
                placeholder="1.3"
                disabled={submitting}
              />
            </div>
          </div>
          <div className="form-grid-two">
            <div>
              <label htmlFor="top-p">Top P (optional)</label>
              <input
                id="top-p"
                type="number"
                step="0.1"
                value={topP}
                onChange={(event) => setTopP(event.target.value)}
                placeholder="1.0"
                disabled={submitting}
              />
            </div>
            <div />
          </div>
          <div>
            <label htmlFor="prompt">Prompt (optional)</label>
            <textarea
              id="prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              rows={4}
              placeholder="Custom system prompt"
              disabled={submitting}
            />
          </div>

          <div style={{ marginTop: 20, display: "flex", gap: 12, alignItems: "center" }}>
            <button type="submit" disabled={submitting}>
              {submitting ? "Submitting..." : "Create Job"}
            </button>
            <a href="/jobs">Go to Jobs</a>
          </div>
        </form>

        {submitting && (
          <div style={{ marginTop: 12 }}>
            <p style={{ margin: "6px 0" }}>Upload progress: {uploadProgress}%</p>
            <div className="progress">
              <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
            </div>
          </div>
        )}

        {message && <p style={{ marginTop: 14 }}>{message}</p>}
        {createdJobId && (
          <p style={{ marginTop: 8 }}>
            Open job details from <a href="/jobs">/jobs</a>: <code>{createdJobId}</code>
          </p>
        )}
      </div>
    </main>
  );
}
