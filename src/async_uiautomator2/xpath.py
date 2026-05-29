"""基于 XML dump 的异步 XPath 查询。"""

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
        element (XMLElement): `uiautomator2.xpath` 解析得到的元素。
    """

    def __init__(self, session: Any, element: XMLElement) -> None:
        self.session = session
        self._element = element

    @property
    def text(self) -> str | None:
        """元素 `text` 属性。"""

        return self._element.text

    @property
    def attrib(self) -> dict[str, str]:
        """元素 XML 属性。"""

        return self._element.attrib

    @property
    def info(self) -> dict[str, Any]:
        """与同步版 XPath 兼容的元素信息。"""

        return self._element.info

    @property
    def bounds(self) -> BoundsTuple:
        """元素 bounds，格式为 `(left, top, right, bottom)`。"""

        return self._element.bounds

    def center(self) -> PointTuple:
        """计算元素中心点。"""

        return self._element.center()

    def get_xpath(self, strip_index: bool = False) -> str:
        """获取元素在 XML 树中的完整 XPath。"""

        return self._element.get_xpath(strip_index=strip_index)

    async def click(self) -> Any:
        """点击元素中心点。"""

        x, y = self.center()
        return await self.session.click(x, y)


class AsyncXPathSelector:
    """异步 XPath 选择器。"""

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
        """立即检查 XPath 是否能匹配到元素的协程。"""

        return self.exists_now()

    @property
    def info(self):
        """获取第一个匹配元素信息的协程。"""

        return self.get_info()

    async def get_page_source(self) -> PageSource:
        """获取当前页面 XML 源。"""

        if self._source is not None:
            return self._source
        return PageSource.parse(await self.session.dump_hierarchy())

    async def all(self, source: str | PageSource | None = None) -> list[AsyncXPathElement]:
        """查找所有匹配元素。"""

        page_source = PageSource.parse(source) if source else await self.get_page_source()
        self._last_source = page_source
        return [
            AsyncXPathElement(self.session, element)
            for element in self._selector.all(page_source)
        ]

    async def exists_now(self) -> bool:
        """立即检查是否存在匹配元素。"""

        return bool(await self.all())

    async def wait(self, timeout: float | None = None, interval: float = 0.2) -> bool:
        """等待 XPath 匹配到元素。"""

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
        """等待 XPath 不再匹配元素。"""

        deadline = time.monotonic() + (20.0 if timeout is None else timeout)
        while True:
            if not await self.exists_now():
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(interval)

    async def get(self, timeout: float | None = None) -> AsyncXPathElement:
        """获取第一个匹配元素。"""

        if not await self.wait(timeout=timeout):
            raise XPathElementNotFoundError(self)
        matches = await self.all(self._last_source)
        return matches[0]

    async def get_info(self, timeout: float | None = None) -> dict[str, Any]:
        """获取第一个匹配元素的信息。"""

        return (await self.get(timeout=timeout)).info

    async def get_text(self, timeout: float | None = None) -> str | None:
        """获取第一个匹配元素的文本。"""

        return (await self.get(timeout=timeout)).text

    async def click(self, timeout: float | None = None) -> Any:
        """点击第一个匹配元素。"""

        return await (await self.get(timeout=timeout)).click()

    async def click_exists(self, timeout: float | None = None) -> bool:
        """元素存在时点击。"""

        try:
            await self.click(timeout=timeout)
            return True
        except XPathElementNotFoundError:
            return False

    def child(self, xpath: str) -> "AsyncXPathSelector":
        """追加子级 XPath。"""

        return AsyncXPathSelector(self.session, self._selector.child(xpath), self._source)

    def __and__(self, xpath: str | XPathSelector) -> "AsyncXPathSelector":
        """组合 AND XPath 条件。"""

        return AsyncXPathSelector(self.session, self._selector & xpath, self._source)

    def __or__(self, xpath: str | XPathSelector) -> "AsyncXPathSelector":
        """组合 OR XPath 条件。"""

        return AsyncXPathSelector(self.session, self._selector | xpath, self._source)
