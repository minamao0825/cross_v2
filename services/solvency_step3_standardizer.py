from __future__ import annotations

"""Template-driven STEP3 standardization helpers.

The UI deliberately keeps the annual-report platform's target-template workflow,
while the output remains the canonical narrow table consumed by STEP5.
"""

import io
from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd

from .solvency_dataset_adapter import append_derived_metrics, supported_metric_catalog
from .solvency_metric_registry import DERIVED_METRICS
from .solvency_normalizer import STANDARD_COLUMNS, normalize_tables
from .solvency_table_extractor import ExtractedTable


TARGET_SHEET_NAME = "指标清单"
STANDARD_SHEET_NAME = "标准数据"
TARGET_TEMPLATE_COLUMNS = [
    "启用",
    "指标编码",
    "指标名称",
    "一级模块",
    "二级模块",
    "标准单位",
    "数据类型",
    "指标属性",
    "计算逻辑",
]


@dataclass(frozen=True)
class Step3StandardizationResult:
    data: pd.DataFrame
    target_catalog: pd.DataFrame
    diagnostics: pd.DataFrame
    target_summary: pd.DataFrame
    warnings: tuple[str, ...]


def step3_metric_catalog(
    taxonomy: pd.DataFrame,
    *,
    include_derived: bool,
) -> pd.DataFrame:
    """Return the exact metric-code range supported by STEP5 mapping."""
    catalog = supported_metric_catalog(
        taxonomy,
        include_derived=include_derived,
        include_step3_only=True,
    ).copy()
    catalog.insert(0, "启用", "是")
    return catalog.reindex(columns=TARGET_TEMPLATE_COLUMNS)


def _find_header_row(preview: pd.DataFrame, required_header: str) -> int | None:
    for index, row in preview.iterrows():
        values = {str(value).strip() for value in row if not pd.isna(value)}
        if required_header in values:
            return int(index)
    return None


def _enabled(value: object) -> bool:
    text = str(value if value is not None else "").strip().lower()
    return text not in {"否", "不启用", "false", "0", "n", "no"}


