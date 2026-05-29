# async-uiautomator2 发现记录

## 文档要点

- 第一版要覆盖 `async_connect()`、`AsyncDevice`、`AsyncUiObject`、`AsyncXPathSelector`。
- 后端第一阶段使用 `asyncio.to_thread` 包装同步 `adbutils`，避免直接阻塞事件循环。
- ADB socket HTTP 客户端需要手写 `GET /ping` 与 `POST /jsonrpc/0`，每次请求后关闭连接。
- `u2.jar` 生命周期由 server 层集中管理，重启要用锁和 generation 防止并发重复重启。
- typed selector 使用 `select(...)` 和 `select_raw(...)`，主线不兼容 `d(text="OK")`。
- XPath 基于 XML dump 在 Python 侧匹配，适合弹窗检测和临时定位。

## MVP 可复用点

- `experiment/async_u2_mvp/async_core.py` 已实现 async ADB wrapper、HTTP client、server、device 和 `async_connect()`。
- `experiment/async_u2_mvp/selector.py` 已实现 `SelectorQuery`、字段映射、`AsyncUiObject`。
- `experiment/async_u2_mvp/async_xpath.py` 已实现 XPath selector/element。
- MVP 内部引用包名需要从 `async_u2_mvp` 调整为 `async_uiautomator2`，并拆分为正式文档建议的模块。

## 环境发现

- PowerShell 不支持 Bash 风格 `python - <<'PY'` here-doc；后续内联 Python 使用 PowerShell here-string 或 `python -c`。

## 2026-05-30 jar 资源发现

- 当前安装的 `uiautomator2 3.5.2` 在 `core.py` 中通过 `with_package_resource("assets/u2.jar")` 获取包内资源并推送到设备。
- `uiautomator2/assets/sync.sh` 中 `JAR_VERSION="0.2.2"`，jar 下载地址为 `https://public.uiauto.devsleep.com/u2jar/$JAR_VERSION/u2.jar`。
- `async-uiautomator2` 不应依赖 `experiment/assets/u2.jar`；默认路径改为显式路径、包资源、本机缓存、devsleep jar 源下载的顺序。
