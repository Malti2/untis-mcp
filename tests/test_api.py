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
