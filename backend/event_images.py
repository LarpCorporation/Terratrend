"""Curated event imagery, cached on disk.

The manifest in ``events/event_images.json`` lists Wikimedia Commons files that
were reviewed against the event they illustrate. Every entry carries its author
and licence, which must be shown with the picture.

Commons rate-limits bursts of requests, and a live demo must not depend on a
remote CDN at the moment a judge clicks. Each image is therefore downloaded
once into ``cache/images/`` and served from there; a failed refresh falls back
to the cached copy rather than showing a broken frame.
"""
import hashlib
import json
import urllib.parse
import urllib.request
import os
import tempfile
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent / "events" / "event_images.json"
CACHE = Path(__file__).resolve().parent / "cache" / "images"
USER_AGENT = "TerraTrend/1.0 (NASA Space Apps project; event imagery)"

_MAGIC = (
    (b"\x89PNG", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
)


def _load():
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f).get("events", {})
    except (OSError, ValueError):
        return {}


def _content_type(raw):
    for magic, ctype in _MAGIC:
        if raw.startswith(magic):
            return ctype
    return "application/octet-stream"


def _cache_path(event_id, index, url):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    safe = "".join(c for c in event_id if c.isalnum() or c in "-_")[:40]
    return CACHE / f"{safe}-{index}-{digest}"


def for_event(event_id):
    """Image records for one event, addressed through the local cache route."""
    entries = _load().get(event_id) or []
    out = []
    for index, item in enumerate(entries):
        out.append({
            "src": f"/api/event-image/{urllib.parse.quote(event_id)}/{index}",
            "caption": item.get("caption", ""),
            "artist": item.get("artist", ""),
            "licence": item.get("licence", ""),
            "page": item.get("page", ""),
            "title": item.get("title", ""),
            "width": item.get("width"),
            "height": item.get("height"),
        })
    return out


def has_images(event_id):
    return bool((_load().get(event_id) or []))


def image_bytes(event_id, index):
    """Return ``(bytes, content_type)`` for one image, caching the download."""
    entries = _load().get(event_id) or []
    if index < 0 or index >= len(entries):
        raise KeyError("No such image")
    url = entries[index]["url"]
    path = _cache_path(event_id, index, url)
    if path.is_file():
        raw = path.read_bytes()
        return raw, _content_type(raw)
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in {'upload.wikimedia.org','commons.wikimedia.org'}:
        raise ValueError('Only curated Wikimedia photograph URLs are supported')
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read(4_000_001)
    except Exception:
        if path.is_file():
            raw = path.read_bytes()
            return raw, _content_type(raw)
        raise
    if len(raw) > 4_000_000:
        raise ValueError('Photograph exceeds the 4 MB limit')
    if len(raw) < 64:
        raise ValueError("Image response was empty")
    CACHE.mkdir(parents=True, exist_ok=True)
    if _content_type(raw)=='application/octet-stream':raise ValueError('The photo source did not return an image')
    with tempfile.NamedTemporaryFile(dir=CACHE,delete=False) as f:
        temp=Path(f.name);f.write(raw)
    try:os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)
    return raw, _content_type(raw)


def warm(event_ids=None):
    """Download every curated image. Returns (ok, failed) counts."""
    entries = _load()
    ok = failed = 0
    for event_id, items in entries.items():
        if event_ids and event_id not in event_ids:
            continue
        for index in range(len(items)):
            try:
                image_bytes(event_id, index)
                ok += 1
            except Exception:  # noqa: BLE001
                failed += 1
    return ok, failed
