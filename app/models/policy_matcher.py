"""政策语义匹配模型：异地就医场景下对比参保地与就医地政策差异。

依赖 LLMClient 扮演医保政策比对专家，输出两地政策差异的结构化结果。
"""
from __future__ import annotations

import json
from typing import Optional

from app.models.llm_base import LLMClient, get_llm


_SYSTEM_PROMPT = """你是中国医保政策比对专家，精通各省市医保政策差异。
你的任务是对比两地的医保政策参数，找出关键差异点。

请以 JSON 数组形式输出差异列表，每个差异包含：
{
  "field": "政策字段名（如 deductible 起付线、reimbursement_ratio 报销比例、pay_limit 封顶线等）",
  "insured_region_value": "参保地对应的值",
  "medical_region_value": "就医地对应的值",
  "description": "差异说明（中文）"
}

仅输出 JSON 数组，不要包含任何解释性文字。"""

_CLAUSES_SYSTEM_PROMPT = """你是中国医保政策语义比对专家。
你的任务是对比两段医保政策文本，找出相似点与差异点。

请以 JSON 对象形式输出：
{
  "similarities": ["相似点1", "相似点2"],
  "differences": ["差异点1", "差异点2"],
  "summary": "整体对比总结（中文）"
}

仅输出 JSON 对象，不要包含任何解释性文字。"""


class PolicyMatcher:
    """政策语义匹配模型，用于异地就医场景下对比参保地与就医地政策差异。"""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm: LLMClient = llm or get_llm()

    def match(self, insured_policy: dict, medical_policy: dict) -> list[dict]:
        """对比两地政策参数，返回差异列表。

        每个差异 dict 含 field, insured_region_value, medical_region_value, description。
        """
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"参保地政策参数：\n{json.dumps(insured_policy, ensure_ascii=False, indent=2)}\n\n"
                    f"就医地政策参数：\n{json.dumps(medical_policy, ensure_ascii=False, indent=2)}\n\n"
                    "请对比两地政策差异，严格按 JSON 数组格式输出。"
                ),
            },
        ]
        try:
            result = self.llm.chat_json(messages)
        except Exception:
            return self._fallback_match(insured_policy, medical_policy)

        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("differences", [])
        return []

    def compare_clauses(self, insured_text: str, medical_text: str) -> dict:
        """用 LLM 对比两段政策文本，返回语义比对结果。

        返回 dict 含 similarities(list[str]), differences(list[str]), summary(str)。
        """
        messages = [
            {"role": "system", "content": _CLAUSES_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"参保地政策文本：\n{insured_text}\n\n"
                    f"就医地政策文本：\n{medical_text}\n\n"
                    "请对比这两段政策文本，严格按 JSON 对象格式输出。"
                ),
            },
        ]
        try:
            result = self.llm.chat_json(messages)
        except Exception:
            return {
                "similarities": [],
                "differences": [],
                "summary": "政策比对服务暂不可用，请稍后重试。",
            }

        if isinstance(result, dict):
            return {
                "similarities": result.get("similarities", []),
                "differences": result.get("differences", []),
                "summary": result.get("summary", ""),
            }
        return {"similarities": [], "differences": [], "summary": ""}

    @staticmethod
    def _fallback_match(insured_policy: dict, medical_policy: dict) -> list[dict]:
        """LLM 不可用时的字段对比回退方案。"""
        differences: list[dict] = []
        all_keys = set(insured_policy.keys()) | set(medical_policy.keys())
        for key in all_keys:
            insured_val = insured_policy.get(key)
            medical_val = medical_policy.get(key)
            if insured_val != medical_val:
                differences.append(
                    {
                        "field": key,
                        "insured_region_value": insured_val,
                        "medical_region_value": medical_val,
                        "description": f"参保地与就医地在「{key}」上存在差异。",
                    }
                )
        return differences
