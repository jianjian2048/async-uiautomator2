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
| 共享锁初始化要求测试替身提供 `serial` | 1 | 使用 `getattr(device, "serial", None)`，未知设备采用保守的 `None` 锁键。 |
| `stop()` 递增共享 generation 会被误判为恢复完成 | 1 | generation 只在成功启动或重启后递增，停止仅通过共享锁串行。 |

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

## 2026-07-29 uiautomator2 3.7.0 对齐

- 当前 `uv.lock` 已由用户升级到 `uiautomator2 3.7.0`，但 `pyproject.toml` 仍声明 `uiautomator2>=3.5.2`。
- 当前安装包的 `assets/version.json` 声明 `u2.jar 0.4.0`，`assets/sync.sh` 使用 GitHub Release 下载 jar。
- 当前项目仍把默认 jar 固定为 `0.2.2`，并使用旧下载源；包资源复制逻辑没有校验 `version.json`。
- server 的 HTTP 客户端接受自定义端口，但启动命令没有传入 `-p`，`async_connect()` 也没有公开端口参数。
- `dump_hierarchy()` 当前固定发送两个 JSON-RPC 参数；上游 3.7.0 在可选 `root_in_active` 不为空时发送第三个参数。
- server 的生命周期锁是实例级，不能兑现文档中同设备多实例串行启动、停止和重启的语义。
- ADB 当前同时连接 `BVL_AN00`、`Pixel_9` 和 `RMX3800`，没有可安全推断的唯一冒烟目标。

## 2026-07-29 XPath API 审查

- `AsyncXPathElement.bounds` 已存在，返回 `(left, top, right, bottom)`，运行时探针得到 `(10, 20, 110, 70)`；但 README、API 契约和现有测试都没有展示或断言该属性。
- 当前调用方必须先 `element = await selector.get()`，再读取 `element.bounds`；`AsyncXPathSelector` 没有像 `AsyncUiObject.bounds()` 一样的直接几何接口。
- `uiautomator2 3.7.0` 的 `XMLElement.rect` 返回 `(left, top, width, height)`，当前 `AsyncXPathElement` 未包装此属性。
- 上游基础 `XMLElement` 还提供 `offset(px, py)` 和 `parent(xpath=None)`；当前异步元素未包装。
- 上游设备 XPath 元素/选择器还提供 `long_click`、元素截图、滑动/滚动、`set_text`、`match`、`click_nowait` 和 fallback 等能力；其中常用交互优先级高于 watcher/fallback/滚动高级能力。
- 推荐优先补齐几何 API：元素层增加 `rect`、`offset`，选择器层增加异步 `bounds()`、`rect()`、`center()`；明确 `bounds` 是四边坐标，`rect` 是左上角加宽高，避免二者混淆。
- 第二优先级建议补齐 `long_click()`、`set_text()`、`screenshot()` 和 `parent()`；滑动、滚动、百分比尺寸、fallback/watchers 可留到后续。
- 记录错误：一次使用绝对 Windows 路径同时更新三份规划文件时，`apply_patch` 未能解析 `progress.md`；改用工作区相对路径继续。
- 已实现元素层 `rect`、`offset()`、`parent()`、`long_click()`、`screenshot()`，以及选择器层 `bounds()`、`rect()`、`center()`、`long_click()`、`set_text()`、`screenshot()`。
- 选择器层几何方法会通过 `get()` 获取当前页面匹配，元素层几何属性继续表示创建该元素时的 XML 快照。
- 本轮未引入滑动、滚动、百分比几何、fallback 或 watcher；这些仍作为后续高级 XPath 能力。

## 2026-07-29 贝塞尔手势设计

- `u2.jar 0.4.0` 已提供 `swipePoints([II)Z`，适合把完整贝塞尔轨迹作为单次
  JSON-RPC 下发，避免逐点网络往返影响滑动平滑度。
- `swipePoints` 的 `segmentSteps` 作用于每一对相邻点；公开 API 的 `duration`
  定义为整条轨迹目标时长，因此需要按轨迹段数分摊为
  `max(2, round(duration * 200 / segment_count))`。
- `u2.jar 0.4.0` 的 `injectInputEvent(action, x, y, metaState)` 支持
  `ACTION_DOWN=0`、`ACTION_UP=1`、`ACTION_MOVE=2`，可以实现真正分离的按下、移动和释放。
- 原始触摸事件是有状态序列，不能让相同设备端口的多个调用交叉；输入锁应与生命周期锁
  使用相同 `(event loop, device.serial, port)` 键，但必须是独立锁。
- 拖动发生异常或取消后必须在释放输入锁前补发 `ACTION_UP`，防止设备残留按下状态。
