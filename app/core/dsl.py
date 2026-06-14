"""
医保领域 DSL 规则语言。

提供规则元素类型、运算符、条件树、规则定义与规则执行引擎，
支持 JSON / DSL 文本双向序列化，兼容主流商业规则引擎格式。

核心概念：
- RuleElement : 规则要素分类（待遇政策、报销比例、支付限制、目录范围、诊疗规范）
- Operator    : 比较运算符
- Condition   : 单个判定条件
- LogicNode   : 由 AND / OR / NOT 组合的条件树
- Rule        : 一条完整规则
- RuleSet     : 规则集合
- RuleEngine  : 对结算单批量执行规则，输出违规列表
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional, Union


class RuleElement(str, Enum):
    """医保规则要素分类。"""
    BENEFIT = "benefit"            # 待遇政策
    REIMBURSE_RATIO = "ratio"      # 报销比例
    PAY_LIMIT = "pay_limit"        # 支付限制
    CATALOG = "catalog"            # 目录范围
    DIAGNOSIS_NORM = "diagnosis"   # 诊疗规范
    ANTI_FRAUD = "anti_fraud"      # 反欺诈


class Operator(str, Enum):
    """比较运算符。"""
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NEQ = "!="
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    CONTAINS = "contains"
    REGEX = "regex"


class LogicalOp(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class RuleStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


# 运算符到 Python 比较的映射
_OP_FUNCS = {
    Operator.GT: lambda a, b: a > b,
    Operator.GTE: lambda a, b: a >= b,
    Operator.LT: lambda a, b: a < b,
    Operator.LTE: lambda a, b: a <= b,
    Operator.EQ: lambda a, b: a == b,
    Operator.NEQ: lambda a, b: a != b,
    Operator.IN: lambda a, b: a in b,
    Operator.NOT_IN: lambda a, b: a not in b,
    Operator.CONTAINS: lambda a, b: b in a,
    Operator.REGEX: lambda a, b: bool(re.search(b, str(a))),
}


@dataclass
class Condition:
    """单个判定条件：claim[<field>] <op> <value>。"""
    field: str
    op: Operator
    value: Any

    def evaluate(self, claim: dict) -> bool:
        actual = _resolve_field(claim, self.field)
        if actual is None:
            return False
        if self.op == Operator.BETWEEN:
            lo, hi = self.value
            return lo <= actual <= hi
        func = _OP_FUNCS.get(self.op)
        if func is None:
            return False
        try:
            return func(actual, self.value)
        except TypeError:
            return False

    def to_dict(self) -> dict:
        return {"field": self.field, "op": self.op.value, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "Condition":
        return cls(field=d["field"], op=Operator(d["op"]), value=d["value"])


@dataclass
class LogicNode:
    """条件树节点：AND / OR / NOT 组合，或叶子 Condition。"""
    op: LogicalOp
    children: list[Union["LogicNode", Condition]] = field(default_factory=list)

    def evaluate(self, claim: dict) -> bool:
        if self.op == LogicalOp.NOT:
            return not self.children[0].evaluate(claim)
        if self.op == LogicalOp.AND:
            return all(c.evaluate(claim) for c in self.children)
        if self.op == LogicalOp.OR:
            return any(c.evaluate(claim) for c in self.children)
        return False

    def to_dict(self) -> dict:
        return {
            "op": self.op.value,
            "children": [
                c.to_dict() if isinstance(c, LogicNode) else c.to_dict()
                for c in self.children
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LogicNode":
        children: list[Union[LogicNode, Condition]] = []
        for c in d.get("children", []):
            if "op" in c and c["op"] in (o.value for o in LogicalOp):
                children.append(cls.from_dict(c))
            else:
                children.append(Condition.from_dict(c))
        return cls(op=LogicalOp(d["op"]), children=children)


def _resolve_field(claim: dict, dotted: str) -> Any:
    """支持 a.b.c 的嵌套字段解析。"""
    cur: Any = claim
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


@dataclass
class Rule:
    """一条完整的医保审核规则。"""
    id: str
    name: str
    element_type: RuleElement
    logic: Union[LogicNode, Condition]
    region: str = "110000"
    priority: int = 50
    status: RuleStatus = RuleStatus.DRAFT
    description: str = ""
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    # 命中后的处置动作
    action: str = "reject"  # reject / warn / flag
    tags: list[str] = field(default_factory=list)

    def is_effective(self, on: Optional[date] = None) -> bool:
        if self.status != RuleStatus.ACTIVE:
            return False
        today = on or date.today()
        if self.effective_date and today < self.effective_date:
            return False
        if self.expiry_date and today > self.expiry_date:
            return False
        return True

    def evaluate(self, claim: dict) -> bool:
        """返回 True 表示命中（违规）。"""
        return self.logic.evaluate(claim)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "element_type": self.element_type.value,
            "logic": self.logic.to_dict(),
            "region": self.region,
            "priority": self.priority,
            "status": self.status.value,
            "description": self.description,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "action": self.action,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        logic_raw = d["logic"]
        if logic_raw["op"] in (o.value for o in LogicalOp):
            logic = LogicNode.from_dict(logic_raw)
        else:
            logic = Condition.from_dict(logic_raw)
        return cls(
            id=d["id"],
            name=d["name"],
            element_type=RuleElement(d["element_type"]),
            logic=logic,
            region=d.get("region", "110000"),
            priority=d.get("priority", 50),
            status=RuleStatus(d.get("status", "draft")),
            description=d.get("description", ""),
            effective_date=date.fromisoformat(d["effective_date"]) if d.get("effective_date") else None,
            expiry_date=date.fromisoformat(d["expiry_date"]) if d.get("expiry_date") else None,
            action=d.get("action", "reject"),
            tags=d.get("tags", []),
        )


@dataclass
class RuleViolation:
    """规则命中（违规）结果。"""
    rule_id: str
    rule_name: str
    element_type: str
    action: str
    description: str
    claim_id: Optional[str] = None


class RuleSet:
    """规则集合，支持按区域、要素类型、状态筛选。"""

    def __init__(self, rules: Optional[list[Rule]] = None) -> None:
        self.rules: list[Rule] = rules or []

    def add(self, rule: Rule) -> None:
        self.rules.append(rule)

    def filter(
        self,
        region: Optional[str] = None,
        element_type: Optional[RuleElement] = None,
        status: RuleStatus = RuleStatus.ACTIVE,
    ) -> list[Rule]:
        result = self.rules
        if status:
            result = [r for r in result if r.status == status]
        if region:
            result = [r for r in result if r.region == region]
        if element_type:
            result = [r for r in result if r.element_type == element_type]
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {"rules": [r.to_dict() for r in self.rules]},
            ensure_ascii=False,
            indent=indent,
        )

    @classmethod
    def from_json(cls, text: str) -> "RuleSet":
        data = json.loads(text)
        return cls(rules=[Rule.from_dict(r) for r in data.get("rules", [])])


class RuleEngine:
    """
    规则执行引擎：对单张或多张结算单批量执行规则。

    用法：
        engine = RuleEngine(rule_set)
        violations = engine.evaluate_claim(claim_dict)
    """

    def __init__(self, rule_set: RuleSet) -> None:
        self.rule_set = rule_set

    def evaluate_claim(
        self,
        claim: dict,
        region: Optional[str] = None,
        element_type: Optional[RuleElement] = None,
    ) -> list[RuleViolation]:
        """对单张结算单执行所有生效规则，返回违规列表。"""
        violations: list[RuleViolation] = []
        rules = self.rule_set.filter(region=region, element_type=element_type)
        # 按 priority 降序
        rules.sort(key=lambda r: r.priority, reverse=True)
        for rule in rules:
            if not rule.is_effective():
                continue
            if rule.evaluate(claim):
                violations.append(
                    RuleViolation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        element_type=rule.element_type.value,
                        action=rule.action,
                        description=rule.description,
                        claim_id=claim.get("claim_id"),
                    )
                )
        return violations

    def evaluate_claims(
        self,
        claims: list[dict],
        region: Optional[str] = None,
    ) -> dict[str, list[RuleViolation]]:
        """批量评估多张结算单。"""
        return {
            str(c.get("claim_id", idx)): self.evaluate_claim(c, region=region)
            for idx, c in enumerate(claims)
        }


# ---------- DSL 文本序列化 ----------
# DSL 文本格式示例：
#   RULE R001 "起付线校验" element=pay_limit region=110000 priority=90 action=reject
#     WHEN total_fee > 1800 AND
#          insurance_type in ["职工","居民"]
#   END

_DSL_HEADER_RE = re.compile(
    r'RULE\s+(?P<id>\S+)\s+"(?P<name>[^"]+)"\s*'
    r'element=(?P<element>\S+)\s*'
    r'(?:region=(?P<region>\S+)\s*)?'
    r'(?:priority=(?P<priority>\d+)\s*)?'
    r'(?:action=(?P<action>\S+)\s*)?',
    re.IGNORECASE,
)


def parse_dsl(text: str) -> RuleSet:
    """将 DSL 文本解析为 RuleSet。"""
    rules: list[Rule] = []
    blocks = re.split(r'\n(?=RULE\s)', text.strip())
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = _DSL_HEADER_RE.match(block)
        if not m:
            continue
        when_match = re.search(r'WHEN\s+(.+?)\s*(?:END|$)', block, re.DOTALL | re.IGNORECASE)
        logic = _parse_when(when_match.group(1).strip()) if when_match else Condition("total_fee", Operator.GT, 0)
        rules.append(
            Rule(
                id=m.group("id"),
                name=m.group("name"),
                element_type=RuleElement(m.group("element")),
                logic=logic,
                region=m.group("region") or "110000",
                priority=int(m.group("priority") or 50),
                action=m.group("action") or "reject",
                status=RuleStatus.ACTIVE,
            )
        )
    return RuleSet(rules=rules)


def _parse_when(expr: str) -> Union[LogicNode, Condition]:
    """简易 WHEN 表达式解析，支持 AND / OR 与单条件。"""
    or_parts = re.split(r'\bOR\b', expr, flags=re.IGNORECASE)
    if len(or_parts) > 1:
        return LogicNode(
            op=LogicalOp.OR,
            children=[_parse_when(p.strip()) for p in or_parts],
        )
    and_parts = re.split(r'\bAND\b', expr, flags=re.IGNORECASE)
    if len(and_parts) > 1:
        return LogicNode(
            op=LogicalOp.AND,
            children=[_parse_single(p.strip()) for p in and_parts],
        )
    return _parse_single(expr)


def _parse_single(expr: str) -> Condition:
    """解析单个条件，如 total_fee > 1800。"""
    for op_str in [">=", "<=", "!=", "==", ">", "<", " in ", " not_in "]:
        if op_str.strip() in expr.replace("  ", " "):
            parts = re.split(r'\s*(>=|<=|!=|==|>|<|in|not_in)\s*', expr, maxsplit=1)
            if len(parts) == 3:
                field, op_token, value = parts
                value = value.strip()
                parsed_val: Any = _parse_value(value)
                op_map = {
                    ">": Operator.GT, ">=": Operator.GTE, "<": Operator.LT,
                    "<=": Operator.LTE, "==": Operator.EQ, "!=": Operator.NEQ,
                    "in": Operator.IN, "not_in": Operator.NOT_IN,
                }
                return Condition(field=field.strip(), op=op_map[op_token], value=parsed_val)
    raise ValueError(f"无法解析条件: {expr}")


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        items = [i.strip().strip('"').strip("'") for i in inner.split(",")]
        return items
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw
