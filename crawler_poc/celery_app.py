import os

from celery import Celery


redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "crawler_poc",
    broker=redis_url,
    backend=redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
# Explicit import is more reliable than autodiscovery in simple PoCs.
import app.tasks  # noqa: F401
