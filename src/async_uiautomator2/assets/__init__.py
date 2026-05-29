"""`u2.jar` 本地缓存与自动获取。"""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
from importlib.resources import as_file, files
from pathlib import Path
from typing import Callable, Iterable

U2_JAR_VERSION = "0.2.2"
U2_JAR_URL_TEMPLATE = "https://public.uiauto.devsleep.com/u2jar/{version}/u2.jar"

Downloader = Callable[[str, Path], None]


def get_default_cache_dir() -> Path:
    """返回默认缓存目录。"""

    env_cache = os.environ.get("ASYNC_UIAUTOMATOR2_CACHE_DIR")
    if env_cache:
        return Path(env_cache).expanduser()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "async-uiautomator2"
    return Path.home() / ".cache" / "async-uiautomator2"


def ensure_u2_jar(
    jar_path: str | Path | None = None,
    *,
    cache_dir: str | Path | None = None,
    package_names: Iterable[str] = ("async_uiautomator2", "uiautomator2"),
    version: str = U2_JAR_VERSION,
    downloader: Downloader | None = None,
) -> Path:
    """确保本地存在可推送到设备的 `u2.jar`。

    Args:
        jar_path (str | Path | None): 调用方显式指定的本地 jar 路径。
        cache_dir (str | Path | None): jar 缓存目录；为空时使用默认缓存目录。
        package_names (Iterable[str]): 优先查找包内资源的包名列表。
        version (str): 下载和缓存使用的 Android server 版本号。
        downloader (Downloader | None): 下载函数，主要用于测试注入。

    Returns:
        Path: 本地 `u2.jar` 路径。

    Raises:
        FileNotFoundError: 显式 `jar_path` 不存在，或无法从包资源/网络获取 jar。
    """

    if jar_path is not None:
        explicit = Path(jar_path).expanduser()
        if not explicit.exists():
            raise FileNotFoundError(explicit)
        return explicit

    cache_root = Path(cache_dir).expanduser() if cache_dir else get_default_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    cached_jar = cache_root / f"u2-{version}.jar"
    if cached_jar.exists():
        return cached_jar

    if _copy_package_resource(cached_jar, package_names):
        return cached_jar

    download = downloader or _download_file
    url = U2_JAR_URL_TEMPLATE.format(version=version)
    download(url, cached_jar)
    if not cached_jar.exists():
        raise FileNotFoundError(cached_jar)
    return cached_jar


def _copy_package_resource(target: Path, package_names: Iterable[str]) -> bool:
    """从已安装包的资源中复制 `u2.jar` 到缓存。"""

    for package_name in package_names:
        try:
            anchor = files(package_name) / "assets" / "u2.jar"
            with as_file(anchor) as source:
                if source.exists():
                    shutil.copy2(source, target)
                    return True
        except (FileNotFoundError, ModuleNotFoundError, AttributeError):
            continue
    return False


def _download_file(url: str, target: Path) -> None:
    """原子下载文件到目标路径。"""

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=target.parent) as tmp:
        tmp_path = Path(tmp.name)
    try:
        urllib.request.urlretrieve(url, tmp_path)
        tmp_path.replace(target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
