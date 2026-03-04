"""
geocoding.py
============
Thin wrapper around OpenStreetMap Nominatim for forward and reverse geocoding.

All results are cached to a local JSON file (geocode_cache.json) so repeated
lookups are instant and the app works offline after the first query.

Public API
----------
  geocode(query)              -> {"lat": float, "lon": float, "display_name": str} | None
  reverse_geocode(lat, lon)   -> str  (human-readable address)
"""

from __future__ import annotations

import json
import time
import hashlib
import logging
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

log = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_FILE = Path(__file__).parent / "geocode_cache.json"
_CACHE: dict = {}


def _load_cache() -> None:
    global _CACHE
    if CACHE_FILE.exists():
        try:
            _CACHE = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {}


def _save_cache() -> None:
    try:
        CACHE_FILE.write_text(json.dumps(_CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"Could not save geocode cache: {e}")


def _cache_key(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode()).hexdigest()


_load_cache()

# ── HTTP helper ───────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": "NouakchottTransportDashboard/1.0 (academic project)",
    "Accept-Language": "en,fr",
}
_TIMEOUT = 6  # seconds
_LAST_CALL = 0.0
_MIN_INTERVAL = 1.1  # Nominatim rate limit: max 1 req/s


def _get_json(url: str) -> dict | list | None:
    """HTTP GET with rate limiting, retries, and error handling."""
    global _LAST_CALL
    now = time.time()
    wait = _MIN_INTERVAL - (now - _LAST_CALL)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL = time.time()

    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        log.warning(f"HTTP {e.code} for {url}")
    except URLError as e:
        log.warning(f"Network error: {e.reason}")
    except Exception as e:
        log.warning(f"Geocoding request failed: {e}")
    return None


# ── Forward geocoding ─────────────────────────────────────────────────────────

# Bounding box around Nouakchott to bias results
_VIEWBOX = "-16.15,17.90,-15.75,18.25"  # W,S,E,N


def geocode(query: str) -> dict | None:
    """
    Convert a place name / address string to coordinates.

    Returns
    -------
    {"lat": float, "lon": float, "display_name": str}  or  None
    """
    if not query or not query.strip():
        return None

    key = _cache_key("fwd", query.strip().lower())
    if key in _CACHE:
        return _CACHE[key]

    params = urlencode({
        "q": query.strip() + ", Nouakchott, Mauritanie",
        "format": "json",
        "limit": 1,
        "viewbox": _VIEWBOX,
        "bounded": 1,
        "addressdetails": 0,
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    data = _get_json(url)

    if not data:
        # Retry without bounding box
        params2 = urlencode({
            "q": query.strip() + ", Nouakchott, Mauritanie",
            "format": "json",
            "limit": 1,
        })
        url2 = f"https://nominatim.openstreetmap.org/search?{params2}"
        data = _get_json(url2)

    if data and isinstance(data, list) and len(data) > 0:
        r = data[0]
        result = {
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "display_name": r.get("display_name", query),
        }
        _CACHE[key] = result
        _save_cache()
        return result

    _CACHE[key] = None  # cache negative result too
    _save_cache()
    return None


# ── Reverse geocoding ─────────────────────────────────────────────────────────

def reverse_geocode(lat: float, lon: float) -> str:
    """
    Convert (lat, lon) to a human-readable address string.
    Falls back to "lat, lon" if the service is unavailable.
    """
    key = _cache_key("rev", f"{lat:.5f}", f"{lon:.5f}")
    if key in _CACHE:
        return _CACHE[key]

    params = urlencode({
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "format": "json",
        "zoom": 17,
        "addressdetails": 1,
    })
    url = f"https://nominatim.openstreetmap.org/reverse?{params}"
    data = _get_json(url)

    if data and "display_name" in data:
        # Build a short version: road + neighbourhood + city
        addr = data.get("address", {})
        parts = [
            addr.get("road") or addr.get("footway") or addr.get("path"),
            addr.get("neighbourhood") or addr.get("suburb"),
            addr.get("city") or addr.get("town") or "Nouakchott",
        ]
        short = ", ".join(p for p in parts if p)
        result = short or data["display_name"]
    else:
        result = f"{lat:.5f}, {lon:.5f}"

    _CACHE[key] = result
    _save_cache()
    return result
