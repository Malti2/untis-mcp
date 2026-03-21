#!/usr/bin/env python3
"""MCP Server for WebUntis.

Provides tools to access school data: timetable, homework, exams, absences,
grades, and messages via the WebUntis platform.
"""

import json
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from .api import WebUntisClient, WebUntisAPIError

# ── Lifespan: create & authenticate the client once ─────────────


@asynccontextmanager
async def app_lifespan(app):
    server = os.environ.get("WEBUNTIS_SERVER", "")
    school = os.environ.get("WEBUNTIS_SCHOOL", "")
    username = os.environ.get("WEBUNTIS_USER", "")
    password = os.environ.get("WEBUNTIS_PASSWORD", "")

    if not all([server, school, username, password]):
        raise RuntimeError(
            "Set WEBUNTIS_SERVER, WEBUNTIS_SCHOOL, WEBUNTIS_USER, "
            "and WEBUNTIS_PASSWORD env vars"
        )

    client = WebUntisClient(server, school, username, password)
    await client.login()
    try:
        yield {"client": client}
    finally:
        await client.logout()
        await client.close()


mcp = FastMCP("untis_mcp", lifespan=app_lifespan)


def _get_client(ctx: Context) -> WebUntisClient:
    return ctx.request_context.lifespan_state["client"]


def _format_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _next_school_day(today: date) -> date:
    """Return the next school day (skip weekends)."""
    nxt = today + timedelta(days=1)
    while nxt.weekday() >= 5:  # 5=Sat, 6=Sun
        nxt += timedelta(days=1)
    return nxt


def _format_untis_date(d: Any) -> str:
    """Format a YYYYMMDD integer or string to DD.MM.YYYY."""
    s = str(d)
    if len(s) == 8 and s.isdigit():
        return f"{s[6:8]}.{s[4:6]}.{s[0:4]}"
    return s


# ── Input Models ────────────────────────────────────────────────


class TimetableInput(BaseModel):
    """Input for fetching the timetable."""
    model_config = ConfigDict(str_strip_whitespace=True)

    student_id: Optional[int] = Field(
        default=None,
        description="Person ID. Omit to use the logged-in user.",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date (YYYY-MM-DD). Defaults to today.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date (YYYY-MM-DD). Defaults to start + 6 days.",
    )


class DateRangeInput(BaseModel):
    """Input for date-range queries."""
    model_config = ConfigDict(str_strip_whitespace=True)

    start_date: Optional[str] = Field(
        default=None,
        description="Start date (YYYY-MM-DD). Defaults to today.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date (YYYY-MM-DD). Defaults vary by tool.",
    )


class ExamsInput(BaseModel):
    """Input for fetching exams."""
    model_config = ConfigDict(str_strip_whitespace=True)

    start_date: Optional[str] = Field(
        default=None,
        description="Start date (YYYY-MM-DD). Defaults to today.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date (YYYY-MM-DD). Defaults to start + 30 days.",
    )


# ── Tools ───────────────────────────────────────────────────────


