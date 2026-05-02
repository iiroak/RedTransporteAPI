# RedTransporteAPI

API unificada para el transporte público de Santiago de Chile. Combina tres fuentes de datos en un solo proyecto:

| Fuente | Tipo | Descripción |
|--------|------|-------------|
| **GTFS** (DTPM) | Estático | Paraderos, recorridos, horarios, shapes — descargado de [dtpm.cl](https://www.dtpm.cl/index.php/noticias/gtfs-vigente) |
| **iBus** (m.ibus.cl) | Tiempo real | Predicciones de llegada vía scraping del sitio móvil |
| **RED web** (red.cl) | Tiempo real | Predicciones vía JWT del predictor web público |

## Características

- **API HTTP** (FastAPI) con Swagger UI automático
- **CLI** completa con subcomandos para todas las consultas
- **Agent tools** compatibles con OpenAI, Claude, LangChain
- **GTFS auto-download** desde DTPM con detección de versión
- **Rutas geoespaciales**: paraderos cercanos, estación de metro más cercana, bounding box, sugerencia de recorridos entre dos puntos
- **Planificador de rutas RAPTOR**: calcula rutas óptimas entre dos coordenadas con transbordos, tiempos de espera reales y tarifa integrada RED
- **Tarifa integrada RED**: cálculo automático de pasaje (punta/valle/baja, estudiante, adulto mayor, transbordos)
- **Cache inteligente** para iBus (TTL 30s) para evitar sobrecarga
- **Instalador Linux** con script `install.sh`
- **Sin base de datos** — GTFS cargado en memoria desde CSVs

## Disclaimer

No me hago responsable del uso de este repositorio. Las APIs utilizadas en este proyecto son de acceso publico y este software se entrega solo con fines personales, educativos y de investigacion.

## Skill para agentes

Este repositorio incluye una skill en la carpeta `skill/` para integrar y usar agentes tipo OpenClaw y herramientas similares dentro de flujos de automatizacion.

## Instalación

### Rápida (uv)

```bash
# Solo CLI
uv sync

# CLI + API HTTP
uv sync --extra api

# Todo (CLI + API + rich output)
uv sync --extra all

# Desarrollo
uv sync --extra dev
```

### Linux (script automatizado)

```bash
bash <(curl -sSL https://raw.githubusercontent.com/iiroak/RedTransporteAPI/main/install.sh)
```

### Desde el repositorio

```bash
git clone https://github.com/iiroak/RedTransporteAPI.git
cd RedTransporteAPI
uv sync --extra all
```

## Inicio rápido

### 1. Datos GTFS

```bash
uv run red-transporte gtfs update
```

El GTFS se descarga automáticamente en el primer uso si no existe un dataset local. Este comando sigue siendo útil para precalentar la cache o forzar la descarga manualmente. Los datos se extraen en `~/.red_transporte/gtfs/`.

### 2. CLI

```bash
# Info de un paradero
uv run red-transporte stop PA433

# Buscar paraderos
uv run red-transporte search "providencia"

# Paraderos cercanos (Plaza Italia)
uv run red-transporte nearby -33.4372 -70.6506

# Estación de metro más cercana
uv run red-transporte station -33.45 -70.65

# Info de un recorrido
uv run red-transporte route 506

# Listar recorridos de metro
uv run red-transporte routes --mode metro

# Predicciones en tiempo real
uv run red-transporte predict PA433

# Sugerir recorridos entre dos puntos
uv run red-transporte suggest -33.4372 -70.6506 -33.4189 -70.6024

# Estadísticas del sistema
uv run red-transporte stats

# Estado de los datos GTFS
uv run red-transporte gtfs status

# Salida JSON (para scripting/pipelines)
uv run red-transporte stop PA433 --json
```

### 3. API HTTP

```bash
# Iniciar servidor
uv run red-transporte server
# o directamente:
uv run red-transporte-server
```

Swagger UI en: http://localhost:8000/docs

### 4. Agent Tools (Python)

```python
from red_transporte_api.agent import RedTransporteTools

tools = RedTransporteTools()

# Consultas offline (GTFS)
tools.get_stop_info("PA433")
tools.search_stops("providencia")
tools.get_nearby_stops(-33.4372, -70.6506)
tools.get_closest_station(-33.45, -70.65)
tools.get_route_info("506")
tools.list_routes("metro")

# Consultas online (tiempo real)
tools.get_predictions("PA433")

# GTFS management
tools.update_gtfs()
tools.get_gtfs_status_info()

# OpenAI function calling
definitions = tools.get_tool_definitions()
result = tools.call_tool("get_stop_info", {"stop_code": "PA433"})
```

## API — Endpoints

### Sistema

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Info de la API |
| GET | `/health` | Health check |
| GET | `/stats` | Estadísticas del sistema |

### Paraderos

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/stops/search?q=providencia&limit=10` | Buscar paraderos |
| GET | `/stops/{code}` | Info de un paradero |
| GET | `/stops/{code}/predictions` | Predicciones del paradero |

### Recorridos

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/routes?mode=bus` | Listar recorridos |
| GET | `/routes/{id}` | Detalle de recorrido |
| GET | `/routes/{id}/stops?direction=0` | Paraderos del recorrido |
| GET | `/routes/{id}/shape?direction=0` | Geometría del recorrido |

### Predicciones

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/predictions/{stop_code}` | Predicciones agregadas |
| GET | `/predictions/{stop_code}/{service}` | Predicciones por servicio |

### Geoespacial

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/nearby/stops?lat=...&lon=...&radius=0.5` | Paraderos cercanos |
| GET | `/nearby/station?lat=...&lon=...` | Estación metro/tren más cercana |
| GET | `/nearby/routes?lat=...&lon=...&radius=0.3` | Recorridos cerca de un punto |
| GET | `/bbox/stops?min_lat=...&min_lon=...&max_lat=...&max_lon=...` | Paraderos en bounding box |
| GET | `/routing/suggest?from_lat=...&from_lon=...&to_lat=...&to_lon=...` | Sugerir recorridos entre dos puntos |
| GET | `/routing/plan?from_lat=...&from_lon=...&to_lat=...&to_lon=...` | **Planificar ruta óptima (RAPTOR)** |

### GTFS

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/gtfs/status` | Estado de los datos GTFS |
| POST | `/gtfs/update?force=false` | Descargar/actualizar GTFS (admin only) |

### Admin

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/admin/settings` | Obtener configuración actual |
| PATCH | `/admin/settings` | Actualizar configuración |
| POST | `/admin/tokens` | Crear nuevo token de API |
| GET | `/admin/tokens` | Listar todos los tokens |
| GET | `/admin/tokens/{id}` | Detalle de un token |
| PATCH | `/admin/tokens/{id}` | Actualizar un token |
| DELETE | `/admin/tokens/{id}` | Eliminar un token |

> Todos los endpoints `/admin/*` requieren `Authorization: Bearer <master_token>`.
> El token maestro se define via `RED_TRANSPORTE_MASTER_TOKEN` en `.env`.

## Planificador de rutas (RAPTOR)

El endpoint `/routing/plan` implementa el algoritmo **RAPTOR** (Round-Based Public Transit Optimized Router), basado en el paper de Microsoft Research ([Delling et al., ALENEX 2015](https://www.microsoft.com/en-us/research/wp-content/uploads/2012/01/raptor_alenex.pdf)), adaptado para datos GTFS basados en frecuencia del sistema RED de Santiago.

### ¿Qué es RAPTOR?

RAPTOR es un algoritmo de enrutamiento de transporte público que encuentra rutas **Pareto-óptimas** considerando dos criterios simultáneamente:
- **Tiempo de llegada** (más rápido)
- **Número de transbordos** (menos cambios)

Funciona por *rondas*: la ronda 1 busca la mejor ruta directa (0 transbordos), la ronda 2 busca la mejor con 1 transbordo, y la ronda 3 con 2 transbordos. Solo devuelve resultados donde más transbordos producen un viaje más rápido.

### Uso del endpoint

```
GET /routing/plan?from_lat=-33.4372&from_lon=-70.634&to_lat=-33.586&to_lon=-70.576
    &departure_time=09:00:00&day=L&max_results=3&max_transfers=2&fare_type=normal
```

**Parámetros:**

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `from_lat`, `from_lon` | (requerido) | Coordenadas del origen |
| `to_lat`, `to_lon` | (requerido) | Coordenadas del destino |
| `departure_time` | `08:00:00` | Hora de salida (HH:MM:SS) |
| `day` | `L` | Día: `L`=laboral, `S`=sábado, `D`=domingo |
| `max_results` | `3` | Máximo de alternativas (1-5) |
| `max_transfers` | `2` | Máximo de transbordos (0-3) |
| `fare_type` | `normal` | Tipo de tarifa: `normal`, `estudiante`, `adulto_mayor` |

**Respuesta:** Lista de planes de viaje, cada uno con:
- Legs (tramos): caminar, subir bus/metro, caminar transbordo, etc.
- Tiempos desglosados: caminata, espera, viaje
- Tarifa calculada con desglose por tramo
- Resumen legible ("L1 (Baquedano → La Moneda) ➜ 506 (Plaza Italia → Mall)")

### Ejemplo de respuesta

```json
{
  "plans": [
    {
      "found": true,
      "total_time_secs": 4113,
      "total_time_human": "1h 9min",
      "departure_time": "09:00:00",
      "arrival_time": "10:08:33",
      "walk_time_secs": 583,
      "ride_time_secs": 2530,
      "wait_time_secs": 1000,
      "transfers": 2,
      "total_walk_m": 760,
      "fare": {
        "total": 815,
        "periodo": "valle",
        "fare_type": "normal",
        "breakdown": [
          {"mode": "metro", "route": "L1", "fare_mode": 815, "paid": 815},
          {"mode": "metro", "route": "L5", "fare_mode": 815, "paid": 0},
          {"mode": "metro", "route": "L4", "fare_mode": 815, "paid": 0}
        ]
      },
      "legs": [
        {"mode": "walk", "walk_distance_m": 177, "duration_secs": 142},
        {"mode": "metro", "route_name": "L1", "board_stop_name": "Estación Central", "alight_stop_name": "Baquedano", "num_stops": 8, "duration_secs": 660, "wait_secs": 340},
        {"mode": "walk", "walk_distance_m": 84, "duration_secs": 67},
        {"mode": "metro", "route_name": "L5", "board_stop_name": "Baquedano", "alight_stop_name": "Vicente Valdés", "num_stops": 12, "duration_secs": 1140, "wait_secs": 330},
        {"mode": "metro", "route_name": "L4", "board_stop_name": "Vicente Valdés", "alight_stop_name": "Protectora de La Infancia", "num_stops": 7, "duration_secs": 730, "wait_secs": 330},
        {"mode": "walk", "walk_distance_m": 499, "duration_secs": 399}
      ],
      "summary": "L1 (Estación Central → Baquedano) ➜ L5 (Baquedano → Vicente Valdés) ➜ L4 (Vicente Valdés → Protectora de La Infancia) (2 trasbordos)"
    }
  ],
  "count": 1,
  "message": "1 alternativa(s) encontrada(s)"
}
```

### Tarifa integrada RED

El cálculo de tarifa sigue las [reglas oficiales de RED](https://www.red.cl/tarifas-y-recargas/conoce-las-tarifas/):

**Tarifas base (adulto normal):**

| Modo | Punta (07-09 / 18-20) | Valle (09-18 / 20-20:44 / fines de semana) | Baja (06-07 / 20:45-23) |
|------|----------------------|-------------------------------------------|------------------------|
| Bus | $795 | $795 | $795 |
| Metro / Tren | $895 | $815 | $735 |

**Reglas de transbordo:**
- Máximo **2 transbordos** (3 etapas) en ventana de **120 minutos**
- **Tarifa integrada**: se paga el **máximo** entre bus y metro para todo el viaje
- Bus → Metro: pagas $795 (bus) + diferencia hasta metro = $895 en punta
- Metro → Bus: pagas $895 (metro) + $0 (bus incluido)
- Bus → Bus: pagas $795 una sola vez
- Primer tramo: pago completo. Siguientes tramos: $0 adicional (incluido en tarifa integrada)

**Tarifas especiales:**

| Tipo | Tarifa |
|------|--------|
| Estudiante | $260 (tarifa plana) |
| Adulto Mayor | $390 (tarifa plana) |

### Detalles técnicos del algoritmo

- **Velocidad de caminata**: 4.5 km/h
- **Radio de búsqueda**: 500m para paraderos origen/destino y transferencias a pie
- **Tiempo de espera**: headway/2 (promedio) + 30s penalización de abordaje
- **Índice espacial**: grilla 0.005° (~500m) para búsqueda rápida de vecinos
- **Perfiles de viaje**: tiempos acumulados de stop_times del GTFS
- **Bandas de frecuencia**: headway real por hora/día del GTFS
- **Query time**: ~130ms por consulta

## Arquitectura

```
red_transporte_api/
├── config.py           # Configuración unificada (env vars, URLs, constantes)
├── models.py           # Modelos Pydantic para responses
├── gtfs/
│   ├── downloader.py   # Auto-descarga GTFS desde DTPM
│   ├── parser.py       # Parser GTFS (dataclasses, índices, queries)
│   ├── router.py       # Planificador RAPTOR (rutas, transbordos, tarifas)
│   └── spatial.py      # Utilidades geoespaciales (Haversine, bbox, nearest)
├── clients/
│   ├── ibus.py         # Scraper iBus con cache TTL
│   ├── red_web.py      # Predictor web RED (JWT flow)
│   └── red_api.py      # API privada RED (requiere MITM)
├── api/
│   ├── app.py          # FastAPI app factory
│   ├── deps.py         # Dependency injection
│   └── routes/         # Routers: stops, routes, predictions, spatial, gtfs, system
├── cli/
│   └── main.py         # CLI con argparse
└── agent/
    └── tools.py        # Tools para AI agents (OpenAI, Claude, LangChain)
```

## Fuentes de datos

### GTFS (Estático)
- Descargado de [dtpm.cl/index.php/noticias/gtfs-vigente](https://www.dtpm.cl/index.php/noticias/gtfs-vigente)
- ~12,800 paraderos, ~425 recorridos, ~26,000 viajes
- Actualizado periódicamente por DTPM
- Almacenado en `~/.red_transporte/gtfs/`

### iBus (Tiempo real)
- Scraping de [m.ibus.cl](http://m.ibus.cl) (sitio móvil de Transantiago)
- Predicciones de llegada, patentes de buses, distancias
- Cache TTL 30s para evitar sobrecarga

### RED Web Predictor (Tiempo real)
- JWT extraído de [red.cl/planifica-tu-viaje/cuando-llega](https://www.red.cl/planifica-tu-viaje/cuando-llega/)
- Predicciones estructuradas en JSON
- Token auto-refreshed antes de expiración

## Configuración

### Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RED_TRANSPORTE_DATA_DIR` | `~/.red_transporte` | Directorio de datos (GTFS + SQLite DB) |
| `RED_TRANSPORTE_HOST` | `0.0.0.0` | Host del servidor API |
| `RED_TRANSPORTE_PORT` | `8000` | Puerto del servidor API |
| `RED_TRANSPORTE_MASTER_TOKEN` | _(vacío)_ | Token maestro para admin (requerido para `/admin/*`) |
| `RED_TRANSPORTE_DB_BACKEND` | `sqlite` | Backend de persistencia: `sqlite` o `mysql` |
| `RED_TRANSPORTE_DB_URL` | _(ver default)_ | URL de conexión MySQL (cuando `DB_BACKEND=mysql`) |
| `RED_TRANSPORTE_PUBLIC_API` | `true` | Habilitar acceso público sin token |
| `RED_TRANSPORTE_PUBLIC_IP_RPM` | `20` | Límite de requests por minuto para IPs públicas |
| `RED_TRANSPORTE_TRUST_PROXY` | `false` | Confiar `X-Forwarded-For` (solo detrás de proxy conocido) |
| `RED_TRANSPORTE_CORS_ORIGINS` | `*` | Orígenes CORS permitidos (comma-separated, `*` para todos) |
| `RED_TRANSPORTE_GTFS_EAGER_LOAD` | `false` | Cargar GTFS al iniciar (`false` = lazy load para ahorrar RAM) |
| `RED_TRANSPORTE_GTFS_IDLE_UNLOAD_SECONDS` | `900` | Descargar GTFS/router de RAM tras inactividad (0 deshabilita) |
| `RED_TRANSPORTE_GTFS_ROUTER_LAZY_BUILD` | `true` | Construir `TransitRouter` solo al usar `/routing/plan` |
| `RED_TRANSPORTE_GTFS_SWEEP_INTERVAL_SECONDS` | `60` | Intervalo del sweeper de inactividad en segundos |
| `RED_API_BASE_URL` | `https://appred.tstgo.cl` | URL base API RED |
| `RED_IBUS_URL` | `http://m.ibus.cl/Servlet` | URL de iBus |
| `RED_IBUS_TIMEOUT` | `15` | Timeout iBus (segundos) |
| `RED_IBUS_CACHE_TTL` | `30` | Cache TTL iBus (segundos) |

## Docker

La imagen oficial está publicada en GitHub Container Registry:

```
docker pull ghcr.io/iiroak/redtransporteapi:latest
```

### docker-compose

```yaml
services:
  api:
    image: ghcr.io/iiroak/redtransporteapi:latest
    env_file: .env
    environment:
      - RED_TRANSPORTE_DATA_DIR=/data
    ports:
      - "8000:8000"
    volumes:
      - red_transporte_data:/data
    restart: unless-stopped
```

> **Nota:** en el primer arranque el contenedor descarga automáticamente el GTFS (~150 MB) si no existe en el volumen. Para precalentar antes de desplegar:
> ```bash
> docker run --rm -v red_transporte_data:/data ghcr.io/iiroak/redtransporteapi:latest \
>   uv run red-transporte gtfs update
> ```

### Build local

```bash
git clone https://github.com/iiroak/RedTransporteAPI.git
cd RedTransporteAPI
docker compose up --build
```

### Variables mínimas para producción

```env
RED_TRANSPORTE_MASTER_TOKEN=<generar con: python -c "import secrets; print(secrets.token_urlsafe(32))">
RED_TRANSPORTE_PUBLIC_API=false       # exigir token para todo el tráfico
RED_TRANSPORTE_TRUST_PROXY=false      # no confiar X-Forwarded-For fuera de un proxy conocido
RED_TRANSPORTE_CORS_ORIGINS=https://tu-dashboard.com
```

## Licencia

MIT
