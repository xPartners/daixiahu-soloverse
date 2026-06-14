"""FastAPI 依赖注入：数据库会话与各引擎实例的工厂函数。"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.database import get_db

# 重导出数据库会话依赖
get_db_session = get_db


async def get_policy_engine(
    db_session: AsyncSession = Depends(get_db),
):
    """获取政策解析引擎依赖。

    自动注入数据库会话；DB 未连接时引擎以无 DB 模式运行（容错）。
    """
    from app.engines.policy_engine import PolicyParseEngine
    return PolicyParseEngine(db_session=db_session)


def get_antifraud_engine():
    """获取反欺诈引擎依赖。"""
    from app.engines.antifraud_engine import AntiFraudEngine
    return AntiFraudEngine()


def get_cross_region_engine():
    """获取异地就医引擎依赖。"""
    from app.engines.cross_region_engine import CrossRegionEngine
    return CrossRegionEngine()
