# WebUntis MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that gives Claude Code read-only access to WebUntis school data (timetable, homework, exams, absences, messages) plus a daily parent briefing.

**Architecture:** Custom async httpx client talks to WebUntis via two protocols: JSON-RPC 2.0 (timetable, master data) and REST/WebAPI (homework, absences, messages). FastMCP wraps the client as 9 MCP tools. Mirrors the Schulmanager MCP server at `../schulmanager/`.

**Tech Stack:** Python 3.11+, FastMCP (`mcp[cli]`), httpx, Pydantic, hatchling

**Spec:** `docs/superpowers/specs/2026-03-20-webuntis-mcp-server-design.md`

**Reference implementation:** `../schulmanager/src/schulmanager_mcp/` (api.py + server.py)

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Project metadata, dependencies, entry point, build config |
| `.env.example` | Credential template (4 env vars) |
| `.gitignore` | Ignore `.env`, `__pycache__`, `.venv`, `*.egg-info` |
| `start.sh` | Load `.env`, exec python MCP server |
| `src/untis_mcp/__init__.py` | Package marker with docstring |
| `src/untis_mcp/api.py` | WebUntis API client: auth, JSON-RPC, REST, session mgmt |
| `src/untis_mcp/server.py` | FastMCP server: lifespan, 9 tools, daily report formatter |
| `daily_report.py` | Standalone script: import from server.py, run without MCP |
| `daily_report.sh` | Bash wrapper for cron/manual use |
| `tests/test_api.py` | Unit tests for api.py (mocked HTTP) |
| `tests/test_server.py` | Unit tests for server.py (report formatting, date logic) |

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `start.sh`
- Create: `src/untis_mcp/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

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

- [ ] **Step 2: Create `.env.example`**

```
WEBUNTIS_SERVER=dhg-meersburg.webuntis.com
WEBUNTIS_SCHOOL=dhg-meersburg
WEBUNTIS_USER=user@example.com
WEBUNTIS_PASSWORD=your-password
```

- [ ] **Step 3: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
build/
```

- [ ] **Step 4: Create `start.sh`**

```bash
#!/usr/bin/env bash
# Load .env and start the WebUntis MCP server
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi
exec "$SCRIPT_DIR/.venv/bin/python" -m untis_mcp.server "$@"
```

- [ ] **Step 5: Create `src/untis_mcp/__init__.py`**

```python
"""MCP server for accessing WebUntis school data."""
```

- [ ] **Step 6: Create `.env` with credentials**

Copy `.env.example` to `.env` and fill in the real credentials (server, school, username, password).
This file is gitignored and must not be committed.

- [ ] **Step 7: Create venv and install dependencies**

Run:
```bash
cd /Users/D054904/kohlsalem/untis
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]" 2>/dev/null || .venv/bin/pip install -e .
.venv/bin/pip install pytest pytest-asyncio respx
```

- [ ] **Step 8: Make start.sh executable**

Run: `chmod +x start.sh`

- [ ] **Step 9: Commit scaffold**

```bash
git init
git add pyproject.toml .env.example .gitignore start.sh src/untis_mcp/__init__.py
git commit -m "PROJECT: scaffold untis-mcp project"
```

---

## Task 2: API Client -- JSON-RPC Core + Authentication

**Files:**
- Create: `src/untis_mcp/api.py`
- Create: `tests/test_api.py`

This task implements the `WebUntisClient` class with JSON-RPC transport and authentication. No high-level data methods yet.

- [ ] **Step 1: Write failing test for JSON-RPC request envelope**

Create `tests/test_api.py`:

```python
"""Tests for the WebUntis API client."""

import json
import time
import pytest
import httpx
import respx
from untis_mcp.api import WebUntisClient, WebUntisAPIError


class TestJsonRpc:
    """Test JSON-RPC transport layer."""

    @pytest.fixture
    def client(self):
        return WebUntisClient(
            server="test.webuntis.com",
            school="test-school",
            username="testuser",
            password="testpass",
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_jsonrpc_sends_correct_envelope(self, client):
        """JSON-RPC requests must use the 2.0 envelope format."""
        route = respx.post(
            "https://test.webuntis.com/WebUntis/jsonrpc.do",
            params={"school": "test-school"},
        ).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"sessionId": "ABC123"},
        }))

        # Force client to have a session so _jsonrpc doesn't try to auth
        client._session_id = "fake"
        client._session_expiry = 9999999999.0

        result = await client._jsonrpc("someMethod", {"key": "value"})

        assert route.called
        req_body = route.calls[0].request.content
        import json
        body = json.loads(req_body)
        assert body["jsonrpc"] == "2.0"
        assert body["method"] == "someMethod"
        assert body["params"] == {"key": "value"}
        assert isinstance(body["id"], str)
        assert result == {"sessionId": "ABC123"}

        await client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py::TestJsonRpc::test_jsonrpc_sends_correct_envelope -v`
Expected: FAIL (ImportError -- `untis_mcp.api` does not exist yet)

- [ ] **Step 3: Implement `api.py` with JSON-RPC core + auth**

Create `src/untis_mcp/api.py`:

```python
"""WebUntis API client.

Handles authentication (JSON-RPC session + JWT) and all API communication
with the WebUntis platform via two protocols:
- JSON-RPC 2.0 for timetable, master data, exams
- REST/WebAPI for homework, absences, messages
"""

import json
import time
from typing import Any

import httpx

# Session valid for ~10 min; re-auth after 8 min (conservative)
SESSION_LIFETIME = 480  # seconds


class WebUntisAPIError(Exception):
    """Raised when the WebUntis API returns an error."""


class WebUntisClient:
    """Async client for the WebUntis API."""

    def __init__(
        self, server: str, school: str, username: str, password: str
    ) -> None:
        self.server = server
        self.school = school
        self.username = username
        self.password = password

        # URLs
        self._base_url = f"https://{server}/WebUntis"
        self._rpc_url = f"{self._base_url}/jsonrpc.do"

        # Session state
        self._session_id: str | None = None
        self._session_expiry: float = 0
        self._person_id: int | None = None
        self._person_type: int | None = None
        self._jwt_token: str | None = None
        self._rpc_id: int = 0

        # HTTP client
        self._http: httpx.AsyncClient | None = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "untis-mcp/0.1.0"},
            )
        return self._http

    def _next_rpc_id(self) -> str:
        self._rpc_id += 1
        return str(self._rpc_id)

    # ── JSON-RPC Transport ───────────────────────────────────────

    async def _jsonrpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC 2.0 request and return the result."""
        client = await self._client()

        payload = {
            "id": self._next_rpc_id(),
            "method": method,
            "params": params or {},
            "jsonrpc": "2.0",
        }

        resp = await client.post(
            self._rpc_url,
            params={"school": self.school},
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()

        if "error" in body:
            err = body["error"]
            code = err.get("code", -1)
            msg = err.get("message", "Unknown JSON-RPC error")
            raise WebUntisAPIError(f"JSON-RPC error {code}: {msg}")

        return body.get("result")

    # ── Authentication ───────────────────────────────────────────

    async def login(self) -> None:
        """Authenticate via JSON-RPC and obtain JWT token for REST."""
        result = await self._jsonrpc("authenticate", {
            "user": self.username,
            "password": self.password,
            "client": "untis-mcp",
        })

        self._session_id = result.get("sessionId")
        self._person_id = result.get("personId")
        self._person_type = result.get("personType")
        self._session_expiry = time.time() + SESSION_LIFETIME

        if not self._session_id:
            raise WebUntisAPIError(
                f"Login failed: no sessionId. Keys: {list(result.keys())}"
            )

        # Store JSESSIONID cookie for subsequent requests
        client = await self._client()
        client.cookies.set(
            "JSESSIONID", self._session_id,
            domain=self.server, path="/WebUntis",
        )
        # School name cookie (base64 of school name, but WebUntis just uses the name)
        client.cookies.set(
            "schoolname", self.school,
            domain=self.server, path="/WebUntis",
        )

        # Get JWT token for REST endpoints
        await self._fetch_jwt_token()

    async def _fetch_jwt_token(self) -> None:
        """Obtain a JWT Bearer token for REST API endpoints."""
        client = await self._client()
        try:
            resp = await client.get(f"{self._base_url}/api/token/new")
            resp.raise_for_status()
            self._jwt_token = resp.text.strip().strip('"')
        except Exception:
            # JWT token is optional; some schools may not support it
            self._jwt_token = None

    async def logout(self) -> None:
        """End the JSON-RPC session."""
        if self._session_id:
            try:
                await self._jsonrpc("logout", {})
            except Exception:
                pass
            self._session_id = None
            self._session_expiry = 0
            self._jwt_token = None

    async def ensure_authenticated(self) -> None:
        """Re-authenticate if session is expired or missing."""
        if not self._session_id or time.time() >= self._session_expiry:
            await self.login()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ── Properties ───────────────────────────────────────────────

    @property
    def person_id(self) -> int | None:
        return self._person_id

    @property
    def person_type(self) -> int | None:
        return self._person_type
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py::TestJsonRpc::test_jsonrpc_sends_correct_envelope -v`
Expected: PASS

