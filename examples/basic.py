"""基础连接和常用操作示例。"""

from __future__ import annotations

import asyncio
import os

from async_uiautomator2 import async_connect


async def main() -> None:
    """连接设备并执行一次基础自动化操作。"""

    serial = os.environ.get("ANDROID_SERIAL")
    async with await async_connect(serial) as d:
        print(await d.info)
        await d.click(100, 200)
        if await d.select(text="确定").exists:
            await d.select(text="确定").click()


if __name__ == "__main__":
    asyncio.run(main())
