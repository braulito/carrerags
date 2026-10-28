# syntax=docker/dockerfile:1
# El primer RUN se ejecuta en la arquitectura nativa del constructor.
FROM --platform=$BUILDPLATFORM python:3.11.14-slim-bookworm AS native
ARG BUILDARCH
ARG TARGETARCH
RUN test "$BUILDARCH" = "arm64" && test "$TARGETARCH" = "arm64"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 DO_NOT_TRACK=1 \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --only-binary=:all: -r requirements.txt && python -m pip check

FROM native AS model
COPY carrerags_embeddings/ ./carrerags_embeddings/
COPY download_model.py ./download_model.py
RUN python download_model.py

FROM native AS runtime
COPY --from=model /opt/models/minilm /opt/models/minilm
COPY carrerags_embeddings/ ./carrerags_embeddings/
COPY healthcheck.py ./healthcheck.py
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/tmp/huggingface
USER 10001:10001
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD ["python", "healthcheck.py"]
CMD ["python", "-m", "carrerags_embeddings.server"]
