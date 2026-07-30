import importlib
import json
from pathlib import Path

import pytest

from async_uiautomator2.assets import (
    U2_JAR_VERSION,
    U2_JAR_URL_TEMPLATE,
    ensure_u2_jar,
    get_default_cache_dir,
)
from async_uiautomator2.server import AsyncBasicUiautomatorServer


def _create_asset_package(
    tmp_path: Path,
    monkeypatch,
    package_name: str,
    *,
    version: str,
    jar_content: bytes,
) -> None:
    """创建带版本信息和 jar 的临时 Python 包。"""

    package_dir = tmp_path / package_name
    assets_dir = package_dir / "assets"
    assets_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (assets_dir / "version.json").write_text(
        json.dumps({"u2.jar": version}),
        encoding="utf-8",
    )
    (assets_dir / "u2.jar").write_bytes(jar_content)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()


def test_ensure_u2_jar_uses_explicit_path(tmp_path) -> None:
    jar = tmp_path / "custom.jar"
    jar.write_bytes(b"custom")

    assert ensure_u2_jar(jar, cache_dir=tmp_path / "cache") == jar


def test_ensure_u2_jar_downloads_to_cache_when_no_resource(tmp_path) -> None:
    downloads = []

    def downloader(url: str, target: Path) -> None:
        downloads.append((url, target))
        target.write_bytes(b"downloaded")

    jar = ensure_u2_jar(
        cache_dir=tmp_path,
        package_names=(),
        downloader=downloader,
    )

    assert jar == tmp_path / "u2-0.4.0.jar"
    assert jar.read_bytes() == b"downloaded"
    assert downloads == [
        (
            "https://github.com/openatx/android-uiautomator-server-jar/"
            "releases/download/0.4.0/u2.jar",
            jar,
        )
    ]


def test_ensure_u2_jar_reuses_cached_download(tmp_path) -> None:
    cached = tmp_path / "u2-0.4.0.jar"
    cached.write_bytes(b"cached")

    def downloader(url: str, target: Path) -> None:
        raise AssertionError("不应该重复下载")

    jar = ensure_u2_jar(
        cache_dir=tmp_path,
        package_names=(),
        downloader=downloader,
    )

    assert jar == cached
    assert jar.read_bytes() == b"cached"


def test_ensure_u2_jar_copies_matching_package_resource(
    tmp_path, monkeypatch
) -> None:
    _create_asset_package(
        tmp_path,
        monkeypatch,
        "matching_u2_assets",
        version="0.4.0",
        jar_content=b"package jar",
    )

    def downloader(url: str, target: Path) -> None:
        raise AssertionError("版本匹配时不应该下载")

    jar = ensure_u2_jar(
        cache_dir=tmp_path / "cache",
        package_names=("matching_u2_assets",),
        downloader=downloader,
    )

    assert jar.name == "u2-0.4.0.jar"
    assert jar.read_bytes() == b"package jar"


def test_ensure_u2_jar_skips_mismatched_package_resource(
    tmp_path, monkeypatch
) -> None:
    _create_asset_package(
        tmp_path,
        monkeypatch,
        "outdated_u2_assets",
        version="0.2.2",
        jar_content=b"outdated package jar",
    )
    downloads = []

    def downloader(url: str, target: Path) -> None:
        downloads.append(url)
        target.write_bytes(b"downloaded jar")

    jar = ensure_u2_jar(
        cache_dir=tmp_path / "cache",
        package_names=("outdated_u2_assets",),
        downloader=downloader,
    )

    assert jar.read_bytes() == b"downloaded jar"
    assert downloads == [
        "https://github.com/openatx/android-uiautomator-server-jar/"
        "releases/download/0.4.0/u2.jar"
    ]


def test_ensure_u2_jar_does_not_reuse_old_version_cache(tmp_path) -> None:
    (tmp_path / "u2-0.2.2.jar").write_bytes(b"old cache")

    def downloader(url: str, target: Path) -> None:
        target.write_bytes(b"new cache")

    jar = ensure_u2_jar(
        cache_dir=tmp_path,
        package_names=(),
        downloader=downloader,
    )

    assert jar == tmp_path / "u2-0.4.0.jar"
    assert jar.read_bytes() == b"new cache"
    assert (tmp_path / "u2-0.2.2.jar").read_bytes() == b"old cache"


def test_ensure_u2_jar_raises_for_missing_explicit_path(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        ensure_u2_jar(tmp_path / "missing.jar")


def test_default_cache_dir_is_not_under_experiment() -> None:
    assert "experiment" not in str(get_default_cache_dir()).lower()


def test_default_download_url_matches_uiautomator2_sync_script() -> None:
    assert U2_JAR_VERSION == "0.4.0"
    assert U2_JAR_URL_TEMPLATE.format(version=U2_JAR_VERSION) == (
        "https://github.com/openatx/android-uiautomator-server-jar/"
        "releases/download/0.4.0/u2.jar"
    )


def test_server_accepts_lazy_default_jar_resolution() -> None:
    server = AsyncBasicUiautomatorServer(device=object(), setup_jar=True)

    assert server.jar_path is None
