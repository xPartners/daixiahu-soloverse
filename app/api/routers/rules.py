"""规则管理路由。"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.dsl import RuleElement, RuleEngine, RuleSet
from app.core.dsl import Rule as DSLRule
from app.data.models.rule import MedicalRule
from app.schemas.rule import (
    RuleCreate,
    RuleEvaluateRequest,
    RuleEvaluateResponse,
    RuleOut,
)

router = APIRouter(prefix="/rules", tags=["规则管理"])


def _to_rule_out(r: MedicalRule) -> RuleOut:
    """将 ORM 对象转换为 RuleOut。"""
    return RuleOut(
        id=r.id,
        name=r.name,
        element_type=r.element_type,
        region=r.region,
        priority=r.priority,
        logic=r.logic,
        description=r.description or "",
        action=r.action,
        tags=r.tags or [],
        status=r.status,
        created_at=r.created_at,
    )


@router.post("/", response_model=RuleOut)
async def create_rule(
    rule: RuleCreate,
    db: AsyncSession = Depends(get_db_session),
) -> RuleOut:
    """创建规则并存入数据库。"""
    rule_id = uuid.uuid4().hex
    medical_rule = MedicalRule(
        id=rule_id,
        rule_code=f"R_{rule_id[:8]}",
        name=rule.name,
        element_type=rule.element_type,
        region=rule.region,
        logic=rule.logic,
        priority=rule.priority,
        status="draft",
        description=rule.description,
        action=rule.action,
        tags=rule.tags,
    )
    db.add(medical_rule)
    await db.commit()
    await db.refresh(medical_rule)
    return _to_rule_out(medical_rule)


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> RuleOut:
    """查询单条规则。"""
    stmt = select(MedicalRule).where(MedicalRule.id == rule_id)
    result = await db.execute(stmt)
    medical_rule = result.scalar_one_or_none()
    if medical_rule is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _to_rule_out(medical_rule)


@router.get("/", response_model=list[RuleOut])
async def list_rules(
    region: Optional[str] = None,
    element_type: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
) -> list[RuleOut]:
    """列表查询规则（支持 region/element_type/status 过滤）。"""
    stmt = select(MedicalRule)
    if region:
        stmt = stmt.where(MedicalRule.region == region)
    if element_type:
        stmt = stmt.where(MedicalRule.element_type == element_type)
    if status:
        stmt = stmt.where(MedicalRule.status == status)
    result = await db.execute(stmt)
    rules = result.scalars().all()
    return [_to_rule_out(r) for r in rules]


@router.post("/evaluate", response_model=RuleEvaluateResponse)
async def evaluate_claim(
    request: RuleEvaluateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> RuleEvaluateResponse:
    """评估单张结算单，用 RuleEngine 执行所有匹配规则。"""
    stmt = select(MedicalRule)
    if request.region:
        stmt = stmt.where(MedicalRule.region == request.region)
    if request.element_type:
        stmt = stmt.where(MedicalRule.element_type == request.element_type)
    result = await db.execute(stmt)
    db_rules = result.scalars().all()

    # 转换为 DSL Rule 并构建 RuleEngine
    dsl_rules: list[DSLRule] = []
    for r in db_rules:
        try:
            rule_dict = {
                "id": r.id,
                "name": r.name,
                "element_type": r.element_type,
                "logic": r.logic,
                "region": r.region,
                "priority": r.priority,
                "status": r.status,
                "description": r.description or "",
                "action": r.action,
                "tags": r.tags or [],
            }
            dsl_rules.append(DSLRule.from_dict(rule_dict))
        except Exception:  # noqa: BLE001
            continue

    rule_set = RuleSet(rules=dsl_rules)
    engine = RuleEngine(rule_set)

    # 解析 element_type 枚举
    element_type_enum: Optional[RuleElement] = None
    if request.element_type:
        try:
            element_type_enum = RuleElement(request.element_type)
        except ValueError:
            element_type_enum = None

    violations = engine.evaluate_claim(
        request.claim,
        region=request.region,
        element_type=element_type_enum,
    )

    return RuleEvaluateResponse(
        claim_id=request.claim.get("claim_id"),
        violations=[asdict(v) for v in violations],
        violation_count=len(violations),
    )
