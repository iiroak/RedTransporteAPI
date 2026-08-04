# RedTransporteAPI HTTP

Guía de integración para la API FastAPI de transporte público de Santiago.

La API combina tres fuentes:

| Fuente | Tipo | Uso |
|---|---|---|
| GTFS DTPM | Estática | Paraderos, recorridos, horarios, frecuencias y shapes |
| iBus | Tiempo real | Llegadas estimadas y datos del sitio móvil |
| RED web | Tiempo real | Predicciones del predictor público de `red.cl` |

El motor GTFS/RAPTOR se ejecuta en memoria. La base de datos no guarda el GTFS:
SQLite o MySQL se usa para configuración, tokens y contadores de rate limit.

## URLs

| Entorno | Base URL | Documentación |
|---|---|---|
| Local | `http://localhost:8000` | `/docs`, `/redoc`, `/openapi.json` |
| Producción | `https://api.example.com` | `/docs`, `/redoc`, `/openapi.json` |

Las rutas de esta guía son relativas a la Base URL.

Para los ejemplos de producción:

```bash
export BASE_URL=https://api.example.com
```

## Primer arranque

El primer endpoint que necesite GTFS descarga automáticamente el dataset si no
existe en `RED_TRANSPORTE_DATA_DIR`. La descarga puede tardar y ocurre antes de
responder. Para precalentar el dataset:

```bash
uv sync --extra api
uv run red-transporte gtfs update
uv run red-transporte-server
```

El directorio predeterminado es `~/.red_transporte/`. En Docker debe montarse
como volumen persistente, por ejemplo `/data`, para no descargar GTFS después de
cada recreación del contenedor.

## Autenticación

La API usa dos clases de credenciales distintas.

### Master token

`RED_TRANSPORTE_MASTER_TOKEN` se configura en el entorno del servidor. Solo
autoriza operaciones administrativas:

- Todas las rutas `/admin/*`.
- `POST /gtfs/update`.

No se almacena como token de API y no concede automáticamente acceso a las rutas
normales de consulta.

```bash
export MASTER_TOKEN='valor-leido-de-un-gestor-de-secretos'

curl -sS -X GET "$BASE_URL/admin/settings" \
  -H "Authorization: Bearer $MASTER_TOKEN"
```

### API tokens

Se crean con `POST /admin/tokens`. La respuesta de creación contiene el token
crudo una sola vez. El servidor almacena únicamente su hash SHA-256.

```bash
curl -sS -X POST "$BASE_URL/admin/tokens" \
  -H "Authorization: Bearer $MASTER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "mi-integracion",
    "requests_per_minute": 60,
    "allow_gtfs": true,
    "allow_ibus": true,
    "allow_red_web": true,
    "allow_raptor": true,
    "is_unlimited": false
  }'
```

Usa el token devuelto como:

```bash
export API_TOKEN='token-devuelto-solo-en-la-creacion'
curl -sS "$BASE_URL/stops/search?q=providencia&limit=5" \
  -H "Authorization: Bearer $API_TOKEN"
```

Un header `Authorization` presente pero inválido devuelve `401`; nunca se
degrada silenciosamente a acceso público.

## Scopes y política pública

Cada ruta se clasifica por recurso. Un token puede leer solo las fuentes que sus
campos `allow_*` permiten.

| Recurso | Campo del token | Rutas principales | Sin token cuando `public_api_enabled=true` |
|---|---|---|---|
| `gtfs_read` | `allow_gtfs` | `/stops`, `/routes`, `/nearby/*`, `/bbox/*`, `/routing/suggest`, `/gtfs/status` | Permitido, con límite por IP |
| `ibus` | `allow_ibus` | `/predictions/*` y predicciones de `/stops/{code}/predictions` | Permitido, con límite por IP |
| `red_web` | `allow_red_web` | Fuente RED web dentro de predicciones | Permitido, con límite por IP |
| `raptor` | `allow_raptor` | `/routing/plan` | Denegado: requiere token con scope |
| `system` | N/A | `/stats` | Permitido, con límite por IP |
| `gtfs_admin` | N/A | `POST /gtfs/update` | Requiere master token |

`is_unlimited=true` solo evita el rate limit del token. No salta los scopes ni
convierte un token en master token.

La configuración pública se controla con:

```env
RED_TRANSPORTE_PUBLIC_API=true
RED_TRANSPORTE_PUBLIC_IP_RPM=20
```

Con `RED_TRANSPORTE_PUBLIC_API=false`, las rutas que normalmente aceptan acceso
público devuelven `401` sin token.

## Rate limiting

