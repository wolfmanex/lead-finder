"""Find and download the open-data files (with a cache and a manual fallback). Standard library only."""
from __future__ import annotations

import logging
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from .config import CACHE_HOURS, RAW_DIR, SOURCES, USER_AGENT

log = logging.getLogger(__name__)


def _open(url: str, timeout: int = 120):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)  # honours HTTP(S)_PROXY settings


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.hrefs.append(v)


_page_cache: dict[str, list[str]] = {}


def _page_links(page: str) -> list[str]:
    if page not in _page_cache:
        with _open(page, 60) as r:
            html = r.read().decode("utf-8", "replace")
        p = _Links()
        p.feed(html)
        _page_cache[page] = [urljoin(page, h) for h in p.hrefs]
    return _page_cache[page]


def find_url(src: dict) -> str:
    rx = re.compile(src["pattern"])
    for page in src["pages"]:
        try:
            for url in _page_links(page):
                if rx.search(url.split("?")[0]):
                    return url
        except Exception as e:  # noqa: BLE001
            log.warning("Could not read %s (%s)", page, e)
    return src["fallback"]


def _fresh(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0 and (time.time() - path.stat().st_mtime) < CACHE_HOURS * 3600


def _download(url: str, dest: Path, progress=None) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _open(url, 300) as r:
        if "text/html" in (r.headers.get("Content-Type") or ""):
            raise RuntimeError(f"{url} returned a web page instead of a data file")
        total = int(r.headers.get("Content-Length") or 0)
        done, last = 0, 0.0
        with open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if progress and time.time() - last > 0.5:
                    last = time.time()
                    progress(f"Downloading {dest.name}: {done / 1e6:,.0f} MB"
                             + (f" of {total / 1e6:,.0f} MB" if total else ""))
    tmp.replace(dest)


def fetch_all(force: bool = False, offline: bool = False, progress=None) -> dict[str, Path]:
    """Return {source_key: local_path}. Reuses fresh files; offline mode only uses what is in data/raw."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    errors = []
    for key, src in SOURCES.items():
        dest = RAW_DIR / src["filename"]
        if offline or (not force and _fresh(dest)):
            if dest.exists():
                log.info("Using local %s", dest.name)
                out[key] = dest
                continue
            if offline:
                errors.append(f"{dest.name} is missing from {RAW_DIR}")
                continue
        url = find_url(src)
        log.info("Downloading %s from %s", dest.name, url)
        try:
            _download(url, dest, progress)
            out[key] = dest
        except Exception as e:  # noqa: BLE001 - report every failure together
            if dest.exists():
                log.warning("Download of %s failed (%s) - using the older local copy", dest.name, e)
                out[key] = dest
            else:
                errors.append(f"{dest.name}: download failed ({e}). Download it manually from "
                              f"{src['pages'][0]} and save it in {RAW_DIR}")
    if errors:
        raise RuntimeError("\n".join(errors))
    return out
