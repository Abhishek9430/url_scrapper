from celery_app import celery_app

from app.worker import process_crawl_job


@celery_app.task(name="crawl_url_task")
def crawl_url_task(job_id: str, url: str) -> None:
    process_crawl_job(job_id, url)
