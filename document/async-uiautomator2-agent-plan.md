# async-uiautomator2 AI Agent 开发计划

本文档面向执行开发的 AI Agent。Agent 应按阶段推进，每个阶段都必须有测试和验收。

## 开发纪律

### 基本要求

- 使用简体中文注释和文档。
- 使用 `uv` 运行命令。
- 新功能先写测试，再实现。
- 不要修改 vendored `uiautomator2` 源码。
- 不要实现 `d(**kwargs)` 或 `d(text="OK")`。
- 不要在第一阶段追求完整 API 复制。
- 每个公开类和公开方法需要中文 Google 风格 docstring。

### 推荐命令

```shell
uv run pytest -q
uv run python -m compileall -q src/async_uiautomator2
```

### 完成标准

每个阶段完成时必须满足：

- 单元测试通过。
- 公开 API 有文档。
- README 示例可以运行或至少能被测试覆盖。
- 没有把阻塞 ADB 调用直接暴露到事件循环主路径中。

## 阶段 0：项目初始化

### 目标

创建独立 Python 包。

### 任务

1. 初始化项目：

```shell
uv init --package async-uiautomator2
uv add uiautomator2
uv add --dev pytest
```

2. 创建目录：

```text
src/async_uiautomator2/
tests/
```

3. 配置 `pyproject.toml`：

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

4. 创建空导出：

```python
"""异步 Android UI 自动化客户端。"""
```

### 验收

```shell
uv run pytest -q
```

结果应为无测试或基础导入测试通过。

## 阶段 1：ADB backend 协议与线程包装

### 目标

先用同步 `adbutils` 实现事件循环不阻塞的 backend。

### 文件

- `src/async_uiautomator2/adb.py`
- `tests/test_adb.py`

### 实现内容

- `AsyncConnection`
- `AsyncAdbDevice`
- `AsyncSocketConnection`
- `ThreadedAdbProcess`
- `ThreadedAdbDevice`

### 关键要求

- `AsyncSocketConnection.sendall/recv/close` 使用 `asyncio.to_thread`。
- `ThreadedAdbDevice.shell/push/app_start/create_connection` 使用 `asyncio.to_thread`。
- `ThreadedAdbProcess` 不要创建阻塞事件循环退出的 asyncio task。
- stream reader 可以使用 daemon thread。

### 测试

必须覆盖：

- `ThreadedAdbProcess` 不增加 `asyncio.all_tasks()`。
- `kill()` 会关闭底层连接。
- 可用 fake socket 测试 `sendall/recv/close`。

## 阶段 2：ADB socket HTTP / JSON-RPC

### 目标

实现不依赖 `adb forward` 的异步 HTTP 客户端。

### 文件

- `src/async_uiautomator2/http.py`
- `tests/test_http.py`

### 实现内容

- `HTTPResponse`
- `AsyncAdbHTTPClient`
  - `ping()`
  - `jsonrpc()`
  - `request()`

### 关键要求

- 通过 `device.create_connection(adbutils.Network.TCP, 9008)` 连接设备端 `u2.jar`。
- 手写：
  - `GET /ping`
  - `POST /jsonrpc/0`
- 每次请求必须关闭连接。
- 使用 `asyncio.wait_for()` 实现请求 timeout。
- JSON-RPC error 要映射到 uiautomator2 异常。

### 测试

必须覆盖：

- ping 请求格式。
- JSON-RPC 请求格式。
- HTTP 非 200 抛出 `HTTPError`。
- timeout 抛出 `HTTPTimeoutError`。
- `UiObjectNotFoundException` 映射到 `UiObjectNotFoundError`。
- `UiAutomation not connected` 映射到 `UiAutomationNotConnectedError`。

## 阶段 3：u2.jar 生命周期管理

### 目标

实现异步 `u2.jar` 启动、ready 检查、关闭和自动重启。

### 文件

- `src/async_uiautomator2/server.py`
- `tests/test_server.py`

### 实现内容

- `AsyncBasicUiautomatorServer`
  - `start_uiautomator()`
  - `stop_uiautomator()`
  - `jsonrpc_call()`
  - `_setup_jar()`
  - `_check_alive()`
  - `launch_uiautomator()`
  - `_wait_ready()`

### 关键要求

- 使用 `asyncio.Lock`。
- 自动重启使用 `_restart_lock` 和 `_generation`。
- 多个 RPC 同时失败，只能重启一次。
- 本地 `u2.jar` 不存在时抛出 `FileNotFoundError`。

### 测试

必须覆盖：

- jar hash 不一致时 push。
- 服务未 ready 时启动 process 并等待 ping。
- `stop_uiautomator()` 会 kill process。
- 并发 RPC 失败只触发一次 restart。

