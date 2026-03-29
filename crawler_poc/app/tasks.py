from celery_app import celery_app

from app.metrics import increment
from app.render_worker import process_render_crawl_job
from app.worker import process_http_crawl_job


@celery_app.task(name="crawl_http_task")
def crawl_http_task(job_id: str, url: str) -> None:
    outcome = process_http_crawl_job(job_id, url)
    if outcome.get("action") == "escalate":
        increment("jobs_escalated_to_render_total")
        celery_app.send_task(
            "crawl_render_task",
            args=[job_id, url, outcome.get("reason_code")],
            queue="render",
        )
    elif outcome.get("action") == "completed":
        increment("jobs_completed_total")
    elif outcome.get("action") == "blocked":
        increment("jobs_blocked_total")


@celery_app.task(name="crawl_render_task")
def crawl_render_task(job_id: str, url: str, escalation_reason: str | None = None) -> None:
    outcome = process_render_crawl_job(job_id, url, escalation_reason=escalation_reason)
    if outcome.get("action") == "completed":
        increment("render_success_total")
        increment("jobs_completed_total")
    elif outcome.get("action") == "blocked":
        increment("jobs_blocked_total")
