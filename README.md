# Reverse Geocoder

Fast offline reverse geocoding for Python.

Give it a latitude and longitude and it returns a small `GeoResult` with the
matching continent, country, ISO codes, ocean or marine area, and nearest city
when one is close enough. It runs locally: no API key, no network call, no
database, and no paid reverse geocoding subscription.

## Installation And Usage

clone the project:

```bash
git clone https://github.com/aminjavadi02/reverseGeocoder-py.git
cd reverseGeocoder
python3 test.py
```

Use it directly from Python:

```python
from reverse_geocoder import get

place = get(35.6892, 51.3890)

print(place.country)          # Iran
print(place.country_iso2)     # IR
print(place.city)             # Tehran
print(place.precision)        # city
```

It is especially useful when you only need to know whether a user coordinate is
in or near a city:

```python
place = get(35.7000, 51.4000, city_radius_km=25)

is_tehran = place.city == "Tehran"
print(is_tehran)              # True
```

`get(lat, lon, city_radius_km=50)` returns:

```python
GeoResult(
    continent: str | None,
    country: str | None,
    country_iso2: str | None,
    country_iso3: str | None,
    ocean: str | None,
    city: str | None,
    city_distance_km: float | None,
    precision: str,
)
```

`precision` is `city`, `country`, `ocean`, or `none`.

## How It Works

Reverse Geocoder moves the expensive GIS work out of your request path. Natural Earth
country, city, and marine datasets are prepared ahead of time into a compact
pickle cache. At runtime, the package loads that cache once and uses simple
spatial grids to jump to the small area around the input coordinate.

That means a lookup does not scan every country polygon or every city. It checks
only nearby candidates, rejects most shapes with bounding boxes, then runs the
exact point-in-polygon and distance math only where it matters.

```text
Natural Earth data
        |
        v
prepared cache
        |
        v
get(lat, lon)
        |
        v
GeoResult(country, city, ocean, precision)
```

This is a compact reverse geocoder, not a street-address geocoder. It does not
return roads, postal codes, house numbers, or full administrative hierarchy.

The code is MIT licensed. The lookup data is derived from
[Natural Earth](https://www.naturalearthdata.com/), a public-domain map dataset.
