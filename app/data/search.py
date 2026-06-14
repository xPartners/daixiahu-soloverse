"""Elasticsearch 全文检索封装。"""
from __future__ import annotations

import logging
from typing import Optional

from elasticsearch import AsyncElasticsearch

from app.config import settings

logger = logging.getLogger(__name__)


class PolicySearch:
    """政策与规则全文检索客户端（连接容错）。"""

    def __init__(self) -> None:
        self.es: Optional[AsyncElasticsearch] = None
        try:
            self.es = AsyncElasticsearch(settings.ES_URL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("无法连接 Elasticsearch: %s", exc)
            self.es = None

    async def index_policy(self, doc_id: str, body: dict) -> None:
        """索引政策文档。"""
        if self.es is None:
            logger.warning("Elasticsearch 未连接，跳过 index_policy")
            return
        try:
            await self.es.index(
                index=settings.ES_INDEX_POLICY,
                id=doc_id,
                document=body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("index_policy 失败: %s", exc)

    async def search_policy(
        self, query: str, region: Optional[str] = None, size: int = 10
    ) -> list[dict]:
        """检索政策文档，返回命中源文档列表。"""
        if self.es is None:
            return []
        try:
            must: list[dict] = [{"match": {"content": query}}]
            filter_clauses: list[dict] = []
            if region:
                filter_clauses.append({"term": {"region": region}})
            resp = await self.es.search(
                index=settings.ES_INDEX_POLICY,
                query={"bool": {"must": must, "filter": filter_clauses}},
                size=size,
            )
            return [hit["_source"] for hit in resp["hits"]["hits"]]
        except Exception as exc:  # noqa: BLE001
            logger.warning("search_policy 失败: %s", exc)
            return []

    async def search_rule(
        self, query: str, region: Optional[str] = None, size: int = 10
    ) -> list[dict]:
        """检索规则，返回命中源文档列表。"""
        if self.es is None:
            return []
        try:
            must: list[dict] = [{"match": {"name": query}}]
            filter_clauses: list[dict] = []
            if region:
                filter_clauses.append({"term": {"region": region}})
            resp = await self.es.search(
                index=settings.ES_INDEX_RULE,
                query={"bool": {"must": must, "filter": filter_clauses}},
                size=size,
            )
            return [hit["_source"] for hit in resp["hits"]["hits"]]
        except Exception as exc:  # noqa: BLE001
            logger.warning("search_rule 失败: %s", exc)
            return []
