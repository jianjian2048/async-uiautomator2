"""uiautomator2 异步化最小可行原型核心模块。

这个模块实现 `document/uiautomator2-async-feasibility.md` 中描述的最小可行原型：

1. 通过 ADB socket 直连设备端 `u2.jar:9008`，不使用 `adb forward`。
2. 在 ADB socket 上手写最小 HTTP/1.1 请求与响应解析。
3. 提供异步 `u2.jar` 生命周期管理和 JSON-RPC 调用。
4. 暴露一个很小的 `AsyncDevice` API，便于验证真实调用方式。

注意：
    这里的 `ThreadedAdbDevice` 仍然基于同步 `adbutils`，只是用 `asyncio.to_thread`
    将阻塞调用隔离出事件循环。它适合第一阶段原型验证，不等价于纯异步 ADB 协议实现。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol

import adbutils
from async_u2_mvp.selector import AsyncUiObject, SelectorQuery
from async_u2_mvp.async_xpath import AsyncXPathSelector

from uiautomator2.exceptions import (
    AccessibilityServiceAlreadyRegisteredError,
    HTTPError,
    HTTPTimeoutError,
    LaunchUiAutomationError,
    RPCInvalidError,
    RPCStackOverflowError,
    RPCUnknownError,
    UiAutomationNotConnectedError,
    UiObjectNotFoundError,
)

DEFAULT_PORT = 9008
DEFAULT_JAR_PATH = Path(__file__).resolve().parent.parent / "assets" / "u2.jar"
U2_JAR_REMOTE_PATH = "/data/local/tmp/u2.jar"
U2_LAUNCH_COMMAND = (
    "CLASSPATH=/data/local/tmp/u2.jar app_process / com.wetest.uia2.Main"
)


class AsyncConnection(Protocol):
    """异步字节连接协议。

    `AsyncAdbHTTPClient` 只依赖这个最小协议，因此真实 ADB socket、测试 fake socket、
    或后续替换成纯异步 ADB backend 时，都可以复用同一套 HTTP/JSON-RPC 逻辑。
    """

    async def sendall(self, data: bytes) -> None:
        """发送完整字节串。

        Args:
            data (bytes): 要写入连接的完整请求内容。
        """

    async def recv(self, size: int) -> bytes:
        """读取一段字节。

        Args:
            size (int): 本次最多读取的字节数。

        Returns:
            bytes: 读取到的数据。返回空字节串表示连接已关闭或无更多数据。
        """

    async def close(self) -> None:
        """关闭连接并释放底层资源。"""


class AsyncAdbDevice(Protocol):
    """异步 ADB 设备协议。

    该协议刻意只定义原型需要的最小能力，避免把 `adbutils` 的完整 API 复制一遍。
    长期方案可以用真正的 async ADB backend 实现这个协议。

    Attributes:
        serial (str | None): ADB 设备序列号。
    """

    serial: str | None

    async def create_connection(
        self, network: Any, address: int | str
    ) -> AsyncConnection:
        """创建到设备端端口或 socket 的连接。

        Args:
            network (Any): ADB 网络类型，例如 `adbutils.Network.TCP`。
            address (int | str): 设备端端口或 socket 名称。

        Returns:
            AsyncConnection: 可异步读写的连接对象。
        """

    async def shell(self, cmd: str | list[str], timeout: float = 60) -> str:
        """执行一次非流式 adb shell。

        Args:
            cmd (str | list[str]): shell 命令。
            timeout (float): 命令超时时间，单位秒。

        Returns:
            str: 命令输出文本。
        """

    async def shell_stream(self, cmd: str | list[str]) -> Any:
        """启动一条流式 shell 连接。

        Args:
            cmd (str | list[str]): shell 命令。

        Returns:
            Any: 具备 `output`、`poll()`、`kill()` 的进程形态对象。
        """

    async def push(
        self, src: str | Path, dst: str, mode: int = 0o644, check: bool = False
    ) -> None:
        """推送文件到设备。

        Args:
            src (str | Path): 本地文件路径。
            dst (str): 设备端目标路径。
            mode (int): 设备端文件权限。
            check (bool): 是否校验推送后的文件大小。
        """

    async def app_start(self, package_name: str) -> Any:
        """启动 Android 应用。

        Args:
            package_name (str): 应用包名。

        Returns:
            Any: backend 返回值。
        """


class AsyncSocketConnection:
    """将同步 socket 包装成 `AsyncConnection`。

    Args:
        sock (Any): 同步 socket 对象，通常来自 `adbutils.AdbDevice.create_connection()`。

    说明：
        这是第一阶段兼容层。`sendall()`、`recv()` 和 `close()` 都通过 `asyncio.to_thread`
        执行，避免阻塞事件循环。
    """

    def __init__(self, sock: Any) -> None:
        self._sock = sock

    async def sendall(self, data: bytes) -> None:
        """异步发送完整字节串。"""

        await asyncio.to_thread(self._sock.sendall, data)

    async def recv(self, size: int) -> bytes:
        """异步读取 socket 数据。"""

        return await asyncio.to_thread(self._sock.recv, size)

    async def close(self) -> None:
        """关闭同步 socket。"""

        close = getattr(self._sock, "close", None)
        if close:
            await asyncio.to_thread(close)


class ThreadedAdbProcess:
    """流式 adb shell 进程包装器。

    Args:
        conn (Any): `adbutils` 返回的流式连接对象。

    说明：
        `u2.jar` 是通过 `adb shell ... stream=True` 启动的长连接进程。早期实现如果用
        `asyncio.create_task()` + `asyncio.to_thread(conn.recv)` 读取输出，`asyncio.run()`
        结束时会等待默认线程池中阻塞的 `recv()`，导致脚本不退出。

        因此这里使用 daemon thread 读取输出，行为更接近 `uiautomator2.core.MockAdbProcess`。
        关闭时调用 `kill()` 会关闭 ADB 连接，让设备端 `app_process` 退出。
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self.output = bytearray()
        self._finished = threading.Event()
        self._reader_thread = threading.Thread(
            target=self._read_output,
            name="async_u2_mvp_adb_stream_reader",
            daemon=True,
        )
        self._reader_thread.start()

    def poll(self) -> int | None:
        """返回进程状态。

        Returns:
            int | None: `None` 表示仍在运行，`0` 表示流已结束。
        """

        return 0 if self._finished.is_set() else None

    async def kill(self) -> None:
        """关闭流式 ADB 连接并等待 reader 线程观察到结束。"""

        await asyncio.to_thread(self._conn.close)
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(asyncio.to_thread(self._finished.wait, 3), timeout=3)

    def _read_output(self) -> None:
        """在 daemon thread 中持续读取 `app_process` 输出。"""

        try:
            while True:
                chunk = self._conn.conn.recv(1024)
                if not chunk:
                    break
                self.output.extend(chunk)
        except Exception:
            pass
        finally:
            self._finished.set()


