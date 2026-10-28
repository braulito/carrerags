FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt \
    && groupadd --system carrerags \
    && useradd --system --gid carrerags --home-dir /app carrerags

COPY --chown=carrerags:carrerags app.py wsgi.py ./
COPY --chown=carrerags:carrerags templates ./templates
COPY --chown=carrerags:carrerags static ./static

USER carrerags
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--worker-class", "gthread", "--threads", "4", "--timeout", "270", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
