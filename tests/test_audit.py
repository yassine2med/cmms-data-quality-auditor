from pathlib import Path

from cmmsaudit import audit, load_rows
from cmmsaudit.audit import check_record, format_report
from cmmsaudit.cli import main

SAMPLE = str(Path(__file__).parent.parent / "examples" / "work_orders.csv")

GOOD = {"wo_id": "WO-1", "asset_id": "A-1", "location": "Building A", "description": "Replace belts on unit",
        "priority": "High", "status": "Open", "created": "2026-01-01", "closed": ""}


def rules(rec):
    return {i.rule for i in check_record(2, rec)}


def test_clean_record_has_no_issues():
    assert check_record(2, GOOD) == []


def test_missing_field_flagged():
    assert "missing-field" in rules({**GOOD, "asset_id": ""})


def test_bad_priority_and_status():
    found = rules({**GOOD, "priority": "Urgent", "status": "Scheduled"})
    assert {"bad-priority", "bad-status"} <= found


def test_bad_date_format():
    assert "bad-date" in rules({**GOOD, "created": "01/02/2026"})


def test_closed_before_created():
    assert "closed-before-created" in rules({**GOOD, "status": "Closed", "closed": "2025-12-31"})


def test_closed_without_date_is_warning():
    issues = check_record(2, {**GOOD, "status": "Closed"})
    assert [(i.rule, i.severity) for i in issues] == [("closed-without-date", "warning")]


def test_open_with_close_date():
    assert "open-with-close-date" in rules({**GOOD, "closed": "2026-01-03"})


def test_short_and_all_caps_description():
    assert "short-description" in rules({**GOOD, "description": "fix"})
    assert "all-caps" in rules({**GOOD, "description": "REPLACE BATTERY IN STAIRWELL"})


def test_duplicate_ids_found_across_rows():
    result = audit([GOOD, dict(GOOD)])
    assert result.by_rule()["duplicate-id"] == 2


def test_scores_are_bounded_and_empty_file_is_perfect():
    bad = {k: "" for k in GOOD}
    result = audit([bad])
    assert result.row_scores[2] == 0
    assert audit([]).overall_score == 100.0


def test_sample_file_and_cli(capsys):
    assert len(load_rows(SAMPLE)) == 14
    assert main([SAMPLE, "--min-score", "99"]) == 1
    assert "Overall score" in capsys.readouterr().out
    assert main([SAMPLE]) == 0


def test_missing_file_returns_2(tmp_path):
    assert main([str(tmp_path / "nope.csv")]) == 2


def test_report_text_lists_rules():
    text = format_report(audit([{**GOOD, "priority": "x"}]))
    assert "bad-priority" in text