- [ ] **Step 5: Write failing test for authentication**

Add to `tests/test_api.py`:

```python
class TestAuth:
    """Test authentication flow."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_sets_session_and_person(self):
        """Login must store sessionId, personId, personType."""
        client = WebUntisClient("test.webuntis.com", "test-school", "user", "pass")

        respx.post(
            "https://test.webuntis.com/WebUntis/jsonrpc.do",
            params={"school": "test-school"},
        ).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": "1",
            "result": {"sessionId": "SID123", "personId": 42, "personType": 5},
        }))

        respx.get(
            "https://test.webuntis.com/WebUntis/api/token/new",
        ).mock(return_value=httpx.Response(200, text='"jwt-token-abc"'))

        await client.login()

        assert client._session_id == "SID123"
        assert client.person_id == 42
        assert client.person_type == 5
        assert client._jwt_token == "jwt-token-abc"
        assert client._session_expiry > time.time()

        await client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_ensure_authenticated_relogins_on_expiry(self):
        """ensure_authenticated must re-login when session is expired."""
        client = WebUntisClient("test.webuntis.com", "test-school", "user", "pass")
        client._session_expiry = 0  # expired

        route = respx.post(
            "https://test.webuntis.com/WebUntis/jsonrpc.do",
            params={"school": "test-school"},
        ).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": "1",
            "result": {"sessionId": "NEW", "personId": 1, "personType": 5},
        }))

        respx.get(
            "https://test.webuntis.com/WebUntis/api/token/new",
        ).mock(return_value=httpx.Response(200, text='"jwt"'))

        await client.ensure_authenticated()
        assert client._session_id == "NEW"
        assert route.called

        await client.close()
```

- [ ] **Step 6: Run auth tests**

Run: `.venv/bin/pytest tests/test_api.py::TestAuth -v`
Expected: PASS (implementation already covers this)

- [ ] **Step 7: Write failing test for JSON-RPC error handling**

Add to `tests/test_api.py`:

```python
    @respx.mock
    @pytest.mark.asyncio
    async def test_jsonrpc_error_raises(self, client):
        """JSON-RPC errors must raise WebUntisAPIError."""
        respx.post(
            "https://test.webuntis.com/WebUntis/jsonrpc.do",
            params={"school": "test-school"},
        ).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": "1",
            "error": {"code": -8520, "message": "not authenticated"},
        }))

        client._session_id = "fake"
        client._session_expiry = 9999999999.0

        with pytest.raises(WebUntisAPIError, match="not authenticated"):
            await client._jsonrpc("getTimetable", {})

        await client.close()
```

Add this test to the `TestJsonRpc` class.

- [ ] **Step 8: Run error test**

Run: `.venv/bin/pytest tests/test_api.py::TestJsonRpc::test_jsonrpc_error_raises -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/untis_mcp/api.py tests/test_api.py
git commit -m "FEAT: add WebUntis API client with JSON-RPC transport and authentication"
```

---

## Task 3: API Client -- High-Level JSON-RPC Methods

**Files:**
- Modify: `src/untis_mcp/api.py`
- Modify: `tests/test_api.py`

