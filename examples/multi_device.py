"""单进程多设备并发示例。"""

from __future__ import annotations

import asyncio
import os

from async_uiautomator2 import async_connect


async def run(serial: str) -> None:
    """在一台设备上执行自动化任务。"""

    async with await async_connect(serial) as d:
        await d.app_start("com.example")
        await d.select(text="开始").click(timeout=5)


async def main() -> None:
    """从环境变量读取多个设备并发执行。"""

    serials = [item for item in os.environ.get("ANDROID_SERIALS", "").split(",") if item]
    await asyncio.gather(*(run(serial) for serial in serials))


if __name__ == "__main__":
    asyncio.run(main())
