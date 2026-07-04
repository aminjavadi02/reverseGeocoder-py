from __future__ import annotations

import math
import pickle
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

CACHE = Path(__file__).resolve().parent / "data" / "reverse_geocoder_cache.pkl"
CACHE_VERSION = 3
EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True, slots=True)
class GeoResult:
    continent: str | None
    country: str | None
    country_iso2: str | None
    country_iso3: str | None
    ocean: str | None
    city: str | None
    city_distance_km: float | None
    precision: str


C_CONTINENT, C_COUNTRY, C_ISO2, C_ISO3, C_BBOX, C_RINGS = range(6)
CITY_NAME, CITY_ISO2, CITY_LAT, CITY_LON = range(4)
M_NAME, M_BBOX, M_RINGS = range(3)


def get(lat: float, lon: float, *, city_radius_km: float = 50) -> GeoResult:
    _validate(lat, lon)
    data = _load()
    country = _find_country(data, lat, lon)
    ocean = None if country else _find_ocean(data, lat, lon)
    city = _find_city(data, lat, lon, city_radius_km, country)
    return GeoResult(
        continent=country[C_CONTINENT] if country else None,
        country=country[C_COUNTRY] if country else None,
        country_iso2=country[C_ISO2] if country else None,
        country_iso3=country[C_ISO3] if country else None,
        ocean=ocean[M_NAME] if ocean else None,
        city=city[0][CITY_NAME] if city else None,
        city_distance_km=round(city[1], 3) if city else None,
        precision="city" if city else "country" if country else "ocean" if ocean else "none",
    )


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    if not CACHE.exists():
        raise RuntimeError("missing reverse geocoder cache; run python3 prepare.py")
    with CACHE.open("rb") as f:
        data = pickle.load(f)
    if data.get("version") != CACHE_VERSION:
        raise RuntimeError("stale reverse geocoder cache; run python3 prepare.py")
    return data


def _find_country(data: dict[str, Any], lat: float, lon: float) -> tuple[Any, ...] | None:
    cell = _cell_id(*_cell(lat, lon, data["country_cell"]), data["country_grid_width"])
    for i in data["country_grid"].get(cell, []):
        country = data["countries"][i]
        if _in_bbox(lat, lon, country[C_BBOX]) and _in_polygon(lat, lon, country[C_RINGS]):
            return country
    return None


def _find_ocean(data: dict[str, Any], lat: float, lon: float) -> tuple[Any, ...] | None:
    cell = _cell_id(*_cell(lat, lon, data["marine_cell"]), data["marine_grid_width"])
    for i in data["marine_grid"].get(cell, []):
        ocean = data["marine"][i]
        if _in_bbox(lat, lon, ocean[M_BBOX]) and _in_polygon(lat, lon, ocean[M_RINGS]):
            return ocean
    return None


def _find_city(data: dict[str, Any], lat: float, lon: float, radius_km: float, country: tuple[Any, ...] | None) -> tuple[tuple[Any, ...], float] | None:
    size = data["city_cell"]
    radius_cells = max(1, math.ceil((radius_km / 111.0) / size))
    width = data["city_grid_width"]
    cx, cy = _cell(lat, lon, size)
    best_city = None
    best_distance = radius_km
    country_iso2 = country[C_ISO2] if country else None
    for x in range(cx - radius_cells, cx + radius_cells + 1):
        for y in range(cy - radius_cells, cy + radius_cells + 1):
            for i in data["city_grid"].get(_cell_id(x, y, width), []):
                city = data["cities"][i]
                if country_iso2 and city[CITY_ISO2] and city[CITY_ISO2] != country_iso2:
                    continue
                distance = _haversine(lat, lon, city[CITY_LAT], city[CITY_LON])
                if distance <= best_distance:
                    best_city = city
                    best_distance = distance
    return (best_city, best_distance) if best_city else None


def _in_polygon(lat: float, lon: float, rings: list[tuple]) -> bool:
    inside = False
    for bbox, points in rings:
        if _in_bbox(lat, lon, bbox) and _point_in_ring(lat, lon, points):
            inside = not inside
    return inside


def _point_in_ring(lat: float, lon: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if ((xi <= lon <= xj) or (xj <= lon <= xi)) and ((yi <= lat <= yj) or (yj <= lat <= yi)):
            cross = (lat - yi) * (xj - xi) - (lon - xi) * (yj - yi)
            if abs(cross) <= 1e-10:
                return True
        if (yi > lat) != (yj > lat):
            x_at_lat = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_at_lat:
                inside = not inside
        j = i
    return inside


def _in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    minx, miny, maxx, maxy = bbox
    return minx <= lon <= maxx and miny <= lat <= maxy


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _cell(lat: float, lon: float, size: float) -> tuple[int, int]:
    return math.floor((lon + 180.0) / size), math.floor((lat + 90.0) / size)


def _cell_id(x: int, y: int, width: int) -> int:
    return y * width + x


def _validate(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90:
        raise ValueError("lat must be between -90 and 90")
    if not -180 <= lon <= 180:
        raise ValueError("lon must be between -180 and 180")
