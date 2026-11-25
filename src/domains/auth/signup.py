"""
Self-serve company signup.

1. POST /auth/signup with the company and your details; a 6-digit code is
   emailed to you.
2. POST /auth/verify-email with the code. This creates the organization (with
   the starter scenarios) and you as its company admin, and signs you in.

POST /auth/resend-code sends a new code (once a minute, 5 times an hour).
"""

import asyncio
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.dependencies import UserRole
from src.core.security import MIN_PASSWORD_LENGTH, hash_password
from src.domains.auth.models import PendingSignup
from src.domains.auth.router import TokenResponse, _issue_token
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.scenarios.service import ScenarioService
from src.domains.tenants.models import Tenant
from src.domains.users.models import User
from src.infrastructure.email.sender import send_email

logger = logging.getLogger("usus.signup")

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

CODE_MINUTES = 10
RESEND_SECONDS = 60
MAX_SENDS_PER_HOUR = 5
MAX_ATTEMPTS = 5

# Free / personal mailbox providers. Signup needs a company email.
PERSONAL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "ymail.com",
    "rocketmail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "gmx.com",
    "gmx.net",
    "mail.com",
    "yandex.com",
    "yandex.ru",
    "zoho.com",
    "zohomail.com",
    "tutanota.com",
    "fastmail.com",
    "hey.com",
    "qq.com",
    "163.com",
    "126.com",
    "mail.ru",
}
# Providers with a domain per country, e.g. yahoo.co.uk, hotmail.fr
PERSONAL_PREFIXES = ("yahoo.", "hotmail.", "outlook.", "live.", "gmx.", "yandex.")


def is_personal_email(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in PERSONAL_DOMAINS or domain.startswith(PERSONAL_PREFIXES)


class SignupRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    email: EmailStr = Field(description="Your email")
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    company_type: str | None = Field(
        default=None, max_length=100, description="e.g. 'Retail', 'Telecom'"
    )
    referral_source: str | None = Field(
        default=None, max_length=100, description="How you heard about Usus"
    )

    @field_validator("company_name", "full_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Required")
        return value

    model_config = {
        "json_schema_extra": {
            "example": {
                "company_name": "Acme Retail",
                "email": "ada@acme.com",
                "full_name": "Ada Obi",
                "password": "a-strong-password",
                "company_type": "Retail",
                "referral_source": "LinkedIn",
            }
        }
    }


class EmailRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class CodeSent(BaseModel):
    email: str
    expires_in: int = Field(description="Seconds until the code expires")
    resend_in: int = Field(description="Seconds before another code can be sent")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    # SQLite (tests) gives back naive datetimes
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _hash(email: str, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), f"{email}:{code}".encode(), hashlib.sha256
    ).hexdigest()


async def _email_taken(db: AsyncSession, email: str) -> bool:
    found = await db.execute(select(User.id).where(func.lower(User.email) == email))
    return found.first() is not None


async def _pending(db: AsyncSession, email: str) -> PendingSignup | None:
    result = await db.execute(
        select(PendingSignup).where(PendingSignup.email == email.lower())
    )
    return result.scalar_one_or_none()


def _wait_seconds(pending: PendingSignup, now: datetime) -> int:
    """Seconds before another code may be sent (0 = now)."""
    if now - _utc(pending.window_started_at) >= timedelta(hours=1):
        return 0
    if pending.sends >= MAX_SENDS_PER_HOUR:
        reopen = _utc(pending.window_started_at) + timedelta(hours=1)
        return max(1, int((reopen - now).total_seconds()))
    ready = _utc(pending.last_sent_at) + timedelta(seconds=RESEND_SECONDS)
    return max(0, int((ready - now).total_seconds()))


def _new_code(pending: PendingSignup, now: datetime) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    pending.code_hash = _hash(pending.email, code)
    pending.expires_at = now + timedelta(minutes=CODE_MINUTES)
    pending.attempts = 0
    if pending.window_started_at is None or now - _utc(
        pending.window_started_at
    ) >= timedelta(hours=1):
        pending.window_started_at = now
        pending.sends = 1
    else:
        pending.sends += 1
    pending.last_sent_at = now
    return code


async def _send_code(email: str, name: str, code: str) -> None:
    body = (
        f"Hello {name},\n\n"
        f"Your Usus verification code is {code}\n\n"
        f"It expires in {CODE_MINUTES} minutes. If you did not sign up for Usus, "
        "you can ignore this email.\n"
    )
    try:
        await asyncio.to_thread(send_email, email, f"Your Usus code: {code}", body)
    except Exception:
        # They can ask for a new code
        logger.exception("Verification email to %s failed", email)


