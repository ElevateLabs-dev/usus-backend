"""
Creating and reading in-app notifications.

Notifications are a side effect: the notify_* helpers log and swallow errors
so a failed notification never breaks the action that triggered it.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import UserRole
from src.domains.notifications.models import Notification
from src.domains.scenarios.models import Scenario
from src.domains.simulations.models import Session
from src.domains.users.models import User

logger = logging.getLogger("usus.notifications")

LIST_LIMIT = 50


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[list[Notification], int]:
    """The user's latest notifications and how many are unread."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(LIST_LIMIT)
    )
    unread = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return list(result.scalars().all()), unread or 0


async def mark_read(
    db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification | None:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        return None
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)
    return notification


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def _active_user_ids(
    db: AsyncSession, tenant_id: uuid.UUID, roles: Iterable[UserRole]
) -> list[uuid.UUID]:
    result = await db.execute(
        select(User.id).where(
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
            User.role.in_([role.value for role in roles]),
        )
    )
    return list(result.scalars().all())


async def notify_evaluation_ready(
    db: AsyncSession, session_id: uuid.UUID, overall_score: int | None
) -> None:
    """Tell the trainee their evaluation is ready, and their managers and
    company admins that they completed a session."""
    try:
        row = (
            await db.execute(
                select(Session, Scenario.name, User)
                .join(Scenario, Scenario.id == Session.scenario_id)
                .join(User, User.id == Session.user_id)
                .where(Session.id == session_id)
            )
        ).first()
        if row is None:
            return
        session, scenario_name, trainee = row
        score = "—" if overall_score is None else f"{overall_score}%"

        notifications = [
            Notification(
                user_id=trainee.id,
                kind="evaluation_ready",
                title="Your evaluation is ready",
                body=f"{scenario_name}: {score}",
                link=f"/history/{session.id}",
            )
        ]

        trainee_name = trainee.full_name or trainee.email
        staff = await db.execute(
            select(User.id, User.role).where(
                User.tenant_id == session.tenant_id,
                User.is_active.is_(True),
                User.role.in_(
                    [UserRole.MANAGER.value, UserRole.COMPANY_ADMIN.value]
                ),
                User.id != trainee.id,
            )
        )
        for user_id, role in staff.all():
            area = (
                "/manager" if role == UserRole.MANAGER.value else "/company-admin"
            )
            notifications.append(
                Notification(
                    user_id=user_id,
                    kind="session_completed",
                    title=f"{trainee_name} completed a session",
                    body=f"{scenario_name}: {score}",
                    link=f"{area}/performance/{trainee.id}",
                )
            )

        db.add_all(notifications)
        await db.commit()
    except Exception:
        logger.exception("Could not notify about session %s", session_id)
        await db.rollback()


async def notify_scenario_added(db: AsyncSession, scenario: Scenario) -> None:
    """Tell the organization's trainees about a new scenario."""
    try:
        trainee_ids = await _active_user_ids(
            db, scenario.tenant_id, [UserRole.TRAINEE]
        )
        db.add_all(
            Notification(
                user_id=user_id,
                kind="scenario_added",
                title="New scenario available",
                body=scenario.name,
                link=f"/scenarios/{scenario.id}",
            )
            for user_id in trainee_ids
        )
        await db.commit()
    except Exception:
        logger.exception("Could not notify about scenario %s", scenario.id)
        await db.rollback()
