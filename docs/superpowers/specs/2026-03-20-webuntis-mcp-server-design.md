# WebUntis MCP Server -- Design Spec

**Date**: 2026-03-20
**Status**: Approved

## Overview

Build a Python MCP server for WebUntis (dhg-meersburg.webuntis.com) that provides Claude Code with read-only access to school data: timetable, homework, exams, absences, messages, and a daily parent briefing. Architecture mirrors the existing Schulmanager MCP server at `../schulmanager/`.

## Context

- **School**: DHG Meersburg, using WebUntis
- **Auth**: Username + Password (no 2FA)
- **Students**: One child currently, but multi-child support built in
- **Approach**: Custom async httpx client (no external webuntis package)

## Project Structure

```
untis/
├── src/untis_mcp/
│   ├── __init__.py
│   ├── api.py          # WebUntis API Client (JSON-RPC + REST)
│   └── server.py       # FastMCP Server with tools + daily report
├── daily_report.py     # Standalone report script (imports _format_daily_report from server.py, runs without MCP)
├── daily_report.sh     # Bash wrapper for cron/manual use
├── start.sh            # Server start with .env loading
├── .env                # Credentials (gitignored)
├── .env.example        # Template
└── pyproject.toml      # Python project config
```

## Dependencies

```toml
[project]
name = "untis-mcp"
version = "0.1.0"
description = "MCP server for accessing WebUntis school data"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
]

[project.scripts]
untis-mcp = "untis_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/untis_mcp"]
```

## Configuration

Four environment variables:

| Variable | Example | Description |
|---|---|---|
| `WEBUNTIS_SERVER` | `dhg-meersburg.webuntis.com` | WebUntis server hostname |
| `WEBUNTIS_SCHOOL` | `dhg-meersburg` | School identifier |
| `WEBUNTIS_USER` | `user@example.com` | Login username/email |
| `WEBUNTIS_PASSWORD` | `your-password` | Login password |

## API Client (`api.py`)

### Dual-Protocol Architecture

WebUntis exposes two API layers:

1. **JSON-RPC 2.0** at `/WebUntis/jsonrpc.do?school=<school>`
   - Cookie-based sessions (JSESSIONID)
   - Used for: timetable, substitutions, teachers, subjects, rooms, classes, holidays, timegrid, schoolyear, exams

2. **REST/WebAPI** at `/WebUntis/api/...`
   - JWT Bearer token (obtained via `/api/token/new` after JSON-RPC login)
   - Used for: homework, absences, messages, news

### Authentication Flow

```
1. JSON-RPC authenticate(user, password, client="untis-mcp")
   → JSESSIONID cookie + personId + personType
2. GET /api/token/new (with JSESSIONID cookie)
   → JWT Bearer token for REST endpoints
3. All subsequent requests use JSESSIONID (JSON-RPC) or Bearer token (REST)
```

### Session Management

- Session timeout: ~10 minutes idle
- Track login timestamp; auto-re-authenticate after 8 minutes (conservative) or on 401/session error
- Check timing in `ensure_authenticated()` (same pattern as Schulmanager: `time.time() >= self.session_expiry`)
- Single httpx.AsyncClient with cookie persistence
- JWT token stored alongside, refreshed on re-auth
- Set `User-Agent: untis-mcp/0.1.0` header on all requests

### JSON-RPC Protocol Details

Request envelope format (JSON-RPC 2.0):
```json
{
  "id": "<sequential-integer>",
  "method": "<method-name>",
  "params": {...},
  "jsonrpc": "2.0"
}
```

Error responses contain `error.code` and `error.message` fields. The client uses a sequential integer counter for request IDs.

### Person Type Codes

| Code | Meaning |
|---|---|
| 1 | Klasse (class) |
| 2 | Lehrer (teacher) |
| 5 | Schueler (student) |

The `authenticate` response returns `personId` and `personType`. For parent accounts, the person type is typically 5 (student) with the child's personId.

### JSON-RPC Methods

| Method | Returns |
|---|---|
| `authenticate` | Session + personId + personType |
| `logout` | Session cleanup |
| `getTimetable` | Lessons for person (params: `id`, `type`, `startDate`, `endDate` as YYYYMMDD ints) |
| `getSubstitutions` | Substitutions for date range |
| `getTeachers` | All teachers |
| `getSubjects` | All subjects |
| `getRooms` | All rooms |
| `getKlassen` | All classes |
| `getHolidays` | Holiday periods |
| `getTimegridUnits` | Period/hour structure |
| `getCurrentSchoolyear` | Current school year dates |
| `getExams` | Exams for date range |

### REST Endpoints

**Note**: REST query parameters use `YYYYMMDD` integer format (no dashes), same as JSON-RPC.

| Endpoint | Returns |
|---|---|
| `GET /api/token/new` | JWT token |
| `GET /api/homeworks/lessons?startDate=YYYYMMDD&endDate=YYYYMMDD` | Homework |
| `GET /api/exams?startDate=YYYYMMDD&endDate=YYYYMMDD` | Exams (detailed) |
| `GET /api/classreg/absences/students?startDate=YYYYMMDD&endDate=YYYYMMDD` | Absences |
| `GET /api/rest/view/v1/messages` | Inbox messages |
| `GET /api/public/news/newsWidgetData` | School news |

### Class: `WebUntisClient`

