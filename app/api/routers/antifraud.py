"""反欺诈路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_antifraud_engine
from app.engines.antifraud_engine import AntiFraudEngine
from app.schemas.antifraud import AntiFraudRequest, AntiFraudResponse

router = APIRouter(prefix="/antifraud", tags=["反欺诈"])


@router.post("/analyze", response_model=AntiFraudResponse)
async def analyze(
    request: AntiFraudRequest,
    engine: AntiFraudEngine = Depends(get_antifraud_engine),
) -> AntiFraudResponse:
    """分析结算数据，生成反欺诈候选规则。"""
    result = engine.generate(request.settlements, region=request.region)
    return AntiFraudResponse(**result)
