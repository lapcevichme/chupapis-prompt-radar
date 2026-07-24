"""Unit tests for ROI export (CSV + native XLSX writer)."""

import io
import zipfile

from service.export import roi_to_csv, roi_to_xlsx
from service.roi.calculator import compute_roi


def _sample_roi(roi_config, make_record):
    records = [
        make_record(task_type="data_analysis", scenario_id="s1", scenario_name="Отчёты"),
        make_record(task_type="code_help", scenario_id="s2", scenario_name="Ревью"),
    ]
    return compute_roi(records, roi_config)


def test_csv_has_all_sections(roi_config, make_record) -> None:
    roi = _sample_roi(roi_config, make_record)
    text = roi_to_csv(roi).decode("utf-8")
    assert text.startswith("﻿")  # BOM for Excel
    assert "# Summary" in text
    assert "# ByCategory" in text
    assert "# ByScenario" in text
    assert "roi_multiplier" in text
    assert "data_analysis" in text
    # cyrillic scenario name survives round-trip
    assert "Отчёты" in text


def test_xlsx_is_valid_zip_with_three_sheets(roi_config, make_record) -> None:
    roi = _sample_roi(roi_config, make_record)
    blob = roi_to_xlsx(roi)
    assert blob[:2] == b"PK"  # zip magic

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert zf.testzip() is None
        names = set(zf.namelist())
        assert "[Content_Types].xml" in names
        assert "xl/workbook.xml" in names
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet3.xml" in names
        workbook = zf.read("xl/workbook.xml").decode("utf-8")
        assert 'name="Summary"' in workbook
        assert 'name="ByCategory"' in workbook
        assert 'name="ByScenario"' in workbook
        # cyrillic inline string is escaped/preserved
        sheet3 = zf.read("xl/worksheets/sheet3.xml").decode("utf-8")
        assert "Отчёты" in sheet3


def test_xlsx_escapes_special_chars(roi_config, make_record) -> None:
    roi = compute_roi(
        [make_record(scenario_id="s&1", scenario_name="A <b> & \"c\"")], roi_config
    )
    blob = roi_to_xlsx(roi)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        sheet3 = zf.read("xl/worksheets/sheet3.xml").decode("utf-8")
    assert "&amp;" in sheet3
    assert "&lt;b&gt;" in sheet3
    assert "<b>" not in sheet3  # raw angle brackets must be escaped


def test_empty_roi_still_exports(roi_config) -> None:
    roi = compute_roi([], roi_config)
    csv_bytes = roi_to_csv(roi)
    xlsx_bytes = roi_to_xlsx(roi)
    assert b"# Summary" in csv_bytes
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        assert zf.testzip() is None