class ThreadedAdbDevice:
    """基于同步 `adbutils` 的异步设备适配器。

    Args:
        serial (str | None): ADB 设备序列号。为 `None` 时使用 `adbutils.adb.device()` 默认设备。

    说明：
        这个类是短期兼容层：所有阻塞 ADB 操作都通过 `asyncio.to_thread` 调用。它能让
        FastAPI、FastStream 或其他事件循环服务不被同步 ADB 调用直接卡住，但取消语义仍
        受限于底层同步函数。
    """

    def __init__(self, serial: str | None = None) -> None:
        self.serial = serial
        self._device: Any = None

    async def create_connection(
        self, network: Any, address: int | str
    ) -> AsyncSocketConnection:
        """创建 ADB socket 连接。"""

        dev = await self._ensure_device()
        sock = await asyncio.to_thread(dev.create_connection, network, address)
        return AsyncSocketConnection(sock)

    async def shell(self, cmd: str | list[str], timeout: float = 60) -> str:
        """执行非流式 shell 命令并返回文本输出。"""

        dev = await self._ensure_device()
        return await asyncio.to_thread(dev.shell, cmd, False, timeout)

    async def shell_stream(self, cmd: str | list[str]) -> ThreadedAdbProcess:
        """启动流式 shell 命令。"""

        dev = await self._ensure_device()
        conn = await asyncio.to_thread(dev.shell, cmd, True)
        return ThreadedAdbProcess(conn)

    async def push(
        self, src: str | Path, dst: str, mode: int = 0o644, check: bool = False
    ) -> None:
        """推送文件到设备。"""

        dev = await self._ensure_device()
        await asyncio.to_thread(dev.sync.push, src, dst, mode=mode, check=check)

    async def app_start(self, package_name: str) -> Any:
        """启动 Android 应用。"""

        dev = await self._ensure_device()
        return await asyncio.to_thread(dev.app_start, package_name)

    async def _ensure_device(self) -> Any:
        """懒加载并缓存 `adbutils.AdbDevice`。"""

        if self._device is None:
            if self.serial:
                self._device = await asyncio.to_thread(adbutils.adb.device, self.serial)
            else:
                self._device = await asyncio.to_thread(adbutils.adb.device)
            self.serial = self._device.serial
        return self._device


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
        """str: 使用 UTF-8 容错解码后的响应体。"""

        return self.content.decode("utf-8", errors="ignore")

    def json(self) -> Any:
        """解析响应体 JSON。

        Returns:
            Any: JSON 解析结果。

        Raises:
            json.JSONDecodeError: 响应体不是合法 JSON。
        """

        return json.loads(self.content)