- Ventana fija de un minuto.
- Tráfico público: clave por IP y recurso.
- Token autenticado: clave por ID de token y recurso.
- Límite predeterminado público: `20` requests/minuto.
- Límite predeterminado de un API token nuevo: `60` requests/minuto.
- Una ráfaga concurrente no puede superar el límite gracias al contador atómico
  de la base de datos.

Las respuestas de límite son `429` con un mensaje de reintento en el siguiente
minuto.

## Proxy y the reverse proxy

Uvicorn no confía automáticamente en headers de proxy. La aplicación solo usa
`CF-Connecting-IP` o `X-Forwarded-For` cuando se cumplen ambas condiciones:

```env
RED_TRANSPORTE_TRUST_PROXY=true
RED_TRANSPORTE_TRUSTED_PROXY_IPS=127.0.0.1
```

La conexión directa debe provenir de una IP incluida en
`RED_TRANSPORTE_TRUSTED_PROXY_IPS`. `CF-Connecting-IP` tiene prioridad sobre
`X-Forwarded-For`. Mantén `TRUST_PROXY=false` si expones Uvicorn directamente.

## Endpoints de consulta

Todos los ejemplos usan:

```bash
BASE_URL=https://api.example.com
```

### Sistema

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/` | Ninguna | Información y versión |
| `GET` | `/health` | Ninguna | Liveness y estado de carga de GTFS |
| `GET` | `/stats` | `system` | Conteos de paraderos, rutas, viajes, días y modos |

```bash
curl -sS "$BASE_URL/health"
curl -sS "$BASE_URL/stats" -H "Authorization: Bearer $API_TOKEN"
```

### Paraderos y recorridos

| Método | Ruta | Auth | Parámetros |
|---|---|---|---|
| `GET` | `/stops/search` | `gtfs_read` | `q` 1-64 caracteres, `limit` 1-100 |
| `GET` | `/stops/{code}` | `gtfs_read` | Código de paradero |
| `GET` | `/stops/{code}/predictions` | `ibus` + `red_web` | Predicciones agregadas por fuente |
| `GET` | `/routes` | `gtfs_read` | `mode=bus\|metro\|rail\|tram` opcional |
| `GET` | `/routes/{route_id}` | `gtfs_read` | Detalle, paradas y frecuencias |
| `GET` | `/routes/{route_id}/stops` | `gtfs_read` | `direction=0` ida o `1` vuelta |
| `GET` | `/routes/{route_id}/shape` | `gtfs_read` | `direction=0` ida o `1` vuelta |

```bash
curl -sS "$BASE_URL/stops/PA433"
curl -sS "$BASE_URL/routes?mode=metro"
curl -sS "$BASE_URL/routes/506/stops?direction=0"
curl -sS "$BASE_URL/routes/506/shape?direction=0"
```

### Predicciones en tiempo real

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/predictions/{stop_code}` | `ibus` + `red_web` | Agrega ambas fuentes disponibles |
| `GET` | `/predictions/{stop_code}/{service}` | `ibus` + `red_web` | Filtra por recorrido |

Cada respuesta incluye `sources` y `access`. Si un token no tiene acceso a una
fuente, esa fuente se omite y las demás pueden responder. Si ninguna fuente está
permitida, la respuesta es `403`; si estaban permitidas pero fallaron upstream,
la respuesta es `503`.

```bash
curl -sS "$BASE_URL/predictions/PA433" \
  -H "Authorization: Bearer $API_TOKEN"

curl -sS "$BASE_URL/predictions/PA433/506" \
  -H "Authorization: Bearer $API_TOKEN"
```

### Consultas geoespaciales

Las latitudes deben estar entre `-90` y `90`, las longitudes entre `-180` y
`180`, y el radio entre `0` y `5` km.

| Método | Ruta | Parámetros principales |
|---|---|---|
| `GET` | `/nearby/stops` | `lat`, `lon`, `radius` default `0.5`, `limit` default `20` |
| `GET` | `/nearby/station` | `lat`, `lon` |
| `GET` | `/nearby/routes` | `lat`, `lon`, `radius` default `0.3` |
| `GET` | `/bbox/stops` | `min_lat`, `min_lon`, `max_lat`, `max_lon` |
| `GET` | `/routing/suggest` | `from_lat`, `from_lon`, `to_lat`, `to_lon`, `radius` |

```bash
curl -sS "$BASE_URL/nearby/stops?lat=-33.4372&lon=-70.6506&radius=0.8&limit=10"
curl -sS "$BASE_URL/nearby/station?lat=-33.45&lon=-70.65"
curl -sS "$BASE_URL/routing/suggest?from_lat=-33.4372&from_lon=-70.6506&to_lat=-33.4189&to_lon=-70.6024"
```

Un bounding box que produce más de 2.000 paraderos devuelve `422` y debe
acotarse.

### Planificación RAPTOR

`GET /routing/plan` requiere un token con `allow_raptor=true`.

