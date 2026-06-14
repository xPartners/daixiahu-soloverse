"""仿真推演引擎：模拟新规则运行效果。

接收一条规则和一批结算数据，统计命中数、基金追回金额、假阳性率等指标，
辅助评估规则的实战效果与风险等级。
"""
from __future__ import annotations

import time
from typing import Optional

from app.core.dsl import Rule, RuleEngine, RuleSet
from app.core.exceptions import SimulationError


class SimulationEngine:
    """仿真推演引擎，模拟新规则运行效果。"""

    def __init__(self, rule_set: Optional[RuleSet] = None) -> None:
        self.rule_set: Optional[RuleSet] = rule_set

    def simulate(
        self,
        rule_dict: dict,
        settlements: list[dict],
        region: str = None,
    ) -> dict:
        """仿真推演单条规则对结算数据集的效果。

        返回 SimulationResult 兼容的 dict。
        """
        if not settlements:
            return self._empty_result(rule_dict)

        # 1. 构造 Rule 对象（补充默认 id）
        rule_id = rule_dict.get("id") or f"SIM_{int(time.time())}"
        prepared = dict(rule_dict)
        prepared["id"] = rule_id
        try:
            rule = Rule.from_dict(prepared)
        except Exception as exc:  # noqa: BLE001
            raise SimulationError(f"规则构造失败: {exc}") from exc

        # 2. 创建临时 RuleEngine 对该 rule 评估所有 settlements
        temp_set = RuleSet(rules=[rule])
        engine = RuleEngine(temp_set)

        # 3. 统计各项指标
        total_evaluated = len(settlements)
        hit_count = 0
        recovered_amount = 0.0
        false_positive = 0
        non_violation_total = 0
        affected_orgs: set[str] = set()
        hit_details: list[dict] = []

        for s in settlements:
            claim = self._to_claim(s)
            violations = engine.evaluate_claim(claim, region=region)

            is_violation = bool(s.get("is_violation", False))
            if not is_violation:
                non_violation_total += 1

            if violations:
                hit_count += 1
                # 累计基金追回金额（insurance_fee 总和）
                insurance_fee = s.get("insurance_fee", 0)
                try:
                    recovered_amount += float(insurance_fee)
                except (TypeError, ValueError):
                    pass
                # 涉及机构（去重 org_code）
                org_code = s.get("org_code")
                if org_code:
                    affected_orgs.add(str(org_code))
                # 假阳性：非违规但被命中
                if not is_violation:
                    false_positive += 1
                hit_details.append(
                    {
                        "claim_id": s.get("claim_id"),
                        "org_code": s.get("org_code"),
                        "is_violation": is_violation,
                    }
                )

        # 4. 假阳性率
        if non_violation_total > 0:
            false_positive_rate = round(false_positive / non_violation_total, 4)
        else:
            false_positive_rate = 0.0

        # 5. 风险等级
        if false_positive_rate < 0.05:
            risk_level = "low"
        elif false_positive_rate <= 0.15:
            risk_level = "medium"
        else:
            risk_level = "high"

        return {
            "rule_id": rule_id,
            "recovered_amount": round(recovered_amount, 2),
            "false_positive_rate": false_positive_rate,
            "affected_org_count": len(affected_orgs),
            "risk_level": risk_level,
            "total_evaluated": total_evaluated,
            "hit_count": hit_count,
            "details": {
                "affected_orgs": sorted(affected_orgs),
                "hit_claims": hit_details,
            },
        }

    @staticmethod
    def _to_claim(settlement: dict) -> dict:
        """将结算单 dict 转换为规则引擎可消费的 claim dict。"""
        claim = dict(settlement)
        # 兼容 diagnosis_codes / diagnosis_code 两种字段名
        if "diagnosis_code" not in claim:
            codes = settlement.get("diagnosis_codes", [])
            if isinstance(codes, list) and codes:
                claim["diagnosis_code"] = codes[0]
        return claim

    @staticmethod
    def _empty_result(rule_dict: dict) -> dict:
        """空结算数据集的结果。"""
        rule_id = rule_dict.get("id") or f"SIM_{int(time.time())}"
        return {
            "rule_id": rule_id,
            "recovered_amount": 0.0,
            "false_positive_rate": 0.0,
            "affected_org_count": 0,
            "risk_level": "low",
            "total_evaluated": 0,
            "hit_count": 0,
            "details": {},
        }
