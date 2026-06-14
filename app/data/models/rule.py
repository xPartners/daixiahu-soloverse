"""医保规则库 ORM 模型。"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class MedicalRule(Base):
    """医保规则表（medical_rules）。"""

    __tablename__ = "medical_rules"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    rule_code: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    element_type: Mapped[str] = mapped_column(
        String(32), index=True, nullable=False
    )
    region: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    logic: Mapped[dict] = mapped_column(JSON, nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, default=50, server_default="50"
    )
    status: Mapped[str] = mapped_column(
        String(16), default="draft", index=True, server_default="draft"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(
        String(16), default="reject", server_default="reject"
    )
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source_document_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("policy_documents.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
