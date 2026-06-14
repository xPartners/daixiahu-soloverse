"""违规案例库 ORM 模型。"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class ViolationCase(Base):
    """违规案例表（violation_cases）。"""

    __tablename__ = "violation_cases"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    claim_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    org_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    violation_type: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    violation_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    detected_by: Mapped[str] = mapped_column(String(16), nullable=False)
    related_rule_id: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    region: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    case_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="confirmed", server_default="confirmed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
