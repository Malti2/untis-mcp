"""Tests for the WebUntis MCP server."""

import json
import pytest
from datetime import date, timedelta

from untis_mcp.server import _format_json, _next_school_day


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
