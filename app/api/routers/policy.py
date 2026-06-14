"""政策解析路由。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_policy_engine
from app.engines.policy_engine import PolicyParseEngine
from app.schemas.policy import PolicyDocumentOut, PolicyParseResponse

router = APIRouter(prefix="/policy", tags=["政策解析"])


@router.post("/parse", response_model=PolicyParseResponse)
async def parse_policy(
    file: UploadFile = File(..., description="政策文件（PDF/Word/文本），系统自动识别格式"),
    region: str = Form(..., description="行政区划代码，如 110000（北京）"),
    source_type: Optional[str] = Form(
        None,
        description="可选；留空则自动识别。手动指定可填 pdf/word/text（用于改名文件等）",
    ),
    engine: PolicyParseEngine = Depends(get_policy_engine),
) -> PolicyParseResponse:
    """上传政策文件并解析为结构化规则。

    文件格式自动识别（基于文件头魔数），无需手动指定 source_type。
    支持格式：文本型 PDF、Word(.docx)、纯文本(.txt)。
    """
    content = await file.read()
    result = await engine.parse_document(
        filename=file.filename or "unknown",
        region=region,
        content=content,
        source_type=source_type,
    )
    document = PolicyDocumentOut(**result["document"])
    return PolicyParseResponse(
        document=document,
        rules=result["rules"],
        rule_count=result["rule_count"],
        accuracy_estimate=result["accuracy_estimate"],
    )
