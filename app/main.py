"""FastAPI 应用入口。

注册所有业务路由，提供健康检查端点，启动时初始化数据库。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import antifraud, cross_region, policy, rules, simulation
from app.config import settings
from app.data.database import init_db

logger = logging.getLogger(__name__)

# 静态资源目录（前端测试页面）
_STATIC_DIR = Path(__file__).parent / "static"


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

# 挂载前端静态资源
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/app")
async def frontend():
    """前端测试台入口。

    通过 URL 版本号 /app?v=N 可强制浏览器拉取最新页面，
    避免内联 JS/CSS 更新后浏览器仍使用旧缓存。
    同时响应头设置 no-cache，开发期默认不缓存。
    """
    return FileResponse(
        str(_STATIC_DIR / "index.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


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