```bash
curl -sS "$BASE_URL/routing/plan?from_lat=-33.4525&from_lon=-70.6783&to_lat=-33.586&to_lon=-70.576&departure_time=09:00:00&day=L&max_results=3&max_transfers=2&fare_type=normal" \
  -H "Authorization: Bearer $API_TOKEN"
```

Parámetros:

| Parámetro | Default | Restricción |
|---|---|---|
| `departure_time` | `08:00:00` | `HH:MM:SS` |
| `day` | `L` | `L` laboral, `S` sábado, `D` domingo |
| `max_results` | `3` | `1-5` |
| `max_transfers` | `2` | `0-3` |
| `fare_type` | `normal` | `normal`, `estudiante`, `adulto_mayor` |

La respuesta contiene alternativas Pareto-óptimas con tramos (`legs`), tiempos
de caminata/espera/viaje, transbordos, resumen y tarifa integrada RED.

### GTFS

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/gtfs/status` | `gtfs_read` | Estado, fecha, tamaño y vigencia del dataset |
| `POST` | `/gtfs/update?force=false` | Master token | Descarga y recarga GTFS en memoria |

```bash
curl -sS "$BASE_URL/gtfs/status"
curl -sS -X POST "$BASE_URL/gtfs/update?force=true" \
  -H "Authorization: Bearer $MASTER_TOKEN"
```

El update devuelve `502` si DTPM o la extracción fallan. El reemplazo del
dataset es atómico: un fallo conserva el dataset anterior.

## Administración de tokens

```bash
# Listar metadatos; nunca devuelve tokens crudos.
curl -sS "$BASE_URL/admin/tokens" \
  -H "Authorization: Bearer $MASTER_TOKEN"

# Desactivar temporalmente un token, conservando su registro.
curl -sS -X PATCH "$BASE_URL/admin/tokens/1" \
  -H "Authorization: Bearer $MASTER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"enabled": false}'

# Cambiar scopes o rate limit.
curl -sS -X PATCH "$BASE_URL/admin/tokens/1" \
  -H "Authorization: Bearer $MASTER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"requests_per_minute":120,"allow_raptor":true}'

# Revocar definitivamente.
curl -sS -X DELETE "$BASE_URL/admin/tokens/1" \
  -H "Authorization: Bearer $MASTER_TOKEN"
```

## Errores

| HTTP | Significado habitual |
|---|---|
| `401` | Falta auth cuando la ruta la exige, o bearer inválido/revocado |
| `403` | Token válido sin el scope requerido, o master token inválido |
| `404` | Paradero, recorrido o token inexistente |
| `422` | Parámetros inválidos o fuera de rango |
| `429` | Rate limit por IP o token superado |
| `502` | Fallo durante actualización GTFS |
| `503` | Fuentes de predicción permitidas pero no disponibles |

FastAPI también expone el esquema exacto y ejemplos generados en `/docs` y
`/openapi.json`.

## Configuración importante

| Variable | Default | Uso |
|---|---|---|
| `RED_TRANSPORTE_DATA_DIR` | `~/.red_transporte` | GTFS y base SQLite |
| `RED_TRANSPORTE_DB_BACKEND` | `sqlite` | `sqlite` o `mysql`; valores desconocidos fallan al iniciar |
| `RED_TRANSPORTE_DB_URL` | `$DATA_DIR/red_transporte.db` | Ruta SQLite o URL MySQL |
| `RED_TRANSPORTE_PUBLIC_API` | `true` | Política sin token |
| `RED_TRANSPORTE_PUBLIC_IP_RPM` | `20` | Rate limit público |
| `RED_TRANSPORTE_TRUST_PROXY` | `false` | Habilita headers de the reverse proxy/proxy confiable |
| `RED_TRANSPORTE_TRUSTED_PROXY_IPS` | `127.0.0.1` | IPs/CIDRs aceptadas como proxy |
| `RED_TRANSPORTE_GTFS_EAGER_LOAD` | `false` | Precarga GTFS durante startup |
| `RED_TRANSPORTE_GTFS_IDLE_UNLOAD_SECONDS` | `900` | Descarga GTFS de RAM tras inactividad |
| `RED_TRANSPORTE_GTFS_ROUTER_LAZY_BUILD` | `true` | Construcción perezosa del router RAPTOR |
| `RED_TRANSPORTE_CORS_ORIGINS` | `*` | Lista separada por comas de orígenes CORS |

## Desarrollo y pruebas

```bash
uv sync --extra dev
uv run pytest tests/ -q --ignore=tests/test_router.py
```

`tests/test_router.py` es un benchmark manual que ejecuta código al importarse y
contiene una ruta GTFS de Windows; no debe incluirse en la colección normal.
