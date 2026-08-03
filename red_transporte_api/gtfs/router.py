"""
RAPTOR — Round-Based Public Transit Optimized Router for GTFS data.

Based on: "Round-Based Public Transit Routing" (Delling et al., ALENEX 2015)
Adapted for frequency-based GTFS (Santiago RED / DTPM system).

Features:
- Pareto-optimal routing (arrival time × number of transfers)
- Frequency-based average wait time by time-of-day
- Walking transfers between nearby stops (spatial grid index)
- Chilean RED fare calculation (transbordos, punta/valle/baja)
- Multi-modal: bus, metro, MetroTren Nos

Transfer rules modelled (red.cl):
- Máximo 2 transbordos (3 etapas) dentro de 120 min
- Ventana de transbordo: 120 min desde primera validación
- Tarifa integrada: se paga el máximo entre bus ($795) y metro/tren (variable)
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field

from .parser import GTFSData, Stop, Route, haversine

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────

WALK_SPEED_KMH = 4.5
MAX_WALK_KM = 0.5
MAX_WALK_NEIGHBORS = 20
DEFAULT_HEADWAY_SECS = 600
BOARD_PENALTY_SECS = 30
MAX_ROUNDS = 4
TRANSFER_WINDOW_SECS = 7200
MAX_JOURNEY_SECS = 7200

# RED fares (CLP)
BUS_FARE = 795
METRO_FARE_PUNTA = 895
METRO_FARE_VALLE = 815
METRO_FARE_BAJA = 735
STUDENT_FARE = 260
SENIOR_FARE = 390


# ── Helpers ──────────────────────────────────────────────────

def time_to_secs(t: str) -> int:
    parts = t.strip().split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def secs_to_time(s: int) -> str:
    h, rem = divmod(max(0, int(s)), 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def secs_to_human(s: int) -> str:
    m = round(s / 60)
    if m < 60:
        return f"{m} min"
    h, rm = divmod(m, 60)
    return f"{h}h {rm}min" if rm else f"{h}h"


def _fare_periodo(dep_secs: int) -> str:
    minutes = dep_secs // 60
    hour = dep_secs // 3600
    if 7 <= hour < 9 or 18 <= hour < 20:
        return "punta"
    if 6 <= hour < 7:
        return "baja"
    if minutes >= 20 * 60 + 45 and minutes < 23 * 60:
        return "baja"
    return "valle"


# ── Result dataclasses ───────────────────────────────────────

@dataclass
class RouteLeg:
    mode: str
    route_id: str = ""
    route_name: str = ""
    route_color: str = ""
    direction: int = 0
    board_stop_id: str = ""
    board_stop_name: str = ""
    alight_stop_id: str = ""
    alight_stop_name: str = ""
    num_stops: int = 0
    duration_secs: int = 0
    wait_secs: int = 0
    walk_distance_m: int = 0


@dataclass
class FareInfo:
    total: int = 0
    periodo: str = ""
    fare_type: str = "normal"
    breakdown: list[dict] = field(default_factory=list)


@dataclass
class RoutingResult:
    found: bool = False
    total_time_secs: int = 0
    total_time_human: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    walk_time_secs: int = 0
    ride_time_secs: int = 0
    wait_time_secs: int = 0
    transfers: int = 0
    total_walk_m: int = 0
    legs: list[RouteLeg] = field(default_factory=list)
    fare: FareInfo = field(default_factory=FareInfo)
    origin_stop_id: str = ""
    origin_stop_name: str = ""
    dest_stop_id: str = ""
    dest_stop_name: str = ""


# ── RAPTOR Router ────────────────────────────────────────────

class TransitRouter:
    """
    RAPTOR-based transit router.

    Rounds:
      k=1 → direct (0 transfers)
      k=2 → 1 transfer
      k=3 → 2 transfers (max for RED)

    Each round:
      1. Route scanning — ride transit, update arrival times
      2. Transfer step  — walk to nearby stops
    """

    def __init__(self, gtfs: GTFSData):
        self.gtfs = gtfs
        self._walk_neighbors: dict[str, list[tuple[str, int, int]]] = {}
        self._routes_at_stop: dict[str, set[tuple[str, int]]] = defaultdict(set)
        self._route_stops: dict[tuple[str, int], list[tuple[str, int]]] = {}
        self._stop_index: dict[tuple[str, int, str], int] = {}
        self._freq_bands: dict[tuple[str, int, str], list[tuple[int, int, int, str]]] = defaultdict(list)
        self._trip_profiles: dict[str, dict[str, int]] = {}
        self._build()

    # ── Index construction ───────────────────────────────────

    def _build(self):
        logger.info("Building RAPTOR indices...")
        self._build_route_patterns()
        self._build_freq_index()
        self._build_walk_index()
        s = self.stats()
        logger.info(
            "RAPTOR ready: %d patterns, %d walk-pairs, %d freq-bands",
            s["route_patterns"], s["walk_pairs"], s["freq_bands"],
        )

    def _build_route_patterns(self):
        trips_by_rd: dict[tuple[str, int], list] = defaultdict(list)
        for trip in self.gtfs.trips.values():
            trips_by_rd[(trip.route_id, trip.direction_id)].append(trip)

        for (route_id, direction), trips in trips_by_rd.items():
            for trip in trips:
                st_list = self.gtfs.stop_times_by_trip.get(trip.trip_id, [])
                if not st_list:
                    continue
                profile = {}
                for st in sorted(st_list, key=lambda s: s.stop_sequence):
                    try:
                        profile[st.stop_id] = time_to_secs(st.arrival_time)
                    except (ValueError, IndexError):
                        continue
                if profile:
                    self._trip_profiles[trip.trip_id] = profile

            rep = None
            for pref in ("L", "S", "D"):
                for t in trips:
                    if t.service_id == pref and self.gtfs.stop_times_by_trip.get(t.trip_id):
                        rep = t
                        break
                if rep:
                    break
            if not rep:
                for t in trips:
                    if self.gtfs.stop_times_by_trip.get(t.trip_id):
                        rep = t
                        break
            if not rep:
                continue

            st_sorted = sorted(
                self.gtfs.stop_times_by_trip[rep.trip_id],
                key=lambda s: s.stop_sequence,
            )
            stops_times = []
            for st in st_sorted:
                try:
                    stops_times.append((st.stop_id, time_to_secs(st.arrival_time)))
                except (ValueError, IndexError):
                    continue
            if not stops_times:
                continue

            self._route_stops[(route_id, direction)] = stops_times
            for i, (sid, _) in enumerate(stops_times):
                self._stop_index[(route_id, direction, sid)] = i
                self._routes_at_stop[sid].add((route_id, direction))

    def _build_freq_index(self):
        for trip in self.gtfs.trips.values():
            for f in self.gtfs.frequencies.get(trip.trip_id, []):
                try:
                    start = time_to_secs(f.start_time)
                    end = time_to_secs(f.end_time)
                    key = (trip.route_id, trip.direction_id, trip.service_id)
                    self._freq_bands[key].append((start, end, f.headway_secs, trip.trip_id))
                except (ValueError, IndexError):
                    continue
        for key in self._freq_bands:
            self._freq_bands[key].sort()

    def _build_walk_index(self):
        GRID = 0.005
        grid: dict[tuple[int, int], list[str]] = defaultdict(list)
        for stop in self.gtfs.stops.values():
            if stop.location_type != 0:
                continue
            cell = (math.floor(stop.stop_lat / GRID), math.floor(stop.stop_lon / GRID))
            grid[cell].append(stop.stop_id)

        for stop in self.gtfs.stops.values():
            if stop.location_type != 0:
                continue
            cx = math.floor(stop.stop_lat / GRID)
            cy = math.floor(stop.stop_lon / GRID)
            nbrs: list[tuple[str, int, int]] = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for nid in grid.get((cx + dx, cy + dy), []):
                        if nid == stop.stop_id:
                            continue
                        n = self.gtfs.stops.get(nid)
                        if not n:
                            continue
                        d = haversine(stop.stop_lat, stop.stop_lon, n.stop_lat, n.stop_lon)
                        if d <= MAX_WALK_KM:
                            nbrs.append((nid, int(d / WALK_SPEED_KMH * 3600), int(d * 1000)))
            if nbrs:
                nbrs.sort(key=lambda x: x[1])
                self._walk_neighbors[stop.stop_id] = nbrs[:MAX_WALK_NEIGHBORS]

    # ── Query helpers ────────────────────────────────────────

    def get_headway(self, route_id: str, direction: int, service_id: str, t: int) -> int:
        for start, end, hw, _ in self._freq_bands.get((route_id, direction, service_id), []):
            if start <= t < end:
                return hw
        return DEFAULT_HEADWAY_SECS

    @staticmethod
    def _service_for_day(day_code: str) -> str:
        m = {
            "l": "L", "lu": "L", "ma": "L", "mi": "L", "ju": "L", "vi": "L",
            "monday": "L", "tuesday": "L", "wednesday": "L", "thursday": "L", "friday": "L",
            "weekday": "L", "laboral": "L",
            "s": "S", "sa": "S", "saturday": "S", "sab": "S", "sabado": "S",
            "d": "D", "do": "D", "sunday": "D", "dom": "D", "domingo": "D",
        }
        return m.get(day_code.lower().strip(), day_code.upper().strip())

    def stats(self) -> dict:
        return {
            "stops": len(self.gtfs.stops),
            "routes": len(self.gtfs.routes),
            "route_patterns": len(self._route_stops),
            "walk_pairs": sum(len(v) for v in self._walk_neighbors.values()),
            "freq_bands": sum(len(v) for v in self._freq_bands.values()),
            "trip_profiles": len(self._trip_profiles),
        }

    # ── Main entry point ─────────────────────────────────────

    def route(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        departure_time: str = "08:00:00",
        service_day: str = "L",
        walk_radius_km: float = 0.5,
        max_results: int = 3,
        max_transfers: int = 2,
        fare_type: str = "normal",
    ) -> list[RoutingResult]:
        """
        Find Pareto-optimal routes between two geographic coordinates.

        Returns up to *max_results* alternatives ordered by total travel time.
        Each alternative has a different number of transfers (RAPTOR rounds).
        """
        service_id = self._service_for_day(service_day)
        dep_secs = time_to_secs(departure_time)
        max_rounds = min(max_transfers + 1, MAX_ROUNDS)

        # Walk-only option
        direct_km = haversine(from_lat, from_lon, to_lat, to_lon)
        walk_only: RoutingResult | None = None
        if direct_km <= MAX_WALK_KM * 2:
            ws = int(direct_km / WALK_SPEED_KMH * 3600)
            walk_only = RoutingResult(
                found=True, total_time_secs=ws, total_time_human=secs_to_human(ws),
                departure_time=secs_to_time(dep_secs),
                arrival_time=secs_to_time(dep_secs + ws),
                walk_time_secs=ws, total_walk_m=int(direct_km * 1000),
                legs=[RouteLeg(mode="walk", duration_secs=ws, walk_distance_m=int(direct_km * 1000))],
                fare=self._calc_fare([], dep_secs, fare_type),
            )

        origin_stops = self.gtfs.get_nearby_stops(from_lat, from_lon, walk_radius_km, limit=15)
        dest_stops = self.gtfs.get_nearby_stops(to_lat, to_lon, walk_radius_km, limit=15)
        if not origin_stops or not dest_stops:
            return [walk_only] if walk_only else [RoutingResult(found=False)]

        origin_arrivals: dict[str, int] = {}
        origin_walk_info: dict[str, tuple[int, int]] = {}
        for stop, d in origin_stops:
            ws = int(d / WALK_SPEED_KMH * 3600)
            wm = int(d * 1000)
            origin_arrivals[stop.stop_id] = dep_secs + ws
            origin_walk_info[stop.stop_id] = (ws, wm)

        dest_walk: dict[str, tuple[int, int]] = {}
        for stop, d in dest_stops:
            dest_walk[stop.stop_id] = (int(d / WALK_SPEED_KMH * 3600), int(d * 1000))
        dest_ids = set(dest_walk.keys())

        # ── Run RAPTOR ───────────────────────────────────────
        best, round_tau, parents = self._raptor(origin_arrivals, dep_secs, service_id, max_rounds)

        # Collect Pareto-optimal results
        prev_best_total = float("inf")
        pareto: list[tuple[int, str, int]] = []  # (round, stop_id, total_secs)

        for k in range(1, max_rounds + 1):
            tau_k = round_tau[k]
            best_for_k: tuple[int, str] | None = None
            for sid in dest_ids:
                arr = tau_k.get(sid, float("inf"))
                if arr >= float("inf"):
                    continue
                fw, _ = dest_walk[sid]
                total = (arr + fw) - dep_secs
                if total >= MAX_JOURNEY_SECS:
                    continue
                if best_for_k is None or total < best_for_k[0]:
                    best_for_k = (total, sid)
            if best_for_k and best_for_k[0] < prev_best_total:
                pareto.append((k, best_for_k[1], best_for_k[0]))
                prev_best_total = best_for_k[0]

        results: list[RoutingResult] = []
        for k, dest_sid, _ in pareto:
            fw, fm = dest_walk[dest_sid]
            journey = self._reconstruct(parents, dest_sid, k, origin_walk_info)
            if journey is None:
                continue
            result = self._build_result(journey, dep_secs, fw, fm, dest_sid, fare_type)
            results.append(result)
            if len(results) >= max_results:
                break

        if walk_only:
            results.append(walk_only)
        if not results:
            return [RoutingResult(found=False)]
        results.sort(key=lambda r: r.total_time_secs)
        return results[:max_results]

    # ── Core RAPTOR ──────────────────────────────────────────

    def _raptor(
        self,
        origin_arrivals: dict[str, int],
        dep_secs: int,
        service_id: str,
        max_rounds: int,
    ) -> tuple[dict[str, float], list[dict[str, float]], list[dict]]:
        """
        Run frequency-based RAPTOR.

        Returns:
          best:       stop_id → best arrival (across all rounds)
          round_tau:  list of per-round {stop_id → arrival} (index 0..max_rounds)
          parents:    list of per-round parent dicts for reconstruction
        """
        INF = float("inf")
        best: dict[str, float] = {}
        prev_tau: dict[str, float] = {}
        round_tau: list[dict[str, float]] = [{} for _ in range(max_rounds + 1)]
        parents: list[dict[str, tuple]] = [{} for _ in range(max_rounds + 1)]
        max_time = dep_secs + MAX_JOURNEY_SECS

        # Round 0: seed with origin walks
        marked: set[str] = set()
        for sid, arr in origin_arrivals.items():
            best[sid] = arr
            prev_tau[sid] = arr
            round_tau[0][sid] = arr
            marked.add(sid)
            ws = arr - dep_secs
            wm = int(ws / 3600 * WALK_SPEED_KMH * 1000)
            parents[0][sid] = ("origin", ws, wm)

        # Initial transfers from origin stops
        for sid in list(marked):
            arr = prev_tau[sid]
            for nid, walk_s, walk_m in self._walk_neighbors.get(sid, []):
                new_arr = arr + walk_s
                if new_arr < best.get(nid, INF) and new_arr <= max_time:
                    best[nid] = new_arr
                    prev_tau[nid] = new_arr
                    round_tau[0][nid] = new_arr
                    marked.add(nid)
                    parents[0][nid] = ("transfer", sid, walk_s, walk_m)

        for k in range(1, max_rounds + 1):
            cur_tau: dict[str, float] = dict(prev_tau)
            new_marked: set[str] = set()

            # 1. Route scanning
            Q: dict[tuple[str, int], int] = {}
            for p in marked:
                for route_id, direction in self._routes_at_stop.get(p, set()):
                    idx = self._stop_index.get((route_id, direction, p))
                    if idx is None:
                        continue
                    key = (route_id, direction)
                    if key not in Q or idx < Q[key]:
                        Q[key] = idx

            for (route_id, direction), start_idx in Q.items():
                stops_times = self._route_stops.get((route_id, direction))
                if not stops_times:
                    continue

                eff_origin: float = INF
                board_idx: int = -1
                board_wait: int = 0

                for i in range(start_idx, len(stops_times)):
                    sid, cum = stops_times[i]

                    # Arrival if riding
                    if board_idx >= 0 and i > board_idx:
                        arrival = eff_origin + cum
                        if arrival < min(best.get(sid, INF), cur_tau.get(sid, INF)):
                            if arrival <= max_time:
                                cur_tau[sid] = arrival
                                best[sid] = arrival
                                new_marked.add(sid)
                                ride = cum - stops_times[board_idx][1]
                                parents[k][sid] = (
                                    "route", route_id, direction,
                                    stops_times[board_idx][0],
                                    board_idx, i, board_wait, ride,
                                )

                    # Try boarding
                    prev_arr = prev_tau.get(sid, INF)
                    if prev_arr < INF:
                        hw = self.get_headway(route_id, direction, service_id, int(prev_arr))
                        wait = hw // 2 + BOARD_PENALTY_SECS
                        cand = prev_arr + wait - cum
                        if cand < eff_origin:
                            eff_origin = cand
                            board_idx = i
                            board_wait = wait

            # 2. Transfer step
            transfer_marked: set[str] = set()
            for p in new_marked:
                arr_p = cur_tau.get(p, INF)
                if arr_p >= INF:
                    continue
                for nid, walk_s, walk_m in self._walk_neighbors.get(p, []):
                    new_arr = arr_p + walk_s
                    if new_arr < min(best.get(nid, INF), cur_tau.get(nid, INF)):
                        if new_arr <= max_time:
                            cur_tau[nid] = new_arr
                            best[nid] = new_arr
                            transfer_marked.add(nid)
                            parents[k][nid] = ("transfer", p, walk_s, walk_m)

            new_marked |= transfer_marked
            round_tau[k] = cur_tau
            prev_tau = cur_tau
            marked = new_marked

            if not marked:
                break

        return best, round_tau, parents

    # ── Journey reconstruction ───────────────────────────────

    def _reconstruct(
        self,
        parents: list[dict],
        dest_stop: str,
        max_round: int,
        origin_walk_info: dict[str, tuple[int, int]],
    ) -> list[tuple] | None:
        """Trace parent labels back to origin. Returns ordered segment list."""
        segments: list[tuple] = []
        stop = dest_stop
        k = max_round
        visited: set[tuple[int, str]] = set()

        while k >= 0:
            if (k, stop) in visited:
                break
            visited.add((k, stop))

            label = None
            for r in range(k, -1, -1):
                if stop in parents[r]:
                    label = parents[r][stop]
                    k = r
                    break

            if label is None:
                break

            if label[0] == "origin":
                ws, wm = origin_walk_info.get(stop, (label[1], label[2]))
                segments.append(("origin", stop, ws, wm))
                break

            if label[0] == "transfer":
                _, from_stop, walk_s, walk_m = label
                segments.append(("transfer", from_stop, stop, walk_s, walk_m))
                stop = from_stop
                continue

            if label[0] == "route":
                _, route_id, direction, board_stop, b_idx, a_idx, wait, ride = label
                segments.append(("route", route_id, direction, board_stop, stop,
                                 b_idx, a_idx, wait, ride))
                stop = board_stop
                k -= 1
                continue

        if not segments:
            return None
        segments.reverse()
        return segments

    # ── Build result from segments ───────────────────────────

    def _build_result(
        self, segments: list[tuple], dep_secs: int,
        final_walk_secs: int, final_walk_m: int,
        dest_stop_id: str, fare_type: str,
    ) -> RoutingResult:
        legs: list[RouteLeg] = []
        tw, twm, twait, tride = 0, 0, 0, 0
        transfers = -1

        for seg in segments:
            if seg[0] == "origin":
                _, stop_id, ws, wm = seg
                if ws > 0:
                    so = self.gtfs.stops.get(stop_id)
                    legs.append(RouteLeg(
                        mode="walk", duration_secs=ws, walk_distance_m=wm,
                        alight_stop_id=stop_id,
                        alight_stop_name=so.clean_name if so else "",
                    ))
                    tw += ws; twm += wm

            elif seg[0] == "transfer":
                _, fs, ts, ws, wm = seg
                if ws > 0:
                    fso = self.gtfs.stops.get(fs)
                    tso = self.gtfs.stops.get(ts)
                    if legs and legs[-1].mode == "walk":
                        legs[-1].duration_secs += ws
                        legs[-1].walk_distance_m += wm
                        legs[-1].alight_stop_id = ts
                        legs[-1].alight_stop_name = tso.clean_name if tso else ""
                    else:
                        legs.append(RouteLeg(
                            mode="walk", duration_secs=ws, walk_distance_m=wm,
                            board_stop_id=fs, board_stop_name=fso.clean_name if fso else "",
                            alight_stop_id=ts, alight_stop_name=tso.clean_name if tso else "",
                        ))
                    tw += ws; twm += wm

            elif seg[0] == "route":
                _, rid, direction, bs, als, bidx, aidx, wait, ride = seg
                transfers += 1
                route = self.gtfs.routes.get(rid)
                bso = self.gtfs.stops.get(bs)
                aso = self.gtfs.stops.get(als)
                ns = aidx - bidx

                if (legs and legs[-1].mode != "walk"
                        and legs[-1].route_id == rid and legs[-1].direction == direction):
                    legs[-1].alight_stop_id = als
                    legs[-1].alight_stop_name = aso.clean_name if aso else ""
                    legs[-1].num_stops += ns
                    legs[-1].duration_secs += ride
                    tride += ride
                else:
                    legs.append(RouteLeg(
                        mode=route.mode if route else "bus",
                        route_id=rid,
                        route_name=route.route_short_name if route else rid,
                        route_color=f"#{route.route_color}" if route and route.route_color else "",
                        direction=direction,
                        board_stop_id=bs, board_stop_name=bso.clean_name if bso else "",
                        alight_stop_id=als, alight_stop_name=aso.clean_name if aso else "",
                        num_stops=ns, duration_secs=ride, wait_secs=wait,
                    ))
                    twait += wait; tride += ride

        # Final walk
        if final_walk_secs > 0:
            ds = self.gtfs.stops.get(dest_stop_id)
            if legs and legs[-1].mode == "walk":
                legs[-1].duration_secs += final_walk_secs
                legs[-1].walk_distance_m += final_walk_m
            else:
                legs.append(RouteLeg(
                    mode="walk", duration_secs=final_walk_secs, walk_distance_m=final_walk_m,
                    board_stop_id=dest_stop_id,
                    board_stop_name=ds.clean_name if ds else "",
                ))
            tw += final_walk_secs; twm += final_walk_m

        total = tw + twait + tride
        transfers = max(0, transfers)

        osid = ""
        if segments:
            s0 = segments[0]
            osid = s0[1] if s0[0] in ("origin", "transfer") else s0[3]
        oso = self.gtfs.stops.get(osid)
        dso = self.gtfs.stops.get(dest_stop_id)
        fare = self._calc_fare(legs, dep_secs, fare_type)

        return RoutingResult(
            found=True, total_time_secs=total, total_time_human=secs_to_human(total),
            departure_time=secs_to_time(dep_secs),
            arrival_time=secs_to_time(dep_secs + total),
            walk_time_secs=tw, ride_time_secs=tride, wait_time_secs=twait,
            transfers=transfers, total_walk_m=twm, legs=legs, fare=fare,
            origin_stop_id=osid, origin_stop_name=oso.clean_name if oso else "",
            dest_stop_id=dest_stop_id, dest_stop_name=dso.clean_name if dso else "",
        )

    # ── Fare calculation ─────────────────────────────────────

    def _calc_fare(self, legs: list[RouteLeg], dep_secs: int, fare_type: str = "normal") -> FareInfo:
        """
        RED integrated fare.

        - Bus: $795 (all hours)
        - Metro/Tren Nos: $735 baja / $815 valle / $895 punta
        - Integrated: max(bus, metro) for the whole journey
        - Student: $260 flat, Senior: $390 flat
        - Walk-only journeys cost $0 regardless of fare_type
        """
        periodo = _fare_periodo(dep_secs)
        transit_legs = [leg for leg in legs if leg.route_id and leg.mode != "walk"]
        if not transit_legs:
            return FareInfo(total=0, periodo=periodo, fare_type=fare_type)
        if fare_type == "estudiante":
            return FareInfo(total=STUDENT_FARE, periodo=periodo, fare_type=fare_type)
        if fare_type == "adulto_mayor":
            return FareInfo(total=SENIOR_FARE, periodo=periodo, fare_type=fare_type)

        metro_fare = {"punta": METRO_FARE_PUNTA, "valle": METRO_FARE_VALLE, "baja": METRO_FARE_BAJA}[periodo]
        uses_metro = any(leg.mode in ("metro", "rail") for leg in transit_legs)
        uses_bus = any(leg.mode not in ("metro", "rail", "walk") for leg in transit_legs)
        breakdown = []

        for leg in transit_legs:
            if leg.mode in ("metro", "rail"):
                breakdown.append({"mode": leg.mode, "route": leg.route_name, "fare_mode": metro_fare})
            else:
                breakdown.append({"mode": leg.mode, "route": leg.route_name, "fare_mode": BUS_FARE})

        if uses_metro:
            total = max(BUS_FARE, metro_fare) if uses_bus else metro_fare
        elif uses_bus:
            total = BUS_FARE
        else:
            total = 0

        # Per-leg payment: the leg that raises the fare pays the difference.
        # This guarantees sum(paid) == total for every combination.
        remaining = total
        for bd in breakdown:
            paid = min(bd["fare_mode"], remaining)
            bd["paid"] = paid
            remaining -= paid

        return FareInfo(total=total, periodo=periodo, fare_type=fare_type, breakdown=breakdown)
