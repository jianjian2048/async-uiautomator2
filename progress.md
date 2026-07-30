# async-uiautomator2 进度记录

## 2026-05-29

- 已读取 `document/` 四份文档，确认第一版正式包范围。
- 已读取 `experiment/async_u2_mvp/` MVP 核心实现，确认可迁移模块。
- 已发现 PowerShell here-doc 差异，后续命令改用 PowerShell 兼容写法。
- 已先写正式包单元测试，覆盖 adb/http/server/device/selector/xpath。
- 首次运行 `uv run pytest -q` 失败：环境缺少 `pytest` 命令；已按文档要求执行 `uv add --dev pytest`。
- 安装 pytest 后再次运行 `uv run pytest -q`，确认 RED：6 个测试模块均因正式包缺少目标模块而收集失败。
- 已实现正式包核心模块；首次 GREEN 验证前运行测试结果为 22 过 1 失败，失败点是测试替身构造函数未模拟真实 server 构造签名。
- 已修正测试替身与包导出，`uv run pytest -q` 得到 23 passed。
- 已补充 README、`examples/basic.py`、`examples/fastapi_service.py`、`examples/multi_device.py`，并在 `pyproject.toml` 中加入 pytest 配置。
- 曾将 `experiment/assets/u2.jar` 复制到正式包资产目录；该方案已在 2026-05-30 根据反馈移除。
- 曾执行 `uv build` 确认早期包内 jar 打包行为；该方案已在 2026-05-30 改为 resolver 自动获取。

## 2026-05-30

## 2026-07-16

- 已新增 `AsyncDevice.pull()`、`AsyncDevice.screenshot()`，并在 `AsyncAdbDevice`/`ThreadedAdbDevice` 中实现对应线程化 ADB 调用。
- 已新增控件 `get_text()`、`info_list()`、`click_exists()`、`click_gone()`，并更新 README 与 API 契约文档。
- 验证结果：`uv run pytest -q` 为 37 passed；`uv run python -m compileall -q src/async_uiautomator2`、`uv build` 与 `git diff --check` 均成功。

- 已检查现有 ADB backend、公开 `AsyncDevice` API、测试和 API 文档，确认截图与 pull 尚未实现。
- 已与用户确认接口：`screenshot(filename=None, format="pillow", display_id=None)` 与 `pull(src, dst, exist_ok=False)`；对应设计规格已提交。
- 用户要求采用 `planning-with-files-zh`；已读取并扩展工作区的 `task_plan.md`、`findings.md` 和 `progress.md`。
- 恢复脚本路径在当前机器不存在，已记录该错误；未影响依据当前工作树与 Git 历史继续跟踪。

- 根据反馈检查了 `uiautomator2` 的 jar 资源机制：当前版本通过 `with_package_resource("assets/u2.jar")` 查找包内资源，`assets/sync.sh` 中 jar 下载源为 `https://public.uiauto.devsleep.com/u2jar/0.2.2/u2.jar`。
- 先添加 `tests/test_assets.py`，确认当前缺少 `async_uiautomator2.assets` resolver 时测试失败。
- 新增 `async_uiautomator2.assets.ensure_u2_jar()`：显式路径优先，其次复制包资源到缓存，最后从 devsleep jar 源下载。
- 移除了 `src/async_uiautomator2/assets/u2.jar` 二进制文件和 `EXPERIMENT_JAR_PATH` fallback。
- 已运行 `uv run pytest -q`，结果为 29 passed。
- 已根据 `sync.sh` 修正默认 jar 版本为 `0.2.2`，默认下载地址为 `https://public.uiauto.devsleep.com/u2jar/0.2.2/u2.jar`。

## 2026-07-29

