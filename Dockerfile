# Jarvis container image — runs the FastAPI/orchestrator "server" side
# of Jarvis (API, orchestrator, memory, vault, planning, security,
# workflows, Cowork routing).
#
# What does NOT function meaningfully in a container, by design: voice
# (needs a real microphone/speaker), desktop automation (needs a real
# display/input devices), and the browser agent (needs `playwright
# install <engine>` plus, for anything visible, a display — headless
# operation works but is a separate concern from this base image). See
# docs/deployment.md for what each optional extra actually buys you
# here versus on bare metal.

FROM python:3.11-slim AS base

# Build tooling only exists in this layer; the final image below is
# copied from the resulting venv, not from this stage's OS packages —
# keeps the shipped image from carrying a compiler toolchain.
FROM base AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY src ./src

# Base install only — the voice/cowork/desktop/browser extras are each
# large, platform-sensitive, and only matter if that specific
# capability is enabled; add them with a build arg if a deployment
# genuinely needs one (e.g. `--build-arg EXTRAS=cowork`).
ARG EXTRAS=""
RUN pip install --no-cache-dir --upgrade pip \
    && if [ -n "$EXTRAS" ]; then \
         pip install --no-cache-dir ".[${EXTRAS}]"; \
       else \
         pip install --no-cache-dir . ; \
       fi

FROM base AS runtime

RUN useradd --create-home --uid 1000 jarvis
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# config/ and the example plugins ship in the image; data/logs/plugins/
# vault are runtime state and are expected to be mounted as volumes
# (see docker-compose.yml) so they survive a container restart/rebuild.
COPY config ./config
COPY src ./src

RUN mkdir -p data logs plugins vault \
    && chown -R jarvis:jarvis /app

USER jarvis

# Containers have no real desktop, so the execution engine's
# desktop/clipboard/screenshot/window handlers stay Null by default
# regardless of this image — that's driven by execution.yaml, not by
# anything here.
ENV API__HOST=0.0.0.0 \
    API__PORT=8756 \
    APP__ENV=production

EXPOSE 8756

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8756/health', timeout=3)" || exit 1

CMD ["python", "-m", "jarvis.main"]
