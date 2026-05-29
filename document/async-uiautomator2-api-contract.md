# async-uiautomator2 API 契约

本文档定义第一版公开 API。AI Agent 开发时应优先满足这里的接口和行为，再扩展其他能力。

## 连接设备

```python
from async_uiautomator2 import async_connect


async with await async_connect("emulator-5554") as d:
    print(await d.info)
```

签名：

```python
async def async_connect(
    serial: str | None = None,
    *,
    device_factory: Callable[[str | None], AsyncAdbDevice] | None = None,
    jar_path: str | Path | None = None,
    setup_jar: bool = True,
) -> AsyncDevice:
    ...
```

行为：

- 默认使用线程包装的 `adbutils` backend。
- 创建 server 并确保 `u2.jar` ready。
- 返回 `AsyncDevice`。
- 测试可以传入 `device_factory` 注入 fake backend。

## AsyncDevice

### 设备信息

```python
info = await d.info
```

行为：

- 调用 JSON-RPC `deviceInfo`。
- 返回设备端原始 dict。

### 坐标点击

```python
await d.click(100, 200)
```

签名：

```python
async def click(self, x: int | float, y: int | float) -> Any:
    ...
```

行为：

- 调用 JSON-RPC `click`。
- 不做坐标合法性裁剪。

### dump hierarchy

```python
xml = await d.dump_hierarchy()
```

签名：

```python
async def dump_hierarchy(
    self,
    compressed: bool = False,
    pretty: bool = False,
    max_depth: int = 50,
) -> str:
    ...
```

行为：

- 调用 JSON-RPC `dumpWindowHierarchy(compressed, max_depth)`。
- `pretty=True` 时可以使用 `lxml` 格式化 XML。

### shell

```python
output = await d.shell("getprop ro.product.model")
```

签名：

```python
async def shell(self, cmd: str | list[str], timeout: float = 60) -> str:
    ...
```

行为：

- 第一阶段通过 `asyncio.to_thread` 调用同步 ADB。
- 超时语义取决于 backend。

### push

```python
await d.push("local.txt", "/data/local/tmp/local.txt")
```

签名：

```python
async def push(self, src: str | Path, dst: str, mode: int = 0o644) -> None:
    ...
```

行为：

- 第一阶段通过同步 `adbutils.sync.push` 的线程包装实现。

### app_start

```python
await d.app_start("com.example")
```

签名：

```python
async def app_start(self, package_name: str) -> Any:
    ...
```

## Typed Selector

推荐写法：

```python
ok = d.select(text="确定", resource_id="com.example:id/ok", clickable=True)
if await ok.exists:
    await ok.click()
```

禁止作为主线实现：

```python
d(text="确定")
```

原因：

- `__call__(**kwargs)` 无法给 IDE 提供可靠提示。
- 字段拼写错误只能运行时发现。

### `select()` 签名

`select()` 必须使用 keyword-only 参数：

```python
def select(
    self,
    *,
    text: str | None = None,
    text_contains: str | None = None,
    text_matches: str | None = None,
    text_starts_with: str | None = None,
    class_name: str | None = None,
    class_name_matches: str | None = None,
    description: str | None = None,
    description_contains: str | None = None,
    description_matches: str | None = None,
    description_starts_with: str | None = None,
    resource_id: str | None = None,
    resource_id_matches: str | None = None,
    package_name: str | None = None,
    package_name_matches: str | None = None,
    index: int | None = None,
    instance: int | None = None,
    checkable: bool | None = None,
    checked: bool | None = None,
    clickable: bool | None = None,
    long_clickable: bool | None = None,
    scrollable: bool | None = None,
    enabled: bool | None = None,
    focusable: bool | None = None,
    focused: bool | None = None,
    selected: bool | None = None,
) -> AsyncUiObject:
    ...
```

字段转换：

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

### `select_raw()`

低层逃生口：

```python
await d.select_raw(textContains="确定").click()
```

行为：

- 直接构造 `uiautomator2._selector.Selector(**kwargs)`。
- 用于兼容原始字段和临时实验。
- 新代码优先使用 `select()`。

## AsyncUiObject

### `info`

```python
info = await obj.info
```

行为：

- 调用 JSON-RPC `objInfo(selector)`。

### `exists`

```python
exists = await obj.exists
```

行为：

- 调用 JSON-RPC `waitForExists(selector, 0)`。
- 返回 bool。

### `wait`

```python
await obj.wait(timeout=10)
await obj.wait(exists=False, timeout=10)
```

行为：

- `exists=True` 调用 `waitForExists`。
- `exists=False` 调用 `waitUntilGone`。
- timeout 单位为秒，传给设备端时转换为毫秒。

### `click`

```python
await obj.click(timeout=10)
```

行为：

1. 等待元素存在。
2. 调用 `objInfo` 获取 bounds。
3. 计算中心点。
4. 调用 `d.click(x, y)`。

### child / sibling

```python
item = d.select(resource_id="android:id/list").child(text="设置")
peer = item.sibling(description="更多")
```

行为：

- 返回新的 `AsyncUiObject`。
- 内部使用 uiautomator2 原生 selector 的 `child()` / `sibling()` 链。

## XPath

XPath 是基于 XML dump 的本地匹配能力。

```python
if await d.xpath("权限请求").exists:
    await d.xpath("允许").click()
```

支持简写：

| 写法 | 含义 |
| --- | --- |
| `"确定"` | 匹配 text、content-desc 或 resource-id 等于该值 |
| `"@com.example:id/ok"` | 匹配 resource-id |
| `"%确定%"` | text 或 content-desc 包含该值 |
| `"确定%"` | text 或 content-desc 前缀匹配 |
| `"%确定"` | text 或 content-desc 后缀匹配 |
| `"//android.widget.Button"` | 标准 XPath |

### AsyncXPathSelector

必须支持：

```python
await selector.exists
await selector.info
await selector.all()
await selector.get()
await selector.wait(timeout=10)
await selector.wait_gone(timeout=10)
await selector.get_text()
await selector.click()
await selector.click_exists()
selector.child("...")
```

行为：

- 每次未传入固定 source 时，调用 `dump_hierarchy()` 获取当前 XML。
- `get()` 超时后抛出 `XPathElementNotFoundError`。
- `click()` 点击第一个匹配元素中心点。

## 资源释放

推荐：

```python
async with await async_connect(serial) as d:
    ...
```

或者：

```python
d = await async_connect(serial)
try:
    ...
finally:
    await d.close()
```

`close()` 行为：

- 停止当前客户端持有的 `u2.jar` stream。
- 不负责清理全局 ADB server。

## 兼容性策略

第一版依赖：

- Python 3.12+
- `uiautomator2>=3.5.0`
- `adbutils`
- `pytest`

建议使用 `uv` 管理项目：

```shell
uv init --package async-uiautomator2
uv add uiautomator2
uv add --dev pytest
```
