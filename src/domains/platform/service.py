"""Platform-wide status, activity, alerts, settings and platform admins."""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import UserRole
from src.domains.evaluations.models import EvaluationResult
from src.domains.platform.models import PlatformSettings
from src.domains.platform.schemas import (
    ActivityItem,
    ActivityType,
    AlertItem,
    AlertType,
    CheckState,
    PlatformStatus,
    StatusCheck,
)
from src.domains.simulations.models import Session, SessionStatus
from src.domains.tenants.models import Tenant
from src.domains.users import service as users_service
from src.domains.users.models import User
from src.domains.users.schemas import TraineeCreate

# How long an invite email or an evaluation may take before it is reported
# as a problem.
ALERT_AFTER = timedelta(minutes=10)

_ROLE_LABELS = {
    UserRole.TRAINEE.value: "a trainee",
    UserRole.MANAGER.value: "a manager",
    UserRole.COMPANY_ADMIN.value: "a company admin",
    UserRole.PLATFORM_ADMIN.value: "a platform admin",
}


class PlatformAdminConflictError(Exception):
    """The email is already registered."""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


async def get_settings(db: AsyncSession) -> PlatformSettings:
    """The platform settings row, created with defaults the first time."""
    row = (await db.execute(select(PlatformSettings).limit(1))).scalar_one_or_none()
    if row is None:
        row = PlatformSettings(maintenance_mode=False)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def set_maintenance_mode(db: AsyncSession, enabled: bool) -> PlatformSettings:
    row = await get_settings(db)
    row.maintenance_mode = enabled
    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


