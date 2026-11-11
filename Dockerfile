# Observatorio de la Curiosidad: una sola imagen para la API (que sirve la web compilada)
# y para el programador de la actualización diaria. Ver docker-compose.yml.

# ---------- 1) Web: compilar React + Vite
FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------- 2) Python: pipeline + API
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OBSERVATORIO_ROOT=/app \
    TZ=America/Santiago
WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY pipeline/ ./pipeline/
RUN pip install ./pipeline

COPY api/ ./api/
COPY config/ ./config/
COPY scripts/programador.py ./scripts/programador.py
COPY docs/ ./docs/
COPY --from=web /web/dist ./web/dist

# Usuario sin privilegios; data/ y reports/ se montan como volúmenes.
RUN useradd --create-home --uid 1000 observatorio \
    && mkdir -p data/cache data/processed reports \
    && chown -R observatorio:observatorio /app
USER observatorio

EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/api/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "observatorio_api.main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "8010"]
