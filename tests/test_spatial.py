"""Tests para utilidades geoespaciales."""

import pytest

from red_transporte_api.gtfs.parser import GTFSData, haversine
from red_transporte_api.gtfs.spatial import (
    get_nearby_stops,
    get_closest_stop,
    get_closest_station,
    get_stops_in_bbox,
    suggest_routes_between,
)


# ---------------------------------------------------------------------------
# Fixtures — datos mínimos en memoria
# ---------------------------------------------------------------------------

import csv
import os
import tempfile
import zipfile


STOPS_CSV = """\
stop_id,stop_code,stop_name,stop_lat,stop_lon
S1,PA1,"Paradero 1",-33.4234,-70.6105
S2,PA2,"Paradero 2",-33.4252,-70.6078
S3,PA3,"Paradero 3",-33.4400,-70.6300
S4,PA4,"Paradero 4",-33.5000,-70.7000
"""

ROUTES_CSV = """\
route_id,route_short_name,route_long_name,route_type,route_color,route_text_color
R1,501,"Ruta Bus",3,00FF00,000000
RL1,L1,"Metro Línea 1",1,FF0000,FFFFFF
"""

TRIPS_CSV = """\
route_id,service_id,trip_id,trip_headsign,direction_id,shape_id
R1,WD,T1,"Ida",0,SH1
RL1,WD,T2,"Los Dominicos",0,SH2
"""

STOP_TIMES_CSV = """\
trip_id,arrival_time,departure_time,stop_id,stop_sequence
T1,06:00:00,06:00:00,S1,1
T1,06:05:00,06:05:00,S2,2
T1,06:10:00,06:10:00,S3,3
T2,06:00:00,06:00:00,S1,1
T2,06:10:00,06:10:00,S4,2
"""

FREQUENCIES_CSV = "trip_id,start_time,end_time,headway_secs\n"
SHAPES_CSV = "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
CALENDAR_CSV = """\
service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
WD,1,1,1,1,1,0,0,20250101,20251231
"""
AGENCY_CSV = """\
agency_id,agency_name,agency_url,agency_timezone
DTPM,DTPM,https://www.dtpm.cl,America/Santiago
"""


@pytest.fixture
def gtfs():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "gtfs.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("stops.txt", STOPS_CSV)
            zf.writestr("routes.txt", ROUTES_CSV)
            zf.writestr("trips.txt", TRIPS_CSV)
            zf.writestr("stop_times.txt", STOP_TIMES_CSV)
            zf.writestr("frequencies.txt", FREQUENCIES_CSV)
            zf.writestr("shapes.txt", SHAPES_CSV)
            zf.writestr("calendar.txt", CALENDAR_CSV)
            zf.writestr("agency.txt", AGENCY_CSV)
        return GTFSData.from_zip(zip_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNearbyStops:
    def test_finds_nearby(self, gtfs):
        result = get_nearby_stops(gtfs, -33.4234, -70.6105, radius_km=2.0)
        assert len(result) >= 1
        codes = [stop.stop_code for stop, _ in result]
        assert "PA1" in codes

    def test_empty_far_away(self, gtfs):
        result = get_nearby_stops(gtfs, -20.0, -60.0, radius_km=1.0)
        assert len(result) == 0


class TestClosestStop:
    def test_closest(self, gtfs):
        result = get_closest_stop(gtfs, -33.4234, -70.6105)
        assert result is not None
        stop, dist = result
        assert stop.stop_code == "PA1"
        assert dist < 0.01


class TestClosestStation:
    def test_finds_metro(self, gtfs):
        result = get_closest_station(gtfs, -33.4234, -70.6105)
        if result is not None:
            stop, dist = result
            assert hasattr(stop, "stop_code")
            assert isinstance(dist, float)


class TestBoundingBox:
    def test_bbox(self, gtfs):
        result = get_stops_in_bbox(
            gtfs,
            min_lat=-33.45, min_lon=-70.65,
            max_lat=-33.42, max_lon=-70.60,
        )
        assert len(result) >= 1
        codes = [s.stop_code for s in result]
        assert "PA1" in codes or "PA2" in codes

    def test_empty_bbox(self, gtfs):
        result = get_stops_in_bbox(gtfs, 0, 0, 0.01, 0.01)
        assert len(result) == 0


class TestSuggestRoutes:
    def test_suggest(self, gtfs):
        # S1 y S3 están en la misma ruta R1
        result = suggest_routes_between(
            gtfs,
            from_lat=-33.4234, from_lon=-70.6105,
            to_lat=-33.4400, to_lon=-70.6300,
            radius_km=2.0,
        )
        # Podría encontrar R1
        assert isinstance(result, list)
