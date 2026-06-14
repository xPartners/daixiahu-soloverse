"""异常检测模型：基于统计 + LLM 识别结算数据中的异常/骗保模式。

统计层使用 Python 标准库 statistics 模块，不引入额外依赖。
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Optional

from app.config import settings
from app.core.exceptions import ModelInferenceError
from app.models.llm_base import LLMClient, get_llm


# 单日项目频次异常阈值
_ITEM_FREQ_THRESHOLD = 10

_SYSTEM_PROMPT = """你是医保基金监管与反欺诈分析专家。
你将收到一组基于统计分析发现的结算异常摘要，请归纳其中的违规/骗保模式，
并为每种模式建议一条可执行的审核规则逻辑。

请以 JSON 数组形式输出，每个元素包含：
{
  "pattern_name": "模式名称",
  "description": "模式说明",
  "severity": "low|medium|high",
  "suggested_rule_logic": {"op": "AND|OR|NOT", "children": [...]} 或 {"field": "...", "op": "...", "value": ...}
}

仅输出 JSON 数组，不要包含任何解释性文字。"""

_USER_TEMPLATE = """以下是基于统计分析发现的结算异常摘要：

{summary}

请归纳违规/骗保模式并建议审核规则逻辑，严格按 JSON 数组格式输出。"""


class AnomalyDetector:
    """基于统计 + LLM 识别结算数据中的异常/骗保模式。"""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm: LLMClient = llm or get_llm()

    def detect(
        self,
        settlements: list[dict],
        region: Optional[str] = None,
    ) -> list[dict]:
        """检测结算数据中的异常模式。

        返回 list[dict]，每个 dict:
        {pattern_name, description, affected_claims, severity, suggested_rule_logic}
        """
        if not settlements:
            return []
        # 第一层：统计检测
        stat_anomalies = self._statistical_detect(settlements)
        # 第二层：LLM 归纳分析
        llm_patterns = self._llm_analyze(stat_anomalies, settlements, region)
        # 合并结果
        return stat_anomalies + llm_patterns

    # ---------- 统计检测 ----------
    def _statistical_detect(self, settlements: list[dict]) -> list[dict]:
        """基于标准库统计的异常检测。"""
        anomalies: list[dict] = []
        anomalies.extend(self._detect_frequency_anomaly(settlements))
        anomalies.extend(self._detect_amount_anomaly(settlements))
        anomalies.extend(self._detect_item_frequency_anomaly(settlements))
        return anomalies

    def _detect_frequency_anomaly(self, settlements: list[dict]) -> list[dict]:
        """频次异常：同一 org_code + diagnosis_code 结算频次 > 均值 + 2 倍标准差。"""
        anomalies: list[dict] = []
        group_counts: dict[tuple, int] = defaultdict(int)
        group_claims: dict[tuple, list[dict]] = defaultdict(list)
        for s in settlements:
            key = (s.get("org_code"), s.get("diagnosis_code"))
            group_counts[key] += 1
            group_claims[key].append(s)
        counts = list(group_counts.values())
        # 样本数不足无法计算标准差
        if len(counts) < 2:
            return anomalies
        mean_c = statistics.mean(counts)
        stdev_c = statistics.stdev(counts)
        threshold = mean_c + 2 * stdev_c
        for key, cnt in group_counts.items():
            if cnt > threshold and threshold > 0:
                affected = [
                    c.get("claim_id") for c in group_claims[key] if c.get("claim_id")
                ]
                anomalies.append(
                    {
                        "pattern_name": "频次异常",
                        "description": (
                            f"机构 {key[0]} 诊断 {key[1]} 的结算频次 {cnt} "
                            f"超过均值+2倍标准差阈值 {threshold:.2f}"
                        ),
                        "affected_claims": affected,
                        "severity": "high",
                        "suggested_rule_logic": {
                            "op": "AND",
                            "children": [
                                {"field": "org_code", "op": "==", "value": key[0]},
                                {
                                    "field": "diagnosis_code",
                                    "op": "==",
                                    "value": key[1],
                                },
                            ],
                        },
                    }
                )
        return anomalies

    def _detect_amount_anomaly(self, settlements: list[dict]) -> list[dict]:
        """金额异常：total_fee > 该 org_code 均值 + 3 倍标准差。"""
        anomalies: list[dict] = []
        org_fees: dict[str, list[float]] = defaultdict(list)
        org_claims: dict[str, list[dict]] = defaultdict(list)
        for s in settlements:
            org = s.get("org_code")
            fee = s.get("total_fee")
            if org is None or fee is None:
                continue
            try:
                fee = float(fee)
            except (TypeError, ValueError):
                continue
            org_fees[org].append(fee)
            org_claims[org].append(s)
        for org, fees in org_fees.items():
            if len(fees) < 2:
                continue
            mean_f = statistics.mean(fees)
            stdev_f = statistics.stdev(fees)
            threshold = mean_f + 3 * stdev_f
            for claim, fee in zip(org_claims[org], fees):
                if fee > threshold and stdev_f > 0:
                    claim_id = claim.get("claim_id")
                    anomalies.append(
                        {
                            "pattern_name": "金额异常",
                            "description": (
                                f"机构 {org} 的结算金额 {fee:.2f} "
                                f"超过该机构均值+3倍标准差阈值 {threshold:.2f}"
                            ),
                            "affected_claims": [claim_id] if claim_id else [],
                            "severity": "medium",
                            "suggested_rule_logic": {
                                "field": "total_fee",
                                "op": ">",
                                "value": round(threshold, 2),
                            },
                        }
                    )
        return anomalies

    def _detect_item_frequency_anomaly(self, settlements: list[dict]) -> list[dict]:
        """项目频次异常：同一 patient 单日内 items 数 > 阈值(10)。"""
        anomalies: list[dict] = []
        patient_day: dict[tuple, list[dict]] = defaultdict(list)
        for s in settlements:
            key = (s.get("patient_id"), s.get("settle_date"))
            patient_day[key].append(s)
        for key, claims in patient_day.items():
            total_items = 0
            for c in claims:
                items = c.get("items", [])
                total_items += len(items) if isinstance(items, list) else 0
            if total_items > _ITEM_FREQ_THRESHOLD:
                affected = [
                    c.get("claim_id") for c in claims if c.get("claim_id")
                ]
                anomalies.append(
                    {
                        "pattern_name": "项目频次异常",
                        "description": (
                            f"患者 {key[0]} 在 {key[1]} 单日项目数 {total_items} "
                            f"超过阈值 {_ITEM_FREQ_THRESHOLD}"
                        ),
                        "affected_claims": affected,
                        "severity": "medium",
                        "suggested_rule_logic": {
                            "field": "items",
                            "op": "regex",
                            "value": f".{{{_ITEM_FREQ_THRESHOLD},}}",
                        },
                    }
                )
        return anomalies

    # ---------- LLM 分析 ----------
    def _llm_analyze(
        self,
        stat_anomalies: list[dict],
        settlements: list[dict],
        region: Optional[str] = None,
    ) -> list[dict]:
        """将统计异常摘要喂给 LLM，归纳违规模式并建议规则。"""
        if not stat_anomalies:
            # 无统计异常时也尝试让 LLM 做整体分析
            summary = self._summarize_settlements(settlements)
        else:
            summary = self._summarize_anomalies(stat_anomalies)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(summary=summary),
            },
        ]
        try:
            result = self.llm.chat_json(messages)
        except ModelInferenceError:
            # LLM 分析失败不影响统计结果，静默返回空
            return []
        raw_patterns = result if isinstance(result, list) else result.get("patterns", [])
        if not isinstance(raw_patterns, list):
            return []
        patterns: list[dict] = []
        for item in raw_patterns:
            if not isinstance(item, dict):
                continue
            name = item.get("pattern_name") or item.get("name")
            if not name:
                continue
            severity = str(item.get("severity", "medium")).strip().lower()
            if severity not in {"low", "medium", "high"}:
                severity = "medium"
            patterns.append(
                {
                    "pattern_name": str(name),
                    "description": str(item.get("description", "")),
                    "affected_claims": [],
                    "severity": severity,
                    "suggested_rule_logic": item.get("suggested_rule_logic", {}),
                }
            )
        return patterns

    @staticmethod
    def _summarize_anomalies(anomalies: list[dict]) -> str:
        """将统计异常整理为 LLM 可读的摘要文本。"""
        lines = [f"共发现 {len(anomalies)} 条统计异常："]
        for idx, a in enumerate(anomalies, 1):
            lines.append(
                f"{idx}. [{a.get('pattern_name')}] {a.get('description')} "
                f"(严重度: {a.get('severity')}, 涉及结算: {len(a.get('affected_claims', []))} 条)"
            )
        return "\n".join(lines)

    @staticmethod
    def _summarize_settlements(settlements: list[dict]) -> str:
        """整体结算数据摘要。"""
        total = len(settlements)
        orgs = {s.get("org_code") for s in settlements if s.get("org_code")}
        fees = []
        for s in settlements:
            fee = s.get("total_fee")
            if fee is not None:
                try:
                    fees.append(float(fee))
                except (TypeError, ValueError):
                    pass
        fee_info = ""
        if fees:
            fee_info = (
                f"总费用均值 {statistics.mean(fees):.2f}，"
                f"最大 {max(fees):.2f}，最小 {min(fees):.2f}。"
            )
        return (
            f"共 {total} 条结算记录，涉及 {len(orgs)} 家机构。{fee_info}"
            "请分析其中可能存在的违规或骗保模式。"
        )
