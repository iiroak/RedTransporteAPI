"""
GTFS data parser for RED Metropolitana (Santiago, Chile).

Parses the official DTPM GTFS data to provide offline access to:
- Bus stops (paraderos): codes, names, coordinates
- Routes/services: names, colors, types
- Trips and schedules
- Stop sequences per route
- Shapes (route geometries)
"""
from __future__ import annotations

import csv
import io
import logging
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


@dataclass
class Stop:
    stop_id: str
    stop_code: str
    stop_name: str
    stop_lat: float
    stop_lon: float
    location_type: int = 0
    parent_station: str = ""
    wheelchair_boarding: int = 0
    level_id: str = ""

    @property
    def clean_name(self) -> str:
        if "-" in self.stop_name:
            return self.stop_name.split("-", 1)[1].strip()
        return self.stop_name


@dataclass
class Route:
    route_id: str
    agency_id: str
    route_short_name: str
    route_long_name: str
    route_desc: str
    route_type: int  # 3=Bus, 1=Metro, 2=Rail, 0=Tram
    route_color: str
    route_text_color: str

    @property
    def mode(self) -> str:
        return {0: "tram", 1: "metro", 2: "rail", 3: "bus"}.get(self.route_type, "unknown")


@dataclass
class Trip:
    route_id: str
    service_id: str
    trip_id: str
    trip_headsign: str
    direction_id: int
    shape_id: str


@dataclass
class StopTime:
    trip_id: str
    arrival_time: str
    departure_time: str
    stop_id: str
    stop_sequence: int


@dataclass
class Frequency:
    trip_id: str
    start_time: str
    end_time: str
    headway_secs: int


@dataclass
class ShapePoint:
    shape_id: str
    lat: float
    lon: float
    sequence: int


@dataclass
class Calendar:
    service_id: str
    monday: bool
    tuesday: bool
    wednesday: bool
    thursday: bool
    friday: bool
    saturday: bool
    sunday: bool
    start_date: str
    end_date: str


