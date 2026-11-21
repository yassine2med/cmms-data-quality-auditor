"""Rules and scoring for work-order records."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REQUIRED = ("wo_id", "asset_id", "location", "description", "priority", "status", "created")
PRIORITIES = {"emergency", "high", "medium", "low"}
STATUSES = {"open", "in progress", "on hold", "closed", "cancelled"}
WEIGHTS = {"error": 15, "warning": 5, "info": 1}
MIN_DESCRIPTION = 12


@dataclass(frozen=True)
class Issue:
    """One rule violation on one record."""

    row: int
    wo_id: str
    rule: str
    severity: str
    message: str


@dataclass
class AuditResult:
    """Issues plus a 0-100 score per record and overall."""

    total_rows: int
    issues: list[Issue] = field(default_factory=list)
    row_scores: dict[int, int] = field(default_factory=dict)

    @property
    def overall_score(self) -> float:
        """Mean record score; 100.0 for an empty file."""
        if not self.row_scores:
            return 100.0
        return round(sum(self.row_scores.values()) / len(self.row_scores), 1)

    def by_rule(self) -> Counter:
        """Count of issues per rule name."""
        return Counter(i.rule for i in self.issues)


def load_rows(path: str | Path) -> list[dict[str, str]]:
    """Read a CSV export into a list of dicts with lowercase, stripped headers."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [
            {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            for row in reader
        ]


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def check_record(row_no: int, rec: dict[str, str]) -> list[Issue]:
    """Apply the per-record rules to one row."""
    wo = rec.get("wo_id", "") or f"(row {row_no})"
    found: list[Issue] = []

    def add(rule: str, severity: str, message: str) -> None:
        found.append(Issue(row_no, wo, rule, severity, message))

    for name in REQUIRED:
        if not rec.get(name):
            add("missing-field", "error", f"{name} is empty")

    priority = rec.get("priority", "").lower()
    if priority and priority not in PRIORITIES:
        add("bad-priority", "error", f"priority '{rec['priority']}' not in {sorted(PRIORITIES)}")

    status = rec.get("status", "").lower()
    if status and status not in STATUSES:
        add("bad-status", "error", f"status '{rec['status']}' not recognised")

    created = _parse_date(rec["created"]) if rec.get("created") else None
    if rec.get("created") and created is None:
        add("bad-date", "error", f"created '{rec['created']}' is not YYYY-MM-DD")
    closed = _parse_date(rec["closed"]) if rec.get("closed") else None
    if rec.get("closed") and closed is None:
        add("bad-date", "error", f"closed '{rec['closed']}' is not YYYY-MM-DD")

    if created and closed and closed < created:
        add("closed-before-created", "error", "closed date is earlier than created date")
    if status == "closed" and not rec.get("closed"):
        add("closed-without-date", "warning", "status is closed but no closed date")
    if status in {"open", "in progress", "on hold"} and rec.get("closed"):
        add("open-with-close-date", "warning", f"status '{status}' but a closed date exists")

    desc = rec.get("description", "")
    if desc and len(desc) < MIN_DESCRIPTION:
        add("short-description", "info", f"description has {len(desc)} characters")
    if len(desc) > MIN_DESCRIPTION and desc.isupper():
        add("all-caps", "info", "description is all capitals")
    return found


def audit(rows: list[dict[str, str]]) -> AuditResult:
    """Score every record and add the duplicate-id rule across the file."""
    result = AuditResult(total_rows=len(rows))
    ids = Counter(r.get("wo_id", "") for r in rows if r.get("wo_id"))
    for index, rec in enumerate(rows, start=2):  # row 1 is the header
        issues = check_record(index, rec)
        if rec.get("wo_id") and ids[rec["wo_id"]] > 1:
            issues.append(Issue(index, rec["wo_id"], "duplicate-id", "error",
                                f"wo_id appears {ids[rec['wo_id']]} times"))
        result.issues.extend(issues)
        penalty = sum(WEIGHTS[i.severity] for i in issues)
        result.row_scores[index] = max(0, 100 - penalty)
    return result


def format_report(result: AuditResult, limit: int = 10) -> str:
    """Plain-text summary: score, rule counts and the worst records."""
    lines = [f"Records: {result.total_rows}   Issues: {len(result.issues)}   "
             f"Overall score: {result.overall_score}/100", "", "Issues by rule:"]
    for rule, count in sorted(result.by_rule().items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {rule:<24}{count}")
    worst = sorted(result.row_scores.items(), key=lambda kv: (kv[1], kv[0]))
    lines += ["", f"Lowest scoring records (max {limit}):"]
    for row, score in worst[:limit]:
        if score == 100:
            break
        first = next(i for i in result.issues if i.row == row)
        lines.append(f"  row {row:<4}{first.wo_id:<10}{score:>3}  {first.message}")
    return "\n".join(lines)
