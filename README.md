# dbt-dochosting-service

A small FastAPI service that hosts the static docs site produced by
`dbt docs generate` (`index.html`, `manifest.json`, `catalog.json`).
Uploaded artifacts are stored via a pluggable storage backend — local
filesystem, S3 (or S3-compatible), or Azure Blob Storage — and served
back at the service root.

Every upload creates a new immutable **version**, so previous docs stay
readable at their own URL and history is preserved.

## Endpoints

### Publishing (requires `x-api-key: <DOCHOST_UPLOAD_API_KEY>`)

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/v1/projects/{project}/versions` | Publish a new version of a project's docs |
| `POST` | `/upload` | Same, for the `default` project (kept for existing CI jobs) |
| `DELETE` | `/api/v1/projects/{project}/versions/{version}` | Delete one version |

Multipart form fields: `index_html`, `manifest_json`, `catalog_json`, and
optionally `run_results_json`. The response includes the new `version` and
both a `url` (latest) and `version_url` (pinned).

### Reading

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/p/{project}/` | Latest docs for a project |
| `GET` | `/p/{project}/{artifact}` | Latest `manifest.json`, `catalog.json`, `run_results.json` |
| `GET` | `/p/{project}/v/{version}/` | A pinned version, immutably cached |
| `GET` | `/p/{project}/v/{version}/{artifact}` | An artifact from a pinned version |
| `GET` | `/`, `/manifest.json`, `/catalog.json`, `/run_results.json` | Shortcuts for the `default` project |
| `GET` | `/api/v1/projects/{project}/versions` | Version history, newest first |

Reads are currently public. Responses carry `ETag`, so conditional `GET`
returns `304`.

All read and ops routes also answer `HEAD`, with the same headers as `GET`.
`HEAD` is served from storage metadata alone, so it never downloads the object
just to discard the body.

### Operations

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/healthz` | Liveness — does not touch storage |
| `GET` | `/readyz` | Readiness — verifies the storage backend is reachable |

Every response carries an `x-request-id` header, echoed from the request when
one is supplied, and logs are emitted as structured JSON by default.

## Configuration

Copy `.env.example` to `.env` and pick a storage backend:

```
cp .env.example .env
```

| Variable | Description |
| --- | --- |
| `DOCHOST_UPLOAD_API_KEY` | API key required to publish or delete |
| `DOCHOST_STORAGE_BACKEND` | `local` (default), `s3`, or `azure` |
| `DOCHOST_MAX_UPLOAD_BYTES` | Largest single artifact accepted (default 100 MiB) |
| `DOCHOST_PRESIGNED_REDIRECTS` | Redirect large artifacts to storage instead of proxying (default `false`, see below) |
| `DOCHOST_PRESIGNED_EXPIRY_SECONDS` | Lifetime of those redirect URLs (default `900`) |
| `DOCHOST_LOG_LEVEL` / `DOCHOST_LOG_FORMAT` | `INFO` and `json` by default; `text` for readable local logs |

### Serving large manifests

By default every byte is proxied through this service. On big dbt projects
`manifest.json` and `catalog.json` dominate that traffic, so setting
`DOCHOST_PRESIGNED_REDIRECTS=true` makes the service redirect those two
artifacts to a short-lived storage URL instead.

It is off by default because the browser then fetches them cross-origin: the
bucket or container needs a CORS rule allowing `GET` from the origin serving
the docs. The local backend cannot issue such URLs and always proxies.

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
uvicorn app.main:create_app --factory --reload
```

The app is built by `create_app()` so configuration is read once at startup
rather than at import time — hence `--factory`.

Run tests (S3 tests use `moto` to mock AWS, Azure tests use a fake
in-memory client — no cloud account needed):

```bash
pytest
```

## Publishing docs from a CI pipeline

After `dbt docs generate`, upload the artifacts from your `target/`
directory:

```bash
curl -X POST "$DOCHOST_URL/api/v1/projects/analytics/versions" \
  -H "x-api-key: $DOCHOST_UPLOAD_API_KEY" \
  -F "index_html=@target/index.html;type=text/html" \
  -F "manifest_json=@target/manifest.json;type=application/json" \
  -F "catalog_json=@target/catalog.json;type=application/json"
```

The response tells you where the docs landed:

```json
{
  "status": "uploaded",
  "project": "analytics",
  "version": "20260821T203426123456Z-f6d5c69e",
  "files": ["index.html", "manifest.json", "catalog.json"],
  "url": "/p/analytics/",
  "version_url": "/p/analytics/v/20260821T203426123456Z-f6d5c69e/"
}
```

Project names must be lowercase and may contain `a-z`, `0-9`, `-` and `_`.

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

## License

Apache License 2.0 — see [LICENSE](LICENSE).
