import json
import uuid

from app.db import get_connection
from app.utils import normalize_url, utc_now


def create_job(url: str) -> str:
    job_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO crawl_jobs (
                job_id, url, normalized_url, status, attempt_count, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, url, normalize_url(url), "QUEUED", 0, utc_now()),
        )
    return job_id


def update_job(
    job_id: str,
    *,
    status: str,
    started_at: str | None = None,
    finished_at: str | None = None,
    attempt_count: int | None = None,
    error_message: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE crawl_jobs
            SET status = ?,
                started_at = COALESCE(?, started_at),
                finished_at = COALESCE(?, finished_at),
                attempt_count = COALESCE(?, attempt_count),
                error_message = ?
            WHERE job_id = ?
            """,
            (status, started_at, finished_at, attempt_count, error_message, job_id),
        )


def save_result(job_id: str, payload: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO crawl_results (
                job_id, final_url, http_status, content_type, title, meta_description,
                canonical_url, h1, body_text, topics_json, content_hash, raw_html_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                payload.get("final_url"),
                payload.get("http_status"),
                payload.get("content_type"),
                payload.get("title"),
                payload.get("meta_description"),
                payload.get("canonical_url"),
                payload.get("h1"),
                payload.get("body_text"),
                json.dumps(payload.get("topics", [])),
                payload.get("content_hash"),
                payload.get("raw_html_path"),
            ),
        )
