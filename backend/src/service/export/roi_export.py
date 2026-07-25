"""Export ROI results to CSV / XLSX (case theme: Excel export).

XLSX is built with the stdlib only (zipfile + minimal OOXML) so no extra
dependency and no Docker rebuild are required.
"""

import csv
import io
import zipfile
from typing import Any

from domain.roi import Roi

CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

Row = list[Any]
Sheet = tuple[str, list[Row]]


def _summary_rows(roi: Roi) -> list[Row]:
    s = roi.summary
    a = roi.assumptions
    return [
        ["metric", "value"],
        ["total_logs", s.total_logs],
        ["success_rate_percent", s.success_rate_percent],
        ["mau_count", s.mau_count],
        ["total_fte_hours_saved", s.total_fte_hours_saved],
        ["total_manual_cost_rub", s.total_manual_cost_rub],
        ["total_agent_cost_rub", s.total_agent_cost_rub],
        ["net_savings_rub", s.net_savings_rub],
        ["roi_multiplier", s.roi_multiplier],
        ["cost_per_successful_action_rub", s.cost_per_successful_action_rub],
        ["wasted_cost_rub", s.wasted_cost_rub],
        ["total_tokens_consumed", s.total_tokens_consumed],
        ["wasted_tokens_on_errors", s.wasted_tokens_on_errors],
        ["token_value_index", s.token_value_index],
        ["process_automation_rate", s.process_automation_rate],
        ["mobile_voice_adoption_rate", s.mobile_voice_adoption_rate],
        ["style_insight", s.style_insight],
        ["fte_hourly_rate_rub", a.fte_hourly_rate_rub],
        ["token_cost_per_1k_rub", a.token_cost_per_1k_rub],
        ["session_coeff_short", a.session_coefficients.short],
        ["session_coeff_medium", a.session_coefficients.medium],
        ["session_coeff_long", a.session_coefficients.long],
    ]


def _by_category_rows(roi: Roi) -> list[Row]:
    rows: list[Row] = [
        [
            "task_type",
            "label",
            "count",
            "success_rate_percent",
            "fte_hours_saved",
            "net_savings_rub",
        ]
    ]
    for c in roi.by_category:
        rows.append(
            [
                c.task_type,
                c.label,
                c.count,
                c.success_rate_percent,
                c.fte_hours_saved,
                c.net_savings_rub,
            ]
        )
    return rows


def _by_scenario_rows(roi: Roi) -> list[Row]:
    rows: list[Row] = [
        ["scenario_id", "name", "count", "fte_hours_saved", "net_savings_rub"]
    ]
    for sc in roi.by_scenario:
        rows.append(
            [
                sc.scenario_id,
                sc.name or "",
                sc.count,
                sc.fte_hours_saved,
                sc.net_savings_rub,
            ]
        )
    return rows


def _by_style_rows(roi: Roi) -> list[Row]:
    rows: list[Row] = [["style", "count", "percentage"]]
    for st, count in roi.summary.style_breakdown.items():
        pct = roi.summary.style_percentages.get(st, 0.0)
        rows.append([st, count, pct])
    return rows


def _roi_sheets(roi: Roi) -> list[Sheet]:
    return [
        ("Summary", _summary_rows(roi)),
        ("ByCategory", _by_category_rows(roi)),
        ("ByScenario", _by_scenario_rows(roi)),
        ("ByStyle", _by_style_rows(roi)),
    ]


def roi_to_csv(roi: Roi) -> bytes:
    """Flatten ROI into a single multi-section CSV (opens in Excel)."""
    buffer = io.StringIO()
    buffer.write("﻿")  # BOM so Excel renders Cyrillic correctly
    writer = csv.writer(buffer)
    for index, (name, rows) in enumerate(_roi_sheets(roi)):
        if index > 0:
            writer.writerow([])
        writer.writerow([f"# {name}"])
        writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def roi_to_xlsx(roi: Roi) -> bytes:
    """Build a real .xlsx workbook (one sheet per ROI section), stdlib only."""
    return _build_xlsx(_roi_sheets(roi))


# --- minimal OOXML writer -------------------------------------------------

def _xml_escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _col_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cell_xml(col: int, row: int, value: Any) -> str:
    ref = f"{_col_letter(col)}{row}"
    if isinstance(value, bool):
        value = str(value)
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{_xml_escape(value)}</t></is></c>'


def _sheet_xml(rows: list[Row]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>',
    ]
    for r_index, row in enumerate(rows, start=1):
        cells = "".join(_cell_xml(c, r_index, val) for c, val in enumerate(row))
        lines.append(f'<row r="{r_index}">{cells}</row>')
    lines.append("</sheetData></worksheet>")
    return "".join(lines)


def _safe_sheet_name(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch not in '[]:*?/\\')
    return cleaned[:31] or "Sheet"


def _build_xlsx(sheets: list[Sheet]) -> bytes:
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    for i in range(len(sheets)):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    content_types.append("</Types>")

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )

    sheet_tags = "".join(
        f'<sheet name="{_xml_escape(_safe_sheet_name(name))}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
        for i, (name, _) in enumerate(sheets)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_tags}</sheets></workbook>"
    )

    wb_rel_tags = "".join(
        f'<Relationship Id="rId{i + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i + 1}.xml"/>'
        for i in range(len(sheets))
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{wb_rel_tags}</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "".join(content_types))
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for i, (_, rows) in enumerate(sheets):
            zf.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet_xml(rows))
    return buffer.getvalue()
