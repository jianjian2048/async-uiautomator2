"""异步 `u2.jar` 生命周期管理。"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Any

from uiautomator2.exceptions import (
    AccessibilityServiceAlreadyRegisteredError,
    HTTPError,
    LaunchUiAutomationError,
    UiAutomationNotConnectedError,
)

from async_uiautomator2.adb import AsyncAdbDevice
from async_uiautomator2.assets import ensure_u2_jar
from async_uiautomator2.http import DEFAULT_PORT, AsyncAdbHTTPClient

U2_JAR_REMOTE_PATH = "/data/local/tmp/u2.jar"
U2_LAUNCH_COMMAND = (
    "CLASSPATH=/data/local/tmp/u2.jar app_process / com.wetest.uia2.Main"
)


class AsyncBasicUiautomatorServer:
    """异步 `u2.jar` 生命周期与 JSON-RPC 管理器。

    Args:
        device (AsyncAdbDevice): 异步 ADB 设备适配器。
        port (int): 设备端 `u2.jar` HTTP 端口。
        jar_path (str | Path): 本地 `u2.jar` 路径。
        setup_jar (bool): 是否在启动前检查并推送 `u2.jar`。
    """

    def __init__(
        self,
        device: AsyncAdbDevice,
        port: int = DEFAULT_PORT,
        jar_path: str | Path | None = None,
        setup_jar: bool = True,
    ) -> None:
        self.device = device
        self.port = port
        self.jar_path = Path(jar_path) if jar_path is not None else None
        self.setup_jar = setup_jar
        self.http = AsyncAdbHTTPClient(device, port)
        self._process: Any = None
        self._lock = asyncio.Lock()
        self._restart_lock = asyncio.Lock()
        self._generation = 0

    async def start_uiautomator(self) -> None:
        """确保 `u2.jar` 服务已启动并可响应 `/ping`。"""

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
        """停止当前客户端启动的 `u2.jar` stream 连接。"""

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
        """调用设备端 JSON-RPC，必要时自动重启后重试一次。"""

        generation = self._generation
        request_params = params if params is not None else []
        try:
            return await self.http.jsonrpc(method, request_params, timeout=timeout)
        except (HTTPError, UiAutomationNotConnectedError):
            async with self._restart_lock:
                if self._generation == generation:
                    await self._force_restart_uiautomator()
            return await self.http.jsonrpc(method, request_params, timeout=timeout)

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

        local_jar = await asyncio.to_thread(ensure_u2_jar, self.jar_path)
        if not await self._check_device_file_hash(local_jar, U2_JAR_REMOTE_PATH):
            await self.device.push(local_jar, U2_JAR_REMOTE_PATH, check=True)

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
                raise LaunchUiAutomationError("server quit unexpectedly", output_buffer)
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
