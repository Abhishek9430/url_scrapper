from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.crawler import extract_page_data
from app.detection import detect_blocking_response, extract_blocked_snapshot
from app.jobs import save_result, update_job
from app.policy import is_render_allowed, mark_domain_blocked
from app.utils import utc_now


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_HTML_DIR = BASE_DIR / "data" / "raw_html"
RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)


def process_render_crawl_job(job_id: str, url: str, escalation_reason: str | None = None) -> dict:
    update_job(job_id, status="RUNNING", started_at=utc_now(), attempt_count=1)

    if not is_render_allowed(url):
        update_job(
            job_id,
            status="BLOCKED",
            finished_at=utc_now(),
            error_message="RENDER_NOT_ALLOWED: Domain not allowlisted for render tier.",
        )
        return {"action": "blocked", "reason_code": "RENDER_NOT_ALLOWED"}

    try:
        rendered = _render_page(url)
    except PlaywrightTimeoutError:
        update_job(
            job_id,
            status="FAILED",
            finished_at=utc_now(),
            error_message="RENDER_TIMEOUT: Timed out while rendering page.",
        )
        return {"action": "failed", "reason_code": "RENDER_TIMEOUT"}
    except Exception as exc:
        reason_suffix = f" Escalation={escalation_reason}." if escalation_reason else ""
        update_job(
            job_id,
            status="BLOCKED",
            finished_at=utc_now(),
            error_message=(
                "RENDER_RUNTIME_UNAVAILABLE: Render backend failed to execute."
                f" Details={exc}.{reason_suffix}"
            ),
        )
        return {"action": "blocked", "reason_code": "RENDER_RUNTIME_UNAVAILABLE"}

    raw_path = RAW_HTML_DIR / f"{job_id}_render.html"
    raw_path.write_text(rendered["html"], encoding="utf-8")

    blocked = detect_blocking_response(
        rendered["http_status"],
        rendered["html"],
        rendered.get("headers", {}),
    )
    if blocked:
        mark_domain_blocked(url)
        blocked_snapshot = extract_blocked_snapshot(rendered["html"])
        save_result(
            job_id,
            {
                "final_url": rendered["final_url"],
                "http_status": rendered["http_status"],
                "content_type": rendered["content_type"],
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

    parsed = extract_page_data(rendered["html"])
    save_result(
        job_id,
        {
            "final_url": rendered["final_url"],
            "http_status": rendered["http_status"],
            "content_type": rendered["content_type"],
            "raw_html_path": str(raw_path),
            **parsed,
        },
    )
    update_job(job_id, status="COMPLETED", finished_at=utc_now(), error_message=None)
    return {"action": "completed", "reason_code": None}


def _render_page(url: str) -> dict:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent="CrawlerPOC-Render/1.0 (+https://example.local)",
        )
        page = context.new_page()
        response = page.goto(url, wait_until="networkidle", timeout=25000)
        page.wait_for_timeout(1000)
        html = page.content()
        final_url = page.url
        status = response.status if response else 200
        headers = response.headers if response else {}
        content_type = headers.get("content-type", "text/html")
        context.close()
        browser.close()
    return {
        "html": html,
        "final_url": final_url,
        "http_status": status,
        "headers": headers,
        "content_type": content_type,
    }