def read_target_template(
    workbook_bytes: bytes,
    filename: str,
    supported_catalog: pd.DataFrame,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Read a target list and constrain it to STEP5-supported metric codes."""
    excel = pd.ExcelFile(io.BytesIO(workbook_bytes))
    sheet_name = (
        TARGET_SHEET_NAME
        if TARGET_SHEET_NAME in excel.sheet_names
        else STANDARD_SHEET_NAME
        if STANDARD_SHEET_NAME in excel.sheet_names
        else excel.sheet_names[0]
    )
    preview = pd.read_excel(excel, sheet_name=sheet_name, header=None, nrows=20)
    header_row = _find_header_row(preview, "指标编码")
    if header_row is None:
        raise ValueError(f"{filename} 未找到“指标编码”表头。")

    frame = pd.read_excel(excel, sheet_name=sheet_name, header=header_row).fillna("")
    frame.columns = [str(column).strip() for column in frame.columns]
    if "启用" in frame.columns:
        frame = frame[frame["启用"].map(_enabled)]
    raw_codes = [
        str(value).strip()
        for value in frame["指标编码"]
        if str(value).strip()
    ]
    codes = list(dict.fromkeys(raw_codes))
    if not codes:
        raise ValueError(f"{filename} 未配置任何已启用的目标指标。")

    supported_codes = set(supported_catalog["指标编码"].astype(str))
    unknown_codes = [code for code in codes if code not in supported_codes]
    if unknown_codes:
        raise ValueError(
            "目标表包含 STEP3 正式指标字典之外的编码：" + "、".join(unknown_codes)
        )

    indexed = supported_catalog.set_index("指标编码", drop=False)
    selected = pd.DataFrame([indexed.loc[code] for code in codes]).reset_index(drop=True)
    selected["启用"] = "是"

    warnings: list[str] = []
    duplicate_count = len(raw_codes) - len(codes)
    if duplicate_count > 0:
        warnings.append(f"目标表中 {duplicate_count} 条重复指标已按指标编码去重。")
    return selected.reindex(columns=TARGET_TEMPLATE_COLUMNS), tuple(warnings)


def _dependency_closure(target_codes: set[str]) -> set[str]:
    derived_by_code = {definition.code: definition for definition in DERIVED_METRICS}
    required = set(target_codes)
    pending = list(target_codes)
    while pending:
        code = pending.pop()
        definition = derived_by_code.get(code)
        if definition is None:
            continue
        for dependency in definition.dependencies:
            if dependency not in required:
                required.add(dependency)
                pending.append(dependency)
    return required


def _target_summary(
    target_catalog: pd.DataFrame,
    data: pd.DataFrame,
) -> pd.DataFrame:
    counts = data["指标编码"].astype(str).value_counts() if not data.empty else pd.Series(dtype=int)
    summary = target_catalog[
        ["指标编码", "指标名称", "一级模块", "二级模块", "指标属性"]
    ].copy()
    summary["填报记录数"] = summary["指标编码"].map(counts).fillna(0).astype(int)
    summary["填报状态"] = summary["填报记录数"].map(lambda value: "已填报" if value else "未填报")
    return summary


def standardize_to_target(
    tables: list[ExtractedTable],
    taxonomy: pd.DataFrame,
    metadata: dict,
    company_type: str,
    target_catalog: pd.DataFrame,
    *,
    report_profile_id: str,
    allowed_company_types: Sequence[str],
    peer_group: str = "",
    peer_group_map: Mapping[str, str] | None = None,
    default_peer_group: str = "",
    include_derived: bool,
    template_warnings: Sequence[str] = (),
) -> Step3StandardizationResult:
    """Fill a target list and return the canonical STEP5-compatible narrow table."""
    target_codes = set(target_catalog["指标编码"].astype(str).str.strip())
    required_codes = _dependency_closure(target_codes)
    derived_codes = {definition.code for definition in DERIVED_METRICS}
    normalization_codes = required_codes - derived_codes
    scoped_taxonomy = taxonomy[
        taxonomy["指标编码"].astype(str).str.strip().isin(normalization_codes)
    ].copy()

    diagnostics: list[dict] = []
    normalized = normalize_tables(
        tables,
        scoped_taxonomy,
        metadata,
        company_type,
        report_profile_id=report_profile_id,
        diagnostics=diagnostics,
        allowed_company_types=allowed_company_types,
        peer_group=peer_group,
        peer_group_map=peer_group_map,
        default_peer_group=default_peer_group,
    )
    enriched = append_derived_metrics(normalized) if include_derived else normalized
    data = enriched[
        enriched["指标编码"].astype(str).str.strip().isin(target_codes)
    ].copy()
    if not data.empty:
        target_order = {
            code: index
            for index, code in enumerate(target_catalog["指标编码"].astype(str))
        }
        data["_目标顺序"] = data["指标编码"].map(target_order)
        data = data.sort_values(
            ["_目标顺序", "期间口径", "来源页码"],
            kind="stable",
        ).drop(columns="_目标顺序")
    data = data.reindex(columns=STANDARD_COLUMNS).reset_index(drop=True)
    diagnostic_frame = pd.DataFrame(diagnostics)
    summary = _target_summary(target_catalog, data)
    warnings = list(template_warnings)
    missing_count = int((summary["填报状态"] == "未填报").sum())
    if missing_count:
        warnings.append(
            f"目标表中有 {missing_count} 个指标未从本次提取表格或计算依赖中取得数值。"
        )
    return Step3StandardizationResult(
        data=data,
        target_catalog=target_catalog.copy(),
        diagnostics=diagnostic_frame,
        target_summary=summary,
        warnings=tuple(warnings),
    )


def _format_workbook(writer: pd.ExcelWriter) -> None:
    for worksheet in writer.book.worksheets:
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for column_cells in worksheet.iter_cols():
            values = [str(cell.value or "") for cell in column_cells[:200]]
            width = min(max(max((len(value) for value in values), default=0) + 2, 10), 32)
            worksheet.column_dimensions[column_cells[0].column_letter].width = width


def target_template_workbook_bytes(
    target_catalog: pd.DataFrame,
    profile_name: str,
) -> bytes:
    output = io.BytesIO()
    instructions = pd.DataFrame(
        [
            ("用途", f"{profile_name} STEP3 目标指标配置；输出可直接进入 STEP5。"),
            ("选择指标", "在“指标清单”中将不需要的指标“启用”改为“否”，不要修改指标编码。"),
            ("窄表字段", "“标准数据”页展示 STEP3/STEP5 共用的标准窄表表头。"),
            ("单位口径", "金额按标准单位万元输出；百分比保留披露百分数，例如 130.98 表示 130.98%。"),
        ],
        columns=["项目", "说明"],
    )
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        instructions.to_excel(writer, sheet_name="使用说明", index=False)
        target_catalog.reindex(columns=TARGET_TEMPLATE_COLUMNS).to_excel(
            writer,
            sheet_name=TARGET_SHEET_NAME,
            index=False,
        )
        pd.DataFrame(columns=STANDARD_COLUMNS).to_excel(
            writer,
            sheet_name=STANDARD_SHEET_NAME,
            index=False,
        )
        _format_workbook(writer)
    return output.getvalue()


def result_workbook_bytes(result: Step3StandardizationResult) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.data.to_excel(writer, sheet_name=STANDARD_SHEET_NAME, index=False)
        result.target_summary.to_excel(writer, sheet_name="填报汇总", index=False)
        if result.diagnostics.empty:
            pd.DataFrame(columns=["状态", "原因"]).to_excel(
                writer,
                sheet_name="匹配诊断",
                index=False,
            )
        else:
            result.diagnostics.to_excel(writer, sheet_name="匹配诊断", index=False)
        _format_workbook(writer)
    return output.getvalue()
