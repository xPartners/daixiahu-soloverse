"""结算数据集 ORM 模型。"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    JSON,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class Settlement(Base):
    """结算数据表（settlements）。"""

    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    claim_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    region: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    org_code: Mapped[str] = mapped_column(String(64), nullable=False)
    org_name: Mapped[str] = mapped_column(String(256), nullable=False)
    insurance_type: Mapped[str] = mapped_column(String(16), nullable=False)
    insurance_type_detail: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    visit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    total_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    insurance_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    patient_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    patient_gender: Mapped[Optional[str]] = mapped_column(
        String(8), nullable=True
    )
    diagnosis_codes: Mapped[list] = mapped_column(JSON, default=list)
    settle_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_violation: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    violation_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
