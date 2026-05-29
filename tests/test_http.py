import asyncio
import json

import pytest
from uiautomator2.exceptions import (
    HTTPError,
    HTTPTimeoutError,
    UiAutomationNotConnectedError,
    UiObjectNotFoundError,
)

from async_uiautomator2.http import AsyncAdbHTTPClient


class FakeConnection:
    def __init__(self, response: bytes = b"", *, delay: float = 0) -> None:
        self.response = bytearray(response)
        self.delay = delay
        self.sent = b""
        self.closed = False

    async def sendall(self, data: bytes) -> None:
        self.sent += data

    async def recv(self, size: int) -> bytes:
        if self.delay:
            await asyncio.sleep(self.delay)
        if not self.response:
            return b""
        chunk = bytes(self.response[:size])
        del self.response[:size]
        return chunk

    async def close(self) -> None:
        self.closed = True


class FakeDevice:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn
        self.calls = []

    async def create_connection(self, network, address):
        self.calls.append((network, address))
        return self.conn


def http_response(body: bytes, status: int = 200, reason: str = "OK") -> bytes:
    return (
        f"HTTP/1.1 {status} {reason}\r\nContent-Length: {len(body)}\r\n\r\n".encode()
        + body
    )


def test_ping_sends_get_request_and_closes_connection() -> None:
    async def run() -> None:
        conn = FakeConnection(http_response(b"pong"))
        client = AsyncAdbHTTPClient(FakeDevice(conn))

        assert await client.ping() == "pong"

        assert conn.closed is True
        assert b"GET /ping HTTP/1.1\r\n" in conn.sent
        assert b"Connection: close\r\n" in conn.sent

    asyncio.run(run())


def test_jsonrpc_sends_post_body_and_returns_result() -> None:
    async def run() -> None:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode()
        conn = FakeConnection(http_response(body))
        client = AsyncAdbHTTPClient(FakeDevice(conn))

        assert await client.jsonrpc("deviceInfo", []) == {"ok": True}

        assert b"POST /jsonrpc/0 HTTP/1.1\r\n" in conn.sent
        assert b'"method":"deviceInfo"' in conn.sent
        assert b"Content-Type: application/json\r\n" in conn.sent

    asyncio.run(run())


def test_http_non_200_raises_http_error() -> None:
    async def run() -> None:
        conn = FakeConnection(http_response(b"bad", 500, "Server Error"))
        client = AsyncAdbHTTPClient(FakeDevice(conn))

        with pytest.raises(HTTPError):
            await client.ping()

        assert conn.closed is True

    asyncio.run(run())


def test_timeout_raises_http_timeout_and_closes_connection() -> None:
    async def run() -> None:
        conn = FakeConnection(http_response(b"pong"), delay=0.2)
        client = AsyncAdbHTTPClient(FakeDevice(conn))

        with pytest.raises(HTTPTimeoutError):
            await client.ping(timeout=0.01)

        assert conn.closed is True

    asyncio.run(run())


def test_jsonrpc_error_maps_known_uiautomator_errors() -> None:
    async def run() -> None:
        not_found = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32002,
                "message": "uiautomator.UiObjectNotFoundException",
            },
        }
        conn = FakeConnection(http_response(json.dumps(not_found).encode()))
        client = AsyncAdbHTTPClient(FakeDevice(conn))

        with pytest.raises(UiObjectNotFoundError):
            await client.jsonrpc("objInfo", [])

        disconnected = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32001, "message": "android.os.DeadObjectException"},
        }
        conn = FakeConnection(http_response(json.dumps(disconnected).encode()))
        client = AsyncAdbHTTPClient(FakeDevice(conn))

        with pytest.raises(UiAutomationNotConnectedError):
            await client.jsonrpc("deviceInfo", [])

    asyncio.run(run())
