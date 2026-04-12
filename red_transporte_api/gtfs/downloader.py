"""
Auto-download GTFS data from DTPM (Directorio de Transporte Público Metropolitano).

Scrapes https://www.dtpm.cl/index.php/noticias/gtfs-vigente to find the latest
GTFS ZIP link, downloads it, and extracts the CSV files for local use.
"""
from __future__ import annotations

import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from red_transporte_api.config import GTFS_DIR, GTFS_METADATA_FILE, GTFS_PAGE_URL

logger = logging.getLogger(__name__)

_GTFS_LINK_PATTERN = re.compile(r"GTFS.*\.zip$", re.IGNORECASE)


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
    with open(GTFS_METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def get_gtfs_path() -> Path | None:
    """Return path to the extracted GTFS directory, or None if not downloaded."""
    meta = _read_metadata()
    extract_dir = meta.get("extract_dir")
    if extract_dir:
        p = Path(extract_dir)
        if p.exists() and (p / "stops.txt").exists():
            return p
    return None


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


def download_latest_gtfs(
    force: bool = False,
    timeout: float = 120.0,
) -> Path:
    """
    Download and extract the latest GTFS from DTPM.

    Returns the path to the extracted directory containing CSV files.
    If the data is already current and force=False, returns the existing path.
    """
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
    zip_path = GTFS_DIR / filename

    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)

    logger.info("Downloaded %s (%.1f MB)", zip_path.name, zip_path.stat().st_size / 1e6)

    extract_dir = GTFS_DIR / zip_path.stem
    if extract_dir.exists():
        import shutil
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    # Some GTFS zips nest files inside a subfolder — flatten if needed
    txt_files = list(extract_dir.rglob("stops.txt"))
    if txt_files and txt_files[0].parent != extract_dir:
        nested = txt_files[0].parent
        for item in nested.iterdir():
            item.rename(extract_dir / item.name)

    _write_metadata({
        "url": url,
        "filename": filename,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "extract_dir": str(extract_dir),
        "zip_size_bytes": zip_path.stat().st_size,
    })

    logger.info("GTFS extracted to %s", extract_dir)
    return extract_dir


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
