"""异步 UiSelector 与 UiObject 原型。

这个模块刻意不复刻 `uiautomator2._selector.UiObject` 的完整能力，而是先实现
最常用、最能验证异步模型的选择器入口：

1. 用 `SelectorQuery` 提供 snake_case、可类型提示的选择器参数。
2. 用 `AsyncUiObject` 提供 `await obj.info`、`await obj.exists` 和
   `await obj.click()` 等异步元素操作。
3. 保留 `select_raw()` 使用原始 uiautomator2 selector 字段，方便临时兼容。
"""

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
    """类型友好的 UiSelector 查询条件。

    `uiautomator2` 原生写法是 `d(text="OK", resourceId="...")`，核心问题是
    `__call__(**kwargs)` 无法给 IDE 和类型检查器提供可靠提示。本类用明确字段替代
    任意 `kwargs`，并在转换时映射到设备端 `u2.jar` 需要的 camelCase 字段。

    Args:
        text (str | None): 精确匹配文本。
        text_contains (str | None): 文本包含匹配，对应 `textContains`。
        text_matches (str | None): 文本正则匹配，对应 `textMatches`。
        text_starts_with (str | None): 文本前缀匹配，对应 `textStartsWith`。
        class_name (str | None): 控件类名，对应 `className`。
        class_name_matches (str | None): 控件类名正则匹配。
        description (str | None): content-desc 精确匹配。
        description_contains (str | None): content-desc 包含匹配。
        description_matches (str | None): content-desc 正则匹配。
        description_starts_with (str | None): content-desc 前缀匹配。
        resource_id (str | None): Android resource id，对应 `resourceId`。
        resource_id_matches (str | None): resource id 正则匹配。
        package_name (str | None): 包名，对应 `packageName`。
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
    """

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
        """转换成 `uiautomator2.Selector` 接受的原始字段。

        Returns:
            dict[str, Any]: 已过滤 `None` 值并完成 camelCase 映射的字段。
        """

        return {
            raw_name: value
            for field_name, raw_name in FIELD_MAP.items()
            if (value := getattr(self, field_name)) is not None
        }

    def to_selector(self) -> Selector:
        """构造 `uiautomator2._selector.Selector`。

        Returns:
            Selector: 可直接序列化给 `u2.jar` JSON-RPC 的选择器对象。
        """

        return Selector(**self.to_kwargs())


class AsyncUiObject:
    """异步 UI 元素对象。

    Args:
        session (Any): 具备 `server.jsonrpc_call()` 和 `click()` 的异步设备对象。
        selector (Selector): 当前元素选择器。

    说明：
        这里的 `info` 与 `exists` 设计为返回 coroutine 的属性，调用方式为
        `await obj.info` 和 `await obj.exists`，与当前 `AsyncDevice.info` 的风格保持一致。
    """

    def __init__(self, session: Any, selector: Selector) -> None:
        self.session = session
        self.selector = selector

    @property
    def info(self):
        """Coroutine[Any]: 获取当前元素信息。"""

        return self.get_info()

    @property
    def exists(self):
        """Coroutine[bool]: 立即检查元素是否存在。"""

        return self.exists_now()

    async def get_info(self, timeout: float = 10) -> dict[str, Any]:
        """获取元素信息。

        Args:
            timeout (float): HTTP 请求超时时间，单位秒。

        Returns:
            dict[str, Any]: 设备端 `objInfo` 返回的元素信息。
        """

        return await self.session.server.jsonrpc_call(
            "objInfo", [self.selector], timeout=timeout
        )

    async def exists_now(self, timeout: float = 10) -> bool:
        """立即检查元素是否存在。

        Args:
            timeout (float): HTTP 请求超时时间，单位秒。

        Returns:
            bool: 元素当前是否存在。
        """

        return bool(
            await self.session.server.jsonrpc_call(
                "waitForExists", [self.selector, 0], timeout=timeout
            )
        )

    async def wait(self, exists: bool = True, timeout: float | None = None) -> bool:
        """等待元素出现或消失。

        Args:
            exists (bool): `True` 表示等待出现，`False` 表示等待消失。
            timeout (float | None): 等待时间，单位秒；`None` 时使用 20 秒。

        Returns:
            bool: 等待条件是否满足。
        """

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
        """等待元素消失。

        Args:
            timeout (float | None): 等待时间，单位秒。

        Returns:
            bool: 元素是否已消失。
        """

        return await self.wait(exists=False, timeout=timeout)

    async def must_wait(
        self, exists: bool = True, timeout: float | None = None
    ) -> None:
        """等待元素满足条件，失败时抛出 `UiObjectNotFoundError`。

        Args:
            exists (bool): `True` 表示等待出现，`False` 表示等待消失。
            timeout (float | None): 等待时间，单位秒。

        Raises:
            UiObjectNotFoundError: 等待条件未满足。
        """

        if not await self.wait(exists=exists, timeout=timeout):
            raise UiObjectNotFoundError(
                {"code": -32002, "data": str(self.selector), "method": "wait"}
            )

    async def bounds(self, timeout: float = 10) -> BoundsTuple:
        """获取元素可见区域。

        Args:
            timeout (float): HTTP 请求超时时间，单位秒。

        Returns:
            BoundsTuple: `(left, top, right, bottom)`。

        Raises:
            UiObjectNotFoundError: 设备端未返回 bounds 信息。
        """

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
        """计算元素内部点击点。

        Args:
            offset (tuple[float, float] | None): 元素内相对偏移，`(0.5, 0.5)` 表示中心。
            timeout (float): 获取元素信息的 HTTP 超时时间，单位秒。

        Returns:
            PointTuple: `(x, y)` 坐标。
        """

        left, top, right, bottom = await self.bounds(timeout=timeout)
        xoff, yoff = (0.5, 0.5) if offset is None else offset
        return (left + (right - left) * xoff, top + (bottom - top) * yoff)

    async def click(
        self,
        timeout: float | None = None,
        offset: tuple[float, float] | None = (0.5, 0.5),
    ) -> Any:
        """点击元素。

        Args:
            timeout (float | None): 等待元素出现的时间，单位秒。
            offset (tuple[float, float] | None): 元素内相对点击位置。

        Returns:
            Any: 底层坐标点击的 JSON-RPC 返回值。
        """

        await self.must_wait(timeout=timeout)
        x, y = await self.center(offset=offset)
        return await self.session.click(x, y)

    def child(
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
        """创建子元素选择器。

        Returns:
            AsyncUiObject: 带有 child 链路的新元素对象。
        """

        child_kwargs = SelectorQuery(
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
        ).to_kwargs()
        return AsyncUiObject(self.session, self.selector.clone().child(**child_kwargs))

    def sibling(
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
        """创建兄弟元素选择器。

        Returns:
            AsyncUiObject: 带有 sibling 链路的新元素对象。
        """

        sibling_kwargs = SelectorQuery(
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
        ).to_kwargs()
        return AsyncUiObject(
            self.session, self.selector.clone().sibling(**sibling_kwargs)
        )

    child_selector = child
    from_parent = sibling
