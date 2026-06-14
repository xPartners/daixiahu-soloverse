"""反欺诈规则自主生成引擎。

基于 AnomalyDetector 检测结算数据中的异常/骗保模式，
并将每个模式的 suggested_rule_logic 转化为可执行的候选规则。
"""
from __future__ import annotations

import uuid
from typing import Optional

from app.models.anomaly_detector import AnomalyDetector

# severity 权重映射
_SEVERITY_WEIGHTS: dict[str, float] = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.3,
}


class AntiFraudEngine:
    """反欺诈规则自主生成引擎。"""

    def __init__(self, detector: Optional[AnomalyDetector] = None) -> None:
        self.detector: AnomalyDetector = detector or AnomalyDetector()

    def generate(self, settlements: list[dict], region: str = None) -> dict:
        """生成反欺诈候选规则。

        返回 dict 含 candidate_rules(list[dict]), patterns(list[dict]), confidence(float)。
        """
        # 1. 检测异常模式
        patterns = self.detector.detect(settlements, region=region)

        # 2. 将每个 pattern 的 suggested_rule_logic 转化为候选规则
        candidate_rules: list[dict] = []
        for idx, pattern in enumerate(patterns):
            logic = pattern.get("suggested_rule_logic")
            if not logic:
                continue
            severity = pattern.get("severity", "medium")
            rule = {
                "id": f"AF_{uuid.uuid4().hex[:8]}",
                "name": pattern.get("pattern_name", f"反欺诈规则{idx + 1}"),
                "element_type": "anti_fraud",
                "logic": logic,
                "description": pattern.get("description", ""),
                "action": "flag",
                "priority": 80 if severity == "high" else 60,
                "status": "active",
                "region": region,
                "tags": [severity],
            }
            candidate_rules.append(rule)

        # 3. 计算置信度
        confidence = self._calc_confidence(patterns)

        return {
            "candidate_rules": candidate_rules,
            "patterns": patterns,
            "confidence": confidence,
        }

    @staticmethod
    def _calc_confidence(patterns: list[dict]) -> float:
        """基于 patterns 数量和平均 severity 计算置信度。

        severity 权重：high=1.0, medium=0.6, low=0.3
        """
        if not patterns:
            return 0.0
        total_weight = sum(
            _SEVERITY_WEIGHTS.get(p.get("severity", "medium"), 0.6)
            for p in patterns
        )
        avg_severity = total_weight / len(patterns)
        # pattern 数量因子：越多越可信，上限 1.0
        count_factor = min(len(patterns) / 10.0, 1.0)
        confidence = round(avg_severity * 0.7 + count_factor * 0.3, 4)
        return min(max(confidence, 0.0), 1.0)
