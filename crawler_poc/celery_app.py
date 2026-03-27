import os

from celery import Celery
from kombu import Exchange, Queue

import app.env  # noqa: F401


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
    task_default_queue="http",
    task_default_exchange="crawler",
    task_default_exchange_type="direct",
    task_default_routing_key="http",
    task_queues=(
        Queue("http", Exchange("crawler"), routing_key="http"),
        Queue("render", Exchange("crawler"), routing_key="render"),
    ),
    task_routes={
        "crawl_http_task": {"queue": "http", "routing_key": "http"},
        "crawl_render_task": {"queue": "render", "routing_key": "render"},
    },
)
# Explicit import is more reliable than autodiscovery in simple PoCs.
import app.tasks  # noqa: F401
