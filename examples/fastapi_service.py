"""FastAPI 常驻服务集成示例。"""

from __future__ import annotations

import os

from fastapi import FastAPI

from async_uiautomator2 import AsyncDevice, async_connect

app = FastAPI()
devices: dict[str, AsyncDevice] = {}


@app.on_event("startup")
async def startup() -> None:
    """服务启动时连接设备。"""

    serial = os.environ.get("ANDROID_SERIAL")
    if serial is None:
        return
    devices[serial] = await async_connect(serial)


@app.on_event("shutdown")
async def shutdown() -> None:
    """服务关闭时释放设备连接。"""

    for device in devices.values():
        await device.close()


@app.post("/devices/{serial}/click-ok")
async def click_ok(serial: str) -> dict[str, bool]:
    """点击常见确认按钮。"""

    device = devices[serial]
    clicked = await device.xpath("确定").click_exists(timeout=1)
    return {"clicked": clicked}