@mcp.tool(
    name="untis_get_students",
    annotations={
        "title": "List Students",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_students(ctx: Context) -> str:
    """List all students linked to this WebUntis account.

    Returns the person ID and type from the login session.
    Use the person ID for timetable queries if needed.

    Returns:
        str: JSON with student/person information.
    """
    client = _get_client(ctx)
    await client.ensure_authenticated()

    # For parent accounts, return child students; otherwise the logged-in person
    if client.students:
        return _format_json(client.students)

    students = []
    if client.person_id is not None:
        students.append({
            "personId": client.person_id,
            "personType": client.person_type,
        })

    if not students:
        return "Kein Schueler-Profil gefunden."
    return _format_json(students)


@mcp.tool(
    name="untis_get_school_info",
    annotations={
        "title": "Get School Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_school_info(ctx: Context) -> str:
    """Fetch school information: current school year, subjects, and period grid.

    Returns:
        str: JSON with schoolyear, subjects list, and timegrid.
    """
    client = _get_client(ctx)

    try:
        schoolyear = await client.get_current_schoolyear()
        subjects = await client.get_subjects()
        timegrid = await client.get_timegrid()

        return _format_json({
            "schoolyear": schoolyear,
            "subjects": subjects,
            "timegrid": timegrid,
        })
    except Exception as e:
        return f"Error fetching school info: {e}"


@mcp.tool(
    name="untis_get_timetable",
    annotations={
        "title": "Get Timetable",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_timetable(params: TimetableInput, ctx: Context) -> str:
    """Fetch the class timetable/schedule for a student.

    Returns all lessons in the requested date range with subject,
    teacher, room, start/end times, and substitution info.

    Args:
        params: Timetable query parameters (student_id, start_date, end_date).

    Returns:
        str: JSON with lesson data for the requested period.
    """
    client = _get_client(ctx)
    await client.ensure_authenticated()

    pid = params.student_id or client.student_id
    ptype = client.student_type
    start = params.start_date or date.today().isoformat()
    end = params.end_date or (
        date.fromisoformat(start) + timedelta(days=6)
    ).isoformat()

    try:
        data = await client.get_timetable_enriched(pid, ptype, start, end)
        substitutions = await client.get_substitutions(start, end)
        return _format_json({
            "timetable": data["periods"],
            "substitutions": substitutions,
        })
    except Exception as e:
        return f"Error fetching timetable: {e}"


@mcp.tool(
    name="untis_get_homework",
    annotations={
        "title": "Get Homework",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_homework(params: DateRangeInput, ctx: Context) -> str:
    """Fetch homework assignments.

    Returns:
        str: JSON with homework data.
    """
    client = _get_client(ctx)
    start = params.start_date or date.today().isoformat()
    end = params.end_date or (
        date.fromisoformat(start) + timedelta(days=7)
    ).isoformat()

    try:
        data = await client.get_homework(start, end)
        return _format_json(data)
    except Exception as e:
        return f"Error fetching homework: {e}"


@mcp.tool(
    name="untis_get_exams",
    annotations={
        "title": "Get Exams",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_exams(params: ExamsInput, ctx: Context) -> str:
    """Fetch upcoming exams and tests.

    Returns:
        str: JSON with exam data.
    """
    client = _get_client(ctx)
    start = params.start_date or date.today().isoformat()
    end = params.end_date or (
        date.fromisoformat(start) + timedelta(days=30)
    ).isoformat()

    try:
        data = await client.get_exams(start, end)
        return _format_json(data)
    except Exception as e:
        return f"Error fetching exams: {e}"


@mcp.tool(
    name="untis_get_absences",
    annotations={
        "title": "Get Absences",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_absences(params: DateRangeInput, ctx: Context) -> str:
    """Fetch student absences and excuse status.

    Returns:
        str: JSON with absence data.
    """
    client = _get_client(ctx)
    start = params.start_date or date.today().isoformat()
    end = params.end_date or (
        date.fromisoformat(start) + timedelta(days=30)
    ).isoformat()

    try:
        data = await client.get_absences(start, end)
        return _format_json(data)
    except Exception as e:
        return f"Error fetching absences: {e}"


@mcp.tool(
    name="untis_get_messages",
    annotations={
        "title": "Get Messages",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_messages(ctx: Context) -> str:
    """Fetch inbox messages and notifications.

    Returns:
        str: JSON with message data.
    """
    client = _get_client(ctx)

    try:
        data = await client.get_messages()
        return _format_json(data)
    except Exception as e:
        return f"Error fetching messages: {e}"


@mcp.tool(
    name="untis_raw_call",
    annotations={
        "title": "Raw JSON-RPC Call",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def raw_call(method: str, parameters: str, ctx: Context) -> str:
    """Make a raw JSON-RPC call to any WebUntis endpoint.

    Use this for methods not covered by the other tools.

    Args:
        method: The JSON-RPC method name (e.g. 'getTeachers').
        parameters: JSON string with request parameters (e.g. '{}').

    Returns:
        str: JSON response from the API.
    """
    client = _get_client(ctx)

    try:
        params = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in parameters: {e}"

    try:
        await client.ensure_authenticated()
        data = await client._jsonrpc(method, params)
        return _format_json(data)
    except Exception as e:
        return f"Error: {e}"


# ── Daily Report Formatting ─────────────────────────────────────


def _format_daily_report(
    person_id: int,
    person_type: int,
    tomorrow: date,
    timetable: list,
    substitutions: list,
    homework: Any,
    exams: Any,
    absences: Any,
    messages: Any,
) -> str:
    """Build a Markdown daily briefing."""
    tom_str = tomorrow.strftime("%d.%m.%Y")
    wd = WEEKDAYS_DE[tomorrow.weekday()]
    tom_date_int = int(tomorrow.strftime("%Y%m%d"))

    lines: list[str] = []
    lines.append(f"## Schueler (ID {person_id})")
    lines.append("")

    # ── Tomorrow's lessons ────────────────────────────────────
    tom_lessons = [l for l in timetable if l.get("date") == tom_date_int]
    tom_lessons.sort(key=lambda l: l.get("startTime", 0))

    # Build substitution lookup: (date, startTime) -> substitution
    sub_lookup: dict[tuple[int, int], dict] = {}
    for sub in substitutions:
        key = (sub.get("date", 0), sub.get("startTime", 0))
        sub_lookup[key] = sub

    # Classify lessons
    regular_subjects: list[str] = []
    cancellations: list[str] = []
    substitution_subjects: list[str] = []

    for lesson in tom_lessons:
        subjects = lesson.get("su", [])
        subj_name = subjects[0].get("name", "?") if subjects else "?"

        key = (lesson.get("date", 0), lesson.get("startTime", 0))
        sub = sub_lookup.get(key)

        if sub and sub.get("type") == "cancel":
            cancellations.append(subj_name)
        elif sub:
            substitution_subjects.append(subj_name)
            regular_subjects.append(subj_name)
        else:
            regular_subjects.append(subj_name)

    # ── Homework ──────────────────────────────────────────────
    hw_list = []
    hw_lessons: dict[int, str] = {}  # lessonId -> subject name
    if isinstance(homework, dict):
        hw_data = homework.get("data", homework)
        hw_list = hw_data.get("homeworks", [])
        # Build lesson->subject lookup
        for lesson in hw_data.get("lessons", []):
            hw_lessons[lesson.get("id", 0)] = lesson.get("subject", "?")
    elif isinstance(homework, list):
        hw_list = homework

    # ── Exams ─────────────────────────────────────────────────
    exam_list = []
    if isinstance(exams, dict):
        exam_list = exams.get("data", {}).get("exams", [])
        if not exam_list:
            exam_list = exams.get("exams", [])
    elif isinstance(exams, list):
        exam_list = exams
    exam_list = sorted(exam_list, key=lambda e: e.get("examDate", 0))

    # ── Absences ──────────────────────────────────────────────
    absence_list = []
    if isinstance(absences, dict):
        absence_list = absences.get("data", {}).get("absences", [])
        if not absence_list:
            absence_list = absences.get("absences", [])
    elif isinstance(absences, list):
        absence_list = absences

    # ── Messages ──────────────────────────────────────────────
    msg_list = []
    if isinstance(messages, dict):
        msg_list = messages.get("data", {}).get("messages", [])
        if not msg_list:
            msg_list = messages.get("messages", [])
    elif isinstance(messages, list):
        msg_list = messages

    unread = [m for m in msg_list if not m.get("isRead", True)]

    # ── Summary ("Auf einen Blick") ───────────────────────────
    summary: list[str] = []

    # Schedule
    if tom_lessons:
        seen = set()
        unique = [s for s in regular_subjects if not (s in seen or seen.add(s))]
        subj_str = ", ".join(unique)

        alerts = []
        if cancellations:
            alerts.append(f"**{len(cancellations)}x Entfall** ({', '.join(cancellations)})")
        if substitution_subjects:
            alerts.append(f"{len(substitution_subjects)}x Vertretung ({', '.join(substitution_subjects)})")

        if alerts:
            summary.append(f"Stundenplan {wd}: {'; '.join(alerts)}, {subj_str}")
        else:
            summary.append(f"Stundenplan {wd}: {subj_str}")
    else:
        summary.append(f"**Kein Unterricht** am {wd}")

    # Exams
    if exam_list:
        summary.append(
            f"**{len(exam_list)} Klausur{'en' if len(exam_list) != 1 else ''} diese Woche**"
        )

    # Homework
    if hw_list:
        summary.append(f"**{len(hw_list)} Hausaufgaben** eingetragen")
    else:
        summary.append("Keine Hausaufgaben eingetragen")

    # Messages
    if unread:
        summary.append(f"**{len(unread)} ungelesene Nachricht{'en' if len(unread) != 1 else ''}**")

    # Absences
    unexcused = [a for a in absence_list if not a.get("isExcused", True)]
    if unexcused:
        summary.append(f"Fehlzeiten: {len(unexcused)} unentschuldigte Eintraege")

    lines.append("### Auf einen Blick")
    for b in summary:
        lines.append(f"- {b}")
    lines.append("")

    # ── Messages detail ───────────────────────────────────────
    lines.append(f"### Neue Nachrichten ({len(unread)})")
    if unread:
        for m in unread:
            subject = m.get("subject", m.get("title", "?"))
            lines.append(f"- **{subject}**")
    else:
        lines.append("- Keine ungelesenen Nachrichten")
    lines.append("")

    # ── Timetable detail ──────────────────────────────────────
    lines.append(f"### Stundenplan {wd} {tom_str}")
    if tom_lessons:
        period = 0
        for lesson in tom_lessons:
            period += 1
            subjects = lesson.get("su", [])
            subj = subjects[0].get("name", "?") if subjects else "?"
            teachers = lesson.get("te", [])
            teacher = teachers[0].get("name", "") if teachers else ""
            rooms = lesson.get("ro", [])
            room = rooms[0].get("name", "") if rooms else ""

            key = (lesson.get("date", 0), lesson.get("startTime", 0))
            sub = sub_lookup.get(key)

            if sub and sub.get("type") == "cancel":
                lines.append(f"- **{period}. Stunde**: ~~{subj}~~ -- Entfall")
            elif sub:
                change = " (Vertretung)"
                room_str = f", Raum {room}" if room else ""
                teacher_str = f" ({teacher})" if teacher else ""
                lines.append(f"- **{period}. Stunde**: {subj}{teacher_str}{room_str}{change}")
            else:
                room_str = f", Raum {room}" if room else ""
                teacher_str = f" ({teacher})" if teacher else ""
                lines.append(f"- **{period}. Stunde**: {subj}{teacher_str}{room_str}")
    else:
        lines.append("- Kein Unterricht")
    lines.append("")

    # ── Exams detail ──────────────────────────────────────────
    lines.append("### Klausuren & Tests (naechste 7 Tage)")
    if exam_list:
        for ex in exam_list:
            ex_date = _format_untis_date(ex.get("examDate", "?"))
            subj = ex.get("subject", ex.get("name", "?"))
            ex_type = ex.get("examType", "Test")
            lines.append(f"- **{ex_date}**: {subj} ({ex_type})")
    else:
        lines.append("- Keine anstehenden Arbeiten")
    lines.append("")

    # ── Homework detail ───────────────────────────────────────
    lines.append("### Hausaufgaben (naechste 7 Tage)")
    if hw_list:
        for h in hw_list:
            # Subject from lesson lookup, or direct field
            subj = h.get("subject", hw_lessons.get(h.get("lessonId", 0), "?"))
            text = h.get("text", h.get("description", ""))
            due_raw = h.get("dueDate", "")
            due = _format_untis_date(due_raw) if due_raw else ""
            lines.append(f"- **{subj}**: {text}" + (f" (bis {due})" if due else ""))
    else:
        lines.append("- Keine Hausaufgaben eingetragen")
    lines.append("")

    # ── Absences detail ───────────────────────────────────────
    lines.append("### Fehlzeiten")
    if absence_list:
        for a in absence_list:
            status = "entschuldigt" if a.get("isExcused", False) else "unentschuldigt"
            a_date = _format_untis_date(a.get("date", a.get("startDate", "?")))
            lines.append(f"- {a_date}: {status}")
    else:
        lines.append("- Keine Fehlzeiten")
    lines.append("")

    return "\n".join(lines)


@mcp.tool(
    name="untis_daily_report",
    annotations={
        "title": "Daily Parent Briefing",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def daily_report(ctx: Context) -> str:
    """Generate a daily parent briefing.

    The report includes:
    - Unread messages
    - Tomorrow's class schedule (next school day, skips weekends)
    - Exams and tests in the next 7 days
    - Homework
    - Absences

    No parameters needed -- automatically picks the right dates.

    Returns:
        str: Markdown-formatted daily briefing.
    """
    client = _get_client(ctx)
    await client.ensure_authenticated()

    if client.student_id is None:
        return "Kein Schueler-Profil gefunden."

    today = date.today()
    tomorrow = _next_school_day(today)
    exam_end = (today + timedelta(days=7)).isoformat()

    # Fetch all data
    try:
        enriched = await client.get_timetable_enriched(
            client.student_id, client.student_type,
            tomorrow.isoformat(), tomorrow.isoformat(),
        )
        timetable = enriched["periods"]
    except Exception:
        timetable = []

    try:
        substitutions = await client.get_substitutions(
            tomorrow.isoformat(), tomorrow.isoformat(),
        )
    except Exception:
        substitutions = []

    try:
        homework = await client.get_homework(
            today.isoformat(), exam_end,
        )
    except Exception:
        homework = {}

    try:
        exams = await client.get_exams(
            today.isoformat(), exam_end,
        )
    except Exception:
        exams = {}

    try:
        absences = await client.get_absences(
            today.isoformat(), exam_end,
        )
    except Exception:
        absences = {}

    try:
        messages = await client.get_messages()
    except Exception:
        messages = {}

    # Build report
    parts: list[str] = []
    parts.append(f"# Eltern-Briefing ({today.strftime('%d.%m.%Y')})")
    parts.append("")
    parts.append(_format_daily_report(
        client.student_id, client.student_type,
        tomorrow, timetable, substitutions,
        homework, exams, absences, messages,
    ))

    return "\n".join(parts)


# ── Entry point ─────────────────────────────────────────────────


def main():
    mcp.run()


if __name__ == "__main__":
    main()
