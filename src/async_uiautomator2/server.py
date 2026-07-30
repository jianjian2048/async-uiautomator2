"""异步 `u2.jar` 生命周期管理。"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

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
U2_LAUNCH_COMMAND_TEMPLATE = (
    "CLASSPATH=/data/local/tmp/u2.jar app_process / "
    "com.wetest.uia2.Main -p {port}"
)


def _check_port(port: int) -> None:
    """检查设备端 HTTP 端口范围。"""

    if not 1 <= port <= 65535:
        raise ValueError(f"port must be 1-65535, got {port}")


@dataclass
class _LifecycleState:
    """同一事件循环内一个设备端口的共享生命周期状态。"""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    input_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    generation: int = 0


class AsyncBasicUiautomatorServer:
    """异步 `u2.jar` 生命周期与 JSON-RPC 管理器。

    Args:
        device (AsyncAdbDevice): 异步 ADB 设备适配器。
        port (int): 设备端 `u2.jar` HTTP 端口。
        jar_path (str | Path): 本地 `u2.jar` 路径。
        setup_jar (bool): 是否在启动前检查并推送 `u2.jar`。
    """

    _lifecycle_states: ClassVar[
        weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            weakref.WeakValueDictionary[
                tuple[str | None, int],
                _LifecycleState,
            ],
        ]
    ] = weakref.WeakKeyDictionary()
    _lifecycle_states_guard: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        device: AsyncAdbDevice,
        port: int = DEFAULT_PORT,
        jar_path: str | Path | None = None,
        setup_jar: bool = True,
    ) -> None:
        _check_port(port)
        self.device = device
        self.port = port
        self.jar_path = Path(jar_path) if jar_path is not None else None
        self.setup_jar = setup_jar
        self.http = AsyncAdbHTTPClient(device, port)
        self._process: Any = None
        self._restart_lock = asyncio.Lock()
        self._lifecycle_serial = getattr(device, "serial", None)
        self._lifecycle_loop: asyncio.AbstractEventLoop | None = None
        self._lifecycle_state: _LifecycleState | None = None
        self._generation = 0

    @property
    def input_lock(self) -> asyncio.Lock:
        """返回当前设备端口共享的原始触摸输入锁。"""

        return self._get_lifecycle_state().input_lock

    async def start_uiautomator(self) -> None:
        """确保 `u2.jar` 服务已启动并可响应 `/ping`。"""

        lifecycle = self._get_lifecycle_state()
        async with lifecycle.lock:
            if self.setup_jar:
                await self._setup_jar()
            if self._process is not None and self._process.poll() is not None:
                self._process = None
            if not await self._check_alive():
                self._process = await self.launch_uiautomator()
                await self._wait_ready()
                lifecycle.generation += 1
            self._generation = lifecycle.generation

    async def stop_uiautomator(self, wait: bool = True) -> None:
        """停止当前客户端启动的 `u2.jar` stream 连接。"""

        lifecycle = self._get_lifecycle_state()
        async with lifecycle.lock:
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

        lifecycle = self._get_lifecycle_state()
        generation = lifecycle.generation
        self._generation = generation
        request_params = params if params is not None else []
        try:
            return await self.http.jsonrpc(method, request_params, timeout=timeout)
        except (HTTPError, UiAutomationNotConnectedError):
            async with self._restart_lock:
                if lifecycle.generation == generation:
                    await self._force_restart_uiautomator(
                        expected_generation=generation
                    )
                else:
                    self._generation = lifecycle.generation
            return await self.http.jsonrpc(method, request_params, timeout=timeout)

    async def _force_restart_uiautomator(
        self,
        expected_generation: int | None = None,
    ) -> None:
        """在持有 restart lock 后强制重启 `u2.jar`。"""

        lifecycle = self._get_lifecycle_state()
        async with lifecycle.lock:
            if (
                expected_generation is not None
                and lifecycle.generation != expected_generation
            ):
                self._generation = lifecycle.generation
                return
            if self._process is not None:
                await self._process.kill()
                self._process = None
            if self.setup_jar:
                await self._setup_jar()
            self._process = await self.launch_uiautomator()
            await self._wait_ready()
            lifecycle.generation += 1
            self._generation = lifecycle.generation

    def _get_lifecycle_state(self) -> _LifecycleState:
        """返回当前事件循环和设备端口对应的共享生命周期状态。"""

        loop = asyncio.get_running_loop()
        if self._lifecycle_loop is loop and self._lifecycle_state is not None:
            return self._lifecycle_state

        key = (self._lifecycle_serial, self.port)
        with self._lifecycle_states_guard:
            loop_states = self._lifecycle_states.get(loop)
            if loop_states is None:
                loop_states = weakref.WeakValueDictionary()
                self._lifecycle_states[loop] = loop_states
            lifecycle = loop_states.get(key)
            if lifecycle is None:
                lifecycle = _LifecycleState()
                loop_states[key] = lifecycle

        self._lifecycle_loop = loop
        self._lifecycle_state = lifecycle
        return lifecycle

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

        command = U2_LAUNCH_COMMAND_TEMPLATE.format(port=self.port)
        return await self.device.shell_stream(command)

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
