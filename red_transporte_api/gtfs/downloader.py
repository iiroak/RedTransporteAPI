"""
Auto-download GTFS data from DTPM (Directorio de Transporte Público Metropolitano).

Scrapes https://www.dtpm.cl/index.php/noticias/gtfs-vigente to find the latest
GTFS ZIP link, downloads it, and extracts the CSV files for local use.

The update is transactional: download to a temp file, validate, extract to a
temp directory, then atomically swap into place. A failed update never destroys
the previously working dataset.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from red_transporte_api.config import GTFS_DIR, GTFS_METADATA_FILE, GTFS_PAGE_URL

logger = logging.getLogger(__name__)

_GTFS_LINK_PATTERN = re.compile(r"GTFS.*\.zip$", re.IGNORECASE)
_MAX_ZIP_BYTES = 2 * 1024**3  # 2 GiB sanity cap
_REQUIRED_FILES = (
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "frequencies.txt",
)
# GTFS allows either calendar.txt or calendar_dates.txt (at least one).
_ALTERNATE_REQUIRED = ("calendar.txt", "calendar_dates.txt")


class _UpdateLock:
    """Inter-process exclusive lock for GTFS updates (no-op where unavailable)."""

    def __init__(self) -> None:
        self._file = None

    def __enter__(self):
        try:
            import fcntl
        except ImportError:
            return self
        GTFS_DIR.mkdir(parents=True, exist_ok=True)
        lock_path = GTFS_DIR / ".gtfs-update.lock"
        self._file = open(lock_path, "w")
        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._file is not None:
            try:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            finally:
                self._file.close()
                self._file = None
        return False


def _find_gtfs_url(page_url: str = GTFS_PAGE_URL, timeout: float = 30.0) -> str:
    """Scrape the DTPM page to find the latest GTFS ZIP download URL."""
    resp = httpx.get(page_url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if _GTFS_LINK_PATTERN.search(href):
            return urljoin(page_url, href)
    raise RuntimeError(
        "No se encontró el enlace de descarga GTFS en la página de DTPM. "
        "Verifica manualmente: " + page_url
    )


def _read_metadata() -> dict:
    if GTFS_METADATA_FILE.exists():
        with open(GTFS_METADATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write_metadata(meta: dict) -> None:
    GTFS_METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = GTFS_METADATA_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, GTFS_METADATA_FILE)


def get_gtfs_path() -> Path | None:
    """Return path to the extracted GTFS directory, or None if not downloaded."""
    meta = _read_metadata()
    extract_dir = meta.get("extract_dir")
    if extract_dir:
        p = Path(extract_dir)
        if p.exists() and (p / "stops.txt").exists():
            return p
    return None


def ensure_gtfs_path(force_download: bool = False) -> Path:
    """Return a local GTFS directory, downloading it when missing."""
    existing = get_gtfs_path()
    if existing and not force_download:
        return existing
    logger.info("No local GTFS data found. Downloading latest dataset...")
    return download_latest_gtfs(force=force_download)


def is_gtfs_outdated(max_age_days: int = 30) -> bool:
    """Check if the local GTFS data is outdated or missing."""
    meta = _read_metadata()
    if not meta.get("download_date"):
        return True
    try:
        dl_date = datetime.fromisoformat(meta["download_date"])
        age = datetime.now(timezone.utc) - dl_date
        return age.days > max_age_days
    except (ValueError, TypeError):
        return True


def _download_zip(url: str, dest: Path, timeout: float) -> int:
    """Stream the GTFS ZIP to *dest*. Returns total bytes written."""
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
        resp.raise_for_status()
        total = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                total += len(chunk)
                if total > _MAX_ZIP_BYTES:
                    raise RuntimeError(
                        f"GTFS ZIP supera el límite de {_MAX_ZIP_BYTES // (1024**3)} GiB; abortando"
                    )
                f.write(chunk)
    return total


def _validate_and_extract(zip_path: Path, extract_dir: Path) -> None:
    """Validate ZIP integrity and extract into *extract_dir* (fresh dir)."""
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"GTFS ZIP corrupto (CRC falla en {bad})")
        names = zf.namelist()
        if any(n.startswith("/") or ".." in n.split("/") for n in names):
            raise RuntimeError("GTFS ZIP contiene rutas inseguras")
        zf.extractall(extract_dir)

    txt_files = list(extract_dir.rglob("stops.txt"))
    if not txt_files:
        raise RuntimeError("GTFS inválido: no contiene stops.txt")
    if txt_files[0].parent != extract_dir:
        nested = txt_files[0].parent
        for item in nested.iterdir():
            item.rename(extract_dir / item.name)

    present = {p.name for p in extract_dir.glob("*.txt")}
    missing = [f for f in _REQUIRED_FILES if f not in present]
    if missing:
        raise RuntimeError(f"GTFS inválido: faltan archivos obligatorios: {', '.join(missing)}")
    if not any(f in present for f in _ALTERNATE_REQUIRED):
        raise RuntimeError(
            "GTFS inválido: falta calendar.txt o calendar_dates.txt"
        )


def download_latest_gtfs(
    force: bool = False,
    timeout: float = 120.0,
) -> Path:
    """
    Download and extract the latest GTFS from DTPM, transactionally.

    Returns the path to the extracted directory containing CSV files.
    If the data is already current and force=False, returns the existing path.
    """
    if not force:
        existing = get_gtfs_path()
        meta = _read_metadata()
        if existing and not is_gtfs_outdated():
            logger.info("GTFS data is up to date: %s", existing)
            return existing

    with _UpdateLock():
        return _download_latest_gtfs_locked(force=force, timeout=timeout)


def _download_latest_gtfs_locked(force: bool, timeout: float) -> Path:
    if not force:
        existing = get_gtfs_path()
        meta = _read_metadata()
        if existing and not is_gtfs_outdated():
            logger.info("GTFS data is up to date: %s", existing)
            return existing

    url = _find_gtfs_url()
    filename = url.rsplit("/", 1)[-1]
    logger.info("Downloading GTFS from %s", url)

    GTFS_DIR.mkdir(parents=True, exist_ok=True)
    final_dir = GTFS_DIR / Path(filename).stem

    zip_path = GTFS_DIR / f".{filename}.part"
    try:
        size = _download_zip(url, zip_path, timeout)
        logger.info("Downloaded %s (%.1f MB)", filename, size / 1e6)

        tmp_dir = Path(tempfile.mkdtemp(prefix=".gtfs-", dir=GTFS_DIR))
        try:
            _validate_and_extract(zip_path, tmp_dir)

            backup_dir = GTFS_DIR / f".{Path(filename).stem}.old"
            if final_dir.exists():
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                os.replace(final_dir, backup_dir)
            try:
                os.replace(tmp_dir, final_dir)
            except OSError:
                # Restore the previous dataset if the swap failed.
                if backup_dir.exists() and not final_dir.exists():
                    os.replace(backup_dir, final_dir)
                raise
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

        _write_metadata({
            "url": url,
            "filename": filename,
            "download_date": datetime.now(timezone.utc).isoformat(),
            "extract_dir": str(final_dir),
            "zip_size_bytes": size,
        })
    finally:
        if zip_path.exists():
            zip_path.unlink()

    logger.info("GTFS extracted to %s", final_dir)
    return final_dir


def get_gtfs_status() -> dict:
    """Return a status dict about the local GTFS data."""
    meta = _read_metadata()
    gtfs_path = get_gtfs_path()
    file_count = 0
    if gtfs_path:
        file_count = len(list(gtfs_path.glob("*.txt")))
    return {
        "available": gtfs_path is not None,
        "path": str(gtfs_path) if gtfs_path else None,
        "url": meta.get("url"),
        "filename": meta.get("filename"),
        "download_date": meta.get("download_date"),
        "zip_size_bytes": meta.get("zip_size_bytes"),
        "file_count": file_count,
        "outdated": is_gtfs_outdated(),
    }
