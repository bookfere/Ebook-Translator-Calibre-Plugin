# Ebook Translator SaaS Stack

This folder contains a production-oriented baseline for running Ebook Translator as a service with:

- FastAPI (`api`)
- Celery worker with Calibre (`worker`)
- Redis queue (`redis`)
- Cloudflare R2 object storage
- Supabase Auth + Postgres
- Next.js admin UI (`ui`)
- Helm chart for GKE deployment (`helm/`)

## Folder structure

- `api/`: FastAPI application
- `worker/`: Celery worker and cleanup job
- `ui/`: Next.js admin UI
- `db/migrations/001_init.sql`: Supabase schema
- `helm/`: Kubernetes manifests via Helm

## Quick start (local)

1. Copy env file:

```bash
cp .env.example .env
```

2. Apply DB schema to your Postgres/Supabase database:

```bash
psql "$DATABASE_URL" -f db/migrations/001_init.sql
```

3. Start services:

```bash
docker compose up --build
```

4. API health check:

```bash
curl http://localhost:8000/healthz
```

## API summary

- `POST /v1/uploads:init`
- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs`
- `POST /v1/jobs/{job_id}:cancel`
- `GET /v1/jobs/{job_id}/download-url`
- `GET /v1/engines`
- `GET /v1/formats`
- `GET /v1/admin/metrics`

All `/v1/*` endpoints require Supabase JWT bearer tokens.

## DeepInfra / DeepSeek v3.2

Set these worker environment variables to use DeepInfra's OpenAI-compatible endpoint:

- `DEEPINFRA_API_KEYS_CSV`
- `DEEPINFRA_MODEL=deepseek-ai/DeepSeek-V3.2`
- `DEEPINFRA_ENDPOINT=https://api.deepinfra.com/v1/openai/chat/completions`
- `ALLOWED_ENGINES_CSV=openai,deepl,google,deepinfra`

When creating a job, set `engine` to `deepinfra`.

## Notes

- Worker reuses plugin conversion and translation logic by importing `calibre_plugins.ebook_translator` from this repository.
- Cleanup runner is in `worker/app/cleanup.py` and is wired as a Kubernetes CronJob in Helm.
- For production, use GCP Secret Manager + External Secrets (template included in `helm/templates/externalsecret.yaml`).