async def _database_check(db: AsyncSession) -> StatusCheck:
    started = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # report it rather than fail the status page
        return StatusCheck(
            name="database", state=CheckState.ERROR, detail=type(exc).__name__
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return StatusCheck(
        name="database", state=CheckState.OK, detail=f"Responded in {elapsed_ms} ms"
    )


def _email_check() -> StatusCheck:
    if settings.RESEND_API_KEY:
        return StatusCheck(
            name="email",
            state=CheckState.OK,
            detail=f"Sending from {settings.EMAIL_FROM}",
        )
    return StatusCheck(
        name="email",
        state=CheckState.NOT_CONFIGURED,
        detail="RESEND_API_KEY is not set; invite emails are only logged",
    )


def _ai_check() -> StatusCheck:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai":
        key, model, label = settings.OPENAI_API_KEY, settings.OPENAI_MODEL, "OpenAI"
    elif provider == "anthropic":
        key, model, label = (
            settings.ANTHROPIC_API_KEY,
            settings.ANTHROPIC_MODEL,
            "Anthropic",
        )
    else:
        return StatusCheck(
            name="ai",
            state=CheckState.ERROR,
            detail=f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'",
        )
    if not key:
        return StatusCheck(
            name="ai",
            state=CheckState.NOT_CONFIGURED,
            detail=f"No {label} API key; simulations and evaluations will fail",
        )
    return StatusCheck(name="ai", state=CheckState.OK, detail=f"{label} ({model})")


async def platform_status(db: AsyncSession, version: str) -> PlatformStatus:
    checks = [
        StatusCheck(name="api", state=CheckState.OK, detail="Responding"),
        await _database_check(db),
        _email_check(),
        _ai_check(),
    ]
    maintenance = (await get_settings(db)).maintenance_mode
    if maintenance:
        overall = "maintenance"
    elif all(check.state == CheckState.OK for check in checks):
        overall = "operational"
    else:
        overall = "degraded"

    return PlatformStatus(
        overall=overall,
        environment=settings.ENVIRONMENT,
        version=version,
        maintenance_mode=maintenance,
        checks=checks,
        checked_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Activity and alerts
# ---------------------------------------------------------------------------


async def _organization_names(db: AsyncSession) -> dict[uuid.UUID, str]:
    return dict((await db.execute(select(Tenant.id, Tenant.name))).all())


async def recent_activity(db: AsyncSession, limit: int) -> list[ActivityItem]:
    """
    The latest platform events, newest first: organizations onboarded, users
    added and training sessions evaluated.
    """
    names = await _organization_names(db)
    items: list[ActivityItem] = []

    tenants = await db.execute(
        select(Tenant).order_by(Tenant.created_at.desc()).limit(limit)
    )
    for tenant in tenants.scalars():
        items.append(
            ActivityItem(
                type=ActivityType.ORGANIZATION_CREATED,
                message=f"{tenant.name} was onboarded",
                organization_id=tenant.id,
                organization_name=tenant.name,
                occurred_at=tenant.created_at,
            )
        )

    users = await db.execute(select(User).order_by(User.created_at.desc()).limit(limit))
    for user in users.scalars():
        label = _ROLE_LABELS.get(user.role, user.role)
        items.append(
            ActivityItem(
                type=ActivityType.USER_ADDED,
                message=f"{user.full_name or user.email} was added as {label}",
                organization_id=user.tenant_id,
                organization_name=names.get(user.tenant_id),
                occurred_at=user.created_at,
            )
        )

    evaluations = await db.execute(
        select(
            EvaluationResult.tenant_id,
            EvaluationResult.overall_score,
            EvaluationResult.created_at,
        )
        .order_by(EvaluationResult.created_at.desc())
        .limit(limit)
    )
    for tenant_id, score, created_at in evaluations.all():
        scored = f" (score {score})" if score is not None else ""
        items.append(
            ActivityItem(
                type=ActivityType.SESSION_COMPLETED,
                message=f"A training session was completed{scored}",
                organization_id=tenant_id,
                organization_name=names.get(tenant_id),
                occurred_at=created_at,
            )
        )

    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items[:limit]


async def open_alerts(db: AsyncSession) -> list[AlertItem]:
    """
    Problems that need a platform admin's attention, newest first:
    - invite emails that never went out (resend the invite);
    - ended sessions whose evaluation never finished (re-run it).
    """
    names = await _organization_names(db)
    cutoff = datetime.now(timezone.utc) - ALERT_AFTER
    alerts: list[AlertItem] = []

    undelivered = await db.execute(
        select(User).where(
            User.must_change_password.is_(True),
            User.is_active.is_(True),
            User.invite_sent_at.is_(None),
            User.created_at < cutoff,
        )
    )
    for user in undelivered.scalars():
        alerts.append(
            AlertItem(
                type=AlertType.INVITE_NOT_DELIVERED,
                message=f"The invite email to {user.email} was not delivered",
                organization_id=user.tenant_id,
                organization_name=names.get(user.tenant_id),
                occurred_at=user.created_at,
            )
        )

    stuck = await db.execute(
        select(Session).where(
            Session.status == SessionStatus.COMPLETED,
            Session.ended_at.is_not(None),
            Session.ended_at < cutoff,
        )
    )
    for session in stuck.scalars():
        alerts.append(
            AlertItem(
                type=AlertType.EVALUATION_MISSING,
                message=f"The evaluation for session {session.id} did not finish",
                organization_id=session.tenant_id,
                organization_name=names.get(session.tenant_id),
                occurred_at=session.ended_at,
            )
        )

    alerts.sort(key=lambda alert: alert.occurred_at, reverse=True)
    return alerts


# ---------------------------------------------------------------------------
# Platform admins
# ---------------------------------------------------------------------------


async def list_platform_admins(db: AsyncSession) -> Sequence[User]:
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.PLATFORM_ADMIN.value)
        .order_by(User.created_at)
    )
    return result.scalars().all()


async def get_platform_admin(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    user = await db.get(User, user_id)
    if user is None or user.role != UserRole.PLATFORM_ADMIN.value:
        return None
    return user


async def add_platform_admin(
    db: AsyncSession, email: str, full_name: str | None
) -> User:
    """Create a platform admin (locked until the invite email is sent)."""
    created, skipped = await users_service.add_users(
        db,
        None,
        [TraineeCreate(email=email, full_name=full_name)],
        UserRole.PLATFORM_ADMIN,
    )
    if not created:
        raise PlatformAdminConflictError(skipped[0].reason)
    return created[0]
