"""规则相关请求/响应模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RuleCreate(BaseModel):
    """规则创建请求。"""

    name: str
    element_type: str
    region: str = "110000"
    priority: int = 50
    logic: dict
    description: str = ""
    action: str = "reject"
    tags: list[str] = Field(default_factory=list)


class RuleOut(RuleCreate):
    """规则输出（在 RuleCreate 基础上增加持久化字段）。"""

    id: str
    status: str
    created_at: datetime


class RuleEvaluateRequest(BaseModel):
    """规则评估请求。"""

    claim: dict
    region: Optional[str] = None
    element_type: Optional[str] = None


class RuleEvaluateResponse(BaseModel):
    """规则评估响应。"""

    claim_id: Optional[str] = None
    violations: list[dict] = Field(default_factory=list)
    violation_count: int