```python
class WebUntisClient:
    def __init__(self, server: str, school: str, username: str, password: str)

    # Auth
    async def login() -> None
    async def logout() -> None
    async def ensure_authenticated() -> None

    # JSON-RPC (low-level)
    async def _jsonrpc(method: str, params: dict) -> Any

    # High-level data access
    async def get_timetable(person_id: int, person_type: int, start: str, end: str) -> list
    async def get_substitutions(start: str, end: str) -> list
    async def get_teachers() -> list
    async def get_subjects() -> list
    async def get_rooms() -> list
    async def get_klassen() -> list
    async def get_holidays() -> list
    async def get_timegrid() -> list
    async def get_current_schoolyear() -> dict
    async def get_exams(start: str, end: str) -> list

    # REST endpoints
    async def get_homework(start: str, end: str) -> list
    async def get_absences(start: str, end: str) -> list
    async def get_messages() -> list
    async def get_news() -> list

    async def close() -> None
```

## MCP Server (`server.py`)

### Lifespan

```python
@asynccontextmanager
async def app_lifespan():
    # Read env vars, create WebUntisClient, login
    # yield {"client": client}
    # logout + close on shutdown
```

### Tools

| Tool Name | Input | Source |
|---|---|---|
| `untis_get_students` | none | Login response (personId, personType). Single-user accounts return one entry. Multi-child accounts: enumerate via `getKlassen` + `getStudents` if available, otherwise store the logged-in person. |
| `untis_get_timetable` | student_id?, start_date?, end_date? | JSON-RPC getTimetable + getSubstitutions |
| `untis_get_homework` | start_date?, end_date? | REST /api/homeworks/lessons |
| `untis_get_exams` | start_date?, end_date? | REST /api/exams |
| `untis_get_absences` | start_date?, end_date? | REST /api/classreg/absences/students |
| `untis_get_messages` | none | REST /api/rest/view/v1/messages |
| `untis_get_school_info` | none | JSON-RPC (schoolyear, subjects, timegrid) |
| `untis_daily_report` | none | Combines timetable, homework, exams, absences, messages |
| `untis_raw_call` | method, params (JSON string) | Arbitrary JSON-RPC call for uncovered endpoints |

All tools annotated with:
- `readOnlyHint: true`
- `destructiveHint: false`
- `idempotentHint: true`
- `openWorldHint: true`

### Pydantic Input Models

```python
class TimetableInput(BaseModel):
    student_id: Optional[int] = None  # personId, defaults to logged-in user
    start_date: Optional[str] = None  # YYYY-MM-DD, defaults to today
    end_date: Optional[str] = None    # YYYY-MM-DD, defaults to start + 6 days

class DateRangeInput(BaseModel):
    start_date: Optional[str] = None  # YYYY-MM-DD, defaults to today
    end_date: Optional[str] = None    # YYYY-MM-DD, defaults vary: +7 days for homework/absences, +30 days for exams
```

### Input Model Defaults by Tool

| Tool | end_date default |
|---|---|
| `untis_get_timetable` | start + 6 days |
| `untis_get_homework` | start + 7 days |
| `untis_get_exams` | start + 30 days |
| `untis_get_absences` | start + 30 days |

## Daily Report Format

```markdown
# Eltern-Briefing (20.03.2026)

## [Schuelername]

### Auf einen Blick
- Stundenplan Mo: Mathe, Deutsch, Englisch, Sport
- **1x Vertretung** (Mathe -> Frau Schmidt)
- **2. Stunde entfaellt** (Physik)
- **1 Klausur diese Woche** -- Mi Deutsch (Klassenarbeit)
- Hausaufgaben fuer Mo: Mathe, Englisch
- **3 ungelesene Nachrichten**
- Fehlzeiten: 2 unentschuldigte Stunden

### Neue Nachrichten (3)
- **Elternsprechtag** (18.03.)

### Stundenplan Mo 21.03.2026
- **1. Stunde**: Mathe (Mueller), Raum 204
- **2. Stunde**: ~~Physik~~ -- Entfall

### Klausuren & Tests (naechste 7 Tage)
- **23.03.**: Deutsch (Klassenarbeit)

### Hausaufgaben (naechste 7 Tage)
- **Mo 21.03. Mathe**: Seite 42, Aufgaben 1-5

### Fehlzeiten
- 2 unentschuldigte Stunden (15.03.)
```

Key differences from Schulmanager report:
- **Absences section** added (WebUntis tracks this)
- **No parent letters** (WebUntis uses "messages" instead)
- Timetable merges substitution data inline

## Error Handling

| Scenario | Handling |
|---|---|
| Session timeout (~10 min) | Auto-re-authenticate after 8 min or on 401 |
| Weekend dates | `_next_school_day()` skips Sat/Sun |
| Holidays | Empty timetable -> "Kein Unterricht (Ferien?)" |
| REST endpoint unavailable | Graceful fallback with info message |
| No student profile | Clear error: "Kein Schueler-Profil gefunden" |
| Invalid credentials | Raise error on login, don't retry |

## Date Formats

- **JSON-RPC**: Dates as integers `YYYYMMDD` (e.g., `20260320`)
- **REST**: Dates as integers `YYYYMMDD` in query params (e.g., `20260320`) -- same format as JSON-RPC
- **MCP Tool inputs**: Accept `YYYY-MM-DD` strings, convert internally
- **Report output**: German format `DD.MM.YYYY`

## Security

- Read-only: No write operations
- Credentials in `.env` file (gitignored)
- Session tokens in memory only, not persisted
- Local execution only (not a public service)
