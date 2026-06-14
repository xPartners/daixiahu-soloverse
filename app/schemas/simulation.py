"""仿真验证相关请求/响应模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SimulationRequest(BaseModel):
    """仿真推演请求。"""

    rule: dict
    region: Optional[str] = None
    sample_size: int = 1000


class SimulationResult(BaseModel):
    """仿真推演结果。"""

    rule_id: str
    recovered_amount: float
    false_positive_rate: float
    affected_org_count: int
    risk_level: str
    total_evaluated: int
    hit_count: int
    details: dict
