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

## 验证结果

- `uv run pytest -q`：29 passed。
- `uv run python -m compileall -q src/async_uiautomator2`：退出码 0。
- `uv build`：成功生成 sdist/wheel；验证后已清理 `dist/`。
