"""WebUntis API client.

Handles authentication (JSON-RPC session + JWT) and all API communication
with the WebUntis platform via two protocols:
- JSON-RPC 2.0 for timetable, master data, exams
- REST/WebAPI for homework, absences, messages
"""

import time
from typing import Any

import httpx

SESSION_LIFETIME = 480  # seconds (8 min, conservative for ~10 min timeout)


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

        self._base_url = f"https://{server}/WebUntis"
        self._rpc_url = f"{self._base_url}/jsonrpc.do"

        self._session_id: str | None = None
        self._session_expiry: float = 0
        self._person_id: int | None = None
        self._person_type: int | None = None
        self._jwt_token: str | None = None
        self._rpc_id: int = 0
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
        client = await self._client()
        client.cookies.set(
            "JSESSIONID", self._session_id,
            domain=self.server, path="/WebUntis",
        )
        client.cookies.set(
            "schoolname", self.school,
            domain=self.server, path="/WebUntis",
        )
        await self._fetch_jwt_token()

    async def _fetch_jwt_token(self) -> None:
        """Obtain a JWT Bearer token for REST API endpoints."""
        client = await self._client()
        try:
            resp = await client.get(f"{self._base_url}/api/token/new")
            resp.raise_for_status()
            self._jwt_token = resp.text.strip().strip('"')
        except Exception:
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

    @property
    def person_id(self) -> int | None:
        return self._person_id

    @property
    def person_type(self) -> int | None:
        return self._person_type

    # ── Date Helpers ─────────────────────────────────────────────

    @staticmethod
    def _to_untis_date(iso_date: str) -> int:
        """Convert 'YYYY-MM-DD' to YYYYMMDD integer."""
        return int(iso_date.replace("-", ""))

    # ── JSON-RPC Data Methods ────────────────────────────────────

    async def get_timetable(
        self, person_id: int, person_type: int, start: str, end: str
    ) -> list[dict[str, Any]]:
        """Fetch timetable for a person in a date range."""
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
