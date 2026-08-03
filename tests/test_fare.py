"""Tests para el cálculo de tarifa integrada RED."""

import pytest

from red_transporte_api.gtfs.router import TransitRouter, RouteLeg

# 10:00 local = valle (metro $815), 08:00 = punta ($895), 06:30 = baja ($735)
PUNTA = 8 * 3600
VALLE = 10 * 3600
BAJA = 6 * 3600 + 30 * 60


def _router():
    return TransitRouter.__new__(TransitRouter)


def _bus(route="506"):
    return RouteLeg(mode="bus", route_id=route, route_name=route, duration_secs=600)


def _metro(route="L1"):
    return RouteLeg(mode="metro", route_id=route, route_name=route, duration_secs=600)


def _walk():
    return RouteLeg(mode="walk", duration_secs=600, walk_distance_m=800)


class TestFare:
    def test_walk_only_cost_zero(self):
        fare = _router()._calc_fare([_walk()], VALLE)
        assert fare.total == 0
        assert fare.breakdown == []

    def test_walk_only_cost_zero_for_special_fares(self):
        for fare_type in ("estudiante", "adulto_mayor"):
            fare = _router()._calc_fare([_walk()], VALLE, fare_type)
            assert fare.total == 0, fare_type

    def test_bus_only(self):
        fare = _router()._calc_fare([_bus()], VALLE)
        assert fare.total == 795
        assert fare.breakdown[0]["paid"] == 795

    def test_metro_valle(self):
        fare = _router()._calc_fare([_metro()], VALLE)
        assert fare.total == 815

    def test_metro_punta(self):
        fare = _router()._calc_fare([_metro()], PUNTA)
        assert fare.total == 895

    def test_metro_baja(self):
        fare = _router()._calc_fare([_metro()], BAJA)
        assert fare.total == 735

    def test_bus_then_metro_breakdown_sums_to_total(self):
        fare = _router()._calc_fare([_bus(), _metro()], VALLE)
        assert fare.total == 815
        assert sum(b["paid"] for b in fare.breakdown) == fare.total
        assert fare.breakdown[0]["paid"] == 795
        assert fare.breakdown[1]["paid"] == 20

    def test_metro_then_bus_breakdown_sums_to_total(self):
        fare = _router()._calc_fare([_metro(), _bus()], VALLE)
        assert fare.total == 815
        assert sum(b["paid"] for b in fare.breakdown) == fare.total

    def test_two_metro_legs_single_fare(self):
        fare = _router()._calc_fare([_metro("L1"), _metro("L5")], VALLE)
        assert fare.total == 815
        assert sum(b["paid"] for b in fare.breakdown) == fare.total
        assert fare.breakdown[1]["paid"] == 0

    def test_student_flat(self):
        fare = _router()._calc_fare([_bus(), _metro()], VALLE, "estudiante")
        assert fare.total == 260

    def test_senior_flat(self):
        fare = _router()._calc_fare([_bus(), _metro()], VALLE, "adulto_mayor")
        assert fare.total == 390

    def test_walk_legs_ignored_in_breakdown(self):
        fare = _router()._calc_fare([_walk(), _bus(), _walk()], VALLE)
        assert fare.total == 795
        assert len(fare.breakdown) == 1
        assert fare.breakdown[0]["paid"] == 795
