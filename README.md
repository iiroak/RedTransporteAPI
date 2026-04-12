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
- **Cache inteligente** para iBus (TTL 30s) para evitar sobrecarga
- **Instalador Linux** con script `install.sh`
- **Sin base de datos** — GTFS cargado en memoria desde CSVs

## Disclaimer

No me hago responsable del uso de este repositorio. Las APIs utilizadas en este proyecto son de acceso publico y este software se entrega solo con fines personales, educativos y de investigacion.

## Skill para agentes

Este repositorio incluye una skill en la carpeta `skill/` para integrar y usar agentes tipo OpenClaw y herramientas similares dentro de flujos de automatizacion.

## Instalación

### Rápida (pip)

```bash
# Solo CLI
pip install .

# CLI + API HTTP
pip install ".[api]"

# Todo (CLI + API + rich output)
pip install ".[all]"

# Desarrollo
pip install ".[dev]"
```

### Linux (script automatizado)

```bash
bash <(curl -sSL https://raw.githubusercontent.com/iiroak/RedTransporteAPI/main/install.sh)
```

### Desde el repositorio

```bash
git clone https://github.com/iiroak/RedTransporteAPI.git
cd RedTransporteAPI
pip install ".[all]"
```

## Inicio rápido

### 1. Descargar datos GTFS

```bash
red-transporte gtfs update
```

Esto descarga automáticamente el último GTFS desde DTPM (~50MB) y lo extrae en `~/.red_transporte/gtfs/`.

### 2. CLI

```bash
# Info de un paradero
red-transporte stop PA433

# Buscar paraderos
red-transporte search "providencia"

# Paraderos cercanos (Plaza Italia)
red-transporte nearby -33.4372 -70.6506

# Estación de metro más cercana
red-transporte station -33.45 -70.65

# Info de un recorrido
red-transporte route 506

# Listar recorridos de metro
red-transporte routes --mode metro

# Predicciones en tiempo real
red-transporte predict PA433

# Sugerir recorridos entre dos puntos
red-transporte suggest -33.4372 -70.6506 -33.4189 -70.6024

# Estadísticas del sistema
red-transporte stats

# Estado de los datos GTFS
red-transporte gtfs status

# Salida JSON (para scripting/pipelines)
red-transporte stop PA433 --json
```

### 3. API HTTP

```bash
# Iniciar servidor
red-transporte server
# o directamente:
red-transporte-server
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

### GTFS

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/gtfs/status` | Estado de los datos GTFS |
| POST | `/gtfs/update?force=false` | Descargar/actualizar GTFS |

## Arquitectura

```
red_transporte_api/
├── config.py           # Configuración unificada (env vars, URLs, constantes)
├── models.py           # Modelos Pydantic para responses
├── gtfs/
│   ├── downloader.py   # Auto-descarga GTFS desde DTPM
│   ├── parser.py       # Parser GTFS (dataclasses, índices, queries)
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

Variables de entorno:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RED_TRANSPORTE_DATA_DIR` | `~/.red_transporte` | Directorio de datos |
| `RED_TRANSPORTE_HOST` | `0.0.0.0` | Host del servidor API |
| `RED_TRANSPORTE_PORT` | `8000` | Puerto del servidor API |
| `RED_API_BASE_URL` | `https://appred.tstgo.cl` | URL base API RED |
| `RED_IBUS_URL` | `http://m.ibus.cl/Servlet` | URL de iBus |
| `RED_IBUS_TIMEOUT` | `15` | Timeout iBus (segundos) |
| `RED_IBUS_CACHE_TTL` | `30` | Cache TTL iBus (segundos) |

## Licencia

MIT
