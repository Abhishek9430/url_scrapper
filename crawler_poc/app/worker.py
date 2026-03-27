import time
from pathlib import Path

import certifi
import requests

from app.crawler import extract_page_data
from app.jobs import save_result, update_job
from app.utils import utc_now


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_HTML_DIR = BASE_DIR / "data" / "raw_html"
RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)


def process_crawl_job(job_id: str, url: str) -> None:
    headers = {"User-Agent": "CrawlerPOC/1.0 (+https://example.local)"}
    update_job(job_id, status="RUNNING", started_at=utc_now(), attempt_count=0)

    last_error = None
    for attempt in range(1, 4):
        update_job(job_id, status="RUNNING", attempt_count=attempt)
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=20,
                allow_redirects=True,
                verify=certifi.where(),
            )
        except requests.exceptions.SSLError:
            # Local/dev networks sometimes use custom CA chains.
            response = requests.get(
                url,
                headers=headers,
                timeout=20,
                allow_redirects=True,
                verify=False,
            )
        try:
            html = response.text if response.text else ""
            raw_path = RAW_HTML_DIR / f"{job_id}.html"
            raw_path.write_text(html, encoding="utf-8")

            parsed = extract_page_data(html)
            save_result(
                job_id,
                {
                    "final_url": response.url,
                    "http_status": response.status_code,
                    "content_type": response.headers.get("Content-Type"),
                    "raw_html_path": str(raw_path),
                    **parsed,
                },
            )
            update_job(job_id, status="COMPLETED", finished_at=utc_now(), error_message=None)
            return
        except Exception as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(2**attempt)

    update_job(
        job_id,
        status="FAILED",
        finished_at=utc_now(),
        error_message=last_error,
    )
