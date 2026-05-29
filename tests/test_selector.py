import asyncio

import pytest

from async_uiautomator2.selector import AsyncUiObject, SelectorQuery


class FakeServer:
    def __init__(self) -> None:
        self.calls = []

    async def jsonrpc_call(self, method, params=None, timeout=10):
        self.calls.append((method, params, timeout))
        if method == "objInfo":
            return {"bounds": {"left": 10, "top": 20, "right": 30, "bottom": 60}}
        if method in {"waitForExists", "waitUntilGone"}:
            return True
        return None


class FakeSession:
    def __init__(self) -> None:
        self.server = FakeServer()
        self.clicks = []

    async def click(self, x, y):
        self.clicks.append((x, y))
        return True


def test_selector_query_maps_snake_case_and_preserves_false() -> None:
    query = SelectorQuery(
        text_contains="确定",
        resource_id="com.example:id/ok",
        long_clickable=False,
    )

    assert query.to_kwargs() == {
        "textContains": "确定",
        "resourceId": "com.example:id/ok",
        "longClickable": False,
    }


def test_selector_query_rejects_unknown_fields() -> None:
    with pytest.raises(TypeError):
        SelectorQuery(resourceId="bad")


def test_async_ui_object_info_exists_wait_and_click() -> None:
    async def run() -> None:
        session = FakeSession()
        obj = AsyncUiObject(session, SelectorQuery(text="确定").to_selector())

        assert await obj.info == {
            "bounds": {"left": 10, "top": 20, "right": 30, "bottom": 60}
        }
        assert await obj.exists is True
        assert await obj.wait(timeout=1) is True
        assert await obj.wait(exists=False, timeout=1) is True
        assert await obj.click(timeout=1) is True

        methods = [call[0] for call in session.server.calls]
        assert methods == [
            "objInfo",
            "waitForExists",
            "waitForExists",
            "waitUntilGone",
            "waitForExists",
            "objInfo",
        ]
        assert session.clicks == [(20.0, 40.0)]

    asyncio.run(run())


def test_child_and_sibling_build_selector_chain() -> None:
    base = AsyncUiObject(FakeSession(), SelectorQuery(resource_id="list").to_selector())

    child = base.child(text="设置")
    sibling = base.sibling(description="更多")

    child_data = dict(child.selector)
    sibling_data = dict(sibling.selector)
    assert child_data["childOrSibling"] == ["child"]
    assert child_data["childOrSiblingSelector"][0]["text"] == "设置"
    assert sibling_data["childOrSibling"] == ["sibling"]
    assert sibling_data["childOrSiblingSelector"][0]["description"] == "更多"
