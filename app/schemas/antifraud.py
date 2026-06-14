"""反欺诈相关请求/响应模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AntiFraudRequest(BaseModel):
    """反欺诈分析请求。"""

    settlements: list[dict]
    region: Optional[str] = None


class AntiFraudResponse(BaseModel):
    """反欺诈分析响应。"""

    candidate_rules: list[dict] = Field(default_factory=list)
    patterns: list[dict] = Field(default_factory=list)
    confidence: float
