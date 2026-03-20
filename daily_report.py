#!/usr/bin/env python3
"""Standalone daily report script for WebUntis.

Prints the daily parent briefing to stdout without requiring MCP.
Reads credentials from environment variables or .env file.
"""

import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Load .env if present
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from untis_mcp.api import WebUntisClient
from untis_mcp.server import _format_daily_report, _next_school_day


async def run():
    server = os.environ.get("WEBUNTIS_SERVER", "")
    school = os.environ.get("WEBUNTIS_SCHOOL", "")
    username = os.environ.get("WEBUNTIS_USER", "")
    password = os.environ.get("WEBUNTIS_PASSWORD", "")

    if not all([server, school, username, password]):
        print("Error: Set WEBUNTIS_SERVER, WEBUNTIS_SCHOOL, WEBUNTIS_USER, WEBUNTIS_PASSWORD")
        sys.exit(1)

    client = WebUntisClient(server, school, username, password)
    await client.login()

    try:
        today = date.today()
        tomorrow = _next_school_day(today)
        exam_end = (today + timedelta(days=7)).isoformat()

        enriched = await client.get_timetable_enriched(
            client.student_id, client.student_type,
            tomorrow.isoformat(), tomorrow.isoformat(),
        )
        timetable = enriched["periods"]
        substitutions = []
        try:
            substitutions = await client.get_substitutions(
                tomorrow.isoformat(), tomorrow.isoformat(),
            )
        except Exception:
            pass

        homework, exams, absences, messages = {}, {}, {}, {}
        try:
            homework = await client.get_homework(today.isoformat(), exam_end)
        except Exception:
            pass
        try:
            exams = await client.get_exams(today.isoformat(), exam_end)
        except Exception:
            pass
        try:
            absences = await client.get_absences(today.isoformat(), exam_end)
        except Exception:
            pass
        try:
            messages = await client.get_messages()
        except Exception:
            pass

        print(f"# Eltern-Briefing ({today.strftime('%d.%m.%Y')})")
        print()
        print(_format_daily_report(
            client.student_id, client.student_type,
            tomorrow, timetable, substitutions,
            homework, exams, absences, messages,
        ))
    finally:
        await client.logout()
        await client.close()


if __name__ == "__main__":
    asyncio.run(run())
