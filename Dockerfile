FROM python:3.12-slim

# Never write .pyc, never buffer stdout (so logs reach the collector promptly).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run unprivileged. The default local storage path lives under /data so it can
# be mounted as a volume and still be writable by this user.
RUN useradd --system --uid 10001 --create-home dochost \
    && mkdir -p /data/docs \
    && chown -R dochost:dochost /data
USER dochost

ENV DOCHOST_LOCAL_STORAGE_PATH=/data/docs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

# --factory: the app is built by create_app() so settings are read once at
# startup rather than at import time.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
