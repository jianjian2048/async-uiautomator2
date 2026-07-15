# async-uiautomator2 发现记录

## 2026-07-16 screenshot / pull

- 当前 `AsyncDevice` 已提供 `push`，但 `AsyncAdbDevice`、`ThreadedAdbDevice` 和公开设备 API 均缺少 `pull` 与 `screenshot`。
- 当前锁定依赖 `adbutils 2.12.0`：`sync.pull(src, dst, exist_ok=False)` 返回已拉取字节数；`screenshot(display_id=None, error_ok=True)` 返回 Pillow 图像。
- `uiautomator2.Device.screenshot(filename=None, format="pillow", display_id=None)` 是兼容目标：传入 `filename` 时保存图像并返回 `None`，未传时返回指定格式的图像。
- 规格已提交至 `docs/superpowers/specs/2026-07-16-screenshot-pull-design.md`（提交 `4b24e84`）。
- 控件 API 审计显示，当前文档中承诺的控件方法均已存在；相较上游常用基础能力，补充了 `get_text()`、`info_list()`、`click_exists()` 与 `click_gone()`。上游 `parent()` 本身未实现，因此没有引入不完整的兼容接口。

## 遇到的错误

| 错误 | 尝试次数 | 解决方案 |
| --- | --- | --- |
| `python` 不能导入 `adbutils` | 1 | 使用项目环境的 `uv run python` 进行 API 检查。 |
| planning skill 指定的 `~/.claude/.../session-catchup.py` 不存在 | 1 | 已读取项目内三份规划文件；后续使用工作区状态与 Git 历史恢复上下文。 |

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
