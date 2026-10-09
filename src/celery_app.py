from celery import Celery

from src.core.config import settings


def _redis_url(url: str) -> str:
    """Celery requires TLS (rediss://) URLs, e.g. Upstash, to state cert checking."""
    if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        url += ("&" if "?" in url else "?") + "ssl_cert_reqs=CERT_REQUIRED"
    return url


celery_app = Celery(
    "usus_celery_app",
    broker=_redis_url(settings.CELERY_BROKER_URL),
    backend=_redis_url(settings.CELERY_RESULT_BACKEND),
)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    # Hosted Redis (Upstash) bills per command. An idle worker waits on BRPOP for
    # up to 20s per call instead of 1s; new tasks are still picked up instantly.
    broker_transport_options={"polling_interval": 20},
    worker_send_task_events=False,
)

# Automatically discover tasks.py files in each domain.
celery_app.autodiscover_tasks(
    [
        "src.domains.evaluations",
        "src.domains.simulations",
    ]
)
