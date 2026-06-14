"""仿真验证路由。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.engines.simulation_engine import SimulationEngine
from app.schemas.simulation import SimulationRequest, SimulationResult

router = APIRouter(prefix="/simulation", tags=["仿真验证"])


class _SimulationRunBody(SimulationRequest):
    """仿真运行请求体（在 SimulationRequest 基础上增加结算数据）。"""

    settlements: list[dict] = Field(default_factory=list)


@router.post("/run", response_model=SimulationResult)
async def run_simulation(body: _SimulationRunBody) -> SimulationResult:
    """运行仿真推演，模拟规则对结算数据集的执行效果。"""
    engine = SimulationEngine()
    result = engine.simulate(
        rule_dict=body.rule,
        settlements=body.settlements,
        region=body.region,
    )
    return SimulationResult(**result)
