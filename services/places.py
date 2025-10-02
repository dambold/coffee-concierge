# services/places.py
from __future__ import annotations

import os
import requests
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any

# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

def _load_env_from_project_root() -> None:
    """
    Loads `.env` from the project root (parent of /services).
    Does nothing if python-dotenv is not installed or file missing.
    """
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    try:
        project_root = Path(__file__).resolve().parents[1]
        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
    except Exception:
        # Non-fatal: just skip
        pass


def _get_api_key() -> str:
    """
    Returns the Google Maps/Places API key.
    Priority:
      1) Environment variable GOOGLE_MAPS_API_KEY
      2) .env in project root (auto-loaded above)
    """
    _load_env_from_project_root()
    return (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance (meters) between two lat/lon points."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dl/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def _safe_get_json(url: str, params: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    """GET JSON with basic error shielding; returns dict with '_http_error' on failure."""
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"_http_error": str(e)}


def _pick_closest(results: list, lat: float, lng: float) -> Optional[dict]:
    """Pick the result closest to the target lat/lng."""
    if not results:
        return None
    return min(
        results,
        key=lambda x: _haversine_m(
            lat, lng,
            x.get("geometry", {}).get("location", {}).get("lat", lat),
            x.get("geometry", {}).get("location", {}).get("lng", lng),
        ),
    )


# ---------------------------------------------------------------------------
# Main lookups
# ---------------------------------------------------------------------------

@lru_cache(maxsize=256)
def get_place_details(
    name: str,
    lat: float,
    lng: float,
    city: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    High-resilience place lookup with multiple strategies.
    Returns:
      {
        "address": str | None,
        "phone": str | None,
        "website": str | None,
        "google_url": str | None,     # canonical Google Maps URL
        "place_id": str | None,
        "photo_reference": str | None,
        "debug": { ... }              # statuses/errors to help diagnose
      }
    If key missing or nothing found, returns a dict with "debug" explaining why.
    """
    key = _get_api_key()
    if not key:
        return {"debug": {"reason": "NO_KEY", "where": "env GOOGLE_MAPS_API_KEY or .env in project root"}}

    debug: Dict[str, Any] = {}
    place_id: Optional[str] = None

    # ---- Strategy A: Text Search (best general signal) ----
    ts_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    q = name if not city or city.lower() in name.lower() else f"{name} coffee {city}"
    ts_params = {"query": q, "location": f"{lat},{lng}", "radius": 5000, "key": key}
    ts = _safe_get_json(ts_url, ts_params)
    debug["textsearch"] = {"status": ts.get("status"), "error_message": ts.get("error_message"), "http_error": ts.get("_http_error")}

    if ts.get("status") == "OK" and ts.get("results"):
        best = _pick_closest(ts["results"], lat, lng)
        place_id = best.get("place_id") if best else None

    # ---- Strategy B: Nearby Search (type=cafe) ----
    if not place_id:
        ns_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        ns_params = {"location": f"{lat},{lng}", "radius": 2000, "type": "cafe", "keyword": name, "key": key}
        ns = _safe_get_json(ns_url, ns_params)
        debug["nearbysearch"] = {"status": ns.get("status"), "error_message": ns.get("error_message"), "http_error": ns.get("_http_error")}
        if ns.get("status") == "OK" and ns.get("results"):
            best = _pick_closest(ns["results"], lat, lng)
            place_id = best.get("place_id") if best else None

    # ---- Strategy C: Find Place from Text ----
    if not place_id:
        fp_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        fp_params = {
            "input": q,
            "inputtype": "textquery",
            "locationbias": f"point:{lat},{lng}",
            "fields": "place_id,geometry,name",
            "key": key,
        }
        fp = _safe_get_json(fp_url, fp_params)
        debug["findplacefromtext"] = {"status": fp.get("status"), "error_message": fp.get("error_message"), "http_error": fp.get("_http_error")}
        cands = fp.get("candidates") or []
        if fp.get("status") == "OK" and cands:
            shaped = [
                {"place_id": c.get("place_id"), "geometry": c.get("geometry", {"location": {"lat": lat, "lng": lng}})}
                for c in cands
            ]
            best = _pick_closest(shaped, lat, lng)
            place_id = best.get("place_id") if best else None

    if not place_id:
        return {"debug": debug or {"reason": "NO_MATCH"}}

    # ---- Details (ask for photos!) ----
    det_url = "https://maps.googleapis.com/maps/api/place/details/json"
    det_params = {
        "place_id": place_id,
        "fields": "formatted_address,formatted_phone_number,international_phone_number,website,url,photos",
        "key": key,
    }
    det = _safe_get_json(det_url, det_params)
    debug["details"] = {"status": det.get("status"), "error_message": det.get("error_message"), "http_error": det.get("_http_error")}

    if det.get("status") != "OK":
        return {"debug": debug, "place_id": place_id}

    res = det.get("result", {}) or {}
    phone = res.get("formatted_phone_number") or res.get("international_phone_number")
    photos = res.get("photos") or []
    photo_ref = photos[0].get("photo_reference") if photos else None

    return {
        "address": res.get("formatted_address"),
        "phone": phone,
        "website": res.get("website"),
        "google_url": res.get("url"),
        "place_id": place_id,
        "photo_reference": photo_ref,
        "debug": debug,
    }


# ---------------------------------------------------------------------------
# Photos (server-side fetch; keeps your key private)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def get_primary_photo_bytes(
    place_id: Optional[str] = None,
    photo_reference: Optional[str] = None,
    maxwidth: int = 640
) -> Optional[bytes]:
    """
    Returns JPEG/PNG bytes for a place's primary photo.
    You can pass either:
      - photo_reference (preferred if you already have it from details), or
      - place_id (we'll fetch details again to get photos).
    """
    key = _get_api_key()
    if not key:
        return None

    ref = (photo_reference or "").strip()

    if not ref and place_id:
        # Fetch minimal details to get a reference
        det_url = "https://maps.googleapis.com/maps/api/place/details/json"
        det_params = {"place_id": place_id, "fields": "photos", "key": key}
        det = _safe_get_json(det_url, det_params)
        if det.get("status") == "OK":
            photos = (det.get("result") or {}).get("photos") or []
            if photos:
                ref = photos[0].get("photo_reference") or ""

    if not ref:
        return None

    # Fetch actual photo bytes
    photo_url = "https://maps.googleapis.com/maps/api/place/photo"
    try:
        r = requests.get(photo_url, params={"maxwidth": maxwidth, "photo_reference": ref, "key": key}, timeout=15)
        r.raise_for_status()
        return r.content
    except Exception:
        return None
