from __future__ import annotations

import unittest

import pandas as pd

from services.solvency_normalizer import normalize_tables
from services.solvency_metric_registry import extend_taxonomy
from services.solvency_table_extractor import ExtractedTable, UnitRecord


class SolvencyNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = pd.DataFrame([
            {
                "指标编码": "CORE_T1_CAPITAL",
                "指标名称": "核心一级资本",
                "别名": "核心一级资本金额|核心一级资本（万元）",
                "一级模块": "实际资本",
                "二级模块": "资本构成",
                "标准单位": "万元",
                "数据类型": "金额",
            },
            {
                "指标编码": "SOLVENCY_RATIO",
                "指标名称": "综合偿付能力充足率",
                "别名": "",
                "一级模块": "主要指标",
                "二级模块": "偿付能力",
                "标准单位": "%",
                "数据类型": "百分比",
            },
        ]).fillna("")
        self.metadata = {
            "公司": "测试人寿保险有限公司",
            "报告年度": 2026,
            "报告季度": "Q1",
            "报告期": "2026Q1",
        }

    @staticmethod
    def _unit(scope: str, target: str, unit: str) -> UnitRecord:
        return UnitRecord(
            scope=scope,
            target=target,
            raw_unit=unit,
            normalized_unit=unit,
            source_page=1,
        )

    def _normalize(self, rows, units, company_type="寿险"):
        table = ExtractedTable(
            table_id="TEST",
            table_name="测试表",
            page=1,
            table_index=1,
            rows=rows,
            source_pages=[1],
            unit_records=units,
        )
        return normalize_tables(
            [table],
            self.taxonomy,
            self.metadata,
            company_type,
        )

    def test_table_yuan_is_converted_to_ten_thousand_yuan(self):
        result = self._normalize(
            [
                ["项目", "期末数"],
                ["核心一级资本", "100,000,000"],
                ["综合偿付能力充足率", "130%"],
            ],
            [
                self._unit("表级", "", "元"),
                self._unit("行级", "综合偿付能力充足率", "%"),
            ],
        )

        capital = result[result["指标编码"] == "CORE_T1_CAPITAL"].iloc[0]
        ratio = result[result["指标编码"] == "SOLVENCY_RATIO"].iloc[0]
        self.assertEqual(capital["数值"], 10_000)
        self.assertEqual(capital["单位"], "万元")
        self.assertEqual(capital["原始披露值"], "100,000,000")
        self.assertIn("原单位：元", capital["备注"])
        self.assertEqual(ratio["数值"], 130)
        self.assertEqual(ratio["单位"], "%")
        self.assertEqual(ratio["备注"], "")

    def test_row_unit_overrides_table_unit(self):
        result = self._normalize(
            [
                ["项目", "期末数"],
                ["核心一级资本（万元）", "123.45"],
            ],
            [
                self._unit("表级", "", "元"),
                self._unit("行级", "核心一级资本（万元）", "万元"),
            ],
        )

        self.assertEqual(result.iloc[0]["数值"], 123.45)
        self.assertEqual(result.iloc[0]["备注"], "")

    def test_structured_row_unit_converts_when_output_label_has_no_unit(self):
        result = self._normalize(
            [
                ["项目", "期末数"],
                ["核心一级资本", "100,000,000"],
            ],
            [
                self._unit("行级", "核心一级资本", "元"),
            ],
        )

        self.assertEqual(result.iloc[0]["数值"], 10_000)
        self.assertEqual(result.iloc[0]["单位"], "万元")
        self.assertIn("原单位：元", result.iloc[0]["备注"])

    def test_column_unit_overrides_table_unit(self):
        result = self._normalize(
            [
                ["项目", "期末数（元）"],
                ["核心一级资本", "25,000"],
            ],
            [
                self._unit("表级", "", "万元"),
                self._unit("列级", "期末数（元）", "元"),
            ],
        )

        self.assertEqual(result.iloc[0]["数值"], 2.5)
        self.assertIn("已换算为万元", result.iloc[0]["备注"])

    def test_missing_amount_unit_is_flagged_without_conversion(self):
        result = self._normalize(
            [
                ["项目", "期末数"],
                ["核心一级资本", "25,000"],
            ],
            [],
        )

        self.assertEqual(result.iloc[0]["数值"], 25_000)
        self.assertEqual(result.iloc[0]["备注"], "未识别原始单位，数值未换算")

    def test_mixed_table_units_are_selected_by_metric_type(self):
        result = self._normalize(
            [
                ["项目", "期末数"],
                ["核心一级资本", "100,000,000"],
                ["综合偿付能力充足率", "130"],
            ],
            [
                self._unit("表级", "", "元"),
                self._unit("表级", "", "%"),
            ],
        )

        capital = result[result["指标编码"] == "CORE_T1_CAPITAL"].iloc[0]
        ratio = result[result["指标编码"] == "SOLVENCY_RATIO"].iloc[0]
        self.assertEqual(capital["报告类型"], "LIFE_SOLVENCY")
        self.assertEqual(capital["数值"], 10_000)
        self.assertIn("原单位：元", capital["备注"])
        self.assertEqual(ratio["数值"], 130)
        self.assertEqual(ratio["单位"], "%")
        self.assertEqual(ratio["备注"], "")

    def test_only_life_company_types_are_accepted(self):
        result = self._normalize(
            [["项目", "期末数（万元）"], ["核心一级资本", "1"]],
            [],
            company_type="健康",
        )
        self.assertEqual(result.iloc[0]["公司类型"], "健康险")

        with self.assertRaisesRegex(ValueError, "公司类型仅支持"):
            self._normalize(
                [["项目", "期末数（万元）"], ["核心一级资本", "1"]],
                [],
                company_type="财险",
            )

    def test_profile_can_explicitly_enable_non_life_company_type(self):
        table = ExtractedTable(
            table_id="TEST",
            table_name="测试表",
            page=1,
            table_index=1,
            rows=[["项目", "期末数（万元）"], ["核心一级资本", "1"]],
            source_pages=[1],
        )
        result = normalize_tables(
            [table],
            self.taxonomy,
            self.metadata,
            "财产保险",
            report_profile_id="NON_LIFE_SOLVENCY",
            allowed_company_types=("财险",),
        )
        self.assertEqual(result.iloc[0]["公司类型"], "财险")
        self.assertEqual(result.iloc[0]["报告类型"], "NON_LIFE_SOLVENCY")

    def test_actual_capital_accepts_step3_only_disclosure_metrics(self):
        taxonomy = pd.DataFrame([
            {
                "指标编码": "FINANCIAL_STATEMENT_ASSETS",
                "指标名称": "财务报表资产总额",
                "别名": "财务报表资产合计",
                "一级模块": "实际资本",
                "二级模块": "汇总口径",
                "标准单位": "万元",
                "数据类型": "金额",
                "STEP5宽表映射": "否",
            },
            {
                "指标编码": "NET_ASSET_ADJUSTMENT",
                "指标名称": "对净资产的调整额",
                "别名": "净资产调整额",
                "一级模块": "实际资本",
                "二级模块": "核心一级资本调整",
                "标准单位": "万元",
                "数据类型": "金额",
                "STEP5宽表映射": "否",
            },
        ]).fillna("")
        table = ExtractedTable(
            table_id="ACTUAL_CAPITAL",
            table_name="S02-实际资本明细表",
            page=1,
            table_index=1,
            rows=[
                ["项目", "期末数（万元）"],
                ["财务报表资产总额", "100"],
                ["对净资产的调整额", "-3"],
            ],
            source_pages=[1],
        )

        result = normalize_tables([table], taxonomy, self.metadata, "寿险")

        self.assertEqual(
            result["指标编码"].tolist(),
            ["FINANCIAL_STATEMENT_ASSETS", "NET_ASSET_ADJUSTMENT"],
        )
        self.assertEqual(result["数值"].tolist(), [100.0, -3.0])

    def test_actual_capital_detail_rows_are_all_standardized_and_disambiguated(self):
        taxonomy = extend_taxonomy(pd.DataFrame([{
            "指标编码": "DEFERRED_TAX_ASSET_ADJUSTMENT",
            "指标名称": "递延所得税资产（由经营性亏损引起的递延所得税资产除外）",
            "别名": "",
            "一级模块": "实际资本",
            "二级模块": "核心一级资本调整",
            "标准单位": "万元",
            "数据类型": "金额",
            "STEP5宽表映射": "否",
        }]).fillna(""))
        table = ExtractedTable(
            table_id="ACTUAL_CAPITAL",
            table_name="S02-实际资本表明细表",
            page=29,
            table_index=1,
            rows=[
                ["行次", "项目", "期末数（万元）"],
                ["1.2.3", "投资性房地产（包括保险公司以物权方式或通过子公司等方式持有的投资性房地产）的公允价值增值（扣除减值、折旧及所得税影响）", "1"],
                ["1.2.5", "对农业保险提取的大灾风险准备金", "2"],
                ["1.2.6", "计入核心一级资本的保单未来盈余", "3"],
                ["1.2.7", "符合核心一级资本标准的负债类资本工具且按规定可计入核心一级资本的金额", "4"],
                ["2.1", "优先股", "5"],
                ["2.2", "计入核心二级资本的保单未来盈余", "6"],
                ["2.3", "其他核心二级资本", "7"],
                ["2.4", "减：超限额应扣除的部分", "181,609.06"],
                ["3.1", "次级定期债务", "8"],
                ["3.2", "资本补充债券", "9"],
                ["3.3", "可转换次级债", "10"],
                ["3.4", "递延所得税资产（由经营性亏损引起的递延所得税资产除外）", "1"],
                ["3.5", "投资性房地产（包括保险公司以物权方式或通过子公司等方式持有的投资性房地产）公允价值增值可计入附属一级资本的金额（扣除减值、折旧及所得税影响）", "11"],
                ["3.6", "计入附属一级资本的保单未来盈余", "12"],
                ["3.7", "其他附属一级资本", "13"],
                ["3.8", "减：超限额应扣除的部分", "2"],
                ["4.1", "应急资本等其他附属二级资本", "14"],
                ["4.2", "计入附属二级资本的保单未来盈余", "15"],
                ["4.3", "减：超限额应扣除的部分", "3"],
            ],
            source_pages=[29],
        )

        result = normalize_tables([table], taxonomy, self.metadata, "寿险")

        self.assertEqual(result["指标编码"].tolist(), [
            "CORE_T1_INVESTMENT_PROPERTY_FAIR_VALUE_ADJUSTMENT",
            "AGRICULTURAL_CATASTROPHE_RISK_RESERVE",
            "POLICY_SURPLUS_CORE_T1",
            "QUALIFYING_CORE_T1_LIABILITY_CAPITAL",
            "CORE_T2_PREFERRED_SHARES",
            "POLICY_SURPLUS_CORE_T2",
            "OTHER_CORE_T2_CAPITAL",
            "CORE_T2_EXCESS_DEDUCTION",
            "ANC_T1_SUBORDINATED_TERM_DEBT",
            "ANC_T1_CAPITAL_SUPPLEMENTARY_BONDS",
            "ANC_T1_CONVERTIBLE_SUBORDINATED_DEBT",
            "ANC_T1_DEFERRED_TAX_ASSET",
            "ANC_T1_INVESTMENT_PROPERTY_FAIR_VALUE",
            "POLICY_SURPLUS_ANC_T1",
            "OTHER_ANC_T1_CAPITAL",
            "ANC_T1_EXCESS_DEDUCTION",
            "EMERGENCY_OTHER_ANC_T2_CAPITAL",
            "POLICY_SURPLUS_ANC_T2",
            "ANC_T2_EXCESS_DEDUCTION",
        ])


if __name__ == "__main__":
    unittest.main()
