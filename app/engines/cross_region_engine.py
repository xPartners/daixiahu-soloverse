"""异地就医规则双向智能适配引擎。

内置各省市基础政策参数表，结合 PolicyMatcher 做参保地与就医地的
政策语义比对，输出合规性判断、报销比例、支付限额与差异说明。
"""
from __future__ import annotations

from typing import Optional

from app.data.search import PolicySearch
from app.models.policy_matcher import PolicyMatcher


class CrossRegionEngine:
    """异地就医规则双向智能适配引擎。"""

    # 内置各省市基础政策参数表
    # 字段：deductible(起付线), reimbursement_ratio(报销比例),
    #       pay_limit(封顶线), fund_share_ratio(基金分担比例)
    _REGION_POLICIES: dict[str, dict] = {
        "110000": {  # 北京
            "name": "北京",
            "inpatient": {
                "deductible": 1300,
                "reimbursement_ratio": 0.85,
                "pay_limit": 500000,
                "fund_share_ratio": 0.85,
            },
            "outpatient": {
                "deductible": 1800,
                "reimbursement_ratio": 0.70,
                "pay_limit": 20000,
                "fund_share_ratio": 0.70,
            },
        },
        "310000": {  # 上海
            "name": "上海",
            "inpatient": {
                "deductible": 1500,
                "reimbursement_ratio": 0.85,
                "pay_limit": 550000,
                "fund_share_ratio": 0.85,
            },
            "outpatient": {
                "deductible": 1500,
                "reimbursement_ratio": 0.75,
                "pay_limit": 25000,
                "fund_share_ratio": 0.75,
            },
        },
        "440000": {  # 广东
            "name": "广东",
            "inpatient": {
                "deductible": 1000,
                "reimbursement_ratio": 0.80,
                "pay_limit": 600000,
                "fund_share_ratio": 0.80,
            },
            "outpatient": {
                "deductible": 1000,
                "reimbursement_ratio": 0.65,
                "pay_limit": 20000,
                "fund_share_ratio": 0.65,
            },
        },
        "510000": {  # 四川
            "name": "四川",
            "inpatient": {
                "deductible": 800,
                "reimbursement_ratio": 0.75,
                "pay_limit": 400000,
                "fund_share_ratio": 0.75,
            },
            "outpatient": {
                "deductible": 800,
                "reimbursement_ratio": 0.60,
                "pay_limit": 15000,
                "fund_share_ratio": 0.60,
            },
        },
    }

    # 未知地区的默认政策参数
    _DEFAULT_POLICY: dict = {
        "deductible": 1000,
        "reimbursement_ratio": 0.75,
        "pay_limit": 400000,
        "fund_share_ratio": 0.75,
    }

    def __init__(
        self,
        matcher: Optional[PolicyMatcher] = None,
        search: Optional[PolicySearch] = None,
    ) -> None:
        self.matcher: Optional[PolicyMatcher] = matcher
        self.search: Optional[PolicySearch] = search

    async def adapt(
        self,
        claim: dict,
        insured_region: str,
        medical_region: str,
        scenario: str = "inpatient",
    ) -> dict:
        """异地就医规则适配，返回 CrossRegionResult 兼容的 dict。"""
        # chronic / maternity 等场景回退到 inpatient 参数
        effective_scenario = scenario if scenario in ("inpatient", "outpatient") else "inpatient"

        # 1. 取参保地和就医地参数
        insured_policy = self._get_region_policy(insured_region, effective_scenario)
        medical_policy = self._get_region_policy(medical_region, effective_scenario)

        # 2. 对比差异（PolicyMatcher 可用时用 LLM，否则字段对比）
        if self.matcher is not None:
            try:
                differences = self.matcher.match(insured_policy, medical_policy)
            except Exception:  # noqa: BLE001
                differences = self._compare_fields(insured_policy, medical_policy)
        else:
            differences = self._compare_fields(insured_policy, medical_policy)

        # 3. 计算核心指标（以参保地政策为准）
        reimbursement_ratio = insured_policy.get("reimbursement_ratio", 0.0)
        pay_limit = insured_policy.get("pay_limit", 0.0)
        fund_share_ratio = insured_policy.get("fund_share_ratio", 0.0)

        # 4. 合规性判断
        compliant = self._check_compliance(claim, insured_policy)

        # 5. 生成总结
        insured_name = self._get_region_name(insured_region)
        medical_name = self._get_region_name(medical_region)
        scenario_name = self._scenario_name(effective_scenario)
        summary = (
            f"参保地（{insured_name}）与就医地（{medical_name}）的{scenario_name}医保政策"
            f"存在 {len(differences)} 项差异。"
            f"报销比例 {reimbursement_ratio:.0%}，支付限额 {pay_limit:,.0f} 元。"
        )
        if compliant:
            summary += "当前结算符合参保地政策要求。"
        else:
            summary += "当前结算可能存在政策差异，需人工复核。"

        return {
            "compliant": compliant,
            "reimbursement_ratio": reimbursement_ratio,
            "pay_limit": float(pay_limit),
            "fund_share_ratio": fund_share_ratio,
            "differences": differences,
            "summary": summary,
        }

    def _get_region_policy(self, region: str, scenario: str) -> dict:
        """获取某地区某场景的政策参数。"""
        region_data = self._REGION_POLICIES.get(region)
        if region_data is None:
            return dict(self._DEFAULT_POLICY)
        return region_data.get(scenario, region_data.get("inpatient", dict(self._DEFAULT_POLICY)))

    def _get_region_name(self, region: str) -> str:
        """获取地区名称。"""
        region_data = self._REGION_POLICIES.get(region)
        if region_data:
            return region_data.get("name", region)
        return region

    @staticmethod
    def _scenario_name(scenario: str) -> str:
        """场景中文名。"""
        return {"inpatient": "住院", "outpatient": "门诊"}.get(scenario, "住院")

    @staticmethod
    def _compare_fields(insured: dict, medical: dict) -> list[dict]:
        """字段对比，生成差异列表。"""
        field_names = {
            "deductible": "起付线",
            "reimbursement_ratio": "报销比例",
            "pay_limit": "封顶线",
            "fund_share_ratio": "基金分担比例",
        }
        differences: list[dict] = []
        for key, label in field_names.items():
            insured_val = insured.get(key)
            medical_val = medical.get(key)
            if insured_val != medical_val:
                differences.append(
                    {
                        "field": key,
                        "insured_region_value": insured_val,
                        "medical_region_value": medical_val,
                        "description": f"{label}：参保地与就医地存在差异。",
                    }
                )
        return differences

    @staticmethod
    def _check_compliance(claim: dict, insured_policy: dict) -> bool:
        """简单合规性检查：总费用不超过参保地封顶线。"""
        total_fee = claim.get("total_fee", 0)
        try:
            total_fee = float(total_fee)
        except (TypeError, ValueError):
            total_fee = 0.0
        pay_limit = insured_policy.get("pay_limit", 0)
        if pay_limit and total_fee > pay_limit:
            return False
        return True