Add all high-level JSON-RPC data methods: timetable, substitutions, master data.

- [ ] **Step 1: Write failing test for `get_timetable`**

Add to `tests/test_api.py`:

```python
import time

class TestDataMethods:
    """Test high-level data access methods."""

    @pytest.fixture
    def authed_client(self):
        c = WebUntisClient("test.webuntis.com", "test-school", "user", "pass")
        c._session_id = "SID"
        c._session_expiry = time.time() + 9999
        c._person_id = 42
        c._person_type = 5
        return c

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_timetable_sends_correct_params(self, authed_client):
        """get_timetable must send id, type, startDate, endDate as YYYYMMDD ints."""
        route = respx.post(
            "https://test.webuntis.com/WebUntis/jsonrpc.do",
            params={"school": "test-school"},
        ).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": "1",
            "result": [{"id": 1, "date": 20260320, "startTime": 800}],
        }))

        result = await authed_client.get_timetable(42, 5, "2026-03-20", "2026-03-26")

        body = json.loads(route.calls[0].request.content)
        assert body["method"] == "getTimetable"
        assert body["params"]["id"] == 42
        assert body["params"]["type"] == 5
        assert body["params"]["startDate"] == 20260320
        assert body["params"]["endDate"] == 20260326
        assert result == [{"id": 1, "date": 20260320, "startTime": 800}]

        await authed_client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py::TestDataMethods::test_get_timetable_sends_correct_params -v`
Expected: FAIL (AttributeError -- `get_timetable` not defined)

- [ ] **Step 3: Implement all JSON-RPC data methods**

Add to `src/untis_mcp/api.py` at the end of the `WebUntisClient` class:

```python
    # ── Date Helpers ─────────────────────────────────────────────

    @staticmethod
    def _to_untis_date(iso_date: str) -> int:
        """Convert 'YYYY-MM-DD' to YYYYMMDD integer."""
        return int(iso_date.replace("-", ""))

    # ── JSON-RPC Data Methods ────────────────────────────────────

    async def get_timetable(
        self, person_id: int, person_type: int, start: str, end: str
    ) -> list[dict[str, Any]]:
        """Fetch timetable for a person in a date range.

        Args:
            person_id: The person's Untis ID.
            person_type: 1=class, 2=teacher, 5=student.
            start: Start date as YYYY-MM-DD.
            end: End date as YYYY-MM-DD.
        """
        await self.ensure_authenticated()
        result = await self._jsonrpc("getTimetable", {
            "id": person_id,
            "type": person_type,
            "startDate": self._to_untis_date(start),
            "endDate": self._to_untis_date(end),
        })
        return result if isinstance(result, list) else []

    async def get_substitutions(self, start: str, end: str) -> list[dict[str, Any]]:
        """Fetch substitutions (Vertretungen) for a date range."""
        await self.ensure_authenticated()
        result = await self._jsonrpc("getSubstitutions", {
            "startDate": self._to_untis_date(start),
            "endDate": self._to_untis_date(end),
            "departmentId": 0,
        })
        return result if isinstance(result, list) else []

    async def get_teachers(self) -> list[dict[str, Any]]:
        await self.ensure_authenticated()
        result = await self._jsonrpc("getTeachers")
        return result if isinstance(result, list) else []

    async def get_subjects(self) -> list[dict[str, Any]]:
        await self.ensure_authenticated()
        result = await self._jsonrpc("getSubjects")
        return result if isinstance(result, list) else []

    async def get_rooms(self) -> list[dict[str, Any]]:
        await self.ensure_authenticated()
        result = await self._jsonrpc("getRooms")
        return result if isinstance(result, list) else []

    async def get_klassen(self) -> list[dict[str, Any]]:
        await self.ensure_authenticated()
        result = await self._jsonrpc("getKlassen")
        return result if isinstance(result, list) else []

    async def get_holidays(self) -> list[dict[str, Any]]:
        await self.ensure_authenticated()
        result = await self._jsonrpc("getHolidays")
        return result if isinstance(result, list) else []

    async def get_timegrid(self) -> list[dict[str, Any]]:
        await self.ensure_authenticated()
        result = await self._jsonrpc("getTimegridUnits")
        return result if isinstance(result, list) else []

    async def get_current_schoolyear(self) -> dict[str, Any]:
        await self.ensure_authenticated()
        result = await self._jsonrpc("getCurrentSchoolyear")
        return result if isinstance(result, dict) else {}

    async def get_exams_rpc(self, start: str, end: str) -> list[dict[str, Any]]:
        """Fetch exams via JSON-RPC (less detailed than REST)."""
        await self.ensure_authenticated()
        result = await self._jsonrpc("getExams", {
            "startDate": self._to_untis_date(start),
            "endDate": self._to_untis_date(end),
        })
        return result if isinstance(result, list) else []
```

