import asyncio

import async_uiautomator2.device as device_module
from async_uiautomator2.device import AsyncDevice, async_connect


class FakeServer:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False

    async def jsonrpc_call(self, method, params=None, timeout=10):
        self.calls.append((method, params, timeout))
        if method == "deviceInfo":
            return {"serial": "demo", "displayWidth": 200, "displayHeight": 100}
        if method == "dumpWindowHierarchy":
            return "<hierarchy />"
        return True

    async def stop_uiautomator(self, wait: bool = True) -> None:
        self.closed = True


class FakeAdb:
    serial = "demo"

    def __init__(self) -> None:
        self.shell_calls = []
        self.push_calls = []
        self.started = []
        self.stopped = []
        self.cleared = []

    async def shell(self, cmd, timeout=60):
        self.shell_calls.append((cmd, timeout))
        return "ok"

    async def push(self, src, dst, mode=0o644, check=False):
        self.push_calls.append((src, dst, mode, check))

    async def app_start(self, package_name):
        self.started.append(package_name)
        return "started"

    async def app_stop(self, package_name):
        self.stopped.append(package_name)
        return "stopped"

    async def app_clear(self, package_name):
        self.cleared.append(package_name)
        return "cleared"


def test_async_device_delegates_public_api() -> None:
    async def run() -> None:
        adb = FakeAdb()
        server = FakeServer()
        device = AsyncDevice(adb, server)

        assert await device.info == {
            "serial": "demo",
            "displayWidth": 200,
            "displayHeight": 100,
        }
        assert await device.click(1, 2) is True
        assert await device.dump_hierarchy() == "<hierarchy />"
        assert await device.shell("echo ok", timeout=3) == "ok"
        await device.push("a.txt", "/data/local/tmp/a.txt", mode=0o600)
        assert await device.app_start("com.example") == "started"

        assert server.calls[:3] == [
            ("deviceInfo", [], 10),
            ("click", [1, 2], 10),
            ("dumpWindowHierarchy", [False, 50], 10),
        ]
        assert adb.shell_calls == [("echo ok", 3)]
        assert adb.push_calls == [("a.txt", "/data/local/tmp/a.txt", 0o600, False)]
        assert adb.started == ["com.example"]

    asyncio.run(run())


def test_async_device_common_input_gesture_and_app_helpers() -> None:
    async def run() -> None:
        adb = FakeAdb()
        server = FakeServer()
        device = AsyncDevice(adb, server)

        assert await device.long_click(10, 20, duration=0.75) is True
        assert await device.swipe(1, 2, 3, 4, duration=0.5) is True
        assert await device.drag(5, 6, 7, 8, duration=0.25) is True
        assert await device.clear_text() is True
        assert await device.send_keys("hello", clear=True) is True
        assert await device.app_stop("com.example") == "stopped"
        assert await device.app_clear("com.example") == "cleared"

        assert server.calls == [
            ("click", [10, 20, 750], 10),
            ("swipe", [1, 2, 3, 4, 100], 10),
            ("drag", [5, 6, 7, 8, 50], 10),
            ("clearInputText", [], 10),
            ("clearInputText", [], 10),
            ("setClipboard", [None, "hello"], 10),
            ("pasteClipboard", [], 10),
        ]
        assert adb.stopped == ["com.example"]
        assert adb.cleared == ["com.example"]

    asyncio.run(run())


def test_async_device_context_manager_closes_server() -> None:
    async def run() -> None:
        server = FakeServer()
        async with AsyncDevice(FakeAdb(), server):
            pass

        assert server.closed is True

    asyncio.run(run())


def test_async_connect_uses_injected_device_factory(monkeypatch) -> None:
    async def run() -> None:
        started = False

        class FakeBasicServer(FakeServer):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__()

            async def start_uiautomator(self) -> None:
                nonlocal started
                started = True

        monkeypatch.setattr(device_module, "AsyncBasicUiautomatorServer", FakeBasicServer)

        device = await async_connect("demo", device_factory=lambda serial: FakeAdb())

        assert isinstance(device, AsyncDevice)
        assert started is True

    asyncio.run(run())
