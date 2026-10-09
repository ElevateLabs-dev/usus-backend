from celery import Celery
from src.core.config import settings

celery_app = Celery(
    "usus_celery_app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Automatically discover tasks.py files in each domain.
celery_app.autodiscover_tasks(
    [
        "src.domains.evaluations",
        "src.domains.simulations",
    ]
)
