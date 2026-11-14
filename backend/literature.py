"""Literature context via OpenAlex (free, no API key).

For a detected trend, surface peer-reviewed papers on the same topic so the
user can see whether the scientific literature agrees.
"""
import json
import math
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.openalex.org/works"
CROSSREF_BASE = "https://api.crossref.org/works"
UA = "TerraTrend/0.1 (NASA Space Apps Challenge; academic demo)"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_TTL = 30 * 24 * 3600
MAX_RETRIES = 3
RETRY_STATUS = {429, 500, 502, 503, 504}

CONCEPT = {
    "T2M": "air temperature",
    "T2M_MAX": "temperature extremes",
    "T2M_MIN": "temperature extremes",
    "PRECTOTCORR": "precipitation",
    "RH2M": "relative humidity",
    "WS2M": "wind speed",
    "ALLSKY_SFC_SW_DNI": "solar radiation",
    "ALLSKY_SFC_LW_DWN": "longwave radiation",
    "QV2M": "specific humidity",
    "PS": "surface pressure",
}

MIN_CITATIONS = 3


def _abstract_text(inv):
    """Rebuild plain text from OpenAlex's abstract_inverted_index."""
    if not isinstance(inv, dict) or not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort(key=lambda p: p[0])
    return " ".join(w for _, w in positions)


def _cache_path(key):
    safe = "".join(c if c.isalnum() else "_" for c in key)[:120]
    return CACHE_DIR / f"lit_{safe}.json"


def search_papers(variable, region_name, limit=5):
    """Return a list of papers relevant to this variable/region."""
    concept = CONCEPT.get(variable, "climate")
    query = f"{region_name} {concept} trend climate"

    cpath = _cache_path(query)
    if cpath.exists():
        try:
            blob = json.loads(cpath.read_text())
            if time.time() - blob.get("t", 0) < CACHE_TTL:
                return blob["data"]
        except Exception:  # noqa: BLE001
            pass

    params = {
        "search": query,
        "per-page": "25",
        "select": "title,publication_year,cited_by_count,doi,"
                  "primary_location,authorships,type,abstract_inverted_index",
        "filter": "from_publication_date:1995-01-01,is_retracted:false",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"

    try:
        data = None
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=45) as r:
                    data = json.loads(r.read())
                last_err = None
                break
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in RETRY_STATUS and attempt < MAX_RETRIES - 1:
                    time.sleep(1.5 * (attempt + 1) + random.random())
                    continue
                raise
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise
        if data is None:
            raise last_err or RuntimeError("empty response")
    except Exception as e:  # noqa: BLE001
        # OpenAlex goes down service-wide now and then (HTTP 503). Crossref is a
        # free, key-less fallback with the same basic metadata, so the panel
        # stays useful instead of showing OFFLINE.
        fb = _crossref(query, region_name, concept, limit)
        if fb.get("ok"):
            fb["degraded"] = True
            fb["fallback_from"] = f"{type(e).__name__}: {e}"
            _write_cache(cpath, fb)
            return fb
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "papers": [], "query": query, "retryable": True}

    region_words = [w.lower() for w in region_name.split() if len(w) > 3]
    concept_words = [w.lower() for w in concept.split() if len(w) > 3]

    def score(w):
        title = (w.get("title") or "").lower()
        abstract = _abstract_text(w.get("abstract_inverted_index")).lower()
        text = f"{title} {abstract}"
        s = 0.0
        # region in title is the strongest signal this paper is about this place
        for rw in region_words:
            if rw in title:
                s += 12
            elif rw in abstract:
                s += 5
        for cw in concept_words:
            if cw in title:
                s += 6
            elif cw in abstract:
                s += 2
        # citations help, but logarithmic so famous global papers don't dominate
        cites = w.get("cited_by_count") or 0
        s += math.log10(cites + 1) * 2.0
        return s

    ranked = sorted(data.get("results", []), key=score, reverse=True)

    papers = []
    for w in ranked:
        title = (w.get("title") or "").strip()
        if not title:
            continue
        venue = ""
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        if isinstance(src, dict):
            venue = src.get("display_name") or ""
        authors = []
        for a in (w.get("authorships") or [])[:3]:
            nm = (a.get("author") or {}).get("display_name")
            if nm:
                authors.append(nm)
        if len(w.get("authorships") or []) > 3:
            authors.append("et al.")
        papers.append({
            "title": title,
            "year": w.get("publication_year"),
            "citations": w.get("cited_by_count", 0),
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
            "url": w.get("doi") or "",
            "venue": venue,
            "authors": authors,
            "type": w.get("type", ""),
        })
        if len(papers) >= limit:
            break

    result = {"ok": True, "papers": papers, "query": query,
              "source": "OpenAlex"}

    _write_cache(cpath, result)
    return result


def _write_cache(cpath, result):
    try:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps({"t": time.time(), "data": result}))
    except OSError:
        pass


def _crossref(query, region_name, concept, limit):
    """Fallback literature source: Crossref (free, no API key)."""
    params = {
        "query": query,
        "rows": "25",
        "select": "title,author,issued,DOI,container-title,is-referenced-by-count",
    }
    url = f"{CROSSREF_BASE}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "papers": [], "query": query,
                "source": "Crossref", "error": f"{type(e).__name__}: {e}"}

    items = (data.get("message") or {}).get("items") or []
    region_words = [w.lower() for w in region_name.split() if len(w) > 3]
    concept_words = [w.lower() for w in concept.split() if len(w) > 3]

    papers = []
    for it in items:
        titles = it.get("title") or []
        title = (titles[0] if titles else "").strip()
        if not title:
            continue
        parts = (it.get("issued") or {}).get("date-parts") or [[None]]
        year = parts[0][0] if parts and parts[0] else None
        authors = []
        for a in (it.get("author") or [])[:3]:
            nm = " ".join(x for x in (a.get("given"), a.get("family")) if x)
            if nm:
                authors.append(nm)
        if len(it.get("author") or []) > 3:
            authors.append("et al.")
        venues = it.get("container-title") or []
        doi = it.get("DOI", "")
        papers.append({
            "title": title,
            "year": year,
            "citations": it.get("is-referenced-by-count", 0),
            "doi": doi,
            "url": f"https://doi.org/{doi}" if doi else "",
            "venue": venues[0] if venues else "",
            "authors": authors,
            "type": it.get("type", ""),
        })

    def score(p):
        t = (p["title"] or "").lower()
        s = sum(12.0 for w in region_words if w in t)
        s += sum(6.0 for w in concept_words if w in t)
        s += math.log10((p.get("citations") or 0) + 1) * 2.0
        return s

    papers.sort(key=score, reverse=True)
    return {"ok": True, "papers": papers[:limit], "query": query,
            "source": "Crossref"}
