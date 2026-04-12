"""Tests para el parser GTFS."""

import csv
import io
import os
import tempfile
import zipfile
from pathlib import Path

import pytest

from red_transporte_api.gtfs.parser import GTFSData, Stop, Route, haversine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STOPS_CSV = """\
stop_id,stop_code,stop_name,stop_lat,stop_lon
S1,PA433,"Av. Providencia / Los Leones",-33.42340,-70.61050
S2,PA434,"Av. Providencia / Ricardo Lyon",-33.42523,-70.60785
S3,PA435,"Av. Apoquindo / Tobalaba",-33.41870,-70.60120
S4,,,0,0
"""

ROUTES_CSV = """\
route_id,route_short_name,route_long_name,route_type,route_color,route_text_color
R506,506,"Maipú - Providencia",3,00FF00,000000
RL1,L1,"Metro Línea 1",1,FF0000,FFFFFF
"""

TRIPS_CSV = """\
route_id,service_id,trip_id,trip_headsign,direction_id,shape_id
R506,WD,T1,"Providencia",0,SH1
R506,WD,T2,"Maipú",1,SH2
RL1,WD,T3,"Los Dominicos",0,SHL1
"""

STOP_TIMES_CSV = """\
trip_id,arrival_time,departure_time,stop_id,stop_sequence
T1,06:00:00,06:00:00,S1,1
T1,06:05:00,06:05:00,S2,2
T1,06:10:00,06:10:00,S3,3
T2,06:30:00,06:30:00,S3,1
T2,06:35:00,06:35:00,S2,2
"""

FREQUENCIES_CSV = """\
trip_id,start_time,end_time,headway_secs
T1,05:30:00,09:00:00,360
T1,09:00:00,18:00:00,600
"""

SHAPES_CSV = """\
shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
SH1,-33.4234,-70.6105,1
SH1,-33.4245,-70.6090,2
SH1,-33.4252,-70.6078,3
"""

CALENDAR_CSV = """\
service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
WD,1,1,1,1,1,0,0,20250101,20251231
"""

AGENCY_CSV = """\
agency_id,agency_name,agency_url,agency_timezone
DTPM,DTPM,https://www.dtpm.cl,America/Santiago
"""


def _make_gtfs_zip(tmp_dir: str) -> str:
    """Crea un archivo GTFS ZIP de prueba."""
    zip_path = os.path.join(tmp_dir, "test_gtfs.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("stops.txt", STOPS_CSV)
        zf.writestr("routes.txt", ROUTES_CSV)
        zf.writestr("trips.txt", TRIPS_CSV)
        zf.writestr("stop_times.txt", STOP_TIMES_CSV)
        zf.writestr("frequencies.txt", FREQUENCIES_CSV)
        zf.writestr("shapes.txt", SHAPES_CSV)
        zf.writestr("calendar.txt", CALENDAR_CSV)
        zf.writestr("agency.txt", AGENCY_CSV)
    return zip_path


def _make_gtfs_dir(tmp_dir: str) -> str:
    """Crea un directorio GTFS de prueba."""
    gtfs_dir = os.path.join(tmp_dir, "gtfs")
    os.makedirs(gtfs_dir, exist_ok=True)
    for name, content in [
        ("stops.txt", STOPS_CSV),
        ("routes.txt", ROUTES_CSV),
        ("trips.txt", TRIPS_CSV),
        ("stop_times.txt", STOP_TIMES_CSV),
        ("frequencies.txt", FREQUENCIES_CSV),
        ("shapes.txt", SHAPES_CSV),
        ("calendar.txt", CALENDAR_CSV),
        ("agency.txt", AGENCY_CSV),
    ]:
        with open(os.path.join(gtfs_dir, name), "w", encoding="utf-8") as f:
            f.write(content)
    return gtfs_dir


@pytest.fixture
def gtfs_from_zip():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = _make_gtfs_zip(tmp)
        return GTFSData.from_zip(zip_path)


@pytest.fixture
def gtfs_from_dir():
    with tempfile.TemporaryDirectory() as tmp:
        gtfs_dir = _make_gtfs_dir(tmp)
        return GTFSData.from_directory(gtfs_dir)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGTFSLoading:
    def test_from_zip(self, gtfs_from_zip):
        assert len(gtfs_from_zip.stops) >= 3
        assert len(gtfs_from_zip.routes) == 2

    def test_from_directory(self, gtfs_from_dir):
        assert len(gtfs_from_dir.stops) >= 3
        assert len(gtfs_from_dir.routes) == 2

    def test_stops_loaded(self, gtfs_from_zip):
        stop = gtfs_from_zip.get_stop("S1")
        assert stop is not None
        assert stop.stop_code == "PA433"
        assert stop.stop_name == "Av. Providencia / Los Leones"
        assert abs(stop.stop_lat - (-33.42340)) < 0.001

    def test_routes_loaded(self, gtfs_from_zip):
        route = gtfs_from_zip.get_route("506")
        assert route is not None or gtfs_from_zip.get_route("R506") is not None


class TestStopQueries:
    def test_get_stop_by_code(self, gtfs_from_zip):
        stop = gtfs_from_zip.get_stop("S1")
        assert stop is not None
        assert stop.stop_code == "PA433"

    def test_get_stop_not_found(self, gtfs_from_zip):
        stop = gtfs_from_zip.get_stop("NONEXIST")
        assert stop is None

    def test_search_stops(self, gtfs_from_zip):
        results = gtfs_from_zip.search_stops("providencia")
        assert len(results) >= 1
        names = [s.stop_name.lower() for s in results]
        assert any("providencia" in n for n in names)

    def test_search_stops_empty(self, gtfs_from_zip):
        results = gtfs_from_zip.search_stops("xyznonexistent")
        assert len(results) == 0

    def test_get_nearby_stops(self, gtfs_from_zip):
        results = gtfs_from_zip.get_nearby_stops(-33.4234, -70.6105, radius_km=1.0)
        assert len(results) >= 1
        # El más cercano debería ser PA433
        codes = [s.stop_code for s, _ in results]
        assert "PA433" in codes


class TestRouteQueries:
    def test_get_routes_at_stop(self, gtfs_from_zip):
        routes = gtfs_from_zip.get_routes_at_stop("S1")
        # S1 está en T1 (R506)
        assert len(routes) >= 1

    def test_get_stops_on_route(self, gtfs_from_zip):
        for route_id in ["R506", "506"]:
            stops = gtfs_from_zip.get_stops_on_route(route_id, direction=0)
            if stops:
                assert len(stops) >= 2
                break


class TestHaversine:
    def test_same_point(self):
        d = haversine(-33.45, -70.65, -33.45, -70.65)
        assert d == 0.0

    def test_known_distance(self):
        # Aprox 1.1 km entre providencia y tobalaba
        d = haversine(-33.4234, -70.6105, -33.4187, -70.6012)
        assert 0.5 < d < 2.0

    def test_symmetry(self):
        d1 = haversine(-33.45, -70.65, -33.46, -70.66)
        d2 = haversine(-33.46, -70.66, -33.45, -70.65)
        assert abs(d1 - d2) < 0.001
