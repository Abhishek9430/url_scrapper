import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "crawler.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_jobs (
                job_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                normalized_url TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                submitted_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error_message TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_results (
                job_id TEXT PRIMARY KEY,
                final_url TEXT,
                http_status INTEGER,
                content_type TEXT,
                title TEXT,
                meta_description TEXT,
                canonical_url TEXT,
                h1 TEXT,
                body_text TEXT,
                topics_json TEXT,
                content_hash TEXT,
                raw_html_path TEXT,
                FOREIGN KEY(job_id) REFERENCES crawl_jobs(job_id)
            )
            """
        )
