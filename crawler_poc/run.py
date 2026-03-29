import json

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import app.env  # noqa: F401
from app.db import get_connection, init_db
from app.metrics import snapshot as metrics_snapshot
from app.jobs import create_job, update_job
from app.policy import decide_initial_tier
from app.tasks import crawl_http_task, crawl_render_task
from app.utils import is_valid_url, utc_now


app = Flask(__name__)
init_db()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["30 per minute"],
    storage_uri="memory://",
)
limiter.init_app(app)


def error_response(code: str, message: str, status_code: int):
    return jsonify({"error": {"code": code, "message": message}}), status_code


@app.errorhandler(429)
def rate_limit_exceeded(_error):
    return error_response(
        "RATE_LIMIT_EXCEEDED",
        "Too many requests. Please retry later.",
        429,
    )


@app.get("/health")
@limiter.exempt
def health() -> tuple[dict, int]:
    return {"status": "ok"}, 200


@app.post("/crawl")
def submit_crawl():
    payload = request.get_json(silent=True) or {}
    url = payload.get("url")
    force_render = bool(payload.get("force_render", False))
    if not isinstance(url, str) or not url.strip():
        return error_response("INVALID_REQUEST", "Field 'url' is required.", 400)
    if not is_valid_url(url):
        return error_response("INVALID_URL", "Invalid URL. Use http/https URL.", 400)

    normalized_url = url.strip()
    job_id = create_job(normalized_url)
    initial_tier, tier_reason = decide_initial_tier(normalized_url, force_render=force_render)
    if initial_tier == "blocked":
        update_job(
            job_id,
            status="BLOCKED",
            finished_at=utc_now(),
            error_message=f"{tier_reason}: Request blocked by routing policy.",
        )
        return (
            jsonify(
                {
                    "job_id": job_id,
                    "status": "BLOCKED",
                    "status_url": f"/crawl/{job_id}",
                }
            ),
            202,
        )
    try:
        if initial_tier == "render":
            crawl_render_task.delay(job_id, normalized_url, "FORCE_RENDER_REQUESTED")
        else:
            crawl_http_task.delay(job_id, normalized_url)
    except Exception as exc:
        update_job(job_id, status="FAILED", error_message=f"QUEUE_UNAVAILABLE: {exc}")
        return error_response(
            "QUEUE_UNAVAILABLE",
            "Failed to enqueue job. Verify Redis/Celery are running.",
            503,
        )

    return (
        jsonify(
            {
                "job_id": job_id,
                "status": "QUEUED",
                "status_url": f"/crawl/{job_id}",
            }
        ),
        202,
    )


@app.post("/crawl/batch")
def submit_batch_crawl():
    payload = request.get_json(silent=True) or {}
    urls = payload.get("urls")
    if not isinstance(urls, list) or not urls:
        return error_response(
            "INVALID_REQUEST",
            "Field 'urls' must be a non-empty array.",
            400,
        )

    created: list[dict] = []
    rejected: list[dict] = []
    # Keep batch endpoint intentionally small for PoC.
    for item in urls[:100]:
        if not isinstance(item, str) or not is_valid_url(item.strip()):
            rejected.append({"url": item, "reason": "INVALID_URL"})
            continue
        job_id = create_job(item.strip())
        initial_tier, tier_reason = decide_initial_tier(item.strip(), force_render=False)
        if initial_tier == "blocked":
            update_job(
                job_id,
                status="BLOCKED",
                finished_at=utc_now(),
                error_message=f"{tier_reason}: Request blocked by routing policy.",
            )
            rejected.append({"url": item, "reason": tier_reason})
            continue
        try:
            if initial_tier == "render":
                crawl_render_task.delay(job_id, item.strip(), "ALLOWLIST_ROUTED_RENDER")
            else:
                crawl_http_task.delay(job_id, item.strip())
            created.append({"job_id": job_id, "url": item.strip(), "status": "QUEUED"})
        except Exception:
            update_job(
                job_id,
                status="FAILED",
                error_message="QUEUE_UNAVAILABLE: Failed to enqueue batch item.",
            )
            rejected.append({"url": item, "reason": "QUEUE_UNAVAILABLE"})

    return jsonify({"created": created, "rejected": rejected}), 202


@app.get("/crawl/<job_id>")
def get_crawl_result(job_id: str):
    with get_connection() as conn:
        job = conn.execute(
            """
            SELECT job_id, url, normalized_url, status, attempt_count,
                   submitted_at, started_at, finished_at, error_message
            FROM crawl_jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

        if not job:
            return error_response("NOT_FOUND", "Job not found.", 404)

        result = conn.execute(
            """
            SELECT final_url, http_status, content_type, title, meta_description,
                   canonical_url, h1, body_text, topics_json, content_hash, raw_html_path
            FROM crawl_results
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

    response = dict(job)
    reason_parts = (response.get("error_message") or "").split(":", 1)
    if response.get("error_message") and reason_parts:
        response["error_reason_code"] = reason_parts[0].strip()
        response["error_reason_message"] = (
            reason_parts[1].strip() if len(reason_parts) > 1 else response["error_message"]
        )
    if result:
        result_dict = dict(result)
        result_dict["topics"] = json.loads(result_dict.pop("topics_json") or "[]")
        response["result"] = result_dict

    return jsonify(response), 200


@app.get("/crawls")
def list_crawls():
    status_filter = request.args.get("status")
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return error_response("INVALID_REQUEST", "limit/offset must be integers.", 400)

    if status_filter:
        query = """
            SELECT job_id, url, normalized_url, status, attempt_count,
                   submitted_at, started_at, finished_at, error_message
            FROM crawl_jobs
            WHERE status = ?
            ORDER BY submitted_at DESC
            LIMIT ? OFFSET ?
        """
        params = (status_filter.upper(), limit, offset)
    else:
        query = """
            SELECT job_id, url, normalized_url, status, attempt_count,
                   submitted_at, started_at, finished_at, error_message
            FROM crawl_jobs
            ORDER BY submitted_at DESC
            LIMIT ? OFFSET ?
        """
        params = (limit, offset)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return jsonify({"items": [dict(row) for row in rows], "limit": limit, "offset": offset}), 200


@app.get("/metrics")
def metrics():
    return jsonify(metrics_snapshot()), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
