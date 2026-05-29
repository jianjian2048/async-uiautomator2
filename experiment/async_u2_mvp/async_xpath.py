"""异步 XPath 查询原型。

这个模块复用 `uiautomator2.xpath` 已有的 XPath 规范化、XML 解析和元素信息转换逻辑，
只把设备交互部分改成异步：

1. 通过 `dumpWindowHierarchy` 异步获取 XML。
2. 在本地 XML 上执行 XPath 匹配。
3. 用元素 bounds 计算坐标，再复用 `AsyncDevice.click()` 完成点击。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from uiautomator2.exceptions import XPathElementNotFoundError
from uiautomator2.xpath import PageSource, XMLElement, XPathSelector

PointTuple = tuple[int, int]
BoundsTuple = tuple[int, int, int, int]


class AsyncXPathElement:
    """异步 XPath 元素对象。

    Args:
        session (Any): 具备 `click()` 的异步设备对象。
        element (XMLElement): `uiautomator2.xpath` 解析得到的本地 XML 元素。
    """

    def __init__(self, session: Any, element: XMLElement) -> None:
        self.session = session
        self._element = element

    @property
    def text(self) -> str | None:
        """str | None: 元素 `text` 属性。"""

        return self._element.text

    @property
    def attrib(self) -> dict[str, str]:
        """dict[str, str]: 元素 XML 属性。"""

        return self._element.attrib

    @property
    def info(self) -> dict[str, Any]:
        """dict[str, Any]: 与同步版 XPath 兼容的元素信息。"""

        return self._element.info

    @property
    def bounds(self) -> BoundsTuple:
        """BoundsTuple: 元素 bounds，格式为 `(left, top, right, bottom)`。"""

        return self._element.bounds

    def center(self) -> PointTuple:
        """计算元素中心点。

        Returns:
            PointTuple: `(x, y)` 坐标。
        """

        return self._element.center()

    def get_xpath(self, strip_index: bool = False) -> str:
        """获取元素在 XML 树中的完整 XPath。

        Args:
            strip_index (bool): 是否移除路径中的下标。

        Returns:
            str: 元素完整 XPath。
        """

        return self._element.get_xpath(strip_index=strip_index)

    async def click(self) -> Any:
        """点击元素中心点。

        Returns:
            Any: 底层坐标点击的 JSON-RPC 返回值。
        """

        x, y = self.center()
        return await self.session.click(x, y)


class AsyncXPathSelector:
    """异步 XPath 选择器。

    Args:
        session (Any): 具备 `dump_hierarchy()` 和 `click()` 的异步设备对象。
        xpath (str | XPathSelector): XPath 表达式或已构造的同步 XPath selector。
        source (str | PageSource | None): 可选固定 XML 源；传入后不会再 dump 当前界面。
    """

    def __init__(
        self,
        session: Any,
        xpath: str | XPathSelector,
        source: str | PageSource | None = None,
    ) -> None:
        self.session = session
        self._selector = xpath if isinstance(xpath, XPathSelector) else XPathSelector(xpath)
        self._source = PageSource.parse(source) if source else None
        self._last_source: PageSource | None = None

    @property
    def exists(self):
        """Coroutine[bool]: 立即检查 XPath 是否能匹配到元素。"""

        return self.exists_now()

    @property
    def info(self):
        """Coroutine[dict[str, Any]]: 获取第一个匹配元素的信息。"""

        return self.get_info()

    async def get_page_source(self) -> PageSource:
        """获取当前页面 XML 源。

        Returns:
            PageSource: 可执行 XPath 查询的页面源对象。
        """

        if self._source is not None:
            return self._source
        return PageSource.parse(await self.session.dump_hierarchy())

    async def all(self, source: str | PageSource | None = None) -> list[AsyncXPathElement]:
        """查找所有匹配元素。

        Args:
            source (str | PageSource | None): 可选 XML 源；为 `None` 时 dump 当前界面。

        Returns:
            list[AsyncXPathElement]: 匹配到的异步元素对象列表。
        """

        page_source = PageSource.parse(source) if source else await self.get_page_source()
        self._last_source = page_source
        return [
            AsyncXPathElement(self.session, element)
            for element in self._selector.all(page_source)
        ]

    async def exists_now(self) -> bool:
        """立即检查是否存在匹配元素。

        Returns:
            bool: 是否匹配到至少一个元素。
        """

        return bool(await self.all())

    async def wait(self, timeout: float | None = None, interval: float = 0.2) -> bool:
        """等待 XPath 匹配到元素。

        Args:
            timeout (float | None): 最长等待时间，单位秒；`None` 时使用 20 秒。
            interval (float): 轮询间隔，单位秒。

        Returns:
            bool: 是否在超时前匹配到元素。
        """

        deadline = time.monotonic() + (20.0 if timeout is None else timeout)
        while True:
            if await self.exists_now():
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(interval)

    async def wait_gone(
        self, timeout: float | None = None, interval: float = 0.2
    ) -> bool:
        """等待 XPath 不再匹配元素。

        Args:
            timeout (float | None): 最长等待时间，单位秒；`None` 时使用 20 秒。
            interval (float): 轮询间隔，单位秒。

        Returns:
            bool: 是否在超时前消失。
        """

        deadline = time.monotonic() + (20.0 if timeout is None else timeout)
        while True:
            if not await self.exists_now():
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(interval)

    async def get(self, timeout: float | None = None) -> AsyncXPathElement:
        """获取第一个匹配元素。

        Args:
            timeout (float | None): 最长等待时间，单位秒。

        Returns:
            AsyncXPathElement: 第一个匹配元素。

        Raises:
            XPathElementNotFoundError: 超时后仍未匹配到元素。
        """

        if not await self.wait(timeout=timeout):
            raise XPathElementNotFoundError(self)
        matches = await self.all(self._last_source)
        return matches[0]

    async def get_info(self, timeout: float | None = None) -> dict[str, Any]:
        """获取第一个匹配元素的信息。

        Args:
            timeout (float | None): 最长等待时间，单位秒。

        Returns:
            dict[str, Any]: 元素信息。
        """

        return (await self.get(timeout=timeout)).info

    async def get_text(self, timeout: float | None = None) -> str | None:
        """获取第一个匹配元素的文本。

        Args:
            timeout (float | None): 最长等待时间，单位秒。

        Returns:
            str | None: 元素文本。
        """

        return (await self.get(timeout=timeout)).text

    async def click(self, timeout: float | None = None) -> Any:
        """点击第一个匹配元素。

        Args:
            timeout (float | None): 最长等待元素出现的时间，单位秒。

        Returns:
            Any: 底层坐标点击的 JSON-RPC 返回值。
        """

        return await (await self.get(timeout=timeout)).click()

    async def click_exists(self, timeout: float | None = None) -> bool:
        """元素存在时点击。

        Args:
            timeout (float | None): 最长等待元素出现的时间，单位秒。

        Returns:
            bool: 是否完成点击。
        """

        try:
            await self.click(timeout=timeout)
            return True
        except XPathElementNotFoundError:
            return False

    def child(self, xpath: str) -> "AsyncXPathSelector":
        """追加子级 XPath。

        Args:
            xpath (str): 子级 XPath 表达式。

        Returns:
            AsyncXPathSelector: 新选择器。
        """

        return AsyncXPathSelector(self.session, self._selector.child(xpath), self._source)

    def __and__(self, xpath: str | XPathSelector) -> "AsyncXPathSelector":
        """组合 AND XPath 条件。"""

        return AsyncXPathSelector(self.session, self._selector & xpath, self._source)

    def __or__(self, xpath: str | XPathSelector) -> "AsyncXPathSelector":
        """组合 OR XPath 条件。"""

        return AsyncXPathSelector(self.session, self._selector | xpath, self._source)
