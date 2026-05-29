from pathlib import Path

import pytest

from async_uiautomator2.assets import (
    U2_JAR_VERSION,
    U2_JAR_URL_TEMPLATE,
    ensure_u2_jar,
    get_default_cache_dir,
)
from async_uiautomator2.server import AsyncBasicUiautomatorServer


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

    assert jar == tmp_path / "u2-0.2.2.jar"
    assert jar.read_bytes() == b"downloaded"
    assert downloads == [
        ("https://public.uiauto.devsleep.com/u2jar/0.2.2/u2.jar", jar)
    ]


def test_ensure_u2_jar_reuses_cached_download(tmp_path) -> None:
    cached = tmp_path / "u2-0.2.2.jar"
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


def test_ensure_u2_jar_raises_for_missing_explicit_path(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        ensure_u2_jar(tmp_path / "missing.jar")


def test_default_cache_dir_is_not_under_experiment() -> None:
    assert "experiment" not in str(get_default_cache_dir()).lower()


def test_default_download_url_matches_uiautomator2_sync_script() -> None:
    assert U2_JAR_VERSION == "0.2.2"
    assert U2_JAR_URL_TEMPLATE.format(version=U2_JAR_VERSION) == (
        "https://public.uiauto.devsleep.com/u2jar/0.2.2/u2.jar"
    )


def test_server_accepts_lazy_default_jar_resolution() -> None:
    server = AsyncBasicUiautomatorServer(device=object(), setup_jar=True)

    assert server.jar_path is None
