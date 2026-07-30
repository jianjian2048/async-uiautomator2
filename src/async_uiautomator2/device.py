"""面向用户的异步设备入口。"""

from __future__ import annotations

import asyncio
import math
import random
from pathlib import Path
from typing import Any, Callable, Sequence

from uiautomator2._selector import Selector
from uiautomator2.utils import image_convert

from async_uiautomator2.adb import AsyncAdbDevice, ThreadedAdbDevice
from async_uiautomator2.http import DEFAULT_PORT
from async_uiautomator2.selector import AsyncUiObject, SelectorQuery
from async_uiautomator2.server import AsyncBasicUiautomatorServer
from async_uiautomator2.xpath import AsyncXPathSelector

SCROLL_STEPS = 55
ACTION_DOWN = 0
ACTION_UP = 1
ACTION_MOVE = 2

Point = tuple[int | float, int | float]


def _generate_bezier_trajectory(
    start: Point,
    end: Point,
    steps: int,
    *,
    control: Point | None = None,
    seed: int | None = None,
) -> list[tuple[float, float]]:
    """在起点和终点之间生成二次贝塞尔曲线轨迹。

    Args:
        start (Point): 起点坐标。
        end (Point): 终点坐标。
        steps (int): 曲线分段数，返回点数为 `steps + 1`。
        control (Point | None): 显式控制点；未提供时自动生成。
        seed (int | None): 自动生成控制点时使用的随机种子。

    Returns:
        list[tuple[float, float]]: 包含起点和终点的曲线坐标。

    Raises:
        ValueError: 分段数小于 2，或起点和终点重合。
    """

    if steps < 2:
        raise ValueError("steps 必须大于等于 2")

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance == 0:
        raise ValueError("start 和 end 不能重合")

    if control is None:
        offset_factor = min(0.3, max(0.1, distance / 1000))
        offset = random.Random(seed).uniform(-1, 1) * distance * offset_factor
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        control_x = mid_x - dy / distance * offset
        control_y = mid_y + dx / distance * offset
    else:
        control_x, control_y = control

    points: list[tuple[float, float]] = []
    for index in range(steps + 1):
        t = index / steps
        inverse_t = 1 - t
        x = (
            inverse_t**2 * start[0]
            + 2 * inverse_t * t * control_x
            + t**2 * end[0]
        )
        y = (
            inverse_t**2 * start[1]
            + 2 * inverse_t * t * control_y
            + t**2 * end[1]
        )
        points.append((x, y))
    return points