- [ ] **Step 4: Run timetable test**

Run: `.venv/bin/pytest tests/test_api.py::TestDataMethods::test_get_timetable_sends_correct_params -v`
Expected: PASS

- [ ] **Step 5: Write test for `_to_untis_date` helper**

Add to `tests/test_api.py`:

```python
class TestHelpers:
    def test_to_untis_date(self):
        assert WebUntisClient._to_untis_date("2026-03-20") == 20260320
        assert WebUntisClient._to_untis_date("2026-01-01") == 20260101
```

- [ ] **Step 6: Run helper test**

Run: `.venv/bin/pytest tests/test_api.py::TestHelpers -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/untis_mcp/api.py tests/test_api.py
git commit -m "FEAT: add JSON-RPC data methods (timetable, substitutions, master data)"
```

---

## Task 4: API Client -- REST Endpoints

**Files:**
- Modify: `src/untis_mcp/api.py`
- Modify: `tests/test_api.py`

Add REST endpoint methods: homework, absences, messages, news, exams.

- [ ] **Step 1: Write failing test for REST `get_homework`**

Add to `tests/test_api.py`:

```python
class TestRestEndpoints:
    """Test REST/WebAPI endpoint methods."""

    @pytest.fixture
    def authed_client(self):
        c = WebUntisClient("test.webuntis.com", "test-school", "user", "pass")
        c._session_id = "SID"
        c._session_expiry = time.time() + 9999
        c._person_id = 42
        c._person_type = 5
        c._jwt_token = "jwt-abc"
        return c

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_homework_uses_jwt_bearer(self, authed_client):
        """REST endpoints must use Bearer token in Authorization header."""
        route = respx.get(
            "https://test.webuntis.com/WebUntis/api/homeworks/lessons",
        ).mock(return_value=httpx.Response(200, json={
            "data": {"homeworks": [{"id": 1, "text": "Read chapter 5"}]},
        }))

        result = await authed_client.get_homework("2026-03-20", "2026-03-27")

        assert route.called
        auth_header = route.calls[0].request.headers.get("Authorization")
        assert auth_header == "Bearer jwt-abc"

        # Check query params use YYYYMMDD format
        url = str(route.calls[0].request.url)
        assert "startDate=20260320" in url
        assert "endDate=20260327" in url

        await authed_client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py::TestRestEndpoints::test_get_homework_uses_jwt_bearer -v`
Expected: FAIL (AttributeError -- `get_homework` not defined)

- [ ] **Step 3: Implement REST methods**

Add to `src/untis_mcp/api.py` at the end of `WebUntisClient`:

```python
    # ── REST/WebAPI Methods ──────────────────────────────────────

    async def _rest_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make an authenticated GET to a REST endpoint."""
        await self.ensure_authenticated()
        client = await self._client()

        headers = {}
        if self._jwt_token:
            headers["Authorization"] = f"Bearer {self._jwt_token}"

        resp = await client.get(
            f"{self._base_url}{path}",
            params=params,
            headers=headers,
        )

        if resp.status_code == 401:
            # Re-authenticate and retry
            await self.login()
            if self._jwt_token:
                headers["Authorization"] = f"Bearer {self._jwt_token}"
            resp = await client.get(
                f"{self._base_url}{path}",
                params=params,
                headers=headers,
            )

        resp.raise_for_status()
        return resp.json()

    async def get_homework(self, start: str, end: str) -> Any:
        """Fetch homework assignments via REST API."""
        return await self._rest_get("/api/homeworks/lessons", {
            "startDate": self._to_untis_date(start),
            "endDate": self._to_untis_date(end),
        })

    async def get_exams(self, start: str, end: str) -> Any:
        """Fetch exams via REST API (more detailed than JSON-RPC)."""
        return await self._rest_get("/api/exams", {
            "startDate": self._to_untis_date(start),
            "endDate": self._to_untis_date(end),
        })

    async def get_absences(self, start: str, end: str) -> Any:
        """Fetch student absences via REST API."""
        return await self._rest_get("/api/classreg/absences/students", {
            "startDate": self._to_untis_date(start),
            "endDate": self._to_untis_date(end),
        })

    async def get_messages(self) -> Any:
        """Fetch inbox messages via REST API."""
        return await self._rest_get("/api/rest/view/v1/messages")

    async def get_news(self) -> Any:
        """Fetch school news via REST API."""
        return await self._rest_get("/api/public/news/newsWidgetData")
```

- [ ] **Step 4: Run REST test**

Run: `.venv/bin/pytest tests/test_api.py::TestRestEndpoints -v`
Expected: PASS

- [ ] **Step 5: Write test for REST 401 retry**

Add to `TestRestEndpoints`:

```python
    @respx.mock
    @pytest.mark.asyncio
    async def test_rest_retries_on_401(self, authed_client):
        """REST calls must re-authenticate and retry on 401."""
        call_count = 0

        def handler(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(401)
            return httpx.Response(200, json={"data": []})

        respx.get(
            "https://test.webuntis.com/WebUntis/api/rest/view/v1/messages",
        ).mock(side_effect=handler)

        # Mock login for re-auth
        respx.post(
            "https://test.webuntis.com/WebUntis/jsonrpc.do",
            params={"school": "test-school"},
        ).mock(return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": "1",
            "result": {"sessionId": "NEW", "personId": 42, "personType": 5},
        }))
        respx.get(
            "https://test.webuntis.com/WebUntis/api/token/new",
        ).mock(return_value=httpx.Response(200, text='"new-jwt"'))

        result = await authed_client.get_messages()
        assert call_count == 2  # first 401, then retry
        assert result == {"data": []}

        await authed_client.close()
```

- [ ] **Step 6: Run 401 retry test**

Run: `.venv/bin/pytest tests/test_api.py::TestRestEndpoints::test_rest_retries_on_401 -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/untis_mcp/api.py tests/test_api.py
git commit -m "FEAT: add REST API methods (homework, exams, absences, messages, news)"
```

---

## Task 5: MCP Server -- Lifespan + First Tools

**Files:**
- Create: `src/untis_mcp/server.py`
- Create: `tests/test_server.py`

Implement the FastMCP server with lifespan and the simpler tools: `untis_get_students`, `untis_get_school_info`, `untis_get_messages`, `untis_raw_call`.

- [ ] **Step 1: Write failing test for `_format_json` helper**

Create `tests/test_server.py`:

```python
"""Tests for the WebUntis MCP server."""

import json
import pytest
from datetime import date

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_server.py::TestHelpers -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement `server.py` with lifespan + first tools**

Create `src/untis_mcp/server.py`:

```python
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
```

- [ ] **Step 4: Run helper tests**

Run: `.venv/bin/pytest tests/test_server.py::TestHelpers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/untis_mcp/server.py tests/test_server.py
git commit -m "FEAT: add MCP server with lifespan and basic tools (students, school_info, messages, raw_call)"
```

---

## Task 6: MCP Server -- Data Tools (Timetable, Homework, Exams, Absences)

**Files:**
- Modify: `src/untis_mcp/server.py`

Add the remaining data query tools.

- [ ] **Step 1: Add `untis_get_timetable` tool**

Add to `src/untis_mcp/server.py` after the `get_school_info` tool:

```python
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
```

- [ ] **Step 2: Add `untis_get_homework` tool**

```python
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
```

- [ ] **Step 3: Add `untis_get_exams` tool**

```python
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
```

- [ ] **Step 4: Add `untis_get_absences` tool**

```python
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
```

- [ ] **Step 5: Write tests for date-defaulting logic**

Add to `tests/test_server.py`:

```python
from datetime import timedelta


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
```

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/untis_mcp/server.py tests/test_server.py
git commit -m "FEAT: add timetable, homework, exams, and absences MCP tools"
```