class AsyncAdbHTTPClient:
    """基于 ADB socket 的最小异步 HTTP/JSON-RPC 客户端。

    Args:
        device (AsyncAdbDevice): 异步 ADB 设备适配器。
        port (int): 设备端 `u2.jar` HTTP 端口，默认 9008。

    说明：
        每次请求都会新建一条 ADB TCP socket，用完后立即关闭。这与当前 `uiautomator2`
        v3.5+ 的连接模型一致，不占用本地转发端口。
    """

    def __init__(self, device: AsyncAdbDevice, port: int = DEFAULT_PORT) -> None:
        self.device = device
        self.port = port

    async def ping(self, timeout: float = 10) -> str:
        """调用 `GET /ping` 检查 `u2.jar` 是否存活。

        Args:
            timeout (float): 请求超时时间，单位秒。

        Returns:
            str: 正常情况下返回 `"pong"`。

        Raises:
            HTTPTimeoutError: 请求超时。
            HTTPError: HTTP 响应异常或响应格式异常。
        """

        response = await self.request("GET", "/ping", timeout=timeout)
        return response.text

    async def jsonrpc(self, method: str, params: Any, timeout: float = 10) -> Any:
        """调用 `POST /jsonrpc/0`。

        Args:
            method (str): JSON-RPC 方法名。
            params (Any): JSON-RPC 参数，通常是列表或字典。
            timeout (float): 请求超时时间，单位秒。

        Returns:
            Any: JSON-RPC `result` 字段。

        Raises:
            RPCInvalidError: 响应不是合法 JSON-RPC 结果。
            UiAutomationNotConnectedError: 设备端 UiAutomation 断开。
            UiObjectNotFoundError: 元素未找到。
            RPCStackOverflowError: 设备端栈溢出。
            RPCUnknownError: 未识别的 JSON-RPC 错误。
            HTTPTimeoutError: 请求超时。
            HTTPError: HTTP 响应异常。
        """

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
        """发送一次 HTTP 请求。

        Args:
            method (str): HTTP 方法。
            path (str): HTTP path。
            data (dict[str, Any] | None): JSON 请求体；为 `None` 时不发送 body。
            timeout (float): 请求超时时间，单位秒。

        Returns:
            HTTPResponse: 解析后的最小 HTTP 响应对象。

        Raises:
            HTTPTimeoutError: 请求超时。
            HTTPError: HTTP 响应异常或响应格式异常。
        """

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
                "User-Agent: async-u2-mvp",
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


