import asyncio

import pytest

import async_uiautomator2.device as device_module
from async_uiautomator2.device import AsyncDevice, async_connect


class FakeServer:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False
        self.input_lock = asyncio.Lock()

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
        self.pull_calls = []
        self.screenshot_calls = []
        self.screenshot_result = None
        self.started = []
        self.stopped = []
        self.cleared = []

    async def shell(self, cmd, timeout=60):
        self.shell_calls.append((cmd, timeout))
        return "ok"

    async def push(self, src, dst, mode=0o644, check=False):
        self.push_calls.append((src, dst, mode, check))

    async def pull(self, src, dst, exist_ok=False):
        self.pull_calls.append((src, dst, exist_ok))
        return 42

    async def screenshot(self, display_id=None):
        self.screenshot_calls.append(display_id)
        return self.screenshot_result

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
        assert (
            await device.dump_hierarchy(root_in_active=True)
            == "<hierarchy />"
        )
        assert (
            await device.dump_hierarchy(root_in_active=False)
            == "<hierarchy />"
        )
        assert await device.shell("echo ok", timeout=3) == "ok"
        await device.push("a.txt", "/data/local/tmp/a.txt", mode=0o600)
        assert await device.app_start("com.example") == "started"

        assert server.calls[:5] == [
            ("deviceInfo", [], 10),
            ("click", [1, 2], 10),
            ("dumpWindowHierarchy", [False, 50], 10),
            ("dumpWindowHierarchy", [False, 50, True], 10),
            ("dumpWindowHierarchy", [False, 50, False], 10),
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


def test_generate_bezier_trajectory_is_reproducible() -> None:
    points = device_module._generate_bezier_trajectory(
        (0, 0),
        (100, 0),
        4,
        seed=7,
    )

    assert points == device_module._generate_bezier_trajectory(
        (0, 0),
        (100, 0),
        4,
        seed=7,
    )
    assert len(points) == 5
    assert points[0] == (0, 0)
    assert points[-1] == (100, 0)
    assert any(y != 0 for _, y in points[1:-1])

    with pytest.raises(ValueError, match="steps"):
        device_module._generate_bezier_trajectory((0, 0), (100, 0), 1)


def test_async_device_swipe_points_and_bezier_use_total_duration() -> None:
    async def run() -> None:
        server = FakeServer()
        device = AsyncDevice(FakeAdb(), server)

        assert (
            await device.swipe_points(
                [(0.5, 0.5), (100, 50), (300, 200)],
                duration=0.3,
            )
            is True
        )
        assert (
            await device.swipe_bezier(
                (10, 20),
                (110, 20),
                control=(60, 70),
                duration=0.4,
                trajectory_steps=4,
            )
            is True
        )

        assert server.calls == [
            ("deviceInfo", [], 10),
            (
                "swipePoints",
                [[100, 50, 199, 99], 60],
                10,
            ),
            ("deviceInfo", [], 10),
            (
                "swipePoints",
                [[10, 20, 35, 39, 60, 45, 85, 39, 110, 20], 20],
                10,
            ),
        ]

    asyncio.run(run())


@pytest.mark.parametrize(
    ("method", "kwargs", "message"),
    [
        ("swipe_points", {"points": [(0, 0)], "duration": 0.5}, "2"),
        (
            "swipe_points",
            {"points": [(0, 0), (1, 1)], "duration": 0},
            "duration",
        ),
        (
            "swipe_bezier",
            {
                "start": (0, 0),
                "end": (10, 10),
                "trajectory_steps": 1,
            },
            "trajectory_steps",
        ),
    ],
)
def test_async_device_rejects_invalid_bezier_gestures(
    method, kwargs, message
) -> None:
    async def run() -> None:
        device = AsyncDevice(FakeAdb(), FakeServer())

        with pytest.raises(ValueError, match=message):
            await getattr(device, method)(**kwargs)

    asyncio.run(run())


def test_async_device_drag_bezier_sends_down_moves_and_up(monkeypatch) -> None:
    async def run() -> None:
        server = FakeServer()
        device = AsyncDevice(FakeAdb(), server)
        sleeps = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr(device_module.asyncio, "sleep", fake_sleep)

        assert (
            await device.drag_bezier(
                (10, 10),
                (90, 10),
                control=(50, 50),
                hold_duration=0.3,
                duration=0.4,
                trajectory_steps=2,
            )
            is True
        )

        assert server.calls == [
            ("deviceInfo", [], 10),
            ("injectInputEvent", [0, 10, 10, 0], 10),
            ("injectInputEvent", [2, 50, 30, 0], 10),
            ("injectInputEvent", [2, 90, 10, 0], 10),
            ("injectInputEvent", [1, 90, 10, 0], 10),
        ]
        assert sleeps == [0.3, 0.2, 0.2]
        assert server.input_lock.locked() is False

    asyncio.run(run())


def test_async_device_drag_bezier_releases_touch_after_error() -> None:
    class FailingServer(FakeServer):
        async def jsonrpc_call(self, method, params=None, timeout=10):
            self.calls.append((method, params, timeout))
            if method == "deviceInfo":
                return {"displayWidth": 200, "displayHeight": 100}
            if method == "injectInputEvent" and params[0] == 2:
                raise RuntimeError("move failed")
            return True

    async def run() -> None:
        server = FailingServer()
        device = AsyncDevice(FakeAdb(), server)

        with pytest.raises(RuntimeError, match="move failed"):
            await device.drag_bezier(
                (10, 10),
                (90, 10),
                control=(50, 50),
                hold_duration=0,
                duration=0.01,
                trajectory_steps=2,
            )

        assert server.calls[-1] == (
            "injectInputEvent",
            [1, 10, 10, 0],
            10,
        )
        assert server.input_lock.locked() is False

    asyncio.run(run())


def test_async_device_drag_bezier_releases_touch_when_cancelled() -> None:
    class BlockingServer(FakeServer):
        def __init__(self) -> None:
            super().__init__()
            self.move_started = asyncio.Event()

        async def jsonrpc_call(self, method, params=None, timeout=10):
            self.calls.append((method, params, timeout))
            if method == "deviceInfo":
                return {"displayWidth": 200, "displayHeight": 100}
            if method == "injectInputEvent" and params[0] == 2:
                self.move_started.set()
                await asyncio.Event().wait()
            return True

    async def run() -> None:
        server = BlockingServer()
        device = AsyncDevice(FakeAdb(), server)
        task = asyncio.create_task(
            device.drag_bezier(
                (10, 10),
                (90, 10),
                control=(50, 50),
                hold_duration=0,
                duration=0.01,
                trajectory_steps=2,
            )
        )

        await asyncio.wait_for(server.move_started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert server.calls[-1] == (
            "injectInputEvent",
            [1, 10, 10, 0],
            10,
        )
        assert server.input_lock.locked() is False

    asyncio.run(run())


def test_async_device_pulls_files_and_captures_screenshots() -> None:
    class FakeImage:
        def __init__(self) -> None:
            self.saved_as = []

        def save(self, filename) -> None:
            self.saved_as.append(filename)

    async def run() -> None:
        adb = FakeAdb()
        image = FakeImage()
        adb.screenshot_result = image
        device = AsyncDevice(adb, FakeServer())

        assert await device.pull("/sdcard/report.txt", "report.txt", exist_ok=True) == 42
        assert adb.pull_calls == [("/sdcard/report.txt", "report.txt", True)]
        assert await device.screenshot(display_id=2) is image
        assert adb.screenshot_calls == [2]
        assert await device.screenshot("home.png") is None
        assert image.saved_as == ["home.png"]

    asyncio.run(run())


def test_async_device_converts_screenshot_when_not_saving(monkeypatch) -> None:
    async def run() -> None:
        adb = FakeAdb()
        image = object()
        converted = object()
        adb.screenshot_result = image
        device = AsyncDevice(adb, FakeServer())
        convert_calls = []

        def fake_image_convert(value, format):
            convert_calls.append((value, format))
            return converted

        monkeypatch.setattr(device_module, "image_convert", fake_image_convert)

        assert await device.screenshot(format="opencv") is converted
        assert convert_calls == [(image, "opencv")]

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
        server_kwargs = {}

        class FakeBasicServer(FakeServer):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__()
                server_kwargs.update(kwargs)

            async def start_uiautomator(self) -> None:
                nonlocal started
                started = True

        monkeypatch.setattr(device_module, "AsyncBasicUiautomatorServer", FakeBasicServer)

        device = await async_connect(
            "demo",
            port=9010,
            device_factory=lambda serial: FakeAdb(),
        )

        assert isinstance(device, AsyncDevice)
        assert started is True
        assert server_kwargs["port"] == 9010

    asyncio.run(run())
