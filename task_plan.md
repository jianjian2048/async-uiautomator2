# async-uiautomator2 任务计划

## 目标

根据 `document/` 中的项目文档，参考 `experiment/async_u2_mvp/` 中已验证的 MVP，完成正式包 `async_uiautomator2` 的第一版实现、测试、README 和基础验证。

## 阶段

| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| 1 | complete | 阅读项目文档与 MVP，确认最小可发布能力 |
| 2 | complete | 建立计划、发现和进度记录 |
| 3 | complete | 先写正式包单元测试并确认失败 |
| 4 | complete | 实现 adb/http/server/device/selector/xpath/exceptions 模块 |
| 5 | complete | 补充 README 和示例 |
| 6 | complete | 运行 `uv run pytest -q` 与 `uv run python -m compileall -q src/async_uiautomator2` |
| 7 | complete | 移除 `experiment/` jar fallback，改为包资源/缓存/devsleep 自动下载 resolver |
| 8 | complete | 截图与 pull 的设计规格已确认、提交并获得用户审阅 |
| 9 | complete | 已为截图、pull 和新增控件辅助方法编写并验证失败单元测试 |
| 10 | complete | 已实现 backend、`AsyncDevice` API、控件辅助方法并更新文档 |
| 11 | complete | 已执行目标测试、完整测试、编译与构建验证 |
| 12 | complete | 为 uiautomator2 3.7.0、u2.jar 0.4.0、端口、层级参数和共享锁补充失败测试 |
| 13 | complete | 实现 jar resolver、端口链路、`root_in_active` 和共享生命周期锁 |
| 14 | complete | 更新依赖约束、README、API 契约和架构文档 |
| 15 | complete | 执行锁文件、测试、编译、构建和 diff 全量验证 |
| 16 | complete | 已探测 Android 设备；因同时连接 3 台设备且目标不唯一，未执行设备写操作和冒烟 |
| 17 | complete | 审查本项目 XPath API、测试与文档，并与 uiautomator2 3.7.0 对齐 |
| 18 | complete | 输出 XPath 能力缺口、兼容性风险与建议优先级 |
| 19 | complete | 为 XPath 几何、父节点、长按、输入和元素截图补充失败测试 |
| 20 | complete | 实现 XPath P0/P1 API 并保持现有调用兼容 |
| 21 | complete | 更新 README、API 契约和架构文档 |
| 22 | complete | 执行目标测试、全量测试、编译、构建和 diff 检查 |
| 23 | complete | 为贝塞尔轨迹、滑动、拖动和输入锁补充失败测试 |
| 24 | complete | 实现 `swipe_points()`、`swipe_bezier()` 和 `drag_bezier()` |
| 25 | complete | 实现同设备端口共享输入锁和异常/取消时的触点释放 |
| 26 | complete | 更新 README、API 契约和架构文档 |
| 27 | complete | 执行目标测试、全量测试、编译、构建和 diff 检查 |

## 验收命令

```shell
uv run pytest -q
uv run python -m compileall -q src/async_uiautomator2
uv build
```

## 注意事项

- 默认使用简体中文注释和 Google 风格 docstring。
- Python 命令使用 `uv run`。
- 新功能先写测试，再实现。
- 不修改 `uiautomator2` 源码。
- 不实现 `d(text="OK")` / `__call__(**kwargs)`。
- 本轮依赖范围固定为 `uiautomator2>=3.7,<4`。
- 本轮不引入 `u2cli`、`agent_cli` 或新的 `launchApp` 封装。
- 贝塞尔滑动使用单次 `swipePoints` RPC，`duration` 表示整条轨迹的目标时长。
- 贝塞尔拖动使用 `injectInputEvent` 的 DOWN/MOVE/UP 序列，并按
  `(device.serial, port)` 串行原始触摸序列。

## 验证结果

- `uv lock --check`：通过。
- `uv run pytest -q`：59 passed。
- `uv run python -m compileall -q src/async_uiautomator2`：退出码 0。
- `uv build`：成功在临时目录生成 sdist 和 wheel。
- `git diff --check`：通过。
- 当前环境：`uiautomator2 3.7.0`、`u2.jar 0.4.0`。
- ADB 探测：发现 3 台在线设备；因目标不唯一，真机冒烟未执行。
- 贝塞尔目标测试：29 passed。
