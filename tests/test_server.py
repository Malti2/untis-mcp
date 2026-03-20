"""Tests for the WebUntis MCP server."""

import json
import pytest
from datetime import date, timedelta

from untis_mcp.server import _format_json, _next_school_day, _format_daily_report


class TestHelpers:
    def test_format_json_returns_indented(self):
        result = _format_json({"key": "value"})
        parsed = json.loads(result)
        assert parsed == {"key": "value"}
        assert "\n" in result  # indented

    def test_next_school_day_skips_weekend(self):
        # Friday 2026-03-20 -> Monday 2026-03-23
        friday = date(2026, 3, 20)
        assert _next_school_day(friday) == date(2026, 3, 23)

    def test_next_school_day_normal(self):
        # Monday -> Tuesday
        monday = date(2026, 3, 23)
        assert _next_school_day(monday) == date(2026, 3, 24)

    def test_next_school_day_saturday(self):
        # Saturday -> Monday
        saturday = date(2026, 3, 21)
        assert _next_school_day(saturday) == date(2026, 3, 23)


class TestDateDefaults:
    """Test that tools apply correct default end_date."""

    def test_timetable_default_end_is_start_plus_6(self):
        start = date(2026, 3, 20)
        expected_end = start + timedelta(days=6)
        assert expected_end == date(2026, 3, 26)

    def test_homework_default_end_is_start_plus_7(self):
        start = date(2026, 3, 20)
        expected_end = start + timedelta(days=7)
        assert expected_end == date(2026, 3, 27)

    def test_exams_default_end_is_start_plus_30(self):
        start = date(2026, 3, 20)
        expected_end = start + timedelta(days=30)
        assert expected_end == date(2026, 4, 19)

    def test_absences_default_end_is_start_plus_30(self):
        start = date(2026, 3, 20)
        expected_end = start + timedelta(days=30)
        assert expected_end == date(2026, 4, 19)


class TestDailyReport:
    def test_report_shows_student_name(self):
        report = _format_daily_report(
            person_id=42,
            person_type=5,
            tomorrow=date(2026, 3, 23),
            timetable=[],
            substitutions=[],
            homework={},
            exams={},
            absences={},
            messages={},
        )
        assert "## Schueler (ID 42)" in report or "Auf einen Blick" in report

    def test_report_shows_no_lessons(self):
        report = _format_daily_report(
            person_id=42,
            person_type=5,
            tomorrow=date(2026, 3, 23),
            timetable=[],
            substitutions=[],
            homework={},
            exams={},
            absences={},
            messages={},
        )
        assert "Kein Unterricht" in report

    def test_report_shows_lessons(self):
        timetable = [
            {
                "id": 1, "date": 20260323,
                "startTime": 800, "endTime": 845,
                "su": [{"id": 10, "name": "Ma"}],
                "te": [{"id": 20, "name": "Mue", "longname": "Mueller"}],
                "ro": [{"id": 30, "name": "204"}],
            },
        ]
        report = _format_daily_report(
            person_id=42,
            person_type=5,
            tomorrow=date(2026, 3, 23),
            timetable=timetable,
            substitutions=[],
            homework={},
            exams={},
            absences={},
            messages={},
        )
        assert "Ma" in report
        assert "Mue" in report or "Mueller" in report
