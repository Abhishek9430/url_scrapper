# Crawler PoC (Python + Flask)

Minimal proof-of-concept crawler service that:
- accepts a URL,
- enqueues crawl jobs to Celery (Redis broker),
- routes jobs through tiered policy (`http` -> `render` -> blocked),
- HTTP worker fetches and parses page metadata/content,
- classifies rough topics,
- stores crawl job state and results.

## Endpoints

- `GET /health`
- `POST /crawl` with JSON body:
  - `{"url": "https://example.com"}`
- `POST /crawl/batch` with JSON body:
  - `{"urls": ["https://example.com", "http://example.org"]}`
- `GET /crawl/<job_id>`
- `GET /crawls?status=COMPLETED&limit=20&offset=0`
- `GET /metrics`

## Local setup

1. Create venv and install dependencies:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
   - `python -m playwright install chromium`
2. Optional: create `.env` in project root for config values (auto-loaded by API and workers):
   - `RENDER_ALLOWLIST_DOMAINS=example.com`
   - `RENDER_DENYLIST_DOMAINS=`
   - `DOMAIN_COOLDOWN_SECONDS=300`
   - `REDIS_URL=redis://localhost:6379/0`
3. Start Redis:
   - `redis-server`
4. Start HTTP queue worker:
   - `celery -A celery_app.celery_app worker --loglevel=info -Q http`
5. Start render queue worker:
   - `celery -A celery_app.celery_app worker --loglevel=info -Q render`
6. Run Flask API server:
   - `python run.py`

Server runs on `http://localhost:5000`.

## Example usage

Submit job:

```bash
curl -X POST http://localhost:5000/crawl \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.example.com"}'
```

Submit force-render job (allowlisted domains only):

```bash
curl -X POST http://localhost:5000/crawl \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.example.com", "force_render": true}'
```

Check result:

```bash
curl http://localhost:5000/crawl/<job_id>
```

## Notes

- SQLite DB path: `data/crawler.db`
- Raw HTML files: `data/raw_html/<job_id>.html`
- Topic classification is keyword-based for PoC only.
- Rate limit is enforced via `Flask-Limiter` (30 requests per IP per minute, `/health` exempt).
- Async job execution is handled by Celery with Redis as broker/backend.
- Render tier uses Playwright Chromium for JS-required pages in allowlisted domains.
- Challenge/blocked pages (e.g., 403 + access-denied markers) are marked `BLOCKED`, not `COMPLETED`.
- Status values include: `QUEUED`, `RUNNING`, `ESCALATED_RENDER`, `COMPLETED`, `BLOCKED`, `FAILED`.
- Job errors are standardized as `REASON_CODE: message` and exposed in API as `error_reason_code` and `error_reason_message`.

## Tiered policy environment variables

- `RENDER_ALLOWLIST_DOMAINS=example.com,news.example.org`
- `RENDER_DENYLIST_DOMAINS=blocked.example.org`
- `DOMAIN_COOLDOWN_SECONDS=300`
