from pathlib import Path

from red_transporte_api.gtfs import downloader


def test_ensure_gtfs_path_uses_existing(monkeypatch):
    existing = Path("C:/tmp/existing-gtfs")

    monkeypatch.setattr(downloader, "get_gtfs_path", lambda: existing)

    def fail_download(*args, **kwargs):
        raise AssertionError("download_latest_gtfs should not be called")

    monkeypatch.setattr(downloader, "download_latest_gtfs", fail_download)

    assert downloader.ensure_gtfs_path() == existing


def test_ensure_gtfs_path_downloads_when_missing(monkeypatch):
    downloaded = Path("C:/tmp/downloaded-gtfs")

    monkeypatch.setattr(downloader, "get_gtfs_path", lambda: None)
    monkeypatch.setattr(
        downloader,
        "download_latest_gtfs",
        lambda force=False: downloaded,
    )

    assert downloader.ensure_gtfs_path() == downloaded