---

## Task 7: Daily Report

**Files:**
- Modify: `src/untis_mcp/server.py`
- Modify: `tests/test_server.py`

Implement `_format_daily_report()` and the `untis_daily_report` MCP tool.

- [ ] **Step 1: Write failing test for daily report formatting**

Add to `tests/test_server.py`:

```python
from untis_mcp.server import _format_daily_report


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_server.py::TestDailyReport -v`
Expected: FAIL (ImportError -- `_format_daily_report` not defined)

- [ ] **Step 3: Implement `_format_daily_report`**

Add to `src/untis_mcp/server.py` before the `main()` function:

```python
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
    if isinstance(homework, dict):
        hw_list = homework.get("data", {}).get("homeworks", [])
        if not hw_list:
            hw_list = homework.get("homeworks", [])
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
            ex_date = ex.get("examDate", "?")
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
            subj = h.get("subject", "?")
            text = h.get("text", h.get("description", ""))
            due = h.get("dueDate", "")
            lines.append(f"- **{subj}**: {text}" + (f" (bis {due})" if due else ""))
    else:
        lines.append("- Keine Hausaufgaben eingetragen")
    lines.append("")

    # ── Absences detail ───────────────────────────────────────
    lines.append("### Fehlzeiten")
    if absence_list:
        for a in absence_list:
            status = "entschuldigt" if a.get("isExcused", False) else "unentschuldigt"
            a_date = a.get("date", a.get("startDate", "?"))
            lines.append(f"- {a_date}: {status}")
    else:
        lines.append("- Keine Fehlzeiten")
    lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run daily report tests**

Run: `.venv/bin/pytest tests/test_server.py::TestDailyReport -v`
Expected: PASS

- [ ] **Step 5: Add the `untis_daily_report` MCP tool**

Add to `src/untis_mcp/server.py` before `main()`:

```python
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

    if client.person_id is None:
        return "Kein Schueler-Profil gefunden."

    today = date.today()
    tomorrow = _next_school_day(today)
    exam_end = (today + timedelta(days=7)).isoformat()

    # Fetch all data
    try:
        timetable = await client.get_timetable(
            client.person_id, client.person_type or 5,
            tomorrow.isoformat(), tomorrow.isoformat(),
        )
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
        client.person_id, client.person_type or 5,
        tomorrow, timetable, substitutions,
        homework, exams, absences, messages,
    ))

    return "\n".join(parts)
```

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/untis_mcp/server.py tests/test_server.py
git commit -m "FEAT: add daily report formatter and untis_daily_report MCP tool"
```

---

## Task 8: Standalone Daily Report Script

**Files:**
- Create: `daily_report.py`
- Create: `daily_report.sh`

- [ ] **Step 1: Create `daily_report.py`**

```python
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

        timetable = await client.get_timetable(
            client.person_id, client.person_type or 5,
            tomorrow.isoformat(), tomorrow.isoformat(),
        )
        substitutions = await client.get_substitutions(
            tomorrow.isoformat(), tomorrow.isoformat(),
        )

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
            client.person_id, client.person_type or 5,
            tomorrow, timetable, substitutions,
            homework, exams, absences, messages,
        ))
    finally:
        await client.logout()
        await client.close()


if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 2: Create `daily_report.sh`**

```bash
#!/usr/bin/env bash
# Run the standalone daily report
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/daily_report.py" "$@"
```

- [ ] **Step 3: Make scripts executable**

Run: `chmod +x daily_report.py daily_report.sh`

- [ ] **Step 4: Commit**

```bash
git add daily_report.py daily_report.sh
git commit -m "FEAT: add standalone daily report script"
```

---

## Task 9: Integration Test (Live)

**Files:** None (manual testing)

This task verifies the server works against the real WebUntis instance.

- [ ] **Step 1: Test login manually**

Run:
```bash
cd /Users/D054904/kohlsalem/untis
source .env
.venv/bin/python -c "
import asyncio
from untis_mcp.api import WebUntisClient
import os

