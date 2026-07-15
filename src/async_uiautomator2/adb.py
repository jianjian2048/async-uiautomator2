"""异步 ADB backend 协议与线程包装实现。"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from pathlib import Path
from typing import Any, Protocol

import adbutils


class AsyncConnection(Protocol):
    """异步字节连接协议。

    Args:
        data (bytes): 发送或接收的原始字节数据。
    """

    async def sendall(self, data: bytes) -> None:
        """发送完整字节串。"""

    async def recv(self, size: int) -> bytes:
        """读取一段字节。"""

    async def close(self) -> None:
        """关闭连接。"""


class AsyncAdbDevice(Protocol):
    """异步 ADB 设备协议。"""

    serial: str | None

    async def create_connection(
        self, network: Any, address: int | str
    ) -> AsyncConnection:
        """创建到设备端端口或 socket 的连接。"""

    async def shell(self, cmd: str | list[str], timeout: float = 60) -> str:
        """执行一次非流式 adb shell。"""

    async def shell_stream(self, cmd: str | list[str]) -> Any:
        """启动一条流式 shell 连接。"""

    async def push(
        self, src: str | Path, dst: str, mode: int = 0o644, check: bool = False
    ) -> None:
        """推送文件到设备。"""

    async def pull(
        self, src: str, dst: str | Path, exist_ok: bool = False
    ) -> int:
        """从设备拉取文件或目录。"""

    async def screenshot(self, display_id: int | None = None) -> Any:
        """截取设备屏幕并返回 Pillow 图像。"""

    async def app_start(self, package_name: str) -> Any:
        """启动 Android 应用。"""

    async def app_stop(self, package_name: str) -> Any:
        """停止 Android 应用。"""

    async def app_clear(self, package_name: str) -> Any:
        """清理 Android 应用数据。"""


class AsyncSocketConnection:
    """将同步 socket 包装成异步连接。

    Args:
        sock (Any): 同步 socket 对象，通常来自 `adbutils`。
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
        if close is not None:
            await asyncio.to_thread(close)


class ThreadedAdbProcess:
    """流式 adb shell 进程包装器。

    Args:
        conn (Any): `adbutils` 返回的流式连接对象。
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self.output = bytearray()
        self._finished = threading.Event()
        self._reader_thread = threading.Thread(
            target=self._read_output,
            name="async_uiautomator2_adb_stream_reader",
            daemon=True,
        )
        self._reader_thread.start()

    def poll(self) -> int | None:
        """返回进程状态，`None` 表示仍在运行。"""

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
        serial (str | None): ADB 设备序列号。为 `None` 时使用默认设备。
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

    async def pull(
        self, src: str, dst: str | Path, exist_ok: bool = False
    ) -> int:
        """从设备拉取文件或目录。"""

        dev = await self._ensure_device()
        return await asyncio.to_thread(dev.sync.pull, src, dst, exist_ok=exist_ok)

    async def screenshot(self, display_id: int | None = None) -> Any:
        """截取设备屏幕并返回 Pillow 图像。"""

        dev = await self._ensure_device()
        return await asyncio.to_thread(dev.screenshot, display_id=display_id)

    async def app_start(self, package_name: str) -> Any:
        """启动 Android 应用。"""

        dev = await self._ensure_device()
        return await asyncio.to_thread(dev.app_start, package_name)

    async def app_stop(self, package_name: str) -> Any:
        """停止 Android 应用。"""

        dev = await self._ensure_device()
        return await asyncio.to_thread(dev.app_stop, package_name)

    async def app_clear(self, package_name: str) -> Any:
        """清理 Android 应用数据。"""

        dev = await self._ensure_device()
        return await asyncio.to_thread(dev.app_clear, package_name)

    async def _ensure_device(self) -> Any:
        """懒加载并缓存 `adbutils.AdbDevice`。"""

        if self._device is None:
            if self.serial:
                self._device = await asyncio.to_thread(adbutils.adb.device, self.serial)
            else:
                self._device = await asyncio.to_thread(adbutils.adb.device)
            self.serial = self._device.serial
        return self._device