class AsyncBasicUiautomatorServer:
    """异步 `u2.jar` 生命周期与 JSON-RPC 管理器。

    Args:
        device (AsyncAdbDevice): 异步 ADB 设备适配器。
        port (int): 设备端 `u2.jar` HTTP 端口。
        jar_path (str | Path): 本地 `u2.jar` 路径。
        setup_jar (bool): 是否在启动前检查并推送 `u2.jar`。

    说明：
        自动重启逻辑使用 `_restart_lock` 和 `_generation`。当多个协程同时发现服务异常时，
        只有第一个进入重启流程；其他协程看到 generation 已变化后直接复用新的服务。
    """

    def __init__(
        self,
        device: AsyncAdbDevice,
        port: int = DEFAULT_PORT,
        jar_path: str | Path = DEFAULT_JAR_PATH,
        setup_jar: bool = True,
    ) -> None:
        self.device = device
        self.port = port
        self.jar_path = Path(jar_path)
        self.setup_jar = setup_jar
        self.http = AsyncAdbHTTPClient(device, port)
        self._process: Any = None
        self._lock = asyncio.Lock()
        self._restart_lock = asyncio.Lock()
        self._generation = 0

    async def start_uiautomator(self) -> None:
        """确保 `u2.jar` 服务已启动并可响应 `/ping`。

        Raises:
            FileNotFoundError: 本地 `u2.jar` 不存在。
            LaunchUiAutomationError: 设备端服务启动失败或超时。
            AccessibilityServiceAlreadyRegisteredError: 设备端 UiAutomation 服务重复注册。
        """

        async with self._lock:
            if self.setup_jar:
                await self._setup_jar()
            if self._process is not None and self._process.poll() is not None:
                self._process = None
            if not await self._check_alive():
                self._process = await self.launch_uiautomator()
                await self._wait_ready()
                self._generation += 1

    async def stop_uiautomator(self, wait: bool = True) -> None:
        """停止当前客户端启动的 `u2.jar` stream 连接。

        Args:
            wait (bool): 是否等待 `/ping` 变为不可用。
        """

        async with self._lock:
            if self._process is not None:
                await self._process.kill()
                self._process = None
        if wait:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if not await self._check_alive():
                    return
                await asyncio.sleep(0.5)

    async def jsonrpc_call(
        self, method: str, params: Any = None, timeout: float = 10
    ) -> Any:
        """调用设备端 JSON-RPC，必要时自动重启 `u2.jar` 后重试一次。

        Args:
            method (str): JSON-RPC 方法名。
            params (Any): JSON-RPC 参数。为 `None` 时使用空列表。
            timeout (float): 单次 HTTP 请求超时时间，单位秒。

        Returns:
            Any: JSON-RPC `result`。
        """

        generation = self._generation
        try:
            return await self.http.jsonrpc(
                method, params if params is not None else [], timeout=timeout
            )
        except (HTTPError, UiAutomationNotConnectedError):
            async with self._restart_lock:
                if self._generation == generation:
                    await self._force_restart_uiautomator()
            return await self.http.jsonrpc(
                method, params if params is not None else [], timeout=timeout
            )

    async def _force_restart_uiautomator(self) -> None:
        """在持有 restart lock 后强制重启 `u2.jar`。"""

        async with self._lock:
            if self._process is not None:
                await self._process.kill()
                self._process = None
            if self.setup_jar:
                await self._setup_jar()
            self._process = await self.launch_uiautomator()
            await self._wait_ready()
            self._generation += 1

    async def _setup_jar(self) -> None:
        """检查设备端 jar 哈希，不一致时推送本地 `u2.jar`。"""

        if not self.jar_path.exists():
            raise FileNotFoundError(self.jar_path)
        if not await self._check_device_file_hash(self.jar_path, U2_JAR_REMOTE_PATH):
            await self.device.push(self.jar_path, U2_JAR_REMOTE_PATH, check=True)

    async def _check_device_file_hash(self, local_file: Path, remote_file: str) -> bool:
        """比较本地文件 MD5 与设备端文件 MD5。"""

        local_md5 = hashlib.md5(local_file.read_bytes()).hexdigest()
        output = await self.device.shell(["toybox", "md5sum", remote_file])
        if "toybox" in output and "not found" in output:
            output = await self.device.shell(["md5", remote_file])
        return local_md5 in output

    async def launch_uiautomator(self) -> Any:
        """通过 `app_process` 启动设备端 `u2.jar` 服务。"""

        return await self.device.shell_stream(U2_LAUNCH_COMMAND)

    async def _wait_ready(self, launch_timeout: float = 30) -> None:
        """等待 `u2.jar` 服务可响应 `/ping`。"""

        deadline = time.monotonic() + launch_timeout
        output_buffer = ""
        while time.monotonic() < deadline:
            output = bytes(getattr(self._process, "output", b"")).decode(
                "utf-8", errors="ignore"
            )
            output_buffer += output
            if "already registered" in output:
                raise AccessibilityServiceAlreadyRegisteredError(output)
            if self._process is not None and self._process.poll() is not None:
                raise LaunchUiAutomationError("server quit unexpectly", output_buffer)
            if await self._check_alive():
                return
            await asyncio.sleep(0.5)
        raise LaunchUiAutomationError("server not ready", output_buffer)

    async def _check_alive(self) -> bool:
        """检查 `u2.jar` 是否存活。"""

        try:
            return await self.http.ping(timeout=10) == "pong"
        except Exception:
            return False