def _sent(pending: PendingSignup) -> CodeSent:
    return CodeSent(
        email=pending.email, expires_in=CODE_MINUTES * 60, resend_in=RESEND_SECONDS
    )


def _too_soon(seconds: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Please wait {seconds} seconds before requesting another code",
        headers={"Retry-After": str(seconds)},
    )


@router.post(
    "/signup",
    response_model=CodeSent,
    status_code=status.HTTP_201_CREATED,
    summary="Sign up your company",
    description=(
        "Starts a company signup and emails a 6-digit code to `email`. Nothing "
        "is created until the code is confirmed with `POST /auth/verify-email`.\n\n"
        "Signing up again with the same email replaces the earlier details and "
        "sends a new code."
    ),
    responses={
        409: {"description": "Email already registered"},
        429: {"description": "A code was sent less than a minute ago"},
    },
)
async def signup(
    body: SignupRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> CodeSent:
    email = body.email.strip().lower()
    # Company emails only: turned off for now, any valid email can sign up
    # if is_personal_email(email):
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="Please use your company email address",
    #     )
    if await _email_taken(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    now = _now()
    pending = await _pending(db, email)
    if pending is not None:
        wait = _wait_seconds(pending, now)
        if wait:
            raise _too_soon(wait)
    else:
        pending = PendingSignup(email=email, sends=0)
        db.add(pending)

    pending.company_name = body.company_name
    pending.full_name = body.full_name
    pending.company_type = (body.company_type or "").strip() or None
    pending.referral_source = (body.referral_source or "").strip() or None
    # bcrypt is CPU-heavy; keep it off the event loop
    pending.hashed_password = await asyncio.to_thread(hash_password, body.password)
    code = _new_code(pending, now)
    await db.commit()

    await _send_code(email, pending.full_name, code)
    return _sent(pending)


@router.post(
    "/resend-code",
    response_model=CodeSent,
    summary="Send a new signup code",
    description=(
        "Emails a new 6-digit code; the previous one stops working. Allowed "
        f"once every {RESEND_SECONDS} seconds and {MAX_SENDS_PER_HOUR} times an "
        "hour."
    ),
    responses={
        404: {"description": "No signup waiting for this email"},
        429: {"description": "Too soon; see the Retry-After header"},
    },
)
async def resend_code(
    body: EmailRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> CodeSent:
    pending = await _pending(db, body.email)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No signup found for this email. Please sign up again.",
        )
    now = _now()
    wait = _wait_seconds(pending, now)
    if wait:
        raise _too_soon(wait)
    code = _new_code(pending, now)
    await db.commit()

    await _send_code(pending.email, pending.full_name, code)
    return _sent(pending)


@router.post(
    "/verify-email",
    response_model=TokenResponse,
    summary="Confirm the signup code",
    description=(
        "Checks the 6-digit code. On success the organization is created with "
        "you as its company admin, and you are signed in (same response as "
        f"`POST /auth/token`). After {MAX_ATTEMPTS} wrong codes, request a new one."
    ),
    responses={
        400: {"description": "Wrong or expired code"},
        404: {"description": "No signup waiting for this email"},
        409: {"description": "Email was registered meanwhile"},
    },
)
async def verify_email(
    body: VerifyRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    pending = await _pending(db, body.email)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No signup found for this email. Please sign up again.",
        )

    def bad(detail: str) -> HTTPException:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if pending.attempts >= MAX_ATTEMPTS:
        raise bad("Too many incorrect codes. Request a new code.")
    if _utc(pending.expires_at) < _now():
        raise bad("This code has expired. Request a new code.")
    if not hmac.compare_digest(pending.code_hash, _hash(pending.email, body.code)):
        pending.attempts += 1
        await db.commit()
        raise bad("Incorrect code")

    if await _email_taken(db, pending.email):
        await db.delete(pending)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    tenant = Tenant(
        name=pending.company_name,
        company_type=pending.company_type,
        referral_source=pending.referral_source,
    )
    db.add(tenant)
    await db.flush()
    user = User(
        email=pending.email,
        full_name=pending.full_name,
        hashed_password=pending.hashed_password,
        role=UserRole.COMPANY_ADMIN.value,
        tenant_id=tenant.id,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    await db.delete(pending)
    await db.commit()
    await db.refresh(user)

    await ScenarioService(scenario_repo).seed_defaults(db, tenant.id)
    return _issue_token(user, tenant.id)
