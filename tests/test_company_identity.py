from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from services.solvency_company_identity import (
    apply_company_identities,
    load_peer_group_config,
    resolve_company_identity,
    resolve_peer_group,
)
from services.solvency_normalizer import STANDARD_COLUMNS, upgrade_standard_frame


class CompanyIdentityTests(unittest.TestCase):
    def test_historical_and_current_names_share_identity(self):
        company_types = {"中韩人寿": "寿险"}
        historical = resolve_company_identity("中韩人寿", company_types)
        current = resolve_company_identity("东方嘉富人寿", company_types)

        self.assertEqual(historical.standard_name, "东方嘉富人寿")
        self.assertEqual(current.standard_name, "东方嘉富人寿")
        self.assertEqual(historical.company_code, current.company_code)
        self.assertEqual(current.company_type, "寿险")
        self.assertEqual(historical.matched_by, "历史名称映射")

    def test_frame_preserves_original_name_and_standardizes_company(self):
        frame = pd.DataFrame([
            {"公司": "中韩人寿", "公司类型": "寿险", "报告期": "2024Q4"},
            {"公司": "东方嘉富人寿", "公司类型": "", "报告期": "2025Q4"},
        ])
        result = apply_company_identities(frame, {"中韩人寿": "寿险"})

        self.assertEqual(result["公司"].tolist(), ["东方嘉富人寿", "东方嘉富人寿"])
        self.assertEqual(result["原始公司名称"].tolist(), ["中韩人寿", "东方嘉富人寿"])
        self.assertEqual(result["公司统一编码"].nunique(), 1)
        self.assertEqual(result["公司类型"].tolist(), ["寿险", "寿险"])

    def test_peer_group_resolves_alias_and_full_legal_name(self):
        peer_groups = {
            "东方嘉富人寿": "小型公司",
            "中国人寿": "大型公司",
        }

        self.assertEqual(resolve_peer_group("中韩人寿", peer_groups), "小型公司")
        self.assertEqual(
            resolve_peer_group("中国人寿保险股份有限公司", peer_groups),
            "大型公司",
        )
        self.assertEqual(resolve_peer_group("未配置人寿", peer_groups), "其他")

    def test_frame_fills_blank_peer_group_but_preserves_reviewed_value(self):
        frame = pd.DataFrame([
            {"公司": "中韩人寿", "公司类型": "寿险", "同业分类": ""},
            {"公司": "中国人寿", "公司类型": "寿险", "同业分类": "自定义"},
        ])
        result = apply_company_identities(
            frame,
            peer_group_map={"东方嘉富人寿": "小型公司", "中国人寿": "大型公司"},
            default_peer_group="其他",
        )

        self.assertEqual(result["同业分类"].tolist(), ["小型公司", "自定义"])

    def test_peer_group_config_rejects_duplicate_company_membership(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "peer_groups.json"
            path.write_text(
                '{"groups":{"大型公司":["甲公司"],"银行系":["甲公司"]}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "同时属于"):
                load_peer_group_config(path)

    def test_upgrades_legacy_session_frame_to_current_schema(self):
        legacy = pd.DataFrame([{
            "公司": "中韩人寿",
            "公司类型": "寿险",
            "报告期": "2024Q4",
            "指标编码": "ACTUAL_CAPITAL",
            "数值": 1.0,
        }])
        result = upgrade_standard_frame(legacy)

        self.assertEqual(list(result.columns), STANDARD_COLUMNS)
        self.assertEqual(result.iloc[0]["原始公司名称"], "中韩人寿")
        self.assertEqual(result.iloc[0]["标准公司名称"], "东方嘉富人寿")
        self.assertEqual(result.iloc[0]["公司统一编码"], "LIFE_ORIENTAL_JIAFU")


if __name__ == "__main__":
    unittest.main()