class AsyncDevice:
    """面向调用方的最小异步设备 API。

    Args:
        adb_device (AsyncAdbDevice): 异步 ADB 设备适配器。
        server (AsyncBasicUiautomatorServer): `u2.jar` 服务管理器。

    Example:
        >>> async with await async_connect("ANDROID_SERIAL") as d:
        ...     info = await d.info
        ...     await d.click(100, 200)
    """

    def __init__(
        self, adb_device: AsyncAdbDevice, server: AsyncBasicUiautomatorServer
    ) -> None:
        self.adb_device = adb_device
        self.server = server

    @property
    def info(self):
        """Coroutine[Any]: 获取设备信息的协程。"""

        return self.server.jsonrpc_call("deviceInfo", [], timeout=10)

    async def click(self, x: int | float, y: int | float) -> Any:
        """点击屏幕坐标。

        Args:
            x (int | float): 横坐标。
            y (int | float): 纵坐标。

        Returns:
            Any: 设备端 JSON-RPC 返回值。
        """

        return await self.server.jsonrpc_call("click", [x, y], timeout=10)

    async def shell(self, cmd: str | list[str], timeout: float = 60) -> str:
        """执行 adb shell 命令。

        Args:
            cmd (str | list[str]): shell 命令。
            timeout (float): 超时时间，单位秒。

        Returns:
            str: shell 输出文本。
        """

        return await self.adb_device.shell(cmd, timeout=timeout)

    async def push(self, src: str | Path, dst: str, mode: int = 0o644) -> None:
        """推送文件到设备。

        Args:
            src (str | Path): 本地文件路径。
            dst (str): 设备端目标路径。
            mode (int): 设备端文件权限。
        """

        await self.adb_device.push(src, dst, mode=mode)

    async def app_start(self, package_name: str) -> Any:
        """启动 Android 应用。

        Args:
            package_name (str): 应用包名。

        Returns:
            Any: backend 返回值。
        """

        return await self.adb_device.app_start(package_name)

    async def dump_hierarchy(
        self,
        compressed: bool = False,
        pretty: bool = False,
        max_depth: int = 50,
    ) -> str:
        """异步 dump 当前窗口 XML 层级。

        Args:
            compressed (bool): 是否使用压缩层级。
            pretty (bool): 是否返回格式化 XML。
            max_depth (int): 最大遍历深度。

        Returns:
            str: 当前窗口层级 XML。
        """

        content = await self.server.jsonrpc_call(
            "dumpWindowHierarchy", [compressed, max_depth], timeout=10
        )
        if pretty:
            from lxml import etree

            root = etree.fromstring(content.encode("utf-8"))
            content = etree.tostring(
                root,
                pretty_print=True,
                encoding="UTF-8",
                xml_declaration=True,
            ).decode("utf-8")
        return content

    def select(
        self,
        *,
        text: str | None = None,
        text_contains: str | None = None,
        text_matches: str | None = None,
        text_starts_with: str | None = None,
        class_name: str | None = None,
        class_name_matches: str | None = None,
        description: str | None = None,
        description_contains: str | None = None,
        description_matches: str | None = None,
        description_starts_with: str | None = None,
        resource_id: str | None = None,
        resource_id_matches: str | None = None,
        package_name: str | None = None,
        package_name_matches: str | None = None,
        index: int | None = None,
        instance: int | None = None,
        checkable: bool | None = None,
        checked: bool | None = None,
        clickable: bool | None = None,
        long_clickable: bool | None = None,
        scrollable: bool | None = None,
        enabled: bool | None = None,
        focusable: bool | None = None,
        focused: bool | None = None,
        selected: bool | None = None,
    ) -> "AsyncUiObject":
        """创建类型友好的异步 UI 元素选择器。

        Args:
            text (str | None): 精确匹配文本。
            text_contains (str | None): 文本包含匹配。
            text_matches (str | None): 文本正则匹配。
            text_starts_with (str | None): 文本前缀匹配。
            class_name (str | None): 控件类名。
            class_name_matches (str | None): 控件类名正则匹配。
            description (str | None): content-desc 精确匹配。
            description_contains (str | None): content-desc 包含匹配。
            description_matches (str | None): content-desc 正则匹配。
            description_starts_with (str | None): content-desc 前缀匹配。
            resource_id (str | None): Android resource id。
            resource_id_matches (str | None): resource id 正则匹配。
            package_name (str | None): 包名。
            package_name_matches (str | None): 包名正则匹配。
            index (int | None): 同层级下标。
            instance (int | None): 匹配实例序号。
            checkable (bool | None): 是否可勾选。
            checked (bool | None): 是否已勾选。
            clickable (bool | None): 是否可点击。
            long_clickable (bool | None): 是否可长按。
            scrollable (bool | None): 是否可滚动。
            enabled (bool | None): 是否启用。
            focusable (bool | None): 是否可聚焦。
            focused (bool | None): 是否已聚焦。
            selected (bool | None): 是否已选中。

        Returns:
            AsyncUiObject: 可异步操作的 UI 元素对象。
        """

        selector = SelectorQuery(
            text=text,
            text_contains=text_contains,
            text_matches=text_matches,
            text_starts_with=text_starts_with,
            class_name=class_name,
            class_name_matches=class_name_matches,
            description=description,
            description_contains=description_contains,
            description_matches=description_matches,
            description_starts_with=description_starts_with,
            resource_id=resource_id,
            resource_id_matches=resource_id_matches,
            package_name=package_name,
            package_name_matches=package_name_matches,
            index=index,
            instance=instance,
            checkable=checkable,
            checked=checked,
            clickable=clickable,
            long_clickable=long_clickable,
            scrollable=scrollable,
            enabled=enabled,
            focusable=focusable,
            focused=focused,
            selected=selected,
        ).to_selector()
        return AsyncUiObject(self, selector)

    def select_raw(self, **kwargs: Any) -> "AsyncUiObject":
        """使用原始 uiautomator2 selector 字段创建元素对象。

        这个方法是兼容逃生口，例如 `textContains`、`resourceId` 等原始字段仍可直接传入。
        新代码优先使用 `select(...)`，这样 IDE 和类型检查器能发现拼写错误。

        Args:
            **kwargs (Any): `uiautomator2._selector.Selector` 支持的原始字段。

        Returns:
            AsyncUiObject: 可异步操作的 UI 元素对象。

        Raises:
            ReferenceError: 传入了 uiautomator2 不支持的原始字段。
        """

        from uiautomator2._selector import Selector

        from async_u2_mvp.selector import AsyncUiObject

        return AsyncUiObject(self, Selector(**kwargs))

    def xpath(self, xpath: str, source: str | None = None) -> "AsyncXPathSelector":
        """创建异步 XPath 选择器。

        Args:
            xpath (str): XPath 表达式或 uiautomator2 支持的简写表达式。
            source (str | None): 可选固定 XML 源；传入后不会 dump 当前界面。

        Returns:
            AsyncXPathSelector: 可异步查询和点击的 XPath 选择器。
        """

        return AsyncXPathSelector(self, xpath, source=source)

    async def close(self) -> None:
        """关闭当前客户端持有的 `u2.jar` stream 连接。"""

        await self.server.stop_uiautomator(wait=False)

    async def __aenter__(self) -> "AsyncDevice":
        """进入 async context manager。"""

        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """退出 async context manager 时释放设备连接。"""

        await self.close()


