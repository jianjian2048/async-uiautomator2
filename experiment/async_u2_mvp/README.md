# async_u2_mvp

这是 `document/uiautomator2-async-feasibility.md` 中“最小可行原型”的独立实现，不放在 `uiautomator2/` 源码目录下。

## 已覆盖内容

- `AsyncAdbHTTPClient`
  - 通过 `await dev.create_connection(adbutils.Network.TCP, 9008)` 建立 ADB socket。
  - 手写 `GET /ping`。
  - 手写 `POST /jsonrpc/0`。
  - 支持 timeout、关闭连接、JSON-RPC 错误映射。

- `AsyncBasicUiautomatorServer`
  - 异步 `_setup_jar()`。
  - 异步 `_check_alive()`。
  - 异步 `launch_uiautomator()`。
  - 异步 `_wait_ready()`。
  - 对并发 RPC 失败使用 restart lock 和 generation，避免重复重启。

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

- `SelectorQuery` / `AsyncUiObject`
  - 用显式的 snake_case 参数替代 `uiautomator2` 原有的 `d(**kwargs)` 入口。
  - 支持 `text`、`text_contains`、`resource_id`、`class_name`、`clickable` 等常用选择器字段。
  - `await obj.info`
  - `await obj.exists`
  - `await obj.wait()`
  - `await obj.click()`
  - `obj.child(...)` / `obj.sibling(...)`

- `AsyncXPathSelector` / `AsyncXPathElement`
  - 通过 `dumpWindowHierarchy` 异步获取 XML。
  - 复用 `uiautomator2.xpath` 的 XPath 简写规则和 XML 匹配逻辑。
  - `await d.xpath("确定").exists`
  - `await d.xpath("@com.example:id/ok").info`
  - `await d.xpath("//android.widget.Button").all()`
  - `await d.xpath("确定").click()`

- `async_connect(serial)`
  - 默认使用 `ThreadedAdbDevice`，通过 `asyncio.to_thread` 隔离同步 `adbutils`，作为第一阶段真实设备后端。
  - 测试中可注入 fake async ADB device。

## 使用示例

```python
import asyncio
from async_u2_mvp import async_connect


async def main():
    async with await async_connect("ANDROID_SERIAL") as d:
        info = await d.info
        print(info)
        await d.click(100, 200)
        await d.select(text="确定", resource_id="com.example:id/ok").click()
        await d.xpath("@com.example:id/ok").click()
        output = await d.shell("getprop ro.product.model")
        print(output)


asyncio.run(main())
```

如果不用 `async with`，脚本结束前请显式调用：

```python
await d.close()
```

`close()` 会停止当前客户端启动的 `u2.jar` stream 连接。原型内部的 stream reader 使用 daemon thread，不会阻塞 `asyncio.run()` 退出，但显式关闭能更快释放 ADB 连接。

## 元素选择器

本原型不实现 `d(text="OK")` 这种 `__call__(**kwargs)` 写法。推荐使用显式入口：

```python
ok = d.select(
    text="确定",
    resource_id="com.example:id/ok",
    class_name="android.widget.Button",
    clickable=True,
)

if await ok.exists:
    await ok.click()
```

字段使用 Python 风格的 snake_case，内部会转换成 `u2.jar` 需要的 selector 字段：

| typed 字段 | 原始 uiautomator2 字段 |
| --- | --- |
| `text_contains` | `textContains` |
| `text_starts_with` | `textStartsWith` |
| `class_name` | `className` |
| `resource_id` | `resourceId` |
| `resource_id_matches` | `resourceIdMatches` |
| `package_name` | `packageName` |
| `long_clickable` | `longClickable` |

如果需要临时使用原始字段，可以走低层逃生口：

```python
await d.select_raw(textContains="确定").click()
```

新代码优先使用 `select(...)`，这样 IDE 和类型检查器能更早发现拼写错误。

## XPath

XPath 走的是另一条路径：先异步调用 `dumpWindowHierarchy` 拿到当前界面 XML，再在 Python 侧做 XPath 匹配。
这适合弹窗检测、跨控件文本匹配和临时定位；如果要高频点击固定控件，优先考虑 `select(...)`。

```python
dialog = d.xpath("权限请求")
if await dialog.exists:
    await d.xpath("允许").click()
```

支持 `uiautomator2.xpath` 原有简写：

| 写法 | 含义 |
| --- | --- |
| `"确定"` | 匹配 `text`、`content-desc` 或 `resource-id` 等于该值 |
| `"@com.example:id/ok"` | 匹配 `resource-id` |
| `"%确定%"` | 匹配 `text` 或 `content-desc` 包含该值 |
| `"确定%"` | 匹配前缀 |
| `"%确定"` | 匹配后缀 |
| `"//android.widget.Button"` | 标准 XPath |

当前 MVP 已覆盖：

- `await selector.exists`
- `await selector.info`
- `await selector.all()`
- `await selector.get()`
- `await selector.wait()`
- `await selector.wait_gone()`
- `await selector.get_text()`
- `await selector.click()`
- `await selector.click_exists()`
- `selector.child(...)`

## 测试

```shell
uv run pytest tests/test_async_u2_mvp.py -q
```
