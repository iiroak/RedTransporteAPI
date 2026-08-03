"""Tests para la actualización GTFS atómica (fallo nunca destruye el dataset activo)."""

import io
import zipfile
from pathlib import Path

import pytest

from red_transporte_api.gtfs import downloader

REQUIRED = (
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "frequencies.txt",
    "calendar.txt",
)


def _make_zip(names=REQUIRED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, "col1,col2\n")
    return buf.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    gtfs_dir = tmp_path / "gtfs"
    monkeypatch.setattr(downloader, "GTFS_DIR", gtfs_dir)
    monkeypatch.setattr(downloader, "GTFS_METADATA_FILE", gtfs_dir / "gtfs_metadata.json")
    monkeypatch.setattr(downloader, "is_gtfs_outdated", lambda: True)
    monkeypatch.setattr(downloader, "_find_gtfs_url", lambda: "https://example.com/gtfs_vigente.zip")
    return tmp_path


def _fake_download(zip_bytes):
    def _download_zip(url, dest, timeout):
        dest.write_bytes(zip_bytes)
        return len(zip_bytes)
    downloader._download_zip = _download_zip


def test_download_valid_zip(env):
    _fake_download(_make_zip())
    result = downloader.download_latest_gtfs(force=True)
    assert result == env / "gtfs" / "gtfs_vigente"
    assert (result / "stops.txt").exists()
    meta = downloader._read_metadata()
    assert meta["extract_dir"] == str(result)
    assert meta["zip_size_bytes"] == len(_make_zip())


def test_download_preserves_previous_on_bad_zip(env):
    _fake_download(_make_zip())
    first = downloader.download_latest_gtfs(force=True)
    assert first.exists()

    _fake_download(_make_zip(names=("stops.txt",)))  # missing required files
    with pytest.raises(RuntimeError, match="faltan archivos"):
        downloader.download_latest_gtfs(force=True)

    assert first.exists(), "dataset anterior destruido"
    assert (first / "routes.txt").exists()
    assert downloader.get_gtfs_path() == first


def test_download_rejects_corrupt_zip(env):
    _fake_download(_make_zip())
    first = downloader.download_latest_gtfs(force=True)

    _fake_download(b"not a real zip")
    with pytest.raises(zipfile.BadZipFile):
        downloader.download_latest_gtfs(force=True)

    assert first.exists()
    assert downloader.get_gtfs_path() == first


def test_download_rejects_missing_calendar(env):
    _fake_download(_make_zip(names=("stops.txt", "routes.txt", "trips.txt",
                                    "stop_times.txt", "frequencies.txt")))
    with pytest.raises(RuntimeError, match="calendar"):
        downloader.download_latest_gtfs(force=True)
    assert downloader.get_gtfs_path() is None


def test_download_keeps_metadata_pointing_at_new_dataset(env):
    _fake_download(_make_zip())
    first = downloader.download_latest_gtfs(force=True)
    _fake_download(_make_zip())
    second = downloader.download_latest_gtfs(force=True)
    assert downloader.get_gtfs_path() == second
    assert second.exists()
    assert downloader._read_metadata()["extract_dir"] == str(second)
