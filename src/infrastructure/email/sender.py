import logging

import httpx

from src.core.config import settings

logger = logging.getLogger("usus.email")

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, body: str) -> None:
    """
    Send a plain-text email through Resend (https://resend.com).

    Without RESEND_API_KEY (local development) the email is printed to the
    server log instead. Blocking; call it from a thread or background task.
    Raises on any delivery error so the caller can record the failure.
    """
    if not settings.RESEND_API_KEY:
        logger.warning(
            "EMAIL (not sent: RESEND_API_KEY is not set)\nTo: %s\nSubject: %s\n\n%s",
            to,
            subject,
            body,
        )
        return

    response = httpx.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "text": body,
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Resend rejected the email to {to}: "
            f"{response.status_code} {response.text}"
        )
