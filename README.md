# dbt-dochosting-service

A small FastAPI service that hosts the static docs site produced by
`dbt docs generate` (`index.html`, `manifest.json`, `catalog.json`).
Uploaded artifacts are stored in an S3-compatible bucket and served back
at the service root.

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

Copy `.env.example` to `.env` and fill in your S3 bucket details and an
upload API key:

```
cp .env.example .env
```

| Variable | Description |
| --- | --- |
| `DOCHOST_S3_BUCKET` | S3 bucket used to store the docs artifacts |
| `DOCHOST_S3_REGION` | AWS region (default `us-east-1`) |
| `DOCHOST_S3_ENDPOINT_URL` | Set for MinIO / other S3-compatible endpoints; leave unset for AWS S3 |
| `DOCHOST_S3_ACCESS_KEY_ID` / `DOCHOST_S3_SECRET_ACCESS_KEY` | Credentials (omit to use the default AWS credential chain) |
| `DOCHOST_S3_PREFIX` | Key prefix under which docs are stored (default `docs`) |
| `DOCHOST_UPLOAD_API_KEY` | API key required to call `POST /upload` |

## Local development

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Run tests (uses `moto` to mock S3, no real AWS access needed):

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
