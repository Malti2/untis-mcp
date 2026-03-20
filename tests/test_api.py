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

        client._session_id = "fake"
        client._session_expiry = 9999999999.0

        result = await client._jsonrpc("someMethod", {"key": "value"})

        assert route.called
        req_body = route.calls[0].request.content
        body = json.loads(req_body)
        assert body["jsonrpc"] == "2.0"
        assert body["method"] == "someMethod"
        assert body["params"] == {"key": "value"}
        assert isinstance(body["id"], str)
        assert result == {"sessionId": "ABC123"}

        await client.close()

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
        client._session_expiry = 0

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


class TestHelpers:
    def test_to_untis_date(self):
        assert WebUntisClient._to_untis_date("2026-03-20") == 20260320
        assert WebUntisClient._to_untis_date("2026-01-01") == 20260101


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
