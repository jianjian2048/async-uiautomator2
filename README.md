# async-uiautomator2

`async-uiautomator2` 是面向 Android UI 自动化的异步 Python 客户端。它不修改
`u2.jar`，也不重写 Android 端服务，而是在 Python 侧把 `uiautomator2` 的关键能力整理成
async API。

第一版重点是：

- 使用 ADB socket 直连设备端 `u2.jar:9008`，不依赖本地 `adb forward`。
- 使用 `asyncio.to_thread` 包装同步 `adbutils`，避免直接阻塞事件循环。
- 提供 typed selector：`d.select(text="确定")`，不实现 `d(text="确定")`。
- 提供基于 XML dump 的异步 XPath，用于弹窗检测和临时定位。
- 用锁保护 `u2.jar` 启动、停止和自动重启。

## u2.jar 获取方式

默认不依赖仓库里的 `experiment/` 目录，也不要求用户手动复制 jar。启动时会按顺序解析：

1. `async_connect(..., jar_path="...")` 显式传入的路径。
2. 已安装包中的 `assets/u2.jar` 资源，例如 `uiautomator2` 自带的资源。
3. 本机缓存目录中的 `u2-<version>.jar`。
4. 从 `uiautomator2/assets/sync.sh` 使用的 jar 源自动下载到缓存：
   `https://public.uiauto.devsleep.com/u2jar/0.2.2/u2.jar`。

可用环境变量覆盖缓存目录：

```shell
$env:ASYNC_UIAUTOMATOR2_CACHE_DIR="D:\cache\async-uiautomator2"
```

## 安装

```shell
uv add async-uiautomator2
```

本仓库开发环境：

```shell
uv sync
uv run pytest -q
```

## 基础用法

```python
import asyncio
from async_uiautomator2 import async_connect


async def main():
    async with await async_connect("emulator-5554") as d:
        print(await d.info)
        await d.click(100, 200)
        print(await d.dump_hierarchy())


asyncio.run(main())
```

如果不使用 `async with`，脚本结束前需要显式关闭：

```python
d = await async_connect("emulator-5554")
try:
    await d.click(100, 200)
finally:
    await d.close()
```

## Typed Selector

推荐使用显式字段：

```python
ok = d.select(
    text="确定",
    resource_id="com.example:id/ok",
    clickable=True,
)

if await ok.exists:
    await ok.click()
```

常用字段会从 Python 风格转换为 `uiautomator2` 原始字段：

| Python 字段 | 原始字段 |
| --- | --- |
| `text_contains` | `textContains` |
| `text_starts_with` | `textStartsWith` |
| `class_name` | `className` |
| `resource_id` | `resourceId` |
| `package_name` | `packageName` |
| `long_clickable` | `longClickable` |

需要临时使用原始字段时，可以走逃生口：

```python
await d.select_raw(textContains="确定").click()
```

## XPath

XPath 会先异步调用 `dumpWindowHierarchy` 获取 XML，再在 Python 侧匹配：

```python
if await d.xpath("权限请求").exists:
    await d.xpath("允许").click()
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

## FastAPI 常驻服务

```python
from async_uiautomator2 import async_connect

devices = {}


async def startup():
    devices["emulator-5554"] = await async_connect("emulator-5554")


async def click_ok(serial: str):
    d = devices[serial]
    if await d.xpath("允许").exists:
        await d.xpath("允许").click()
```

## 并发规则

- 多台设备可以用 `asyncio.gather()` 自然并发。
- 同一设备上的启动、停止、重启由 server 层锁保护。
- UI 操作仍应按业务流程顺序执行，不建议在同一台设备上并发乱点。
- 长时间 shell/push 通过线程隔离阻塞，但第一阶段不保证取消后设备端命令立即回滚。

## 第一阶段限制

- 不完整复制 `uiautomator2` 的所有 API。
- 不修改或重写 `u2.jar`。
- 不实现纯异步 ADB 协议。
- 不实现 `d(text="OK")` 或 `d(**kwargs)`。

## 开发验证

```shell
uv run pytest -q
uv run python -m compileall -q src/async_uiautomator2
```
