from datetime import datetime

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base_model import Base


class PendingSignup(Base):
    """
    A company signup waiting for its emailed 6-digit code. The organization
    and its admin are only created once the code is confirmed; signing up
    again with the same email replaces the row.
    """

    __tablename__ = "pending_signups"

    email: Mapped[str] = mapped_column(
        String(254), nullable=False, unique=True, index=True
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    company_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    referral_source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Wrong guesses for the current code
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Codes sent since window_started_at (limits sends per hour)
    sends: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
