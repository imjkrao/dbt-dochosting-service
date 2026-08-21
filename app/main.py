from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from .security import verify_upload_api_key
from .storage import StorageBackend, get_storage_backend

app = FastAPI(title="dbt Doc Hosting Service")

CONTENT_TYPES = {
    "index.html": "text/html",
    "manifest.json": "application/json",
    "catalog.json": "application/json",
    "run_results.json": "application/json",
}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/upload", dependencies=[Depends(verify_upload_api_key)])
async def upload_docs(
    index_html: UploadFile = File(...),
    manifest_json: UploadFile = File(...),
    catalog_json: UploadFile = File(...),
    run_results_json: UploadFile | None = File(None),
    storage: StorageBackend = Depends(get_storage_backend),
):
    """Accept the artifacts produced by `dbt docs generate` and store them.

    Upload the generated `target/index.html`, `target/manifest.json` and
    `target/catalog.json` as the form fields `index_html`, `manifest_json`
    and `catalog_json` respectively. `run_results_json` is optional.
    """
    uploads = {
        "index.html": index_html,
        "manifest.json": manifest_json,
        "catalog.json": catalog_json,
    }
    if run_results_json is not None:
        uploads["run_results.json"] = run_results_json

    for filename, upload in uploads.items():
        content = await upload.read()
        storage.put_object(filename, content, CONTENT_TYPES[filename])

    return {"status": "uploaded", "files": list(uploads.keys())}


def _serve_file(filename: str, storage: StorageBackend) -> Response:
    if not storage.object_exists(filename):
        raise HTTPException(status_code=404, detail="Docs have not been uploaded yet")
    content = storage.get_object(filename)
    return Response(content=content, media_type=CONTENT_TYPES[filename])


@app.get("/")
def serve_index(storage: StorageBackend = Depends(get_storage_backend)):
    return _serve_file("index.html", storage)


@app.get("/manifest.json")
def serve_manifest(storage: StorageBackend = Depends(get_storage_backend)):
    return _serve_file("manifest.json", storage)


@app.get("/catalog.json")
def serve_catalog(storage: StorageBackend = Depends(get_storage_backend)):
    return _serve_file("catalog.json", storage)
