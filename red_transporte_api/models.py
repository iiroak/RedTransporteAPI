"""Pydantic response models for RedTransporteAPI."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ── Stop models ──────────────────────────────────────────────

class ServiceInfo(BaseModel):
    route_id: str
    short_name: str
    long_name: str
    color: Optional[str] = None
    mode: str


class StopInfo(BaseModel):
    stop_id: str
    stop_name: str
    stop_full_name: str
    latitude: float
    longitude: float
    wheelchair_boarding: bool = False
    services: list[ServiceInfo] = []
    service_count: int = 0


class NearbyStop(BaseModel):
    stop_id: str
    stop_name: str
    latitude: float
    longitude: float
    distance_m: int


class NearbyStation(BaseModel):
    stop_id: str
    stop_name: str
    latitude: float
    longitude: float
    distance_m: int
    mode: str = "metro"


# ── Route models ─────────────────────────────────────────────

class RouteStopBasic(BaseModel):
    stop_id: str
    name: str


class FrequencySlot(BaseModel):
    start: str
    end: str
    headway_min: float


class RouteInfo(BaseModel):
    route_id: str
    short_name: str
    long_name: str
    color: Optional[str] = None
    mode: str
    agency: str = ""
    stops_ida: list[RouteStopBasic] = []
    stops_vuelta: list[RouteStopBasic] = []
    frequency_weekday: list[FrequencySlot] = []
    frequency_saturday: list[FrequencySlot] = []
    frequency_sunday: list[FrequencySlot] = []


class RouteBasic(BaseModel):
    route_id: str
    short_name: str
    long_name: str
    mode: str
    color: Optional[str] = None


class RouteShape(BaseModel):
    route_id: str
    direction: int
    point_count: int
    coordinates: list[list[float]]


class RouteStopSequence(BaseModel):
    sequence: int
    stop_id: str
    stop_name: str
    latitude: float
    longitude: float


# ── Prediction models ────────────────────────────────────────

class BusArrival(BaseModel):
    patente: str = ""
    tiempo_llegada: str = ""
    distancia: int = 0
    source: str = "unknown"


class ServicePrediction(BaseModel):
    servicio: str
    buses: list[BusArrival] = []
    mensaje: Optional[str] = None


class StopPrediction(BaseModel):
    paradero: dict = {}
    servicios: list[ServicePrediction] = []
    sources: list[str] = []


# ── Spatial models ───────────────────────────────────────────

class RouteSuggestion(BaseModel):
    route_id: str
    short_name: str
    long_name: str
    mode: str
    color: Optional[str] = None
    board_at: NearbyStop
    alight_at: NearbyStop


# ── System models ────────────────────────────────────────────

class SystemStats(BaseModel):
    total_stops: int
    total_routes: int
    total_trips: int
    service_days: list[str]
    agencies: list[str]
    modes: list[str]


class GTFSStatus(BaseModel):
    available: bool
    path: Optional[str] = None
    url: Optional[str] = None
    filename: Optional[str] = None
    download_date: Optional[str] = None
    zip_size_bytes: Optional[int] = None
    file_count: int = 0
    outdated: bool = True


class HealthCheck(BaseModel):
    status: str = "ok"
    version: str
    gtfs_loaded: bool


class APIInfo(BaseModel):
    nombre: str = "RedTransporteAPI"
    version: str
    descripcion: str = "API unificada para el transporte público de Santiago de Chile"
    docs: str = "/docs"
    fuentes: list[str] = ["GTFS (DTPM)", "iBus (m.ibus.cl)", "RED web predictor (red.cl)"]


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