class AsyncDevice:
    """面向调用方的最小异步设备 API。

    Args:
        adb_device (AsyncAdbDevice): 异步 ADB 设备适配器。
        server (AsyncBasicUiautomatorServer): `u2.jar` 服务管理器。
    """

    def __init__(
        self, adb_device: AsyncAdbDevice, server: AsyncBasicUiautomatorServer
    ) -> None:
        self.adb_device = adb_device
        self.server = server

    @property
    def info(self):
        """获取设备信息的协程。"""

        return self.server.jsonrpc_call("deviceInfo", [], timeout=10)

    async def click(self, x: int | float, y: int | float) -> Any:
        """点击屏幕坐标。"""

        return await self.server.jsonrpc_call("click", [x, y], timeout=10)

    async def long_click(
        self, x: int | float, y: int | float, duration: float = 0.5
    ) -> Any:
        """长按屏幕坐标。"""

        x, y = await self._pos_rel2abs(x, y)
        return await self.server.jsonrpc_call(
            "click", [x, y, int(duration * 1000)], timeout=10
        )

    async def swipe(
        self,
        fx: int | float,
        fy: int | float,
        tx: int | float,
        ty: int | float,
        duration: float | None = None,
        steps: int | None = None,
    ) -> Any:
        """从一个坐标滑动到另一个坐标。"""

        if duration is not None and steps is not None:
            duration = None
        if duration is not None:
            steps = int(duration * 200)
        if not steps:
            steps = SCROLL_STEPS
        fx, fy = await self._pos_rel2abs(fx, fy)
        tx, ty = await self._pos_rel2abs(tx, ty)
        return await self.server.jsonrpc_call(
            "swipe", [fx, fy, tx, ty, max(2, steps)], timeout=10
        )

    async def swipe_points(
        self,
        points: Sequence[Point],
        duration: float = 0.5,
    ) -> Any:
        """沿多个轨迹点完成一次连续滑动。

        `duration` 表示整条轨迹的目标时长，而不是每一段的时长。
        """

        self._validate_duration(duration, "duration")
        absolute_points = await self._prepare_gesture_points(points)
        return await self._swipe_points_absolute(absolute_points, duration)

    async def swipe_bezier(
        self,
        start: Point,
        end: Point,
        *,
        control: Point | None = None,
        duration: float = 0.5,
        trajectory_steps: int = 30,
        seed: int | None = None,
    ) -> Any:
        """沿二次贝塞尔曲线完成一次连续滑动。"""

        self._validate_duration(duration, "duration")
        points = await self._prepare_bezier_trajectory(
            start,
            end,
            control=control,
            trajectory_steps=trajectory_steps,
            seed=seed,
        )
        return await self._swipe_points_absolute(points, duration)

    async def drag(
        self,
        sx: int | float,
        sy: int | float,
        ex: int | float,
        ey: int | float,
        duration: float = 0.5,
    ) -> Any:
        """从一个坐标拖拽到另一个坐标。"""

        sx, sy = await self._pos_rel2abs(sx, sy)
        ex, ey = await self._pos_rel2abs(ex, ey)
        return await self.server.jsonrpc_call(
            "drag", [sx, sy, ex, ey, int(duration * 200)], timeout=10
        )

    async def drag_bezier(
        self,
        start: Point,
        end: Point,
        *,
        control: Point | None = None,
        hold_duration: float = 0.5,
        duration: float = 1.0,
        trajectory_steps: int = 30,
        seed: int | None = None,
    ) -> Any:
        """按下后沿二次贝塞尔曲线移动，最后释放触点。"""

        self._validate_duration(duration, "duration")
        self._validate_duration(
            hold_duration,
            "hold_duration",
            allow_zero=True,
        )
        points = await self._prepare_bezier_trajectory(
            start,
            end,
            control=control,
            trajectory_steps=trajectory_steps,
            seed=seed,
        )
        interval = duration / (len(points) - 1)

        async with self.server.input_lock:
            down_sent = False
            released = False
            current_point = points[0]
            failure: BaseException | None = None
            try:
                down_result = await self._inject_input_event(
                    ACTION_DOWN,
                    current_point,
                )
                if not down_result:
                    return down_result
                down_sent = True

                if hold_duration:
                    await asyncio.sleep(hold_duration)
                for point in points[1:]:
                    await asyncio.sleep(interval)
                    move_result = await self._inject_input_event(
                        ACTION_MOVE,
                        point,
                    )
                    if not move_result:
                        return move_result
                    current_point = point

                up_result = await self._inject_input_event(
                    ACTION_UP,
                    current_point,
                )
                released = bool(up_result)
                return up_result
            except BaseException as exc:
                failure = exc
                raise
            finally:
                if down_sent and not released:
                    try:
                        await self._release_touch_safely(current_point)
                    except BaseException:
                        if failure is None:
                            raise

    async def clear_text(self) -> Any:
        """清空当前聚焦输入框文本。"""

        return await self.server.jsonrpc_call("clearInputText", [], timeout=10)

    async def set_clipboard(self, text: str, label: str | None = None) -> Any:
        """设置设备剪贴板文本。"""

        return await self.server.jsonrpc_call(
            "setClipboard", [label, text], timeout=10
        )

    async def send_keys(self, text: str, clear: bool = False) -> Any:
        """向当前聚焦输入框输入文本。"""

        if clear:
            await self.clear_text()
        await self.set_clipboard(text)
        return await self.server.jsonrpc_call("pasteClipboard", [], timeout=10)

    async def shell(self, cmd: str | list[str], timeout: float = 60) -> str:
        """执行 adb shell 命令。"""

        return await self.adb_device.shell(cmd, timeout=timeout)

    async def push(self, src: str | Path, dst: str, mode: int = 0o644) -> None:
        """推送文件到设备。"""

        await self.adb_device.push(src, dst, mode=mode)

    async def pull(
        self, src: str, dst: str | Path, exist_ok: bool = False
    ) -> int:
        """从设备拉取文件或目录。"""

        return await self.adb_device.pull(src, dst, exist_ok=exist_ok)

    async def screenshot(
        self,
        filename: str | Path | None = None,
        format: str = "pillow",
        display_id: int | None = None,
    ) -> Any | None:
        """截取设备屏幕。"""

        image = await self.adb_device.screenshot(display_id=display_id)
        if filename:
            image.save(filename)
            return None
        return image_convert(image, format)

    async def app_start(self, package_name: str) -> Any:
        """启动 Android 应用。"""

        return await self.adb_device.app_start(package_name)

    async def app_stop(self, package_name: str) -> Any:
        """停止 Android 应用。"""

        app_stop = getattr(self.adb_device, "app_stop", None)
        if app_stop is not None:
            return await app_stop(package_name)
        return await self.shell(["am", "force-stop", package_name])

    async def app_clear(self, package_name: str) -> Any:
        """停止并清理 Android 应用数据。"""

        app_clear = getattr(self.adb_device, "app_clear", None)
        if app_clear is not None:
            return await app_clear(package_name)
        return await self.shell(["pm", "clear", package_name])

    async def window_size(self) -> tuple[int, int]:
        """获取当前设备屏幕尺寸。"""

        info = await self.info
        width = info.get("displayWidth")
        height = info.get("displayHeight")
        if width is None or height is None:
            display_size = info.get("displaySize") or {}
            width = display_size.get("width")
            height = display_size.get("height")
        if width is None or height is None:
            raise RuntimeError("deviceInfo 未返回屏幕尺寸")
        return int(width), int(height)

    async def dump_hierarchy(
        self,
        compressed: bool = False,
        pretty: bool = False,
        max_depth: int = 50,
        root_in_active: bool | None = None,
    ) -> str:
        """异步 dump 当前窗口 XML 层级。"""

        params: list[Any] = [compressed, max_depth]
        if root_in_active is not None:
            params.append(root_in_active)
        content = await self.server.jsonrpc_call(
            "dumpWindowHierarchy", params, timeout=10
        )
        if pretty:
            from lxml import etree

            root = etree.fromstring(content.encode("utf-8"))
            content = etree.tostring(
                root,
                pretty_print=True,
                encoding="UTF-8",
                xml_declaration=True,
            ).decode("utf-8")
        return content

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
        """创建类型友好的异步 UI 元素选择器。"""

        selector = SelectorQuery(
            text=text,
            text_contains=text_contains,
            text_matches=text_matches,
            text_starts_with=text_starts_with,
            class_name=class_name,
            class_name_matches=class_name_matches,
            description=description,
            description_contains=description_contains,
            description_matches=description_matches,
            description_starts_with=description_starts_with,
            resource_id=resource_id,
            resource_id_matches=resource_id_matches,
            package_name=package_name,
            package_name_matches=package_name_matches,
            index=index,
            instance=instance,
            checkable=checkable,
            checked=checked,
            clickable=clickable,
            long_clickable=long_clickable,
            scrollable=scrollable,
            enabled=enabled,
            focusable=focusable,
            focused=focused,
            selected=selected,
        ).to_selector()
        return AsyncUiObject(self, selector)

    def select_raw(self, **kwargs: Any) -> AsyncUiObject:
        """使用原始 uiautomator2 selector 字段创建元素对象。"""

        return AsyncUiObject(self, Selector(**kwargs))

    def xpath(self, xpath: str, source: str | None = None) -> AsyncXPathSelector:
        """创建异步 XPath 选择器。"""

        return AsyncXPathSelector(self, xpath, source=source)

    async def _pos_rel2abs(
        self, x: int | float, y: int | float
    ) -> tuple[int | float, int | float]:
        """将小于 1 的相对坐标转换为绝对坐标。"""

        if x < 0 or y < 0:
            raise ValueError("坐标不能为负数")
        if x < 1 or y < 1:
            width, height = await self.window_size()
            if x < 1:
                x = int(width * x)
            if y < 1:
                y = int(height * y)
        return x, y

    async def _prepare_gesture_points(
        self,
        points: Sequence[Point],
    ) -> list[tuple[int, int]]:
        """转换、裁剪轨迹点，并移除连续重复坐标。"""

        raw_points = list(points)
        if len(raw_points) < 2:
            raise ValueError("轨迹至少需要 2 个坐标")
        width, height = await self.window_size()
        normalized = [
            self._normalize_input_point(point, width, height)
            for point in raw_points
        ]
        return self._deduplicate_points(normalized)

    async def _prepare_bezier_trajectory(
        self,
        start: Point,
        end: Point,
        *,
        control: Point | None,
        trajectory_steps: int,
        seed: int | None,
    ) -> list[tuple[int, int]]:
        """将输入坐标转换为屏幕坐标并生成贝塞尔轨迹。"""

        if trajectory_steps < 2:
            raise ValueError("trajectory_steps 必须大于等于 2")

        width, height = await self.window_size()
        absolute_start = self._normalize_input_point(start, width, height)
        absolute_end = self._normalize_input_point(end, width, height)
        absolute_control = (
            self._normalize_input_point(control, width, height)
            if control is not None
            else None
        )
        trajectory = _generate_bezier_trajectory(
            absolute_start,
            absolute_end,
            trajectory_steps,
            control=absolute_control,
            seed=seed,
        )
        normalized = [
            self._clamp_absolute_point(point, width, height)
            for point in trajectory
        ]
        return self._deduplicate_points(normalized)

    async def _swipe_points_absolute(
        self,
        points: Sequence[tuple[int, int]],
        duration: float,
    ) -> Any:
        """将绝对坐标轨迹通过单次 `swipePoints` RPC 下发。"""

        segment_steps = max(
            2,
            round(duration * 200 / (len(points) - 1)),
        )
        flat_points = [coordinate for point in points for coordinate in point]
        return await self.server.jsonrpc_call(
            "swipePoints",
            [flat_points, segment_steps],
            timeout=max(10, duration + 5),
        )

    async def _inject_input_event(
        self,
        action: int,
        point: tuple[int, int],
    ) -> Any:
        """发送一个原始触摸事件。"""

        return await self.server.jsonrpc_call(
            "injectInputEvent",
            [action, point[0], point[1], 0],
            timeout=10,
        )

    async def _release_touch_safely(
        self,
        point: tuple[int, int],
    ) -> None:
        """在外层任务取消时也尽量完成触点释放。"""

        release_task = asyncio.create_task(
            self._inject_input_event(ACTION_UP, point)
        )
        try:
            await asyncio.shield(release_task)
        except asyncio.CancelledError as cancellation:
            try:
                await release_task
            except Exception:
                pass
            raise cancellation

    @staticmethod
    def _normalize_input_point(
        point: Point,
        width: int,
        height: int,
    ) -> tuple[int, int]:
        """将一个相对/绝对输入坐标转换并裁剪到屏幕范围。"""

        x, y = point
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("坐标必须是有限数值")
        if x < 0 or y < 0:
            raise ValueError("坐标不能为负数")
        if x < 1:
            x = width * x
        if y < 1:
            y = height * y
        return AsyncDevice._clamp_absolute_point((x, y), width, height)

    @staticmethod
    def _clamp_absolute_point(
        point: Point,
        width: int,
        height: int,
    ) -> tuple[int, int]:
        """将绝对坐标取整并裁剪到屏幕范围。"""

        x = min(max(round(point[0]), 0), width - 1)
        y = min(max(round(point[1]), 0), height - 1)
        return x, y

    @staticmethod
    def _deduplicate_points(
        points: Sequence[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        """移除连续重复点并保证轨迹仍包含至少两个坐标。"""

        deduplicated: list[tuple[int, int]] = []
        for point in points:
            if not deduplicated or point != deduplicated[-1]:
                deduplicated.append(point)
        if len(deduplicated) < 2:
            raise ValueError("轨迹至少需要 2 个不同坐标")
        return deduplicated

    @staticmethod
    def _validate_duration(
        duration: float,
        name: str,
        *,
        allow_zero: bool = False,
    ) -> None:
        """校验手势时长参数。"""

        valid = duration >= 0 if allow_zero else duration > 0
        if not math.isfinite(duration) or not valid:
            comparison = "大于等于 0" if allow_zero else "大于 0"
            raise ValueError(f"{name} 必须是{comparison}的有限数值")

    async def close(self) -> None:
        """关闭当前客户端持有的 `u2.jar` stream 连接。"""

        await self.server.stop_uiautomator(wait=False)

    async def __aenter__(self) -> "AsyncDevice":
        """进入 async context manager。"""

        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """退出 async context manager 时释放设备连接。"""

        await self.close()


async def async_connect(
    serial: str | None = None,
    *,
    port: int = DEFAULT_PORT,
    device_factory: Callable[[str | None], AsyncAdbDevice] | None = None,
    jar_path: str | Path | None = None,
    setup_jar: bool = True,
) -> AsyncDevice:
    """连接设备并返回最小异步设备对象。"""

    factory = device_factory or ThreadedAdbDevice
    adb_device = factory(serial)
    server = AsyncBasicUiautomatorServer(
        adb_device,
        port=port,
        jar_path=jar_path,
        setup_jar=setup_jar,
    )
    await server.start_uiautomator()
    return AsyncDevice(adb_device, server)
