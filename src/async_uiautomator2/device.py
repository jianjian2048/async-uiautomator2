"""面向用户的异步设备入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from uiautomator2._selector import Selector

from async_uiautomator2.adb import AsyncAdbDevice, ThreadedAdbDevice
from async_uiautomator2.selector import AsyncUiObject, SelectorQuery
from async_uiautomator2.server import AsyncBasicUiautomatorServer
from async_uiautomator2.xpath import AsyncXPathSelector

SCROLL_STEPS = 55


class AsyncDevice:
    """面向调用方的最小异步设备 API。

    Args:
        adb_device (AsyncAdbDevice): 异步 ADB 设备适配器。
        server (AsyncBasicUiautomatorServer): `u2.jar` 服务管理器。
    """

    def __init__(
        self, adb_device: AsyncAdbDevice, server: AsyncBasicUiautomatorServer
    ) -> None:
        self.adb_device = adb_device
        self.server = server

    @property
    def info(self):
        """获取设备信息的协程。"""

        return self.server.jsonrpc_call("deviceInfo", [], timeout=10)

    async def click(self, x: int | float, y: int | float) -> Any:
        """点击屏幕坐标。"""

        return await self.server.jsonrpc_call("click", [x, y], timeout=10)

    async def long_click(
        self, x: int | float, y: int | float, duration: float = 0.5
    ) -> Any:
        """长按屏幕坐标。"""

        x, y = await self._pos_rel2abs(x, y)
        return await self.server.jsonrpc_call(
            "click", [x, y, int(duration * 1000)], timeout=10
        )

    async def swipe(
        self,
        fx: int | float,
        fy: int | float,
        tx: int | float,
        ty: int | float,
        duration: float | None = None,
        steps: int | None = None,
    ) -> Any:
        """从一个坐标滑动到另一个坐标。"""

        if duration is not None and steps is not None:
            duration = None
        if duration is not None:
            steps = int(duration * 200)
        if not steps:
            steps = SCROLL_STEPS
        fx, fy = await self._pos_rel2abs(fx, fy)
        tx, ty = await self._pos_rel2abs(tx, ty)
        return await self.server.jsonrpc_call(
            "swipe", [fx, fy, tx, ty, max(2, steps)], timeout=10
        )

    async def drag(
        self,
        sx: int | float,
        sy: int | float,
        ex: int | float,
        ey: int | float,
        duration: float = 0.5,
    ) -> Any:
        """从一个坐标拖拽到另一个坐标。"""

        sx, sy = await self._pos_rel2abs(sx, sy)
        ex, ey = await self._pos_rel2abs(ex, ey)
        return await self.server.jsonrpc_call(
            "drag", [sx, sy, ex, ey, int(duration * 200)], timeout=10
        )

    async def clear_text(self) -> Any:
        """清空当前聚焦输入框文本。"""

        return await self.server.jsonrpc_call("clearInputText", [], timeout=10)

    async def set_clipboard(self, text: str, label: str | None = None) -> Any:
        """设置设备剪贴板文本。"""

        return await self.server.jsonrpc_call(
            "setClipboard", [label, text], timeout=10
        )

    async def send_keys(self, text: str, clear: bool = False) -> Any:
        """向当前聚焦输入框输入文本。"""

        if clear:
            await self.clear_text()
        await self.set_clipboard(text)
        return await self.server.jsonrpc_call("pasteClipboard", [], timeout=10)

    async def shell(self, cmd: str | list[str], timeout: float = 60) -> str:
        """执行 adb shell 命令。"""

        return await self.adb_device.shell(cmd, timeout=timeout)

    async def push(self, src: str | Path, dst: str, mode: int = 0o644) -> None:
        """推送文件到设备。"""

        await self.adb_device.push(src, dst, mode=mode)

    async def app_start(self, package_name: str) -> Any:
        """启动 Android 应用。"""

        return await self.adb_device.app_start(package_name)

    async def app_stop(self, package_name: str) -> Any:
        """停止 Android 应用。"""

        app_stop = getattr(self.adb_device, "app_stop", None)
        if app_stop is not None:
            return await app_stop(package_name)
        return await self.shell(["am", "force-stop", package_name])

    async def app_clear(self, package_name: str) -> Any:
        """停止并清理 Android 应用数据。"""

        app_clear = getattr(self.adb_device, "app_clear", None)
        if app_clear is not None:
            return await app_clear(package_name)
        return await self.shell(["pm", "clear", package_name])

    async def window_size(self) -> tuple[int, int]:
        """获取当前设备屏幕尺寸。"""

        info = await self.info
        width = info.get("displayWidth")
        height = info.get("displayHeight")
        if width is None or height is None:
            display_size = info.get("displaySize") or {}
            width = display_size.get("width")
            height = display_size.get("height")
        if width is None or height is None:
            raise RuntimeError("deviceInfo 未返回屏幕尺寸")
        return int(width), int(height)

    async def dump_hierarchy(
        self,
        compressed: bool = False,
        pretty: bool = False,
        max_depth: int = 50,
    ) -> str:
        """异步 dump 当前窗口 XML 层级。"""

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
    ) -> AsyncUiObject:
        """创建类型友好的异步 UI 元素选择器。"""

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

    def select_raw(self, **kwargs: Any) -> AsyncUiObject:
        """使用原始 uiautomator2 selector 字段创建元素对象。"""

        return AsyncUiObject(self, Selector(**kwargs))

    def xpath(self, xpath: str, source: str | None = None) -> AsyncXPathSelector:
        """创建异步 XPath 选择器。"""

        return AsyncXPathSelector(self, xpath, source=source)

    async def _pos_rel2abs(
        self, x: int | float, y: int | float
    ) -> tuple[int | float, int | float]:
        """将小于 1 的相对坐标转换为绝对坐标。"""

        if x < 0 or y < 0:
            raise ValueError("坐标不能为负数")
        if x < 1 or y < 1:
            width, height = await self.window_size()
            if x < 1:
                x = int(width * x)
            if y < 1:
                y = int(height * y)
        return x, y

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
    jar_path: str | Path | None = None,
    setup_jar: bool = True,
) -> AsyncDevice:
    """连接设备并返回最小异步设备对象。"""

    factory = device_factory or ThreadedAdbDevice
    adb_device = factory(serial)
    server = AsyncBasicUiautomatorServer(
        adb_device, jar_path=jar_path, setup_jar=setup_jar
    )
    await server.start_uiautomator()
    return AsyncDevice(adb_device, server)
