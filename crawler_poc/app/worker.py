import time
from pathlib import Path

import certifi
import requests

from app.crawler import extract_page_data
from app.detection import detect_blocking_response, extract_blocked_snapshot
from app.jobs import save_result, update_job
from app.policy import mark_domain_blocked, should_escalate_to_render
from app.utils import utc_now


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_HTML_DIR = BASE_DIR / "data" / "raw_html"
RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)


def process_http_crawl_job(job_id: str, url: str) -> dict:
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
            if response.status_code >= 500:
                last_error = f"UPSTREAM_HTTP_{response.status_code}"
                if attempt < 3:
                    time.sleep(2**attempt)
                    continue
                update_job(
                    job_id,
                    status="FAILED",
                    finished_at=utc_now(),
                    error_message=last_error,
                )
                return {"action": "failed", "reason_code": last_error}

            html = response.text if response.text else ""
            raw_path = RAW_HTML_DIR / f"{job_id}.html"
            raw_path.write_text(html, encoding="utf-8")

            blocked = detect_blocking_response(response.status_code, html, dict(response.headers))
            if blocked:
                mark_domain_blocked(url)
                blocked_snapshot = extract_blocked_snapshot(html)
                save_result(
                    job_id,
                    {
                        "final_url": response.url,
                        "http_status": response.status_code,
                        "content_type": response.headers.get("Content-Type"),
                        "raw_html_path": str(raw_path),
                        **blocked_snapshot,
                    },
                )
                update_job(
                    job_id,
                    status="BLOCKED",
                    finished_at=utc_now(),
                    error_message=f"{blocked['reason_code']}: {blocked['reason_message']}",
                )
                return {"action": "blocked", "reason_code": blocked["reason_code"]}

            parsed = extract_page_data(html)
            escalate, reason_code = should_escalate_to_render(
                url,
                status_code=response.status_code,
                content_type=response.headers.get("Content-Type"),
                html=html,
                extracted_body_text=parsed.get("body_text"),
            )
            if escalate:
                update_job(
                    job_id,
                    status="ESCALATED_RENDER",
                    error_message=f"{reason_code}: Escalated from HTTP tier to render tier.",
                )
                return {"action": "escalate", "reason_code": reason_code}

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
            return {"action": "completed", "reason_code": None}
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
    return {"action": "failed", "reason_code": "HTTP_PROCESSING_FAILED"}
