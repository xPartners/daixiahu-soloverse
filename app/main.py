"""FastAPI 应用入口。

注册所有业务路由，提供健康检查端点，启动时初始化数据库。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import antifraud, cross_region, policy, rules, simulation
from app.config import settings
from app.data.database import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库（容错）。"""
    try:
        await init_db()
        logger.info("数据库初始化完成")
    except Exception as exc:  # noqa: BLE001
        logger.warning("数据库初始化失败（将以无 DB 模式运行）: %s", exc)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# 注册所有路由到 API_V1_PREFIX
app.include_router(policy.router, prefix=settings.API_V1_PREFIX)
app.include_router(rules.router, prefix=settings.API_V1_PREFIX)
app.include_router(antifraud.router, prefix=settings.API_V1_PREFIX)
app.include_router(simulation.router, prefix=settings.API_V1_PREFIX)
app.include_router(cross_region.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root() -> dict:
    """根路径健康检查。"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health")
async def health() -> dict:
    """健康检查端点。"""
    return {"status": "healthy"}
