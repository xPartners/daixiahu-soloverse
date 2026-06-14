"""政策解析相关请求/响应模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PolicyParseRequest(BaseModel):
    """政策文档解析请求。"""

    filename: str
    region: str
    source_type: Literal["pdf", "word", "web", "scan", "text"]


class PolicyDocumentOut(BaseModel):
    """政策文档输出模型。"""

    id: str
    title: str
    region: str
    source_type: str
    status: str
    created_at: datetime
    parsed_rules_count: int


class PolicyParseResponse(BaseModel):
    """政策解析响应。"""

    document: PolicyDocumentOut
    rules: list[dict] = Field(default_factory=list)
    rule_count: int
    accuracy_estimate: float
