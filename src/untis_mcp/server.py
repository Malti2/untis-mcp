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
async def app_lifespan():
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

    pid = params.student_id or client.person_id
    ptype = client.person_type or 5
    start = params.start_date or date.today().isoformat()
    end = params.end_date or (
        date.fromisoformat(start) + timedelta(days=6)
    ).isoformat()

    try:
        timetable = await client.get_timetable(pid, ptype, start, end)
        substitutions = await client.get_substitutions(start, end)
        return _format_json({
            "timetable": timetable,
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


# ── Entry point ─────────────────────────────────────────────────


def main():
    mcp.run()


if __name__ == "__main__":
    main()
