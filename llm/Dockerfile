# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Argentina/Buenos_Aires

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install -r requirements.txt && python -m pip check

RUN groupadd --gid 10001 api \
    && useradd --uid 10001 --gid api --no-create-home --shell /usr/sbin/nologin api \
    && mkdir -p /app/JSON \
    && chown api:api /app/JSON

COPY --chown=10001:10001 main.py log_config.json healthcheck.py ./
COPY --chown=10001:10001 routers/ ./routers/
COPY --chown=10001:10001 helpers/ ./helpers/
COPY --chown=10001:10001 --chmod=0444 .env /app/.env

USER 10001:10001
EXPOSE 8021

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "healthcheck.py"]

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8021", "--log-config", "log_config.json"]
