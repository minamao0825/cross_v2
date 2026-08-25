from __future__ import annotations

import io
import unittest

import pandas as pd

from services.solvency_dataset_adapter import (
    read_standard_workbook,
    supported_metric_catalog,
)
from services.solvency_normalizer import STANDARD_COLUMNS
from services.solvency_metric_registry import extend_taxonomy
from services.solvency_step3_standardizer import (
    read_target_template,
    result_workbook_bytes,
    standardize_to_target,
    step3_metric_catalog,
    target_template_workbook_bytes,
)
from services.solvency_table_extractor import ExtractedTable


class Step3StandardizerTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = pd.DataFrame([
            {
                "指标编码": "RECOGNIZED_ASSETS",
                "指标名称": "认可资产",
                "别名": "认可资产合计",
                "一级模块": "主要指标",
                "二级模块": "偿付能力",
                "标准单位": "万元",
                "数据类型": "金额",
            },
            {
                "指标编码": "ACTUAL_CAPITAL",
                "指标名称": "实际资本",
                "别名": "实际资本合计",
                "一级模块": "主要指标",
                "二级模块": "偿付能力",
                "标准单位": "万元",
                "数据类型": "金额",
            },
            {
                "指标编码": "STEP3_ONLY_DISCLOSURE",
                "指标名称": "STEP3新增披露指标",
                "别名": "",
                "一级模块": "实际资本",
                "二级模块": "补充披露",
                "标准单位": "万元",
                "数据类型": "金额",
                "STEP5宽表映射": "否",
            },
        ]).fillna("")

    @staticmethod
    def _workbook(frame: pd.DataFrame, sheet_name: str = "指标清单") -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
        return output.getvalue()

    def test_step5_wide_catalog_is_a_subset_of_step3_catalog(self):
        step5_catalog = supported_metric_catalog(
            self.taxonomy,
            include_derived=True,
        )
        step3_catalog = step3_metric_catalog(
            self.taxonomy,
            include_derived=True,
        )

        step5_codes = set(step5_catalog["指标编码"])
        step3_codes = set(step3_catalog["指标编码"])
        self.assertTrue(step5_codes < step3_codes)
        self.assertNotIn("STEP3_ONLY_DISCLOSURE", step5_codes)
        self.assertIn("STEP3_ONLY_DISCLOSURE", step3_codes)
        self.assertEqual(step3_catalog["指标编码"].nunique(), len(step3_catalog))
        self.assertIn("ACTUAL_CAPITAL_TO_RECOGNIZED_ASSETS", set(step3_catalog["指标编码"]))

    def test_actual_capital_details_are_step3_only_but_remain_valid_narrow_metrics(self):
        taxonomy = extend_taxonomy(self.taxonomy)
        step5_catalog = supported_metric_catalog(taxonomy, include_derived=False)
        step3_catalog = step3_metric_catalog(taxonomy, include_derived=False)
        detail_codes = {
            "CORE_T1_INVESTMENT_PROPERTY_FAIR_VALUE_ADJUSTMENT",
            "CORE_T2_EXCESS_DEDUCTION",
            "ANC_T1_DEFERRED_TAX_ASSET",
            "ANC_T2_EXCESS_DEDUCTION",
        }

        self.assertTrue(detail_codes <= set(step3_catalog["指标编码"]))
        self.assertTrue(detail_codes.isdisjoint(set(step5_catalog["指标编码"])))

    def test_custom_target_template_is_filtered_by_enable_flag(self):
        supported = step3_metric_catalog(self.taxonomy, include_derived=True)
        custom = pd.DataFrame([
            {"启用": "是", "指标编码": "ACTUAL_CAPITAL"},
            {"启用": "否", "指标编码": "RECOGNIZED_ASSETS"},
        ])

        selected, warnings = read_target_template(
            self._workbook(custom),
            "custom.xlsx",
            supported,
        )

        self.assertEqual(selected["指标编码"].tolist(), ["ACTUAL_CAPITAL"])
        self.assertEqual(warnings, ())

    def test_custom_target_rejects_code_outside_step3_dictionary(self):
        supported = step3_metric_catalog(self.taxonomy, include_derived=True)
        custom = pd.DataFrame([{"启用": "是", "指标编码": "OUT_OF_SCOPE"}])

        with self.assertRaisesRegex(ValueError, "STEP3 正式指标字典之外"):
            read_target_template(
                self._workbook(custom),
                "custom.xlsx",
                supported,
            )

    def test_target_driven_standardization_calculates_dependencies_but_outputs_target_only(self):
        table = ExtractedTable(
            table_id="TEST",
            table_name="测试表",
            page=1,
            table_index=1,
            rows=[
                ["项目", "期末数（万元）"],
                ["认可资产", "200"],
                ["实际资本", "100"],
            ],
            source_pages=[1],
        )
        catalog = step3_metric_catalog(self.taxonomy, include_derived=True)
        target = catalog[
            catalog["指标编码"] == "ACTUAL_CAPITAL_TO_RECOGNIZED_ASSETS"
        ].copy()

        result = standardize_to_target(
            [table],
            self.taxonomy,
            {
                "公司": "测试人寿保险有限公司",
                "报告年度": 2026,
                "报告季度": "Q1",
                "报告期": "2026Q1",
                "来源文件": "测试报告.pdf",
                "导入批次": "测试报告:2026Q1",
            },
            "寿险",
            target,
            report_profile_id="LIFE_SOLVENCY",
            allowed_company_types=("寿险", "健康险", "养老险"),
            peer_group_map={"测试人寿": "小型公司"},
            default_peer_group="其他",
            include_derived=True,
        )

        self.assertEqual(list(result.data.columns), STANDARD_COLUMNS)
        self.assertEqual(
            result.data["指标编码"].tolist(),
            ["ACTUAL_CAPITAL_TO_RECOGNIZED_ASSETS"],
        )
        self.assertAlmostEqual(float(result.data.iloc[0]["数值"]), 0.5)
        self.assertEqual(result.data.iloc[0]["同业分类"], "小型公司")
        self.assertEqual(result.target_summary.iloc[0]["填报状态"], "已填报")

    def test_generated_workbooks_are_readable_by_step5(self):
        catalog = step3_metric_catalog(self.taxonomy, include_derived=False)
        template_bytes = target_template_workbook_bytes(catalog, "测试偿付能力报告")
        selected, _ = read_target_template(template_bytes, "target.xlsx", catalog)
        self.assertEqual(set(selected["指标编码"]), set(catalog["指标编码"]))

        table = ExtractedTable(
            table_id="TEST",
            table_name="测试表",
            page=1,
            table_index=1,
            rows=[["项目", "期末数（万元）"], ["实际资本", "100"]],
            source_pages=[1],
        )
        result = standardize_to_target(
            [table],
            self.taxonomy,
            {
                "公司": "测试人寿保险有限公司",
                "报告年度": 2026,
                "报告季度": "Q1",
                "报告期": "2026Q1",
            },
            "寿险",
            catalog[catalog["指标编码"] == "ACTUAL_CAPITAL"],
            report_profile_id="LIFE_SOLVENCY",
            allowed_company_types=("寿险", "健康险", "养老险"),
            include_derived=False,
        )
        workbook = result_workbook_bytes(result)
        step5_data = read_standard_workbook(workbook, "step3.xlsx")

        self.assertEqual(list(step5_data.columns), STANDARD_COLUMNS)
        self.assertEqual(step5_data["指标编码"].tolist(), ["ACTUAL_CAPITAL"])


if __name__ == "__main__":
    unittest.main()