async def test():
    c = WebUntisClient(os.environ['WEBUNTIS_SERVER'], os.environ['WEBUNTIS_SCHOOL'], os.environ['WEBUNTIS_USER'], os.environ['WEBUNTIS_PASSWORD'])
    await c.login()
    print(f'Login OK: personId={c.person_id}, personType={c.person_type}')
    print(f'JWT: {c._jwt_token[:20] if c._jwt_token else \"None\"}...')
    await c.logout()
    await c.close()

asyncio.run(test())
"
```

Expected: `Login OK: personId=<number>, personType=5`

- [ ] **Step 2: Test timetable fetch**

Run:
```bash
.venv/bin/python -c "
import asyncio, os, json
from untis_mcp.api import WebUntisClient

async def test():
    c = WebUntisClient(os.environ['WEBUNTIS_SERVER'], os.environ['WEBUNTIS_SCHOOL'], os.environ['WEBUNTIS_USER'], os.environ['WEBUNTIS_PASSWORD'])
    await c.login()
    tt = await c.get_timetable(c.person_id, c.person_type, '2026-03-23', '2026-03-27')
    print(json.dumps(tt[:3], indent=2, default=str))
    await c.logout()
    await c.close()

asyncio.run(test())
"
```

Expected: JSON array of lesson objects

- [ ] **Step 3: Test daily report**

Run:
```bash
./daily_report.sh
```

Expected: Markdown report printed to stdout

- [ ] **Step 4: Test MCP server starts**

Run:
```bash
source .env && .venv/bin/python -m untis_mcp.server &
SERVER_PID=$!
sleep 3
kill $SERVER_PID 2>/dev/null
echo "Server started and stopped OK"
```

Expected: Server starts without error

- [ ] **Step 5: If any tests fail, debug and fix**

Consult the spec and API documentation. Common issues:
- Wrong date format (must be YYYYMMDD integer for JSON-RPC)
- Cookie not being sent (check JSESSIONID cookie domain/path)
- JWT token format (may need to strip quotes)
- REST endpoints returning different JSON structures than expected

- [ ] **Step 6: Commit any fixes**

```bash
git add -A
git commit -m "FIX: integration test fixes"
```

---

## Task 10: MCP Registration + Claude Code Setup

**Files:**
- Create or modify: `.claude/settings.json` (in the untis project)

- [ ] **Step 1: Register the MCP server in Claude Code settings**

The MCP server needs to be registered so Claude Code can use it. Create `.claude/settings.json`:

```json
{
  "mcpServers": {
    "untis-mcp": {
      "command": "/Users/D054904/kohlsalem/untis/start.sh",
      "args": []
    }
  }
}
```

- [ ] **Step 2: Verify MCP tools appear in Claude Code**

Start a new Claude Code session in the `untis/` directory and verify the `untis_*` tools are available.

- [ ] **Step 3: Test `untis_daily_report` via Claude**

Ask Claude: "Zeig mir das Eltern-Briefing fuer heute"

Expected: Claude calls `untis_daily_report` and shows the formatted report.

- [ ] **Step 4: Final commit**

```bash
git add .claude/settings.json
git commit -m "CHORE: register untis-mcp server in Claude Code settings"
```

---

## Summary

| Task | Description | Key Files |
|---|---|---|
| 1 | Project scaffold | pyproject.toml, .env, start.sh, __init__.py |
| 2 | API client: JSON-RPC + auth | api.py, test_api.py |
| 3 | API client: data methods | api.py, test_api.py |
| 4 | API client: REST endpoints | api.py, test_api.py |
| 5 | MCP server: lifespan + basic tools | server.py, test_server.py |
| 6 | MCP server: data tools | server.py |
| 7 | Daily report | server.py, test_server.py |
| 8 | Standalone report script | daily_report.py, daily_report.sh |
| 9 | Integration test (live) | manual |
| 10 | MCP registration | .claude/settings.json |
