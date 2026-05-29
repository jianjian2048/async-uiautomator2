"""基于 ADB socket 的最小异步 HTTP/JSON-RPC 客户端。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import adbutils
from uiautomator2.exceptions import (
    HTTPError,
    HTTPTimeoutError,
    RPCInvalidError,
    RPCStackOverflowError,
    RPCUnknownError,
    UiAutomationNotConnectedError,
    UiObjectNotFoundError,
)

from async_uiautomator2.adb import AsyncAdbDevice, AsyncConnection

DEFAULT_PORT = 9008


class HTTPResponse:
    """最小 HTTP 响应对象。

    Args:
        status (int): HTTP 状态码。
        reason (str): HTTP reason phrase。
        headers (dict[str, str]): 小写 header 名到值的映射。
        content (bytes): 响应体字节。
    """

    def __init__(
        self, status: int, reason: str, headers: dict[str, str], content: bytes
    ) -> None:
        self.status = status
        self.reason = reason
        self.headers = headers
        self.content = content

    @property
    def text(self) -> str:
        """使用 UTF-8 容错解码后的响应体。"""

        return self.content.decode("utf-8", errors="ignore")

    def json(self) -> Any:
        """解析响应体 JSON。"""

        return json.loads(self.content)


class AsyncAdbHTTPClient:
    """基于 ADB socket 的最小异步 HTTP/JSON-RPC 客户端。

    Args:
        device (AsyncAdbDevice): 异步 ADB 设备适配器。
        port (int): 设备端 `u2.jar` HTTP 端口。
    """

    def __init__(self, device: AsyncAdbDevice, port: int = DEFAULT_PORT) -> None:
        self.device = device
        self.port = port

    async def ping(self, timeout: float = 10) -> str:
        """调用 `GET /ping` 检查 `u2.jar` 是否存活。"""

        response = await self.request("GET", "/ping", timeout=timeout)
        return response.text

    async def jsonrpc(self, method: str, params: Any, timeout: float = 10) -> Any:
        """调用 `POST /jsonrpc/0` 并返回 JSON-RPC result。"""

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        response = await self.request("POST", "/jsonrpc/0", payload, timeout=timeout)
        data = response.json()
        if not isinstance(data, dict):
            raise RPCInvalidError("Unknown RPC error: not a dict")
        if "error" in data:
            self._raise_jsonrpc_error(data, response.text, params)
        if "result" not in data:
            raise RPCInvalidError("Unknown RPC error: no result field")
        return data["result"]

    async def request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        timeout: float = 10,
    ) -> HTTPResponse:
        """发送一次 HTTP 请求。"""

        try:
            return await asyncio.wait_for(
                self._request_once(method, path, data), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            raise HTTPTimeoutError(f"HTTP request timeout: {timeout}s") from exc

    async def _request_once(
        self, method: str, path: str, data: dict[str, Any] | None
    ) -> HTTPResponse:
        """在单条 ADB socket 上完成一次 HTTP 请求。"""

        conn = await self.device.create_connection(adbutils.Network.TCP, self.port)
        try:
            body = (
                b""
                if data is None
                else json.dumps(data, separators=(",", ":")).encode("utf-8")
            )
            headers = [
                f"{method} {path} HTTP/1.1",
                "Host: 127.0.0.1",
                "User-Agent: async-uiautomator2",
                "Accept-Encoding:",
                "Connection: close",
            ]
            if data is not None:
                headers.append("Content-Type: application/json")
                headers.append(f"Content-Length: {len(body)}")
            raw_request = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + body
            await conn.sendall(raw_request)
            response = await self._read_response(conn)
            if response.status != 200:
                raise HTTPError(
                    f"HTTP request failed: {response.status} {response.reason}"
                )
            return response
        finally:
            await conn.close()

    async def _read_response(self, conn: AsyncConnection) -> HTTPResponse:
        """读取并解析最小 HTTP/1.1 响应。"""

        buffer = bytearray()
        while b"\r\n\r\n" not in buffer:
            chunk = await conn.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
        header_raw, _, body = bytes(buffer).partition(b"\r\n\r\n")
        if not header_raw:
            raise HTTPError("empty HTTP response")

        lines = header_raw.decode("iso-8859-1").split("\r\n")
        status_parts = lines[0].split(" ", 2)
        if len(status_parts) < 2 or not status_parts[1].isdigit():
            raise HTTPError(f"invalid HTTP status line: {lines[0]}")

        status = int(status_parts[1])
        reason = status_parts[2] if len(status_parts) > 2 else ""
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.lower()] = value.strip()

        content_length = int(headers.get("content-length", len(body)))
        body_buffer = bytearray(body)
        while len(body_buffer) < content_length:
            chunk = await conn.recv(content_length - len(body_buffer))
            if not chunk:
                break
            body_buffer.extend(chunk)

        return HTTPResponse(
            status, reason, headers, bytes(body_buffer[:content_length])
        )

    def _raise_jsonrpc_error(
        self, data: dict[str, Any], text: str, params: Any
    ) -> None:
        """把设备端 JSON-RPC 错误映射为 uiautomator2 Python 异常。"""

        error = data.get("error") or {}
        code = error.get("code")
        message = error.get("message", "")
        stacktrace = error.get("data") or ""

        if "UiAutomation not connected" in text:
            raise UiAutomationNotConnectedError("UiAutomation not connected")
        if "android.os.DeadObjectException" in message:
            raise UiAutomationNotConnectedError("android.os.DeadObjectException")
        if "android.os.DeadSystemRuntimeException" in message:
            raise UiAutomationNotConnectedError("android.os.DeadSystemRuntimeException")
        if "uiautomator.UiObjectNotFoundException" in message:
            raise UiObjectNotFoundError(code, message, params)
        if "java.lang.StackOverflowError" in message:
            raise RPCStackOverflowError(
                f"StackOverflowError: {message}", params, str(stacktrace)
            )
        raise RPCUnknownError(
            f"Unknown RPC error: {code} {message}", params, stacktrace
        )