class GTFSData:
    """Parsed GTFS dataset with query helpers."""

    def __init__(self):
        self.stops: dict[str, Stop] = {}
        self.routes: dict[str, Route] = {}
        self.trips: dict[str, Trip] = {}
        self.stop_times_by_trip: dict[str, list[StopTime]] = {}
        self.frequencies: dict[str, list[Frequency]] = {}
        self.shapes: dict[str, list[ShapePoint]] = {}
        self.calendars: dict[str, Calendar] = {}
        self._stops_by_route: dict[str, list[str]] = {}
        self._routes_by_stop: dict[str, set[str]] = {}

    @classmethod
    def from_zip(cls, zip_path: str | Path) -> GTFSData:
        data = cls()
        zip_path = Path(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            data._load_stops(zf)
            data._load_routes(zf)
            data._load_trips(zf)
            data._load_calendars(zf)
            if "stop_times.txt" in zf.namelist():
                data._load_stop_times(zf)
            if "frequencies.txt" in zf.namelist():
                data._load_frequencies(zf)
            if "shapes.txt" in zf.namelist():
                data._load_shapes(zf)
        data._build_indices()
        return data

    @classmethod
    def from_directory(cls, dir_path: str | Path) -> GTFSData:
        data = cls()
        dir_path = Path(dir_path)
        data._load_stops_from_file(dir_path / "stops.txt")
        data._load_routes_from_file(dir_path / "routes.txt")
        data._load_trips_from_file(dir_path / "trips.txt")
        data._load_calendars_from_file(dir_path / "calendar.txt")
        st = dir_path / "stop_times.txt"
        if st.exists():
            data._load_stop_times_from_file(st)
        freq = dir_path / "frequencies.txt"
        if freq.exists():
            data._load_frequencies_from_file(freq)
        shapes = dir_path / "shapes.txt"
        if shapes.exists():
            data._load_shapes_from_file(shapes)
        data._build_indices()
        return data

    # ── Query methods ────────────────────────────────────────

    def get_stop(self, stop_id: str) -> Stop | None:
        return self.stops.get(stop_id) or self.stops.get(stop_id.upper())

    def search_stops(self, query: str, limit: int = 20) -> list[Stop]:
        q = query.lower()
        results = []
        for stop in self.stops.values():
            if stop.location_type != 0:
                continue
            if q in stop.stop_id.lower() or q in stop.stop_name.lower():
                results.append(stop)
                if len(results) >= limit:
                    break
        return results

    def get_nearby_stops(
        self, lat: float, lon: float, radius_km: float = 0.5, limit: int = 20
    ) -> list[tuple[Stop, float]]:
        results: list[tuple[Stop, float]] = []
        for stop in self.stops.values():
            if stop.location_type != 0:
                continue
            dist = haversine(lat, lon, stop.stop_lat, stop.stop_lon)
            if dist <= radius_km:
                results.append((stop, dist))
        results.sort(key=lambda x: x[1])
        return results[:limit]

    def get_route(self, route_id: str) -> Route | None:
        if route_id in self.routes:
            return self.routes[route_id]
        for r in self.routes.values():
            if r.route_short_name.lower() == route_id.lower():
                return r
        return None

    def get_routes_at_stop(self, stop_id: str) -> list[Route]:
        route_ids = self._routes_by_stop.get(stop_id, set())
        return [self.routes[rid] for rid in route_ids if rid in self.routes]

    def get_stops_on_route(self, route_id: str, direction: int = 0) -> list[Stop]:
        for trip in self.trips.values():
            if trip.route_id == route_id and trip.direction_id == direction:
                stop_times = self.stop_times_by_trip.get(trip.trip_id, [])
                stop_times.sort(key=lambda st: st.stop_sequence)
                return [
                    self.stops[st.stop_id]
                    for st in stop_times
                    if st.stop_id in self.stops
                ]
        return []

    def get_route_shape(self, route_id: str, direction: int = 0) -> list[ShapePoint]:
        for trip in self.trips.values():
            if trip.route_id == route_id and trip.direction_id == direction:
                points = self.shapes.get(trip.shape_id, [])
                return sorted(points, key=lambda p: p.sequence)
        return []

    def get_route_frequency(self, route_id: str, service_id: str = "L") -> list[Frequency]:
        for trip in self.trips.values():
            if trip.route_id == route_id and trip.service_id == service_id:
                return self.frequencies.get(trip.trip_id, [])
        return []

    # ── Loaders ──────────────────────────────────────────────

    def _read_csv(self, zf: zipfile.ZipFile, fname: str) -> Iterator[dict]:
        with zf.open(fname) as f:
            text = io.TextIOWrapper(f, encoding="utf-8-sig")
            yield from csv.DictReader(text)

    def _read_csv_file(self, path: Path) -> Iterator[dict]:
        with open(path, encoding="utf-8-sig", newline="") as f:
            yield from csv.DictReader(f)

    def _load_stops(self, zf: zipfile.ZipFile):
        for row in self._read_csv(zf, "stops.txt"):
            self._add_stop(row)

    def _load_stops_from_file(self, path: Path):
        for row in self._read_csv_file(path):
            self._add_stop(row)

    def _add_stop(self, row: dict):
        lat_str = row.get("stop_lat", "")
        lon_str = row.get("stop_lon", "")
        if not lat_str or not lon_str:
            return
        s = Stop(
            stop_id=row["stop_id"],
            stop_code=row.get("stop_code", ""),
            stop_name=row.get("stop_name", ""),
            stop_lat=float(lat_str),
            stop_lon=float(lon_str),
            location_type=int(row.get("location_type", 0) or 0),
            parent_station=row.get("parent_station", ""),
            wheelchair_boarding=int(row.get("wheelchair_boarding", 0) or 0),
            level_id=row.get("level_id", ""),
        )
        self.stops[s.stop_id] = s

    def _load_routes(self, zf: zipfile.ZipFile):
        for row in self._read_csv(zf, "routes.txt"):
            self._add_route(row)

    def _load_routes_from_file(self, path: Path):
        for row in self._read_csv_file(path):
            self._add_route(row)

    def _add_route(self, row: dict):
        r = Route(
            route_id=row["route_id"],
            agency_id=row.get("agency_id", ""),
            route_short_name=row.get("route_short_name", ""),
            route_long_name=row.get("route_long_name", ""),
            route_desc=row.get("route_desc", ""),
            route_type=int(row.get("route_type", 3)),
            route_color=row.get("route_color", ""),
            route_text_color=row.get("route_text_color", ""),
        )
        self.routes[r.route_id] = r

    def _load_trips(self, zf: zipfile.ZipFile):
        for row in self._read_csv(zf, "trips.txt"):
            self._add_trip(row)

    def _load_trips_from_file(self, path: Path):
        for row in self._read_csv_file(path):
            self._add_trip(row)

    def _add_trip(self, row: dict):
        t = Trip(
            route_id=row["route_id"],
            service_id=row.get("service_id", ""),
            trip_id=row["trip_id"],
            trip_headsign=row.get("trip_headsign", ""),
            direction_id=int(row.get("direction_id", 0) or 0),
            shape_id=row.get("shape_id", ""),
        )
        self.trips[t.trip_id] = t

    def _load_stop_times(self, zf: zipfile.ZipFile):
        for row in self._read_csv(zf, "stop_times.txt"):
            self._add_stop_time(row)

    def _load_stop_times_from_file(self, path: Path):
        for row in self._read_csv_file(path):
            self._add_stop_time(row)

    def _add_stop_time(self, row: dict):
        st = StopTime(
            trip_id=row["trip_id"],
            arrival_time=row.get("arrival_time", ""),
            departure_time=row.get("departure_time", ""),
            stop_id=row["stop_id"],
            stop_sequence=int(row.get("stop_sequence", 0)),
        )
        self.stop_times_by_trip.setdefault(st.trip_id, []).append(st)

    def _load_frequencies(self, zf: zipfile.ZipFile):
        for row in self._read_csv(zf, "frequencies.txt"):
            self._add_frequency(row)

    def _load_frequencies_from_file(self, path: Path):
        for row in self._read_csv_file(path):
            self._add_frequency(row)

    def _add_frequency(self, row: dict):
        f = Frequency(
            trip_id=row["trip_id"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            headway_secs=int(row["headway_secs"]),
        )
        self.frequencies.setdefault(f.trip_id, []).append(f)

    def _load_shapes(self, zf: zipfile.ZipFile):
        for row in self._read_csv(zf, "shapes.txt"):
            self._add_shape(row)

    def _load_shapes_from_file(self, path: Path):
        for row in self._read_csv_file(path):
            self._add_shape(row)

    def _add_shape(self, row: dict):
        sp = ShapePoint(
            shape_id=row["shape_id"],
            lat=float(row["shape_pt_lat"]),
            lon=float(row["shape_pt_lon"]),
            sequence=int(row["shape_pt_sequence"]),
        )
        self.shapes.setdefault(sp.shape_id, []).append(sp)

    def _load_calendars(self, zf: zipfile.ZipFile):
        for row in self._read_csv(zf, "calendar.txt"):
            self._add_calendar(row)

    def _load_calendars_from_file(self, path: Path):
        for row in self._read_csv_file(path):
            self._add_calendar(row)

    def _add_calendar(self, row: dict):
        c = Calendar(
            service_id=row["service_id"],
            monday=row["monday"] == "1",
            tuesday=row["tuesday"] == "1",
            wednesday=row["wednesday"] == "1",
            thursday=row["thursday"] == "1",
            friday=row["friday"] == "1",
            saturday=row["saturday"] == "1",
            sunday=row["sunday"] == "1",
            start_date=row["start_date"],
            end_date=row["end_date"],
        )
        self.calendars[c.service_id] = c

    def _build_indices(self):
        for trip in self.trips.values():
            stop_times = self.stop_times_by_trip.get(trip.trip_id, [])
            for st in stop_times:
                self._routes_by_stop.setdefault(st.stop_id, set()).add(trip.route_id)


# ── Utility ──────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two coordinates using the Haversine formula."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
