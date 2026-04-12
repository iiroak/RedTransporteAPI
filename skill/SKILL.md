# RedTransporteAPI CLI — SKILL

Esta skill esta enfocada exclusivamente en el uso de la CLI `red-transporte`.

## Requisitos

- Python 3.9 o superior
- Instalar dependencias del proyecto
- Descargar GTFS local antes de consultas que usan datos estaticos

```bash
pip install ".[all]"
red-transporte gtfs update
```

## Sintaxis general

```bash
red-transporte [--json] [--verbose|-v] <comando> [opciones]
```

## Flags globales

- `--json`: imprime salida JSON cruda.
- `--verbose` o `-v`: activa logging en nivel debug.

Ejemplo:

```bash
red-transporte --json stop PA433
red-transporte -v predict PA433
```

## Comandos CLI detallados

### 1) `gtfs`

Gestiona datos GTFS locales.

Subcomandos:

- `gtfs update [--force]`
	- Descarga/actualiza el GTFS vigente desde DTPM.
	- `--force`: fuerza re-descarga aunque exista version local.
- `gtfs status`
	- Muestra estado de los datos GTFS locales.

Ejemplos:

```bash
red-transporte gtfs update
red-transporte gtfs update --force
red-transporte --json gtfs status
```

### 2) `stop`

Obtiene informacion completa de un paradero.

Uso:

```bash
red-transporte stop <code>
```

Argumentos:

- `<code>`: codigo del paradero (ejemplo: `PA433`).

Ejemplos:

```bash
red-transporte stop PA433
red-transporte --json stop PA433
```

### 3) `search`

Busca paraderos por texto.

Uso:

```bash
red-transporte search <query> [--limit N]
```

Argumentos y opciones:

- `<query>`: texto de busqueda.
- `--limit`: maximo de resultados (default: `10`).

Ejemplos:

```bash
red-transporte search "providencia"
red-transporte search "macul" --limit 5
```

### 4) `nearby`

Lista paraderos cercanos a una coordenada.

Uso:

```bash
red-transporte nearby <lat> <lon> [--radius KM]
```

Argumentos y opciones:

- `<lat>`: latitud (float).
- `<lon>`: longitud (float).
- `--radius`: radio en kilometros (default: `0.5`).

Ejemplos:

```bash
red-transporte nearby -33.4372 -70.6506
red-transporte nearby -33.4372 -70.6506 --radius 1.0
```

### 5) `station`

Devuelve la estacion de metro/tren mas cercana.

Uso:

```bash
red-transporte station <lat> <lon>
```

Argumentos:

- `<lat>`: latitud (float).
- `<lon>`: longitud (float).

Ejemplo:

```bash
red-transporte station -33.45 -70.65
```

### 6) `route`

Muestra informacion de un recorrido.

Uso:

```bash
red-transporte route <route_id>
```

Argumentos:

- `<route_id>`: ID o nombre corto del recorrido (ejemplo: `506`, `D12`).

Ejemplos:

```bash
red-transporte route 506
red-transporte route D12
```

### 7) `routes`

Lista recorridos, opcionalmente filtrados por modo.

Uso:

```bash
red-transporte routes [--mode bus|metro|rail|tram]
```

Opciones:

- `--mode`: filtra por modo de transporte.

Ejemplos:

```bash
red-transporte routes
red-transporte routes --mode metro
red-transporte routes --mode bus
```

### 8) `predict`

Consulta predicciones en tiempo real para un paradero.

Uso:

```bash
red-transporte predict <code>
```

Argumentos:

- `<code>`: codigo del paradero.

Ejemplos:

```bash
red-transporte predict PA433
red-transporte --json predict PA433
```

### 9) `stats`

Entrega estadisticas globales del sistema.

Uso:

```bash
red-transporte stats
```

Ejemplo:

```bash
red-transporte --json stats
```

### 10) `suggest`

Sugiere recorridos entre dos puntos geograficos.

Uso:

```bash
red-transporte suggest <from_lat> <from_lon> <to_lat> <to_lon> [--radius KM]
```

Argumentos y opciones:

- `<from_lat>`: latitud origen.
- `<from_lon>`: longitud origen.
- `<to_lat>`: latitud destino.
- `<to_lon>`: longitud destino.
- `--radius`: radio de busqueda en kilometros (default: `0.5`).

Ejemplos:

```bash
red-transporte suggest -33.4372 -70.6506 -33.4189 -70.6024
red-transporte suggest -33.4372 -70.6506 -33.4189 -70.6024 --radius 0.8
```

### 11) `server`

Inicia el servidor HTTP de la API.

Uso:

```bash
red-transporte server
```

Salida esperada:

- API disponible localmente (por defecto) en `http://localhost:8000`.
- Documentacion Swagger en `http://localhost:8000/docs`.

## Flujo recomendado de uso CLI

1. Descargar GTFS: `red-transporte gtfs update`
2. Verificar estado: `red-transporte gtfs status`
3. Consultar paraderos/recorridos: `stop`, `search`, `route`, `routes`
4. Consultar tiempo real: `predict`
5. Consultas geoespaciales: `nearby`, `station`, `suggest`

## Notas operativas CLI

- Si no existe GTFS local, varios comandos fallaran hasta ejecutar `red-transporte gtfs update`.
- `predict` consulta fuentes en tiempo real y puede variar entre llamadas.
- Para integraciones de scripts, usar siempre `--json`.