## 阶段 4：AsyncDevice 基础能力

### 目标

提供用户入口和最小设备 API。

### 文件

- `src/async_uiautomator2/device.py`
- `src/async_uiautomator2/__init__.py`
- `tests/test_device.py`

### 实现内容

- `AsyncDevice`
  - `info`
  - `click()`
  - `dump_hierarchy()`
  - `shell()`
  - `push()`
  - `app_start()`
  - `close()`
  - async context manager
- `async_connect()`

### 测试

必须覆盖：

- `await d.info` 调用 `deviceInfo`。
- `await d.click(x, y)` 调用 `click`。
- `await d.dump_hierarchy()` 调用 `dumpWindowHierarchy`。
- `await d.close()` 停止 server。
- `async with` 自动 close。

## 阶段 5：typed selector

### 目标

用类型友好的 `select()` 替代 `__call__(**kwargs)`。

### 文件

- `src/async_uiautomator2/selector.py`
- `tests/test_selector.py`

### 实现内容

- `SelectorQuery`
- `AsyncUiObject`
- `AsyncDevice.select()`
- `AsyncDevice.select_raw()`

### 关键要求

- `SelectorQuery` 使用 `@dataclass(frozen=True, slots=True)`。
- `select()` 使用显式 keyword-only 参数。
- 拼错参数应由 Python 直接抛出 `TypeError`。
- `select_raw()` 保留原始字段逃生口。

### 测试

必须覆盖：

- `resource_id` 转换为 `resourceId`。
- `text_contains` 转换为 `textContains`。
- bool `False` 不能被错误过滤。
- 拼错字段会 `TypeError`。
- `await obj.exists` 调用 `waitForExists(selector, 0)`。
- `await obj.info` 调用 `objInfo`。
- `await obj.click()` 会 wait、获取 bounds、坐标点击。
- `child()` / `sibling()` 生成正确 selector 链。

## 阶段 6：XPath

### 目标

实现基于 XML dump 的异步 XPath。

### 文件

- `src/async_uiautomator2/xpath.py`
- `tests/test_xpath.py`

### 实现内容

- `AsyncXPathElement`
- `AsyncXPathSelector`
- `AsyncDevice.xpath()`

### 关键要求

- 复用 `uiautomator2.xpath.PageSource`、`XPathSelector`、`XMLElement`。
- 未传入固定 source 时，每次查询通过 `dump_hierarchy()` 获取 XML。
- `click()` 点击第一个匹配元素中心点。
- `get()` 找不到时抛出 `XPathElementNotFoundError`。

### 测试

必须覆盖：

- 简写 `"确定"`。
- 简写 `"@resource-id"`。
- 标准 XPath `"//android.widget.Button"`。
- `exists/info/all/get_text`。
- `click()` 坐标正确。
- `wait()` 从不存在等到存在。
- `get(timeout=0)` 找不到时抛异常。

## 阶段 7：README 与集成示例

### 目标

让用户能在 5 分钟内理解项目并跑通第一个脚本。

### 文件

- `README.md`
- `examples/basic.py`
- `examples/fastapi_service.py`
- `examples/multi_device.py`

### README 必须包含

- 项目定位。
- 安装命令。
- 基础使用。
- typed selector 用法。
- XPath 用法。
- FastAPI 常驻服务注意事项。
- 并发规则。
- 第一阶段 backend 限制。

## 阶段 8：真实设备集成测试

### 目标

验证原型在真实 Android 设备上可用。

### 文件

- `tests/integration/test_real_device.py`

### 要求

- 默认跳过，只有设置环境变量才运行：

```shell
ASYNC_U2_SERIAL=emulator-5554 uv run pytest tests/integration -q
```

### 覆盖场景

- connect。
- info。
- dump_hierarchy。
- 坐标 click。
- selector exists。
- XPath exists。
- close 后程序正常退出。

## 给 AI Agent 的启动提示词

可以把下面内容交给开发 Agent：

```text
你要实现一个新 Python 项目 async-uiautomator2。
请先阅读 document/async-uiautomator2-project-brief.md、
document/async-uiautomator2-architecture.md、
document/async-uiautomator2-api-contract.md、
document/async-uiautomator2-agent-plan.md。

按 agent plan 分阶段开发。每个阶段必须先写测试，再实现。
使用 uv 运行测试。不要修改 uiautomator2 源码。
第一阶段使用 asyncio.to_thread 包装 adbutils 即可，不要过早自研 async ADB。
不要实现 d(text="OK")，必须实现 d.select(text="OK")。
完成每个阶段后运行：
uv run pytest -q
uv run python -m compileall -q src/async_uiautomator2
```
