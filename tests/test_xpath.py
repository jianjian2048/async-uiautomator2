import asyncio

import pytest
from uiautomator2.exceptions import XPathElementNotFoundError

from async_uiautomator2.xpath import AsyncXPathSelector


XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node index="0" text="确定" resource-id="com.example:id/ok"
        class="android.widget.Button" package="com.example"
        content-desc="确认按钮" bounds="[10,20][110,70]" />
  <node index="1" text="取消" resource-id="com.example:id/cancel"
        class="android.widget.Button" package="com.example"
        content-desc="取消按钮" bounds="[120,20][220,70]" />
</hierarchy>
"""


class FakeSession:
    def __init__(self, source: str = XML) -> None:
        self.source = source
        self.dumps = 0
        self.clicks = []

    async def dump_hierarchy(self):
        self.dumps += 1
        return self.source

    async def click(self, x, y):
        self.clicks.append((x, y))
        return True


def test_xpath_shorthand_exists_info_text_and_click() -> None:
    async def run() -> None:
        session = FakeSession()
        selector = AsyncXPathSelector(session, "确定")

        assert await selector.exists is True
        assert (await selector.info)["text"] == "确定"
        assert await selector.get_text() == "确定"
        assert await selector.click() is True

        assert session.dumps >= 4
        assert session.clicks == [(60, 45)]

    asyncio.run(run())


def test_xpath_supports_resource_id_and_standard_xpath() -> None:
    async def run() -> None:
        session = FakeSession()

        by_id = await AsyncXPathSelector(session, "@com.example:id/ok").all()
        by_class = await AsyncXPathSelector(
            session, "//android.widget.Button"
        ).all()

        assert len(by_id) == 1
        assert by_id[0].attrib["resource-id"] == "com.example:id/ok"
        assert len(by_class) == 2

    asyncio.run(run())


def test_xpath_wait_and_get_timeout() -> None:
    async def run() -> None:
        selector = AsyncXPathSelector(FakeSession(), "不存在")

        assert await selector.wait(timeout=0, interval=0) is False
        with pytest.raises(XPathElementNotFoundError):
            await selector.get(timeout=0)

    asyncio.run(run())
