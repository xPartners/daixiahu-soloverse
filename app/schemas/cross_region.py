"""异地就医适配相关请求/响应模型。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CrossRegionRequest(BaseModel):
    """异地就医适配请求。"""

    claim: dict
    insured_region: str
    medical_region: str
    scenario: Literal["outpatient", "inpatient", "chronic", "maternity"] = "inpatient"


class DifferenceItem(BaseModel):
    """异地就医差异项。"""

    field: str
    insured_region_value: Any
    medical_region_value: Any
    description: str


class CrossRegionResult(BaseModel):
    """异地就医适配结果。"""

    compliant: bool
    reimbursement_ratio: float
    pay_limit: float
    fund_share_ratio: float
    differences: list[DifferenceItem] = Field(default_factory=list)
    summary: str
