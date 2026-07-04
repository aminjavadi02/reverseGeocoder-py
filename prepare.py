from __future__ import annotations

import math
import pickle
import struct
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = ROOT / "reverse_geocoder" / "app" / "data" / "reverse_geocoder_cache.pkl"
COUNTRIES = DATA / "ne_10m_admin_0_countries.zip"
CITIES = DATA / "ne_10m_populated_places_simple.zip"
MARINE = DATA / "ne_10m_geography_marine_polys.zip"
CACHE_VERSION = 3

COUNTRY_CELL = 2.0
CITY_CELL = 1.0
MARINE_CELL = 2.0
COUNTRY_GRID_WIDTH = math.ceil(360 / COUNTRY_CELL)
CITY_GRID_WIDTH = math.ceil(360 / CITY_CELL)
MARINE_GRID_WIDTH = math.ceil(360 / MARINE_CELL)


def prepare(cache_path: Path = CACHE) -> Path:
    countries = _load_countries(COUNTRIES)
    cities = _load_cities(CITIES)
    marine = _load_marine(MARINE)
    payload = {
        "version": CACHE_VERSION,
        "country_cell": COUNTRY_CELL,
        "city_cell": CITY_CELL,
        "marine_cell": MARINE_CELL,
        "country_grid_width": COUNTRY_GRID_WIDTH,
        "city_grid_width": CITY_GRID_WIDTH,
        "marine_grid_width": MARINE_GRID_WIDTH,
        "countries": countries,
        "cities": cities,
        "marine": marine,
        "country_grid": _bbox_grid(countries, COUNTRY_CELL, COUNTRY_GRID_WIDTH),
        "city_grid": _city_grid(cities),
        "marine_grid": _bbox_grid(marine, MARINE_CELL, MARINE_GRID_WIDTH),
        "sources": {str(p): p.stat().st_mtime for p in (COUNTRIES, CITIES, MARINE)},
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    return cache_path


def _load_countries(path: Path) -> list[tuple[Any, ...]]:
    records = _read_zip_shapefile(path)
    countries = []
    for shape, row in records:
        if shape["type"] != 5:
            continue
        countries.append(
            (
                _field(row, "CONTINENT"),
                _field(row, "ADMIN") or _field(row, "NAME"),
                _clean_iso(_field(row, "ISO_A2")) or _clean_iso(_field(row, "ISO_A2_EH")),
                _clean_iso(_field(row, "ISO_A3")) or _clean_iso(_field(row, "ISO_A3_EH")),
                shape["bbox"],
                shape["rings"],
            )
        )
    return countries


def _load_cities(path: Path) -> list[tuple[Any, ...]]:
    records = _read_zip_shapefile(path)
    cities = []
    for shape, row in records:
        if shape["type"] != 1:
            continue
        lon, lat = shape["point"]
        cities.append((_field(row, "name") or _field(row, "NAME"), _clean_iso(_field(row, "iso_a2") or _field(row, "ISO_A2")), float(lat), float(lon)))
    return cities


def _load_marine(path: Path) -> list[tuple[Any, ...]]:
    records = _read_zip_shapefile(path)
    marine = []
    for shape, row in records:
        if shape["type"] != 5:
            continue
        marine.append((_field(row, "name") or _field(row, "label"), shape["bbox"], shape["rings"]))
    return marine


def _read_zip_shapefile(path: Path) -> list[tuple[dict, dict]]:
    with zipfile.ZipFile(path) as z:
        shp_name = next(n for n in z.namelist() if n.endswith(".shp"))
        dbf_name = next(n for n in z.namelist() if n.endswith(".dbf"))
        shapes = list(_read_shapes(z.read(shp_name)))
        rows = _read_dbf(z.read(dbf_name))
    if len(shapes) != len(rows):
        raise ValueError(f"{path.name}: {len(shapes)} shapes, {len(rows)} rows")
    return list(zip(shapes, rows))


def _read_shapes(data: bytes):
    offset = 100
    while offset < len(data):
        if offset + 8 > len(data):
            break
        length_words = struct.unpack(">i", data[offset + 4 : offset + 8])[0]
        start = offset + 8
        end = start + length_words * 2
        body = data[start:end]
        shape_type = struct.unpack("<i", body[:4])[0]
        if shape_type == 1:
            x, y = struct.unpack("<2d", body[4:20])
            yield {"type": shape_type, "point": (x, y)}
        elif shape_type == 5:
            bbox = struct.unpack("<4d", body[4:36])
            part_count, point_count = struct.unpack("<2i", body[36:44])
            parts = list(struct.unpack(f"<{part_count}i", body[44 : 44 + part_count * 4]))
            points_start = 44 + part_count * 4
            points = list(struct.unpack(f"<{point_count * 2}d", body[points_start : points_start + point_count * 16]))
            pairs = list(zip(points[0::2], points[1::2]))
            rings = []
            for i, part_start in enumerate(parts):
                part_end = parts[i + 1] if i + 1 < len(parts) else point_count
                ring = pairs[part_start:part_end]
                xs = [p[0] for p in ring]
                ys = [p[1] for p in ring]
                rings.append(((min(xs), min(ys), max(xs), max(ys)), ring))
            yield {"type": shape_type, "bbox": bbox, "rings": rings}
        offset = end


def _read_dbf(data: bytes) -> list[dict]:
    row_count = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    row_len = struct.unpack("<H", data[10:12])[0]
    fields = []
    pos = 32
    while pos < header_len - 1:
        raw = data[pos : pos + 32]
        if raw[0] == 13:
            break
        name = raw[:11].split(b"\0", 1)[0].decode("ascii").strip()
        fields.append((name, chr(raw[11]), raw[16]))
        pos += 32

    rows = []
    pos = header_len
    for _ in range(row_count):
        raw = data[pos : pos + row_len]
        pos += row_len
        if not raw or raw[0:1] == b"*":
            continue
        row = {}
        col = 1
        for name, kind, size in fields:
            value = _decode(raw[col : col + size])
            row[name] = _number(value) if kind in {"N", "F"} else value
            col += size
        rows.append(row)
    return rows


def _decode(raw: bytes) -> str:
    raw = raw.rstrip(b"\0 ").lstrip()
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin1")


def _number(value: str):
    if not value:
        return ""
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def _bbox_grid(items: list[tuple[Any, ...]], size: float, width: int) -> dict[int, list[int]]:
    grid: dict[int, list[int]] = {}
    for i, item in enumerate(items):
        minx, miny, maxx, maxy = item[-2]
        for cell in _cells_for_bbox(minx, miny, maxx, maxy, size):
            grid.setdefault(_cell_id(*cell, width), []).append(i)
    return grid


def _city_grid(cities: list[tuple[Any, ...]]) -> dict[int, list[int]]:
    grid: dict[int, list[int]] = {}
    for i, city in enumerate(cities):
        grid.setdefault(_cell_id(*_cell(city[2], city[3], CITY_CELL), CITY_GRID_WIDTH), []).append(i)
    return grid


def _cells_for_bbox(minx: float, miny: float, maxx: float, maxy: float, size: float):
    x1, y1 = _cell(miny, minx, size)
    x2, y2 = _cell(maxy, maxx, size)
    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            yield x, y


def _cell(lat: float, lon: float, size: float) -> tuple[int, int]:
    x = math.floor((lon + 180.0) / size)
    y = math.floor((lat + 90.0) / size)
    return x, y


def _cell_id(x: int, y: int, width: int) -> int:
    return y * width + x


def _field(row: dict, name: str):
    lowered = name.lower()
    for key, value in row.items():
        if key.lower() == lowered:
            return value
    return None


def _clean_iso(value):
    if not value or value == "-99":
        return None
    return str(value)


if __name__ == "__main__":
    print(prepare())
