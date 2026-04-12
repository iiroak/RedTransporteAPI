"""Test script for the transit graph router."""
import sys
import time

sys.path.insert(0, ".")

from pathlib import Path
from red_transporte_api.gtfs.parser import GTFSData
from red_transporte_api.gtfs.router import TransitRouter, secs_to_human

GTFS_DIR = Path(r"C:\Users\Kaori\Desktop\RED\red_agent\gtfs_data\public_gtfs")

print("=" * 70)
print("TRANSIT ROUTER TEST")
print("=" * 70)

# 1. Load GTFS
print("\n[1] Loading GTFS data...")
t0 = time.time()
gtfs = GTFSData.from_directory(GTFS_DIR)
print(f"    Loaded in {time.time() - t0:.1f}s — {len(gtfs.stops)} stops, {len(gtfs.routes)} routes")

# 2. Build router
print("\n[2] Building transit graph...")
t0 = time.time()
router = TransitRouter(gtfs)
elapsed = time.time() - t0
print(f"    Built in {elapsed:.1f}s")
stats = router.stats()
for k, v in stats.items():
    print(f"    {k}: {v}")

# ── Test cases ───────────────────────────────────────────────
# Coordinates in Santiago:
# Plaza Italia:     -33.4372, -70.6340
# La Moneda:        -33.4422, -70.6537
# Estación Central: -33.4525, -70.6783
# Mall Plaza Vespucio: -33.5195, -70.5980
# Hospital Sótero del Río (Puente Alto): -33.5860, -70.5760

tests = [
    {
        "name": "Plaza Italia → La Moneda (corta)",
        "from": (-33.4372, -70.6340),
        "to": (-33.4422, -70.6537),
        "time": "08:00:00",
        "day": "L",
    },
    {
        "name": "Plaza Italia → Mall Plaza Vespucio (media)",
        "from": (-33.4372, -70.6340),
        "to": (-33.5195, -70.5980),
        "time": "08:00:00",
        "day": "L",
    },
    {
        "name": "Estación Central → Puente Alto (larga)",
        "from": (-33.4525, -70.6783),
        "to": (-33.5860, -70.5760),
        "time": "09:00:00",
        "day": "L",
    },
    {
        "name": "Plaza Italia → Estación Central (domingo tarde)",
        "from": (-33.4372, -70.6340),
        "to": (-33.4525, -70.6783),
        "time": "15:00:00",
        "day": "D",
    },
]

for i, test in enumerate(tests, 1):
    print(f"\n{'='*70}")
    print(f"[TEST {i}] {test['name']}")
    print(f"  Salida: {test['time']} | Día: {test['day']}")
    print(f"  Origen: {test['from']} → Destino: {test['to']}")

    t0 = time.time()
    results = router.route(
        test["from"][0], test["from"][1],
        test["to"][0], test["to"][1],
        departure_time=test["time"],
        service_day=test["day"],
        max_results=3,
    )
    query_ms = (time.time() - t0) * 1000

    print(f"  Query: {query_ms:.0f}ms | Resultados: {len(results)}")

    for j, r in enumerate(results, 1):
        if not r.found:
            print(f"\n  [Alternativa {j}] NO ENCONTRADA")
            continue
        print(f"\n  [Alternativa {j}] Tiempo total: {r.total_time_human} ({r.total_time_secs}s)")
        print(f"    Salida: {r.departure_time} → Llegada: {r.arrival_time}")
        print(f"    Caminata: {secs_to_human(r.walk_time_secs)} ({r.total_walk_m}m)")
        print(f"    Espera: {secs_to_human(r.wait_time_secs)}")
        print(f"    Viaje: {secs_to_human(r.ride_time_secs)}")
        print(f"    Transbordos: {r.transfers}")
        print(f"    Tarifa: ${r.fare.total} ({r.fare.periodo}, {r.fare.fare_type})")
        if r.fare.breakdown:
            for bd in r.fare.breakdown:
                print(f"      - {bd['route']}: ${bd.get('paid', 0)} ({bd['mode']})")
        print(f"    Parada origen: {r.origin_stop_id} ({r.origin_stop_name})")
        print(f"    Parada destino: {r.dest_stop_id} ({r.dest_stop_name})")
        for k, leg in enumerate(r.legs, 1):
            if leg.mode == "walk":
                print(f"    Leg {k}: 🚶 Caminar {leg.walk_distance_m}m ({secs_to_human(leg.duration_secs)})")
                if leg.board_stop_name:
                    print(f"            desde {leg.board_stop_name}")
                if leg.alight_stop_name:
                    print(f"            hasta {leg.alight_stop_name}")
            else:
                print(f"    Leg {k}: 🚌 {leg.route_name} ({leg.mode})")
                print(f"            Subir: {leg.board_stop_name} ({leg.board_stop_id})")
                print(f"            Bajar: {leg.alight_stop_name} ({leg.alight_stop_id})")
                print(f"            {leg.num_stops} paradas, {secs_to_human(leg.duration_secs)} viaje, {secs_to_human(leg.wait_secs)} espera")

print(f"\n{'='*70}")
print("TESTS COMPLETED")
