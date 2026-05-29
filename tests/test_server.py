import asyncio
import hashlib
from pathlib import Path

import pytest
from uiautomator2.exceptions import HTTPError

from async_uiautomator2.server import AsyncBasicUiautomatorServer


class FakeProcess:
    def __init__(self) -> None:
        self.output = bytearray()
        self.killed = False

    def poll(self):
        return None if not self.killed else 0

    async def kill(self) -> None:
        self.killed = True


class FakeDevice:
    def __init__(self, shell_output: str = "") -> None:
        self.shell_output = shell_output
        self.pushes = []
        self.streams = []

    async def shell(self, cmd, timeout: float = 60) -> str:
        return self.shell_output

    async def push(self, src, dst, mode: int = 0o644, check: bool = False) -> None:
        self.pushes.append((Path(src), dst, mode, check))

    async def shell_stream(self, cmd):
        process = FakeProcess()
        self.streams.append((cmd, process))
        return process


class ReadyServer(AsyncBasicUiautomatorServer):
    def __init__(self, *args, alive_sequence=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.alive_sequence = list(alive_sequence or [])
        self.ready_waits = 0

    async def _check_alive(self) -> bool:
        if self.alive_sequence:
            return self.alive_sequence.pop(0)
        return True

    async def _wait_ready(self, launch_timeout: float = 30) -> None:
        self.ready_waits += 1


def test_setup_jar_pushes_when_hash_is_different(tmp_path) -> None:
    async def run() -> None:
        jar = tmp_path / "u2.jar"
        jar.write_bytes(b"local jar")
        dev = FakeDevice(shell_output="different-md5  /data/local/tmp/u2.jar")
        server = AsyncBasicUiautomatorServer(dev, jar_path=jar, setup_jar=True)

        await server._setup_jar()

        assert dev.pushes == [(jar, "/data/local/tmp/u2.jar", 0o644, True)]

    asyncio.run(run())


def test_setup_jar_skips_push_when_hash_matches(tmp_path) -> None:
    async def run() -> None:
        jar = tmp_path / "u2.jar"
        jar.write_bytes(b"local jar")
        md5 = hashlib.md5(jar.read_bytes()).hexdigest()
        dev = FakeDevice(shell_output=f"{md5}  /data/local/tmp/u2.jar")
        server = AsyncBasicUiautomatorServer(dev, jar_path=jar, setup_jar=True)

        await server._setup_jar()

        assert dev.pushes == []

    asyncio.run(run())


def test_start_launches_process_when_not_alive(tmp_path) -> None:
    async def run() -> None:
        jar = tmp_path / "u2.jar"
        jar.write_bytes(b"local jar")
        dev = FakeDevice(shell_output=hashlib.md5(b"local jar").hexdigest())
        server = ReadyServer(dev, jar_path=jar, alive_sequence=[False])

        await server.start_uiautomator()

        assert len(dev.streams) == 1
        assert server.ready_waits == 1

    asyncio.run(run())


def test_stop_kills_current_process_without_global_cleanup() -> None:
    async def run() -> None:
        dev = FakeDevice()
        server = AsyncBasicUiautomatorServer(dev, setup_jar=False)
        process = FakeProcess()
        server._process = process

        await server.stop_uiautomator(wait=False)

        assert process.killed is True
        assert server._process is None

    asyncio.run(run())


def test_concurrent_jsonrpc_failures_trigger_one_restart() -> None:
    async def run() -> None:
        dev = FakeDevice()
        server = AsyncBasicUiautomatorServer(dev, setup_jar=False)
        restarts = 0

        class FakeHTTP:
            async def jsonrpc(self, method, params, timeout=10):
                if server._generation == 0:
                    raise HTTPError("down")
                return {"ok": True}

        async def restart() -> None:
            nonlocal restarts
            restarts += 1
            server._generation += 1

        server.http = FakeHTTP()
        server._force_restart_uiautomator = restart

        results = await asyncio.gather(
            server.jsonrpc_call("deviceInfo"),
            server.jsonrpc_call("deviceInfo"),
            server.jsonrpc_call("deviceInfo"),
        )

        assert results == [{"ok": True}, {"ok": True}, {"ok": True}]
        assert restarts == 1

    asyncio.run(run())


def test_missing_local_jar_raises_file_not_found(tmp_path) -> None:
    async def run() -> None:
        server = AsyncBasicUiautomatorServer(
            FakeDevice(), jar_path=tmp_path / "missing.jar", setup_jar=True
        )

        with pytest.raises(FileNotFoundError):
            await server._setup_jar()

    asyncio.run(run())
