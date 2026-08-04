# Deploying Jarvis

Jarvis is local-first by design (see `README.md`), but the "server"
side of it — the FastAPI app, the orchestrator, memory, vault,
planning, security, and autonomous workflows — is an ordinary Python
process that runs fine in a container or on a bare-metal host. This
document covers both, plus what deliberately does *not* work the same
way in each.

## What runs where

| Capability | Bare metal | Container |
|---|---|---|
| API (`/health`, `/config`, `/message`) | Yes | Yes |
| Orchestrator, intent routing, plugins | Yes | Yes |
| Memory, vault, planning, security, workflows | Yes | Yes |
| Claude Cowork routing (`cowork` extra) | Yes | Yes |
| Filesystem/terminal/application automation | Yes | Yes (within the container's own filesystem) |
| Desktop automation (click/type/screenshot/window) | Yes, with the `desktop` extra | No meaningful display/input inside a container |
| Voice (wake word/STT/TTS) | Yes, with the `voice` extra + a real mic/speaker | No audio hardware inside a container |
| Browser agent (`browser` extra) | Yes | Possible with a headless browser, but out of scope for the base image |

If a deployment needs desktop automation or voice, run Jarvis directly
on the host (see `README.md`'s Quick Start) rather than in the
container — those capabilities are about controlling *this machine's*
display, input devices, and audio, which a container by construction
doesn't have.

## Running with Docker Compose (recommended for the API/orchestrator side)

```bash
# 1. Configure secrets (COWORK_API_KEY if cowork.yaml's enabled: true, etc.)
cp .env.example .env
# edit .env

# 2. Build and start
docker compose up --build -d

# 3. Verify
curl http://localhost:8756/health
```

`docker-compose.yml` mounts `config/` from the host (so editing
`config/*.yaml` takes effect live, per `settings.yaml`'s
`config.live_reload`) and four named volumes for state that must
survive a rebuild: `jarvis-data` (SQLite databases — memory, workflow
history), `jarvis-logs`, `jarvis-plugins` (external plugins), and
`jarvis-vault` (the Obsidian vault).

To build with an optional extra installed (e.g. the real Cowork HTTP
transport), uncomment the `build.args.EXTRAS` line in
`docker-compose.yml`:

```yaml
build:
  args:
    EXTRAS: cowork
```

## Running the image directly

```bash
docker build -t jarvis:local .
docker run -d \
  --name jarvis \
  -p 8756:8756 \
  --env-file .env \
  -e API__HOST=0.0.0.0 \
  -v jarvis-data:/app/data \
  -v jarvis-logs:/app/logs \
  -v jarvis-plugins:/app/plugins \
  -v jarvis-vault:/app/vault \
  -v "$(pwd)/config:/app/config" \
  jarvis:local
```

## Environment variables

Only `settings.yaml` supports environment-variable overrides
(`SECTION__FIELD=value`, see `docs/architecture.md`'s Phase 3
section and `.env.example`). The ones that matter for a container
deployment specifically:

| Variable | Why it matters in a container |
|---|---|
| `API__HOST` | Must be `0.0.0.0` (not the `127.0.0.1` default) or nothing outside the container can reach it |
| `API__PORT` | Must match the port you publish/expose |
| `APP__ENV` | Set to `production` — affects nothing structurally today, but is read by `/health` and worth setting honestly |
| `COWORK_API_KEY` (or whatever `cowork.yaml`'s `api_key_env_var` names) | Only needed if `cowork.yaml`'s `enabled: true` |

Every other config domain (`permissions.yaml`, `voice.yaml`,
`memory.yaml`, `plugins.yaml`, `filesystem.yaml`, `cowork.yaml`,
`vault.yaml`, `execution.yaml`, `planning.yaml`, `security.yaml`,
`workflow.yaml`) is edited directly, not via environment variables —
mount your edited `config/` directory as shown above.

## Health checks

`GET /health` reports `{"status": "ok", "app": ..., "version": ...,
"env": ..., "plugins_loaded": [...]}` and reads through `ConfigManager`
so it reflects a live-reloaded `settings.yaml` without a restart. Both
the Dockerfile and `docker-compose.yml` wire this into a container
`HEALTHCHECK` (30s interval, 3 retries) so an orchestrator (Compose,
Kubernetes, etc.) can detect a hung process.

## Filesystem allowlisting inside a container

`filesystem.yaml`'s `allowed_dirs` is resolved against whatever
`core/config/_paths.py`'s `PROJECT_ROOT` is inside the container
(`/app` in this image) — an allowlist written for a bare-metal path
like `C:\Users\you\Documents` will resolve to nothing meaningful inside
the container and every filesystem action will be denied. Write
container-specific paths (e.g. `data/notes`, which maps to the
`jarvis-data` volume) into `config/filesystem.yaml` before deploying,
the same way you would for any other machine-specific config.

## Persistence and backups

Everything that must survive a container restart lives in the four
named volumes above. Back up `jarvis-data` (SQLite databases: long-term
memory, security audit log, workflow history) and `jarvis-vault` (the
Obsidian vault) the same way you'd back up any other stateful service's
data directory — there's no separate export/import tooling built for
this yet.

## What's deliberately not covered here

- **No reverse proxy / TLS termination config** — `/health`, `/config`,
  and `/message` are plain HTTP on the port you expose; put a reverse
  proxy (nginx, Caddy, Traefik) in front if you need TLS or need to
  expose this beyond a trusted network. `/config` in particular has no
  authentication (see `docs/architecture.md`'s Phase 2 "what's
  deliberately missing" list) and dumps every config domain's current
  value — don't expose it publicly without addressing that first.
- **No Kubernetes manifests** — the Dockerfile and `docker-compose.yml`
  are the deployment surface this phase built; a Helm chart or raw
  manifests are a natural extension, not built here.
- **No multi-instance/horizontal-scaling guidance** — `SqliteMemoryManager`,
  `SqliteWorkflowStore`, and the security audit log are all single-file
  SQLite databases behind a `threading.Lock`, which assumes one process
  owns the file. Running more than one Jarvis instance against the same
  volume is not supported.