- 已确认本轮采用核心兼容对齐范围：`uiautomator2>=3.7,<4`、`u2.jar 0.4.0`、自定义端口、`root_in_active` 和按设备端口共享生命周期锁。
- 已确认不引入 `u2cli`、`agent_cli` 或新的 `launchApp` 封装，不修改项目自身版本。
- 实施前基线验证通过：`uv lock --check`、`uv run pytest -q`（37 passed）和源码编译均成功。
- 已保留用户对 `uv.lock` 的现有修改，后续只在该结果上更新依赖约束。
- 已新增 jar 资源版本校验、缓存隔离、端口链路、层级参数和多实例生命周期并发测试。
- RED 验证结果：目标测试共 14 个失败、16 个通过；失败点均对应尚未实现的升级能力。
- 首轮实现后目标测试为 29 passed、1 failed；失败原因是旧的最小 server 测试替身没有 `serial`，已改为未知 serial 使用 `None` 锁键。
- 修正后目标测试全部通过：30 passed。
- 已实现 jar 0.4.0 官方下载和包资源版本校验、自定义端口启动、`root_in_active` 参数，以及同一事件循环内按 `(serial, port)` 共享的生命周期状态和 generation。
- 已将依赖约束更新为 `uiautomator2>=3.7,<4`，并用 `uv lock` 对齐用户现有锁文件升级。
- 已更新 README、API 契约和架构文档，说明端口、hierarchy 参数、jar resolver 和多实例并发语义。
- 静态并发审查发现并修正 stop generation 语义：停止不再递增 generation，避免其他实例把“已停止”误判为“已恢复”。
- 全量验收通过：`uv lock --check`、48 个测试、源码编译、临时目录构建和 `git diff --check` 均成功。
- 已确认项目环境实际解析为 `uiautomator2 3.7.0`，其资源清单声明 `u2.jar 0.4.0`。
- ADB 探测发现 3 台在线设备；由于目标设备不唯一，未执行 jar 推送、服务启动、点击或 hierarchy 真机冒烟。
- 开始 XPath 能力审查，重点核对元素矩形、中心点、属性读取、等待、集合和交互能力。
- 已对比项目 XPath 实现、README/API 契约、测试与本地安装的 `uiautomator2 3.7.0` 源码。
- 已用运行时探针确认 `AsyncXPathElement.bounds` 可用，但 `rect` 不存在，且选择器层没有直接几何接口。
- XPath 现有回归测试通过：`uv run pytest -q tests/test_xpath.py` 为 3 passed；`git diff --check` 通过。
- 用户确认开始落地 XPath P0/P1 能力；本轮将先补失败测试，再实现和更新文档。
- 已新增 XPath 几何、父节点、长按、输入和元素截图测试；RED 结果为 2 failed、3 passed，失败均对应待实现 API。
- 已实现 XPath P0/P1 API，目标测试转绿：`uv run pytest -q tests/test_xpath.py` 为 5 passed。
- 已更新 README、API 契约和架构文档，明确几何返回格式、快照语义和新增交互方法。
- 全量验收通过：`uv lock --check`、50 个测试、源码编译、临时目录构建和 `git diff --check` 均成功。
- 用户确认开始落地贝塞尔滑动和贝塞尔拖动；已恢复三份规划文件并新增阶段 23-27。
- 已确认实现边界：滑动使用单次 `swipePoints`，拖动使用
  `injectInputEvent` DOWN/MOVE/UP，并为同设备端口增加独立共享输入锁。
- 已补充轨迹复现、总时长换算、相对坐标与边界裁剪、参数校验、DOWN/MOVE/UP
  顺序、异常/取消释放和共享输入锁测试。
- RED 验证结果：目标测试 9 failed、20 passed；失败均对应尚未实现的贝塞尔 API
  和共享输入锁。
- 已实现二次贝塞尔轨迹生成器、`swipe_points()`、`swipe_bezier()` 和
  `drag_bezier()`，支持显式控制点或随机种子。
- 已为共享生命周期状态增加独立输入锁；贝塞尔拖动在锁内发送 DOWN/MOVE/UP，
  并在异常或取消时以 `finally` 补发 UP。
- 目标测试转绿：`uv run pytest -q tests/test_device.py tests/test_server.py`
  为 29 passed。
- 已更新 README、API 契约和架构文档，说明总时长、坐标处理、控制点、
  原始输入事件和并发语义。
- 贝塞尔功能全量验收通过：`uv lock --check`、59 个测试、源码编译、
  临时目录构建和 `git diff --check` 均成功。
- 构建产物为 `async_uiautomator2-0.1.4.tar.gz` 和
  `async_uiautomator2-0.1.4-py3-none-any.whl`；未修改项目版本号。
- 当前仍有 3 台在线 Android 设备且目标不唯一，因此未执行会启动服务和注入触摸事件的
  真机冒烟。
