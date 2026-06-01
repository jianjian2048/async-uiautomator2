"""类型友好的异步 UiSelector 与 UI 对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from uiautomator2._selector import Selector
from uiautomator2.exceptions import UiObjectNotFoundError

BoundsTuple = tuple[int | float, int | float, int | float, int | float]
PointTuple = tuple[int | float, int | float]

FIELD_MAP = {
    "text": "text",
    "text_contains": "textContains",
    "text_matches": "textMatches",
    "text_starts_with": "textStartsWith",
    "class_name": "className",
    "class_name_matches": "classNameMatches",
    "description": "description",
    "description_contains": "descriptionContains",
    "description_matches": "descriptionMatches",
    "description_starts_with": "descriptionStartsWith",
    "checkable": "checkable",
    "checked": "checked",
    "clickable": "clickable",
    "long_clickable": "longClickable",
    "scrollable": "scrollable",
    "enabled": "enabled",
    "focusable": "focusable",
    "focused": "focused",
    "selected": "selected",
    "package_name": "packageName",
    "package_name_matches": "packageNameMatches",
    "resource_id": "resourceId",
    "resource_id_matches": "resourceIdMatches",
    "index": "index",
    "instance": "instance",
}


@dataclass(frozen=True, slots=True)
class SelectorQuery:
    """类型友好的 UiSelector 查询条件。"""

    text: str | None = None
    text_contains: str | None = None
    text_matches: str | None = None
    text_starts_with: str | None = None
    class_name: str | None = None
    class_name_matches: str | None = None
    description: str | None = None
    description_contains: str | None = None
    description_matches: str | None = None
    description_starts_with: str | None = None
    resource_id: str | None = None
    resource_id_matches: str | None = None
    package_name: str | None = None
    package_name_matches: str | None = None
    index: int | None = None
    instance: int | None = None
    checkable: bool | None = None
    checked: bool | None = None
    clickable: bool | None = None
    long_clickable: bool | None = None
    scrollable: bool | None = None
    enabled: bool | None = None
    focusable: bool | None = None
    focused: bool | None = None
    selected: bool | None = None

    def to_kwargs(self) -> dict[str, Any]:
        """转换成 `uiautomator2.Selector` 接受的原始字段。"""

        return {
            raw_name: value
            for field_name, raw_name in FIELD_MAP.items()
            if (value := getattr(self, field_name)) is not None
        }

    def to_selector(self) -> Selector:
        """构造 `uiautomator2._selector.Selector`。"""

        return Selector(**self.to_kwargs())


class AsyncUiObject:
    """异步 UI 元素对象。

    Args:
        session (Any): 具备 `server.jsonrpc_call()` 和 `click()` 的异步设备对象。
        selector (Selector): 当前元素选择器。
    """

    def __init__(self, session: Any, selector: Selector) -> None:
        self.session = session
        self.selector = selector

    @property
    def info(self):
        """获取当前元素信息的协程。"""

        return self.get_info()

    @property
    def exists(self):
        """立即检查元素是否存在的协程。"""

        return self.exists_now()

    async def get_info(self, timeout: float = 10) -> dict[str, Any]:
        """获取元素信息。"""

        return await self.session.server.jsonrpc_call(
            "objInfo", [self.selector], timeout=timeout
        )

    async def exists_now(self, timeout: float = 10) -> bool:
        """立即检查元素是否存在。"""

        return bool(
            await self.session.server.jsonrpc_call(
                "waitForExists", [self.selector, 0], timeout=timeout
            )
        )

    async def wait(self, exists: bool = True, timeout: float | None = None) -> bool:
        """等待元素出现或消失。"""

        wait_timeout = 20.0 if timeout is None else timeout
        method = "waitForExists" if exists else "waitUntilGone"
        return bool(
            await self.session.server.jsonrpc_call(
                method,
                [self.selector, int(wait_timeout * 1000)],
                timeout=wait_timeout + 10,
            )
        )

    async def wait_gone(self, timeout: float | None = None) -> bool:
        """等待元素消失。"""

        return await self.wait(exists=False, timeout=timeout)

    async def must_wait(
        self, exists: bool = True, timeout: float | None = None
    ) -> None:
        """等待元素满足条件，失败时抛出 `UiObjectNotFoundError`。"""

        if not await self.wait(exists=exists, timeout=timeout):
            raise UiObjectNotFoundError(
                {"code": -32002, "data": str(self.selector), "method": "wait"}
            )

    async def bounds(self, timeout: float = 10) -> BoundsTuple:
        """获取元素可见区域。"""

        info = await self.get_info(timeout=timeout)
        bounds = info.get("visibleBounds") or info.get("bounds")
        if not bounds:
            raise UiObjectNotFoundError(
                {"code": -32002, "data": str(self.selector), "method": "bounds"}
            )
        return (
            bounds["left"],
            bounds["top"],
            bounds["right"],
            bounds["bottom"],
        )

    async def center(
        self,
        offset: tuple[float, float] | None = (0.5, 0.5),
        timeout: float = 10,
    ) -> PointTuple:
        """计算元素内部点击点。"""

        left, top, right, bottom = await self.bounds(timeout=timeout)
        xoff, yoff = (0.5, 0.5) if offset is None else offset
        return (left + (right - left) * xoff, top + (bottom - top) * yoff)

    async def click(
        self,
        timeout: float | None = None,
        offset: tuple[float, float] | None = (0.5, 0.5),
    ) -> Any:
        """点击元素。"""

        await self.must_wait(timeout=timeout)
        x, y = await self.center(offset=offset)
        return await self.session.click(x, y)

    async def set_text(self, text: str | None, timeout: float | None = None) -> Any:
        """设置元素文本，空文本会清空输入框。"""

        await self.must_wait(timeout=timeout)
        if not text:
            return await self.session.server.jsonrpc_call(
                "clearTextField", [self.selector], timeout=10
            )
        return await self.session.server.jsonrpc_call(
            "setText", [self.selector, text], timeout=10
        )

    async def send_keys(self, text: str, timeout: float | None = None) -> Any:
        """`set_text()` 的别名。"""

        return await self.set_text(text, timeout=timeout)

    async def clear_text(self, timeout: float | None = None) -> Any:
        """清空元素文本。"""

        return await self.set_text(None, timeout=timeout)

    async def long_click(
        self, duration: float = 0.5, timeout: float | None = None
    ) -> Any:
        """长按元素中心点。"""

        await self.must_wait(timeout=timeout)
        x, y = await self.center()
        return await self.session.long_click(x, y, duration=duration)

    async def swipe(
        self, direction: str, steps: int = 10, timeout: float | None = None
    ) -> Any:
        """从元素中心向指定方向滑动。"""

        if direction not in ("left", "right", "up", "down"):
            raise ValueError("direction 必须是 left/right/up/down 之一")
        await self.must_wait(timeout=timeout)
        left, top, right, bottom = await self.bounds()
        cx = left + (right - left) * 0.5
        cy = top + (bottom - top) * 0.5
        if direction == "up":
            return await self.session.swipe(cx, cy, cx, top, steps=steps)
        if direction == "down":
            return await self.session.swipe(cx, cy, cx, bottom - 1, steps=steps)
        if direction == "left":
            return await self.session.swipe(cx, cy, left, cy, steps=steps)
        return await self.session.swipe(cx, cy, right - 1, cy, steps=steps)

    async def drag(
        self,
        x: int | float,
        y: int | float,
        duration: float = 0.5,
        timeout: float | None = None,
    ) -> Any:
        """将元素中心拖拽到指定坐标。"""

        await self.must_wait(timeout=timeout)
        sx, sy = await self.center()
        return await self.session.drag(sx, sy, x, y, duration=duration)

    def child(self, **kwargs: Any) -> "AsyncUiObject":
        """创建子元素选择器。"""

        child_kwargs = SelectorQuery(**kwargs).to_kwargs()
        return AsyncUiObject(self.session, self.selector.clone().child(**child_kwargs))

    def sibling(self, **kwargs: Any) -> "AsyncUiObject":
        """创建兄弟元素选择器。"""

        sibling_kwargs = SelectorQuery(**kwargs).to_kwargs()
        return AsyncUiObject(
            self.session, self.selector.clone().sibling(**sibling_kwargs)
        )

    child_selector = child
    from_parent = sibling
