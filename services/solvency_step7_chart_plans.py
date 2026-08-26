from __future__ import annotations

from dataclasses import dataclass

from .solvency_navigation import (
    COMPANY_NAVIGATION,
    CREDIT_RISK_ASSET_SCATTER,
    INSURANCE_RISK_LIABILITY_SCATTER,
    MARKET_RISK_ASSET_SCATTER,
)


SINGLE_METRIC_TREND = "single_metric_trend"
TREND_WITH_COMPANY_BARS = "trend_with_company_bars"
COMPANY_BAR_TREND = "company_bar_trend"
COMPANY_PERIOD_BAR = "company_period_bar"
SOLVENCY_RATIO_COMBO = "solvency_ratio_combo"
CAPITAL_AMOUNT_COMBO = "capital_amount_combo"
CAPITAL_RATIO_COMBO = "capital_ratio_combo"
CAPITAL_STRUCTURE_COMBO = "capital_structure_combo"
CAPITAL_EFFICIENCY_BUBBLE = "capital_efficiency_bubble"
COMPONENT_STACK = "component_stack"
EFFECT_DIVERGING = "effect_diverging"
SOLVENCY_MATRIX = "solvency_matrix"
MARKET_CREDIT_MATRIX = "market_credit_matrix"
RISK_RATIO_SCATTER = "risk_ratio_scatter"
KEY_METRICS_TABLE = "key_metrics_table"
FINANCING_TABLE = "financing_table"
PENDING_DEFINITION = "pending_definition"


@dataclass(frozen=True)
class ChartPlan:
    kind: str
    description: str


SPECIAL_CHART_PLANS: dict[str, ChartPlan] = {
    "关键偿付数据概览": ChartPlan(
        KEY_METRICS_TABLE,
        "最新两期关键偿付数据变动表",
    ),
    "核心及综合充足率": ChartPlan(
        SOLVENCY_RATIO_COMBO,
        "按公司和报告期展示综合偿付能力充足率柱形与核心偿付能力充足率折线",
    ),
    "综合充足率变化": ChartPlan(
        CAPITAL_RATIO_COMBO,
        "实际资本与最低资本堆叠柱组合综合偿付能力充足率折线",
    ),
    "核心充足率变化": ChartPlan(
        CAPITAL_RATIO_COMBO,
        "核心资本与最低资本堆叠柱组合核心偿付能力充足率折线",
    ),
    "核心资本占比": ChartPlan(
        CAPITAL_STRUCTURE_COMBO,
        "核心资本与附属资本堆叠柱组合核心资本占实际资本比例折线",
    ),
    "资本使用效率与核心资本占比气泡图": ChartPlan(
        CAPITAL_EFFICIENCY_BUBBLE,
        "最新报告期实际资本/认可资产、核心资本/注册资本与认可资产规模气泡图",
    ),
    "核心资本/注册资本": ChartPlan(
        TREND_WITH_COMPANY_BARS,
        "多公司跨期折线图及统一纵轴的公司报告期柱状小图",
    ),
    "计入核心资本的保单未来盈余/核心资本的比例": ChartPlan(
        TREND_WITH_COMPANY_BARS,
        "多公司跨期折线图及统一纵轴的公司报告期柱状小图",
    ),
    "资本规模与结构": ChartPlan(
        CAPITAL_AMOUNT_COMBO,
        "核心一级、核心二级、附属一级和附属二级资本堆叠图",
    ),
    "核心资本明细占比-待定": ChartPlan(
        PENDING_DEFINITION,
        "Excel 标记为待定，尚无组成指标定义",
    ),
    "附属资本明细占比-待定": ChartPlan(
        PENDING_DEFINITION,
        "Excel 标记为待定，尚无组成指标定义",
    ),
    "计入各级资本的保单未来盈余构成占比": ChartPlan(
        COMPONENT_STACK,
        "计入各级资本的保单未来盈余构成占比堆叠图",
    ),
    "量化风险最低资本构成": ChartPlan(
        COMPONENT_STACK,
        "量化风险最低资本正负向构成堆叠图",
    ),
    "各类保险风险（寿）占比": ChartPlan(
        COMPONENT_STACK,
        "寿险保险风险最低资本构成堆叠图",
    ),
    "各类市场风险占比": ChartPlan(
        COMPONENT_STACK,
        "市场风险最低资本构成堆叠图",
    ),
    "各类信用风险占比": ChartPlan(
        COMPONENT_STACK,
        "信用风险最低资本构成堆叠图",
    ),
    MARKET_RISK_ASSET_SCATTER: ChartPlan(
        RISK_RATIO_SCATTER,
        "最新报告期利率风险与权益价格风险占认可资产率公司气泡图",
    ),
    CREDIT_RISK_ASSET_SCATTER: ChartPlan(
        RISK_RATIO_SCATTER,
        "最新报告期利差风险与对手违约风险占认可资产率公司气泡图",
    ),
    INSURANCE_RISK_LIABILITY_SCATTER: ChartPlan(
        RISK_RATIO_SCATTER,
        "最新报告期寿险与非寿险保险风险占认可负债率公司气泡图",
    ),
    "增资发债信息统计": ChartPlan(
        FINANCING_TABLE,
        "重大融资信息表",
    ),
}


CHART_PLAN_REGISTRY: dict[str, ChartPlan] = {
    entry.chart_name: SPECIAL_CHART_PLANS.get(
        entry.chart_name,
        ChartPlan(SINGLE_METRIC_TREND, "跨期趋势图"),
    )
    for entry in COMPANY_NAVIGATION
}


def chart_plan_for(chart_name: str) -> ChartPlan:
    return CHART_PLAN_REGISTRY.get(
        str(chart_name),
        ChartPlan(SINGLE_METRIC_TREND, "跨期趋势图"),
    )
