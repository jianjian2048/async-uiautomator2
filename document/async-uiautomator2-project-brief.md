# async-uiautomator2 项目说明

## 项目定位

本项目目标是实现一个面向 Android UI 自动化的异步 Python 客户端。它不是重写 Android
`uiautomator2` 服务端，也不是修改 `u2.jar`，而是在 Python 侧对 `uiautomator2` 的关键能力进行异步包装和整理。

核心判断：

- `u2.jar` 的 HTTP / JSON-RPC 协议本身很容易异步化。
- 真正需要认真设计的是 ADB 通道、`u2.jar` 生命周期、设备级并发、取消和超时语义。
- 第一阶段可以用 `asyncio.to_thread` 包装同步 `adbutils`，快速得到事件循环不阻塞的可用方案。
- 后续可以替换为真正的 async ADB backend，而不影响上层 API。

## 主要使用场景

### FastAPI / FastStream 常驻服务

服务进程长期连接一台或多台 Android 设备，在业务请求到来时执行自动化任务。

示例：

```python
from async_uiautomator2 import async_connect


devices = {}


async def startup():
    devices["emulator-5554"] = await async_connect("emulator-5554")


async def click_ok(serial: str):
    d = devices[serial]
    if await d.xpath("权限请求").exists:
        await d.xpath("允许").click()
```

### 单进程多设备控制

一个事件循环同时管理多台设备。设备之间可以并发执行，单设备内部根据操作类型控制串行或限流。

示例：

```python
import asyncio
from async_uiautomator2 import async_connect


async def run(serial: str):
    async with await async_connect(serial) as d:
        await d.app_start("com.example")
        await d.select(text="开始").click()


async def main():
    await asyncio.gather(run("device-a"), run("device-b"))


asyncio.run(main())
```

### 弹窗检测与后台 watcher

异步的价值不在于同一设备同时乱点，而在于一个任务执行时，可以并发进行低频弹窗检测、状态检查、超时控制。

示例：

```python
import asyncio


async def dialog_watcher(d):
    while True:
        if await d.xpath("允许").exists:
            await d.xpath("允许").click()
        await asyncio.sleep(0.5)
```

## 非目标

第一阶段不追求：

- 完整复制 `uiautomator2` 的所有 API。
- 修改或重写 `u2.jar`。
- 立即实现纯异步 ADB 协议。
- 让同一台设备上的所有 UI 操作都并发执行。
- 兼容 `d(text="OK")` 这种 `__call__(**kwargs)` 写法。

原因：

- 完整 API 复制会显著拖慢项目启动。
- Android UI 自动化本身多数操作依赖顺序和界面状态。
- `__call__(**kwargs)` 缺少类型提示，容易写错 selector 字段。

## 推荐项目名称与包结构

暂定包名：

```text
async_uiautomator2
```

推荐目录：

```text
async-uiautomator2/
  pyproject.toml
  README.md
  src/
    async_uiautomator2/
      __init__.py
      adb.py
      http.py
      server.py
      device.py
      selector.py
      xpath.py
      exceptions.py
      types.py
  tests/
    test_http.py
    test_server.py
    test_device.py
    test_selector.py
    test_xpath.py
```

## 最小可发布能力

第一版建议覆盖：

- `async_connect(serial=None)`
- `AsyncDevice`
  - `await d.info`
  - `await d.click(x, y)`
  - `await d.dump_hierarchy()`
  - `d.select(...)`
  - `d.select_raw(...)`
  - `d.xpath(...)`
  - `await d.shell(cmd)`
  - `await d.push(src, dst)`
  - `await d.app_start(package_name)`
  - `await d.close()`
- `AsyncUiObject`
  - `await obj.info`
  - `await obj.exists`
  - `await obj.wait()`
  - `await obj.click()`
  - `obj.child(...)`
  - `obj.sibling(...)`
- `AsyncXPathSelector`
  - `await selector.exists`
  - `await selector.info`
  - `await selector.all()`
  - `await selector.get()`
  - `await selector.wait()`
  - `await selector.click()`

## 技术路线

### 第一阶段：异步包装层

使用同步 `adbutils` 作为 backend，用 `asyncio.to_thread` 隔离阻塞调用。目标是快速验证 API、并发模型和服务集成体验。

### 第二阶段：backend 抽象稳定

抽象 `AsyncAdbDevice` / `AsyncConnection` 协议。上层 HTTP、server、device、selector、xpath 不依赖具体 ADB 实现。

### 第三阶段：替换纯异步 ADB

引入或自研 async ADB backend，实现真正的异步 transport、shell、sync push/pull。上层 API 不变。

## 成功标准

- 在 FastAPI / FastStream 事件循环中执行设备操作时，不直接阻塞事件循环。
- 多设备可以自然并发。
- 同一设备的服务启动、重启、安装等状态修改操作具备锁保护。
- 用户可以通过 typed selector 避免常见字段拼写错误。
- XPath 能满足弹窗检测和临时定位。
- 测试覆盖 HTTP、server 生命周期、selector、XPath、取消和并发重启。
