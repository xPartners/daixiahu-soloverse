"""政策解析路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_policy_engine
from app.engines.policy_engine import PolicyParseEngine
from app.schemas.policy import PolicyDocumentOut, PolicyParseResponse

router = APIRouter(prefix="/policy", tags=["政策解析"])


@router.post("/parse", response_model=PolicyParseResponse)
async def parse_policy(
    file: UploadFile = File(...),
    region: str = Form(...),
    source_type: str = Form(...),
    engine: PolicyParseEngine = Depends(get_policy_engine),
) -> PolicyParseResponse:
    """上传政策文件并解析为结构化规则。"""
    content = await file.read()
    result = await engine.parse_document(
        filename=file.filename or "unknown",
        region=region,
        source_type=source_type,
        content=content,
    )
    document = PolicyDocumentOut(**result["document"])
    return PolicyParseResponse(
        document=document,
        rules=result["rules"],
        rule_count=result["rule_count"],
        accuracy_estimate=result["accuracy_estimate"],
    )
