"""The dbt artifacts this service accepts and serves.

This registry used to live in ``main.py`` as a single dict doing triple duty as
allow-list, MIME map and implicit schema. Keeping it here makes each role
explicit and gives upload/serve a single source of truth.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Artifact:
    #: Name the file is stored under, matching dbt's own ``target/`` filenames.
    filename: str
    #: Multipart form field the uploader sends it as.
    field: str
    content_type: str
    required: bool
    #: Large artifacts are the ones worth handing off to a presigned URL rather
    #: than proxying through this process.
    large: bool = False


ARTIFACTS: tuple[Artifact, ...] = (
    Artifact("index.html", "index_html", "text/html", required=True),
    Artifact("manifest.json", "manifest_json", "application/json", required=True, large=True),
    Artifact("catalog.json", "catalog_json", "application/json", required=True, large=True),
    Artifact("run_results.json", "run_results_json", "application/json", required=False),
)

BY_FILENAME: dict[str, Artifact] = {a.filename: a for a in ARTIFACTS}
BY_FIELD: dict[str, Artifact] = {a.field: a for a in ARTIFACTS}

REQUIRED_FILENAMES: tuple[str, ...] = tuple(a.filename for a in ARTIFACTS if a.required)


def content_type_for(filename: str) -> str:
    artifact = BY_FILENAME.get(filename)
    return artifact.content_type if artifact else "application/octet-stream"
