# async-uiautomator2

面向 Android UI 自动化的异步 Python 客户端。

`async-uiautomator2` 不修改 `u2.jar`，也不重写 Android 端服务。它复用
[`uiautomator2`](https://github.com/openatx/uiautomator2) 的设备端能力，在 Python
侧提供 async API、ADB socket HTTP/JSON-RPC 客户端、`u2.jar` 生命周期管理、typed selector
和 XPath 查询。

## 特性

- **异步 API**：公开入口使用 `async` / `await`，适合 FastAPI、FastStream、任务队列 worker
  和长期运行的自动化服务。
- **不阻塞事件循环**：第一阶段通过 `asyncio.to_thread()` 包装同步 `adbutils` 调用，避免把
  ADB shell、push、socket I/O 直接跑在事件循环主路径上。参考 Python 官方文档：
  [`asyncio.to_thread`](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread)。
- **ADB socket 直连 u2.jar**：每次 HTTP 请求通过 ADB socket 连接设备端 `u2.jar:9008`，
  手写最小 HTTP/1.1 请求，不依赖本地 `adb forward` 端口。
- **JSON-RPC 封装**：提供 `deviceInfo`、`click`、`dumpWindowHierarchy`、`objInfo`、
  `waitForExists` 等常用 JSON-RPC 调用，并把常见错误映射到 `uiautomator2.exceptions`。
- **u2.jar 生命周期管理**：启动、ready 检查、停止和异常后的自动重启集中在 server 层；
  并发重启使用锁和 generation 控制，避免多个协程同时拉起服务。
- **typed selector**：使用 `d.select(text="确定", resource_id="...")` 代替
  `d(text="确定")`，让 IDE 和类型检查器更早发现 selector 字段拼写错误。
- **本地 XPath 匹配**：通过 `dumpWindowHierarchy` 获取 XML，再复用 `uiautomator2.xpath`
  的表达式能力做本地匹配，适合弹窗检测、临时定位和低频 watcher。
- **多设备并发**：不同设备可以在同一事件循环中自然并发；单设备内部仍建议按 UI 流程顺序执行。
- **可测试 backend**：`async_connect(..., device_factory=...)` 支持注入 fake ADB backend，
  单元测试不需要真实 Android 设备。

## 安装

```shell
uv add async-uiautomator2
```

依赖：

- Python 3.12+
- `uiautomator2>=3.5.2`
- `adbutils`，由 `uiautomator2` 间接提供

使用前请确保设备已连接并授权：

```shell
adb devices
```

## 快速开始

```python
import asyncio
from async_uiautomator2 import async_connect


async def main():
    async with await async_connect("emulator-5554") as d:
        print(await d.info)
        await d.app_start("com.example")
        await d.click(100, 200)


asyncio.run(main())
```

不使用 `async with` 时，需要显式关闭当前客户端持有的 `u2.jar` stream：

```python
d = await async_connect("emulator-5554")
try:
    await d.click(100, 200)
finally:
    await d.close()
```

## 设备 API

```python
info = await d.info
xml = await d.dump_hierarchy()
output = await d.shell("getprop ro.product.model")

await d.click(100, 200)
await d.push("local.txt", "/data/local/tmp/local.txt")
await d.app_start("com.example")
```

`dump_hierarchy()` 默认调用：

```python
await d.dump_hierarchy(compressed=False, pretty=False, max_depth=50)
```

`pretty=True` 会使用 `lxml` 格式化 XML。

## Typed Selector

推荐写法：

```python
ok = d.select(
    text="确定",
    resource_id="com.example:id/ok",
    clickable=True,
)

if await ok.exists:
    await ok.click()
```

支持的常用能力：

```python
await obj.info
await obj.exists
await obj.wait(timeout=10)
await obj.wait(exists=False, timeout=10)
await obj.click(timeout=10)

child = obj.child(text="设置")
peer = obj.sibling(description="更多")
```

字段会从 Python 风格转换为 `uiautomator2` 原始字段：

| Python 字段 | uiautomator2 字段 |
| --- | --- |
| `text_contains` | `textContains` |
| `text_matches` | `textMatches` |
| `text_starts_with` | `textStartsWith` |
| `class_name` | `className` |
| `class_name_matches` | `classNameMatches` |
| `description_contains` | `descriptionContains` |
| `description_matches` | `descriptionMatches` |
| `description_starts_with` | `descriptionStartsWith` |
| `resource_id` | `resourceId` |
| `resource_id_matches` | `resourceIdMatches` |
| `package_name` | `packageName` |
| `package_name_matches` | `packageNameMatches` |
| `long_clickable` | `longClickable` |

需要临时使用原始字段时，可以走低层逃生口：

```python
await d.select_raw(textContains="确定").click()
```

本项目刻意不实现 `d(text="OK")` / `d(**kwargs)`，避免把无类型提示的 selector 入口作为主线 API。

## XPath

XPath 基于 XML dump 做本地匹配：

```python
if await d.xpath("权限请求").exists:
    await d.xpath("允许").click()
```

常用方法：

```python
selector = d.xpath("@com.example:id/ok")

await selector.exists
await selector.info
await selector.all()
await selector.get()
await selector.wait(timeout=10)
await selector.wait_gone(timeout=10)
await selector.get_text()
await selector.click()
await selector.click_exists()
selector.child("//android.widget.TextView")
```

支持 `uiautomator2.xpath` 的常用简写：

| 写法 | 含义 |
| --- | --- |
| `"确定"` | 匹配 text、content-desc 或 resource-id 等于该值 |
| `"@com.example:id/ok"` | 匹配 resource-id |
| `"%确定%"` | text 或 content-desc 包含该值 |
| `"确定%"` | text 或 content-desc 前缀匹配 |
| `"%确定"` | text 或 content-desc 后缀匹配 |
| `"//android.widget.Button"` | 标准 XPath |

## u2.jar 获取方式

默认不依赖 `experiment/` 目录，也不把 `u2.jar` 二进制文件打进 wheel。启动时按顺序解析：

1. `async_connect(..., jar_path="...")` 显式传入的路径。
2. 已安装包中的 `assets/u2.jar` 资源，例如 `uiautomator2` 自带资源。
3. 本机缓存目录中的 `u2-<version>.jar`。
4. 从 `uiautomator2/assets/sync.sh` 使用的 jar 源下载到缓存：
   `https://public.uiauto.devsleep.com/u2jar/0.2.2/u2.jar`。

可用环境变量覆盖缓存目录：

```powershell
$env:ASYNC_UIAUTOMATOR2_CACHE_DIR="D:\cache\async-uiautomator2"
```

也可以显式传入本地 jar：

```python
d = await async_connect("emulator-5554", jar_path="D:/tools/u2.jar")
```

## 常驻服务示例

```python
from async_uiautomator2 import async_connect

devices = {}


async def startup():
    devices["emulator-5554"] = await async_connect("emulator-5554")


async def click_permission(serial: str):
    d = devices[serial]
    if await d.xpath("权限请求").exists:
        await d.xpath("允许").click()


async def shutdown():
    for d in devices.values():
        await d.close()
```

## 并发语义

- 多设备之间可以并发，例如 `await asyncio.gather(run("device-a"), run("device-b"))`。
- 同一设备上的服务启动、停止、重启由锁保护。
- 同一设备的 UI 操作仍应按界面状态顺序执行；并发 watcher 适合低频弹窗检测，不适合同时乱点。
- shell、push 等阻塞 ADB 调用已隔离到线程；第一阶段不保证取消后设备端命令立即停止。

## 当前范围

已覆盖：

- `async_connect()`
- `AsyncDevice`
- `AsyncUiObject`
- `AsyncXPathSelector`
- ADB socket HTTP / JSON-RPC
- `u2.jar` setup、ready、stop、restart
- fake backend 单元测试

暂不覆盖：

- 完整复刻 `uiautomator2` 全量 API
- 修改或重写 Android 端 `u2.jar`
- 纯异步 ADB transport
- `d(text="OK")` / `d(**kwargs)` 兼容入口
- 高频复杂 UI 轮询优化

## 开发

```shell
uv sync
uv run pytest -q
uv run python -m compileall -q src/async_uiautomator2
```

## 引用

- [`openatx/uiautomator2`](https://github.com/openatx/uiautomator2)：上游 Python Android 自动化库。本项目复用其设备端协议、异常类型、selector 和 XPath 相关能力。
- [`openatx/android-uiautomator-server`](https://github.com/openatx/android-uiautomator-server)：`u2.jar` 对应的 Android 端服务项目。
- [`openatx/adbutils`](https://github.com/openatx/adbutils)：第一阶段 ADB backend 的同步基础库。
- [`uiautomator2/assets/sync.sh`](https://github.com/openatx/uiautomator2/blob/master/uiautomator2/assets/sync.sh)：`u2.jar` 版本和下载源参考。
- [`asyncio.to_thread`](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread)：Python 官方对线程隔离阻塞调用的支持。
- [`uv`](https://github.com/astral-sh/uv)：本项目使用的包管理、构建和发布工具。
