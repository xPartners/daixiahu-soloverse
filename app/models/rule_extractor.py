"""规则抽取 NLP 模型：从医保政策文本中抽取结构化审核规则。

依赖 LLMClient 扮演医保政策专家，输出可被 DSL 规则引擎消费的条件树。
"""
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.core.exceptions import ModelInferenceError, RuleExtractionError
from app.models.llm_base import LLMClient, get_llm


# 五类规则要素
_VALID_ELEMENT_TYPES = {"benefit", "ratio", "pay_limit", "catalog", "diagnosis"}
# 合法逻辑组合算子
_LOGICAL_OPS = {"AND", "OR", "NOT"}
# 合法比较算子（与 core.dsl.Operator 对齐）
_COMPARISON_OPS = {
    ">", ">=", "<", "<=", "==", "!=", "in", "not_in",
    "between", "contains", "regex",
}

_SYSTEM_PROMPT = """你是一位资深的中国医保政策专家，精通各地医保待遇、报销、支付与诊疗规范政策。
你的任务是从给定的医保政策文本中抽取结构化审核规则。

规则要素分为五类：
- benefit（待遇政策）：参保身份、险种、待遇享受条件等
- ratio（报销比例）：各级医院、不同金额区间的报销比例
- pay_limit（支付限制）：起付线、封顶线、年度限额、次数限制
- catalog（目录范围）：药品、诊疗项目、耗材目录限定
- diagnosis（诊疗规范）：诊断与用药/检查的合理性限定

请以 JSON 数组形式输出，每个规则包含以下字段：
{
  "name": "规则名称",
  "element_type": "benefit|ratio|pay_limit|catalog|diagnosis",
  "logic": 组合条件或叶子条件,
  "description": "规则说明",
  "action": "reject|warn|flag",
  "priority": 1-100 的整数
}

logic 字段说明：
- 叶子条件为 {"field": "结算单字段名", "op": "运算符", "value": "比较值"}
- 组合条件为 {"op": "AND|OR|NOT", "children": [子条件...]}
- 运算符可选：> >= < <= == != in not_in between contains regex
- 常见结算单字段：insurance_type(险种)、org_level(医院等级)、total_fee(总费用)、diagnosis_code(诊断编码)、age(年龄)、gender(性别)、items(项目列表)、region(地区) 等

仅输出 JSON 数组，不要包含任何解释性文字。"""

_USER_TEMPLATE = """请从以下医保政策文本中抽取结构化审核规则：

---
{policy_text}
---

请严格按要求的 JSON 数组格式输出所有可识别的规则。"""


class RuleExtractor:
    """从医保政策文本中抽取结构化审核规则。"""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm: LLMClient = llm or get_llm()

    def extract(self, policy_text: str, region: Optional[str] = None) -> list[dict]:
        """抽取规则，返回 list[dict]。

        每个 dict 包含 name, element_type, logic, description, action, priority。
        """
        if not policy_text or not policy_text.strip():
            return []
        effective_region = region or settings.DEFAULT_RULE_REGION
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(policy_text=policy_text.strip()),
            },
        ]
        try:
            result = self.llm.chat_json(messages)
        except ModelInferenceError as exc:
            raise RuleExtractionError(f"规则抽取失败: {exc}") from exc
        # chat_json 可能返回 list 或包含 rules 键的 dict
        if isinstance(result, list):
            raw_rules = result
        elif isinstance(result, dict):
            raw_rules = result.get("rules", result.get("data", []))
            if isinstance(raw_rules, dict):
                raw_rules = [raw_rules]
        else:
            raw_rules = []
        return self._postprocess(raw_rules, effective_region)

    # ---------- 后处理 ----------
    def _postprocess(self, raw_rules, region: str) -> list[dict]:
        """清洗 LLM 输出，补全默认字段，过滤无效规则。"""
        cleaned: list[dict] = []
        if not isinstance(raw_rules, list):
            return cleaned
        for raw in raw_rules:
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            logic = raw.get("logic")
            if not name or not logic:
                continue
            # 校验 logic 结构合法性
            if not self._is_valid_logic(logic):
                continue
            # 校验并归一化 element_type
            element_type = str(raw.get("element_type", "benefit")).strip().lower()
            if element_type not in _VALID_ELEMENT_TYPES:
                element_type = "benefit"
            # 解析 priority，非法时回退默认值
            try:
                priority = int(raw.get("priority", 50))
            except (TypeError, ValueError):
                priority = 50
            priority = max(1, min(100, priority))
            # 归一化 action
            action = str(raw.get("action", "reject")).strip().lower()
            if action not in {"reject", "warn", "flag"}:
                action = "reject"
            rule = {
                "name": str(name).strip(),
                "element_type": element_type,
                "logic": logic,
                "description": str(raw.get("description", "")).strip(),
                "action": action,
                "priority": priority,
                "region": raw.get("region", region),
                "status": "active",
            }
            cleaned.append(rule)
        return cleaned

    @staticmethod
    def _is_valid_logic(logic) -> bool:
        """校验 logic 是否为合法的条件树结构。"""
        if not isinstance(logic, dict):
            return False
        op = logic.get("op")
        if op is None:
            return False
        # 组合节点：AND / OR / NOT，需带非空 children
        if op in _LOGICAL_OPS:
            children = logic.get("children")
            return isinstance(children, list) and len(children) > 0
        # 叶子节点：需包含 field 与 value，op 为合法比较算子
        if op in _COMPARISON_OPS:
            return "field" in logic and "value" in logic
        return False
