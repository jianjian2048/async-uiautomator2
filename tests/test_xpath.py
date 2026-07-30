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
        self.long_clicks = []
        self.clear_count = 0
        self.keys = []
        self.screenshot_image = FakeImage()

    async def dump_hierarchy(self):
        self.dumps += 1
        return self.source

    async def click(self, x, y):
        self.clicks.append((x, y))
        return True

    async def long_click(self, x, y, duration=0.5):
        self.long_clicks.append((x, y, duration))
        return True

    async def clear_text(self):
        self.clear_count += 1
        return True

    async def send_keys(self, text):
        self.keys.append(text)
        return True

    async def screenshot(self):
        return self.screenshot_image


class FakeImage:
    def __init__(self) -> None:
        self.crops = []

    def crop(self, bounds):
        self.crops.append(bounds)
        return ("cropped", bounds)


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


def test_xpath_element_and_selector_geometry() -> None:
    async def run() -> None:
        selector = AsyncXPathSelector(FakeSession(), "确定")
        element = await selector.get(timeout=0)

        assert element.bounds == (10, 20, 110, 70)
        assert element.rect == (10, 20, 100, 50)
        assert element.center() == (60, 45)
        assert element.offset() == (10, 20)
        assert element.offset(1, 1) == (110, 70)
        assert element.parent().get_xpath() == "/hierarchy"
        assert element.parent("//missing") is None

        assert await selector.bounds(timeout=0) == (10, 20, 110, 70)
        assert await selector.rect(timeout=0) == (10, 20, 100, 50)
        assert await selector.center(timeout=0) == (60, 45)

    asyncio.run(run())


def test_xpath_common_interactions() -> None:
    async def run() -> None:
        long_click_session = FakeSession()
        long_click_selector = AsyncXPathSelector(long_click_session, "确定")
        assert (
            await long_click_selector.long_click(duration=0.75, timeout=0) is True
        )
        assert long_click_session.long_clicks == [(60, 45, 0.75)]

        text_session = FakeSession()
        text_selector = AsyncXPathSelector(text_session, "确定")
        assert await text_selector.set_text("hello", timeout=0) is None
        assert text_session.clicks == [(60, 45)]
        assert text_session.clear_count == 1
        assert text_session.keys == ["hello"]

        screenshot_session = FakeSession()
        screenshot_selector = AsyncXPathSelector(screenshot_session, "确定")
        assert await screenshot_selector.screenshot(timeout=0) == (
            "cropped",
            (10, 20, 110, 70),
        )
        assert screenshot_session.screenshot_image.crops == [(10, 20, 110, 70)]

    asyncio.run(run())
