# dbt-dochosting-service

A small FastAPI service that hosts the static docs site produced by
`dbt docs generate` (`index.html`, `manifest.json`, `catalog.json`).
Uploaded artifacts are stored via a pluggable storage backend — local
filesystem, S3 (or S3-compatible), or Azure Blob Storage — and served
back at the service root.

## Endpoints

- `GET /healthz` — health check.
- `POST /upload` — upload the generated docs. Requires header
  `x-api-key: <DOCHOST_UPLOAD_API_KEY>` and multipart form fields
  `index_html`, `manifest_json`, `catalog_json` (and optionally
  `run_results_json`).
- `GET /` — serves the uploaded `index.html`.
- `GET /manifest.json`, `GET /catalog.json` — serve the corresponding
  uploaded artifacts.

## Configuration

Copy `.env.example` to `.env` and pick a storage backend:

```
cp .env.example .env
```

| Variable | Description |
| --- | --- |
| `DOCHOST_UPLOAD_API_KEY` | API key required to call `POST /upload` |
| `DOCHOST_STORAGE_BACKEND` | `local` (default), `s3`, or `azure` |

### `local` backend (default — no cloud account needed)

| Variable | Description |
| --- | --- |
| `DOCHOST_LOCAL_STORAGE_PATH` | Directory the docs artifacts are written to (default `./data/docs`) |

Good for local development or a single-instance deployment with a
persistent disk/volume. Not suitable for multi-instance deployments,
since each instance would have its own copy of the files.

### `s3` backend

| Variable | Description |
| --- | --- |
| `DOCHOST_S3_BUCKET` | S3 bucket used to store the docs artifacts (required) |
| `DOCHOST_S3_REGION` | AWS region (default `us-east-1`) |
| `DOCHOST_S3_ENDPOINT_URL` | Set for MinIO / other S3-compatible endpoints; leave unset for AWS S3 |
| `DOCHOST_S3_ACCESS_KEY_ID` / `DOCHOST_S3_SECRET_ACCESS_KEY` | Credentials (omit to use the default AWS credential chain) |
| `DOCHOST_S3_PREFIX` | Key prefix under which docs are stored (default `docs`) |

### `azure` backend

| Variable | Description |
| --- | --- |
| `DOCHOST_AZURE_CONTAINER` | Blob container used to store the docs artifacts (required) |
| `DOCHOST_AZURE_CONNECTION_STRING` | Connection string (use this, or the account URL + key below) |
| `DOCHOST_AZURE_ACCOUNT_URL` / `DOCHOST_AZURE_ACCOUNT_KEY` | Account URL + key, as an alternative to a connection string |
| `DOCHOST_AZURE_PREFIX` | Blob name prefix under which docs are stored (default `docs`) |

Switching backends later is just an env var change — the API and
upload/serve behavior are identical across all three.

## Local development

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Run tests (S3 tests use `moto` to mock AWS, Azure tests use a fake
in-memory client — no cloud account needed):

```bash
pytest
```

## Publishing docs from a CI pipeline

After `dbt docs generate`, upload the artifacts from your `target/`
directory:

```bash
curl -X POST "$DOCHOST_URL/upload" \
  -H "x-api-key: $DOCHOST_UPLOAD_API_KEY" \
  -F "index_html=@target/index.html;type=text/html" \
  -F "manifest_json=@target/manifest.json;type=application/json" \
  -F "catalog_json=@target/catalog.json;type=application/json"
```

## Docker

```bash
docker build -t dbt-dochosting-service .
docker run -p 8000:8000 --env-file .env dbt-dochosting-service
```

If using the `local` storage backend in Docker, mount a volume so
uploads survive container restarts:

```bash
docker run -p 8000:8000 --env-file .env \
  -e DOCHOST_LOCAL_STORAGE_PATH=/data/docs \
  -v "$(pwd)/data:/data/docs" \
  dbt-dochosting-service
```
