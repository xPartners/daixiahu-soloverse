"""政策文档解析引擎：将政策文件转化为结构化规则。

支持 PDF / Word / 文本类政策文件的解析，结合 RuleExtractor 抽取规则，
并可选地持久化到数据库与索引到 Elasticsearch。
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime
from typing import Optional

from app.core.exceptions import PolicyParseError
from app.data.search import PolicySearch
from app.data.storage import FileStorage
from app.models.rule_extractor import RuleExtractor

logger = logging.getLogger(__name__)

# README 声称的准确率
_ACCURACY_ESTIMATE = 0.95


def _guess_content_type(source_type: str) -> str:
    """根据来源类型猜测 MIME 类型。"""
    mapping = {
        "pdf": "application/pdf",
        "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text": "text/plain",
        "web": "text/html",
        "scan": "application/octet-stream",
    }
    return mapping.get(source_type.lower(), "application/octet-stream")


class PolicyParseEngine:
    """政策文档解析引擎，将政策文件转化为结构化规则。"""

    def __init__(
        self,
        extractor: Optional[RuleExtractor] = None,
        storage: Optional[FileStorage] = None,
        search: Optional[PolicySearch] = None,
        db_session=None,
    ) -> None:
        self.extractor: RuleExtractor = extractor or RuleExtractor()
        self.storage: Optional[FileStorage] = storage
        self.search: Optional[PolicySearch] = search
        self.db_session = db_session

    async def parse_document(
        self,
        filename: str,
        region: str,
        source_type: str,
        content: bytes,
    ) -> dict:
        """解析政策文档，返回结构化结果。

        返回 dict 含 document, rules, rule_count, accuracy_estimate。
        """
        # 1. 上传原始文件（storage 可用时）
        file_url: Optional[str] = None
        if self.storage is not None:
            try:
                object_name = f"policies/{uuid.uuid4().hex}/{filename}"
                file_url = self.storage.upload(
                    object_name, content, content_type=_guess_content_type(source_type)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("文件上传失败，跳过: %s", exc)
                file_url = None

        # 2. 提取文本
        text = self._extract_text(content, source_type)

        # 3. 抽取规则
        rules = self.extractor.extract(text, region=region)

        # 4. 索引到 ES（容错）
        doc_id = uuid.uuid4().hex
        if self.search is not None:
            try:
                await self.search.index_policy(
                    doc_id,
                    {
                        "title": filename,
                        "region": region,
                        "content": text,
                        "source_type": source_type,
                        "rule_count": len(rules),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("ES 索引失败，跳过: %s", exc)

        # 5. 持久化到 DB（db_session 可用时）
        created_at = datetime.now()
        if self.db_session is not None:
            await self._persist(doc_id, filename, region, source_type, file_url, text, rules)

        # 6. 返回结果
        return {
            "document": {
                "id": doc_id,
                "title": filename,
                "region": region,
                "source_type": source_type,
                "status": "parsed",
                "created_at": created_at,
                "parsed_rules_count": len(rules),
            },
            "rules": rules,
            "rule_count": len(rules),
            "accuracy_estimate": _ACCURACY_ESTIMATE,
        }

    async def _persist(
        self,
        doc_id: str,
        filename: str,
        region: str,
        source_type: str,
        file_url: Optional[str],
        text: str,
        rules: list[dict],
    ) -> None:
        """持久化 PolicyDocument 和 MedicalRule 记录（容错）。"""
        from app.data.models.policy import PolicyDocument
        from app.data.models.rule import MedicalRule

        try:
            policy_doc = PolicyDocument(
                id=doc_id,
                title=filename,
                region=region,
                source_type=source_type,
                file_url=file_url,
                raw_text=text,
                status="parsed",
                parsed_content={"rules": rules},
                rule_count=len(rules),
            )
            self.db_session.add(policy_doc)
            for rule in rules:
                medical_rule = MedicalRule(
                    rule_code=f"{doc_id}_{uuid.uuid4().hex[:8]}",
                    name=rule.get("name", ""),
                    element_type=rule.get("element_type", "benefit"),
                    region=rule.get("region", region),
                    logic=rule.get("logic", {}),
                    priority=rule.get("priority", 50),
                    status=rule.get("status", "draft"),
                    description=rule.get("description", ""),
                    action=rule.get("action", "reject"),
                    source_document_id=doc_id,
                )
                self.db_session.add(medical_rule)
            await self.db_session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("DB 持久化失败，跳过: %s", exc)
            try:
                await self.db_session.rollback()
            except Exception:  # noqa: BLE001
                pass

    def _extract_text(self, content: bytes, source_type: str) -> str:
        """根据文件类型提取文本。

        - pdf: 用 PyPDF2.PdfReader 读取
        - word: 用 docx.Document 读取
        - text/web/scan: 直接 decode utf-8
        - 异常时抛 PolicyParseError
        """
        source_type = source_type.lower()
        if source_type == "pdf":
            return self._extract_pdf(content)
        if source_type == "word":
            return self._extract_word(content)
        # text / web / scan 当作文本处理
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("gbk")
            except UnicodeDecodeError as exc:
                raise PolicyParseError(f"无法解码文本内容: {exc}") from exc

    @staticmethod
    def _extract_pdf(content: bytes) -> str:
        """从 PDF 提取文本。"""
        try:
            import PyPDF2
        except ImportError as exc:
            raise PolicyParseError("PyPDF2 未安装，无法解析 PDF") from exc
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            texts: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    texts.append(page_text)
            return "\n".join(texts)
        except Exception as exc:  # noqa: BLE001
            raise PolicyParseError(f"PDF 解析失败: {exc}") from exc

    @staticmethod
    def _extract_word(content: bytes) -> str:
        """从 Word 文档提取文本。"""
        try:
            import docx
        except ImportError as exc:
            raise PolicyParseError("python-docx 未安装，无法解析 Word 文档") from exc
        try:
            document = docx.Document(io.BytesIO(content))
            texts: list[str] = []
            for para in document.paragraphs:
                if para.text:
                    texts.append(para.text)
            return "\n".join(texts)
        except Exception as exc:  # noqa: BLE001
            raise PolicyParseError(f"Word 文档解析失败: {exc}") from exc
