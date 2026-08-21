import logging

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, RedirectResponse

from . import keys
from .artifacts import ARTIFACTS, BY_FILENAME, content_type_for
from .config import Settings, get_settings
from .observability import RequestContextMiddleware, configure_logging
from .security import verify_upload_api_key
from .storage import StorageBackend, build_storage_backend

log = logging.getLogger("dochost")

UPLOAD_CHUNK_BYTES = 1024 * 1024


# --------------------------------------------------------------------------- #
# Dependencies — resolved from app state so one process can host one config
# now and, later, per-tenant configuration without a module-level singleton.
# --------------------------------------------------------------------------- #


def get_storage(request: Request) -> StorageBackend:
    return request.app.state.storage


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _read_capped(upload: UploadFile, limit: int) -> bytes:
    """Read an upload in chunks, refusing anything over the configured cap.

    The cap is what makes memory use predictable: without it a single large
    manifest decides how much the process allocates.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"{upload.filename or 'file'} exceeds the {limit} byte upload limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _resolve_latest(storage: StorageBackend, org: str, project: str) -> str:
    pointer = keys.latest_pointer_key(org, project)
    if storage.get_metadata(pointer) is None:
        raise HTTPException(status_code=404, detail="Docs have not been uploaded yet")
    return storage.get_object(pointer).decode("utf-8").strip()


def _serve(
    *,
    request: Request,
    storage: StorageBackend,
    settings: Settings,
    key: str,
    filename: str,
    immutable: bool,
) -> Response:
    info = storage.get_metadata(key)
    if info is None:
        raise HTTPException(status_code=404, detail="Docs have not been uploaded yet")

    etag = f'"{info.etag}"' if info.etag else None
    cache_control = "public, max-age=31536000, immutable" if immutable else "public, max-age=60"
    headers = {"Cache-Control": cache_control}
    if etag:
        headers["ETag"] = etag
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    artifact = BY_FILENAME.get(filename)
    if settings.presigned_redirects and artifact and artifact.large:
        url = storage.get_presigned_url(key, settings.presigned_expiry_seconds)
        if url:
            return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    media_type = content_type_for(filename)

    if request.method == "HEAD":
        # Answer from metadata alone. Fetching the object to discard its body
        # would mean downloading a whole manifest per HEAD request.
        headers["Content-Length"] = str(info.size)
        return Response(status_code=200, media_type=media_type, headers=headers)

    return Response(content=storage.get_object(key), media_type=media_type, headers=headers)


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(title="dbt Doc Hosting Service", version="0.2.0")
    app.add_middleware(RequestContextMiddleware)

    app.state.settings = settings
    app.state.storage = build_storage_backend(settings)

    @app.exception_handler(keys.InvalidKeyError)
    async def _invalid_key(_: Request, exc: keys.InvalidKeyError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ----------------------------- health ---------------------------------- #

    @app.api_route("/healthz", methods=["GET", "HEAD"], tags=["ops"])
    def healthz() -> dict:
        """Liveness: is the process up. Deliberately does not touch storage."""
        return {"status": "ok"}

    @app.api_route("/readyz", methods=["GET", "HEAD"], tags=["ops"])
    def readyz(storage: StorageBackend = Depends(get_storage)) -> dict:
        """Readiness: can the process actually reach its storage backend."""
        try:
            storage.health_check()
        except Exception as exc:
            log.warning("readiness check failed", extra={"error": str(exc)})
            raise HTTPException(status_code=503, detail="Storage backend unreachable") from exc
        return {"status": "ok", "backend": app.state.settings.storage_backend}

    # ----------------------------- upload ---------------------------------- #

    @app.post(
        "/api/v1/projects/{project}/versions",
        dependencies=[Depends(verify_upload_api_key)],
        tags=["publish"],
    )
    async def publish_version(
        project: str,
        index_html: UploadFile = File(...),
        manifest_json: UploadFile = File(...),
        catalog_json: UploadFile = File(...),
        run_results_json: UploadFile | None = File(None),
        storage: StorageBackend = Depends(get_storage),
        settings: Settings = Depends(get_app_settings),
    ) -> dict:
        """Publish a new immutable version of a project's docs."""
        org = keys.DEFAULT_ORG
        keys.validate_slug(project, field="project")

        uploads = {
            "index.html": index_html,
            "manifest.json": manifest_json,
            "catalog.json": catalog_json,
        }
        if run_results_json is not None:
            uploads["run_results.json"] = run_results_json

        version = keys.new_version_id()
        written: list[str] = []
        for filename, upload in uploads.items():
            body = await _read_capped(upload, settings.max_upload_bytes)
            storage.put_object(
                keys.doc_key(org, project, version, filename), body, content_type_for(filename)
            )
            written.append(filename)

        # Publish the pointer only once every artifact landed, so a failed
        # upload never leaves "latest" pointing at a half-written version.
        storage.put_object(
            keys.latest_pointer_key(org, project), version.encode("utf-8"), "text/plain"
        )

        log.info("published docs", extra={"project": project, "version": version, "files": len(written)})
        return {
            "status": "uploaded",
            "project": project,
            "version": version,
            "files": written,
            "url": f"/p/{project}/",
            "version_url": f"/p/{project}/v/{version}/",
        }

    @app.post("/upload", dependencies=[Depends(verify_upload_api_key)], tags=["publish"])
    async def upload_docs(
        index_html: UploadFile = File(...),
        manifest_json: UploadFile = File(...),
        catalog_json: UploadFile = File(...),
        run_results_json: UploadFile | None = File(None),
        storage: StorageBackend = Depends(get_storage),
        settings: Settings = Depends(get_app_settings),
    ) -> dict:
        """Publish to the default project. Kept for existing single-project CI jobs."""
        return await publish_version(
            project=keys.DEFAULT_PROJECT,
            index_html=index_html,
            manifest_json=manifest_json,
            catalog_json=catalog_json,
            run_results_json=run_results_json,
            storage=storage,
            settings=settings,
        )

    # ----------------------------- history --------------------------------- #

    @app.get("/api/v1/projects/{project}/versions", tags=["history"])
    def list_versions(
        project: str, storage: StorageBackend = Depends(get_storage)
    ) -> dict:
        org = keys.DEFAULT_ORG
        prefix = keys.versions_prefix(org, project)

        seen: dict[str, dict] = {}
        for info in storage.list_objects(prefix):
            version = keys.version_from_key(info.key)
            if version is None:
                continue
            entry = seen.setdefault(
                version, {"version": version, "size_bytes": 0, "created_at": None, "files": []}
            )
            entry["size_bytes"] += info.size
            entry["files"].append(info.key.rsplit("/", 1)[-1])
            if info.last_modified and (
                entry["created_at"] is None or info.last_modified < entry["created_at"]
            ):
                entry["created_at"] = info.last_modified

        versions = sorted(seen.values(), key=lambda v: v["version"], reverse=True)
        return {"project": project, "count": len(versions), "versions": versions}

    @app.delete(
        "/api/v1/projects/{project}/versions/{version}",
        dependencies=[Depends(verify_upload_api_key)],
        tags=["history"],
    )
    def delete_version(
        project: str, version: str, storage: StorageBackend = Depends(get_storage)
    ) -> dict:
        org = keys.DEFAULT_ORG
        prefix = keys.version_prefix(org, project, version)

        objects = storage.list_objects(prefix)
        if not objects:
            raise HTTPException(status_code=404, detail="Version not found")
        for info in objects:
            storage.delete_object(info.key)

        log.info("deleted version", extra={"project": project, "version": version})
        return {"status": "deleted", "project": project, "version": version, "removed": len(objects)}

    # ----------------------------- serving --------------------------------- #

    def _serve_from(project: str, version: str, filename: str, request, storage, settings, immutable):
        return _serve(
            request=request,
            storage=storage,
            settings=settings,
            key=keys.doc_key(keys.DEFAULT_ORG, project, version, filename),
            filename=filename,
            immutable=immutable,
        )

    # Pinned-version routes are declared first so "v" is never taken as a filename.
    @app.api_route("/p/{project}/v/{version}/", methods=["GET", "HEAD"], tags=["serve"])
    def serve_pinned_index(
        project: str,
        version: str,
        request: Request,
        storage: StorageBackend = Depends(get_storage),
        settings: Settings = Depends(get_app_settings),
    ) -> Response:
        return _serve_from(project, version, "index.html", request, storage, settings, True)

    @app.api_route("/p/{project}/v/{version}/{filename}", methods=["GET", "HEAD"], tags=["serve"])
    def serve_pinned_file(
        project: str,
        version: str,
        filename: str,
        request: Request,
        storage: StorageBackend = Depends(get_storage),
        settings: Settings = Depends(get_app_settings),
    ) -> Response:
        if filename not in BY_FILENAME:
            raise HTTPException(status_code=404, detail="Unknown artifact")
        return _serve_from(project, version, filename, request, storage, settings, True)

    @app.api_route("/p/{project}/", methods=["GET", "HEAD"], tags=["serve"])
    def serve_index(
        project: str,
        request: Request,
        storage: StorageBackend = Depends(get_storage),
        settings: Settings = Depends(get_app_settings),
    ) -> Response:
        version = _resolve_latest(storage, keys.DEFAULT_ORG, project)
        return _serve_from(project, version, "index.html", request, storage, settings, False)

    @app.api_route("/p/{project}/{filename}", methods=["GET", "HEAD"], tags=["serve"])
    def serve_file(
        project: str,
        filename: str,
        request: Request,
        storage: StorageBackend = Depends(get_storage),
        settings: Settings = Depends(get_app_settings),
    ) -> Response:
        if filename not in BY_FILENAME:
            raise HTTPException(status_code=404, detail="Unknown artifact")
        version = _resolve_latest(storage, keys.DEFAULT_ORG, project)
        return _serve_from(project, version, filename, request, storage, settings, False)

    # Default-project shortcuts, preserving the original single-project URLs.
    @app.api_route("/", methods=["GET", "HEAD"], tags=["serve"])
    def serve_default_index(
        request: Request,
        storage: StorageBackend = Depends(get_storage),
        settings: Settings = Depends(get_app_settings),
    ) -> Response:
        return serve_index(keys.DEFAULT_PROJECT, request, storage, settings)

    for artifact in ARTIFACTS:
        _register_default_route(app, artifact.filename)

    return app


def _register_default_route(app: FastAPI, filename: str) -> None:
    """Expose ``/{filename}`` for the default project (e.g. ``/manifest.json``)."""

    @app.api_route(
        f"/{filename}",
        methods=["GET", "HEAD"],
        tags=["serve"],
        name=f"serve_default_{filename.replace('.', '_')}",
    )
    def _route(
        request: Request,
        storage: StorageBackend = Depends(get_storage),
        settings: Settings = Depends(get_app_settings),
    ) -> Response:
        version = _resolve_latest(storage, keys.DEFAULT_ORG, keys.DEFAULT_PROJECT)
        return _serve(
            request=request,
            storage=storage,
            settings=settings,
            key=keys.doc_key(keys.DEFAULT_ORG, keys.DEFAULT_PROJECT, version, filename),
            filename=filename,
            immutable=False,
        )
