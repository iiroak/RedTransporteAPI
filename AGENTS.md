# AGENTS.md

## Setup And Commands
- Use `uv` for local work in this repo. Sync the right extra for the job: `uv sync` for CLI only, `uv sync --extra api` for FastAPI server support, `uv sync --extra all` for CLI + API + rich output, `uv sync --extra dev` to get `pytest`.
- The package exposes two real entrypoints from `pyproject.toml`: `red-transporte` and `red-transporte-server`.
- Run project commands through `uv run`; `uv run python -m red_transporte_api` runs the CLI, not the HTTP server.

## GTFS Runtime Gotchas
- GTFS is auto-downloaded on first use when no local dataset exists; `uv run red-transporte gtfs update` is only needed to prewarm or force refresh the cache.
- GTFS is stored outside the repo by default at `~/.red_transporte/gtfs/`; override with `RED_TRANSPORTE_DATA_DIR`.
- GTFS-dependent CLI/API/tool flows may block on the initial download before responding.
- FastAPI startup loads GTFS and builds the in-memory `TransitRouter` singleton in `red_transporte_api/api/deps.py`.

## Package Map
- `red_transporte_api/gtfs/` is the core offline engine: GTFS download/parsing, spatial queries, and the RAPTOR router.
- `red_transporte_api/clients/` contains live data integrations: `red_web.py` is the public JWT-based predictor, `ibus.py` is the HTML scraper with in-memory TTL cache, `red_api.py` is the private/MITM-dependent client.
- `red_transporte_api/agent/tools.py` is the main unified facade used by CLI and agent integrations; prefer changing behavior there only when the public tool/CLI surface should change.
- `red_transporte_api/api/app.py` wires routers and loads GTFS on lifespan startup; route modules stay thin and delegate to `gtfs`, clients, or deps singletons.
- `red_transporte_api/auth/` contains the auth system: `models.py` (Pydantic schemas), `storage.py` (abstract base), `sqlite.py` and `mysql.py` (implementations), `service.py` (business logic), `rate_limit.py` (limiting), `deps.py` (FastAPI dependencies).

## Auth System
- Master token is set via `RED_TRANSPORTE_MASTER_TOKEN` in `.env`; it grants access to `/admin/*` and `POST /gtfs/update`.
- API tokens are created via `POST /admin/tokens` (master token required); the raw token is returned only at creation time.
- Tokens are stored as SHA-256 hashes (never plaintext). Use `AuthService.validate_token()` to verify.
- Resource scopes: `gtfs_read`, `ibus`, `red_web`, `raptor`, `gtfs_admin`, `system`. Token capabilities gate access per source.
- `is_unlimited` only skips rate limiting; it NEVER bypasses resource scopes (`AuthService.check_access` always enforces `allow_*`).
- A present-but-invalid/revoked `Authorization` header returns 401; it never degrades to public access (`_resolve_token_record` in `auth/deps.py`).
- Public policy (no token, `public_api_enabled = true`): `gtfs_read`/`ibus`/`red_web` allowed, `raptor` denied, all rate limited by IP.
- For predictions endpoints, `require_access_for_sources()` checks ibus/red_web independently and degrades gracefully when a source is not allowed. When sources ARE allowed but all fail upstream, the route returns 503 (not 403).
- Rate limiting: per-minute window, keyed by `subject_type` (ip/token) + `subject_key` + `resource_type`. The counter is incremented atomically via `consume_rate_counter` (single conditional UPDATE), so concurrent bursts cannot exceed the limit.
- Proxy trust: `RED_TRANSPORTE_TRUST_PROXY` (default false) gates proxy-header handling. When false, `CF-Connecting-IP`/`X-Forwarded-For` are ignored entirely and the direct connection IP is used. When true, headers are only trusted if the connection comes from an IP/CIDR in `RED_TRANSPORTE_TRUSTED_PROXY_IPS` (default `127.0.0.1` — the the reverse proxy tunnel ingress). `CF-Connecting-IP` takes precedence over `X-Forwarded-For`. Uvicorn's own proxy middleware stays disabled; all handling lives in `_get_client_ip` (`auth/deps.py`), so `request.client` is always the true connection IP.
- Storage backends: `RED_TRANSPORTE_DB_BACKEND=sqlite` (default, stores in `~/.red_transporte/red_transporte.db`) or `mysql` for production. Unknown values raise at startup (no silent fallback). SQLite creates its parent dir (0700), the DB file (0600), WAL and a busy_timeout.
- MySQL support requires `aiomysql` and `RED_TRANSPORTE_DB_BACKEND=mysql`; the same schema applies.

## Testing
- There is no repo-local lint, formatter, typecheck, or CI config to rely on; only `pytest` tests are present.
- Safe focused test commands: `uv run pytest tests/test_auth.py tests/test_gtfs_downloader.py tests/test_gtfs_downloader_atomic.py tests/test_fare.py tests/test_gtfs_parser.py tests/test_spatial.py tests/test_ibus.py tests/test_api_integration.py`.
- Do not run `tests/test_router.py` as part of normal pytest collection. It is a manual benchmark-style script, not a real test module: it executes at import time and hard-codes a local GTFS path (`C:\Users\Kaori\Desktop\RED\red_agent\gtfs_data\public_gtfs`).

## Existing Repo Guidance
- `skill/SKILL.md` is a CLI usage guide for external agent systems; keep it aligned if CLI flags or subcommands change.