async def async_connect(
    serial: str | None = None,
    *,
    device_factory: Callable[[str | None], AsyncAdbDevice] | None = None,
    jar_path: str | Path = DEFAULT_JAR_PATH,
    setup_jar: bool = True,
) -> AsyncDevice:
    """连接设备并返回最小异步设备对象。

    Args:
        serial (str | None): ADB 设备序列号。为 `None` 时使用默认设备。
        device_factory (Callable[[str | None], AsyncAdbDevice] | None): 设备适配器工厂。
            测试中可传入 fake backend；生产默认使用 `ThreadedAdbDevice`。
        jar_path (str | Path): 本地 `u2.jar` 路径。
        setup_jar (bool): 是否检查并推送 `u2.jar`。

    Returns:
        AsyncDevice: 可 `await` 调用的最小设备对象。

    Example:
        >>> d = await async_connect("ANDROID_SERIAL")
        >>> try:
        ...     await d.click(100, 200)
        ... finally:
        ...     await d.close()
    """

    factory = device_factory or ThreadedAdbDevice
    adb_device = factory(serial)
    server = AsyncBasicUiautomatorServer(
        adb_device, jar_path=jar_path, setup_jar=setup_jar
    )
    await server.start_uiautomator()
    return AsyncDevice(adb_device, server)
