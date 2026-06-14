"""异地就医路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_cross_region_engine
from app.engines.cross_region_engine import CrossRegionEngine
from app.schemas.cross_region import CrossRegionRequest, CrossRegionResult

router = APIRouter(prefix="/cross-region", tags=["异地就医"])


@router.post("/adapt", response_model=CrossRegionResult)
async def adapt(
    request: CrossRegionRequest,
    engine: CrossRegionEngine = Depends(get_cross_region_engine),
) -> CrossRegionResult:
    """异地就医规则适配。"""
    result = await engine.adapt(
        claim=request.claim,
        insured_region=request.insured_region,
        medical_region=request.medical_region,
        scenario=request.scenario,
    )
    return CrossRegionResult(**result)
