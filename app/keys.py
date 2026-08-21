"""Storage key layout for hosted dbt docs.

Keys are fully parameterized by org, project and version, so one deployment can
host many projects and retain history:

    orgs/{org}/projects/{project}/versions/{version}/{filename}
    orgs/{org}/projects/{project}/LATEST

Until organizations and projects live in a database, callers pass
``DEFAULT_ORG``/``DEFAULT_PROJECT``. The single-project deployment keeps working
while the layout underneath it is already multi-tenant.

The ``LATEST`` pointer is a stopgap for resolving the newest version without a
database: it holds a single version id. Concurrent uploads resolve last-writer-
wins, which is acceptable because a project's docs are published by one CI job.
"""

import re
import secrets
from datetime import datetime, timezone

DEFAULT_ORG = "default"
DEFAULT_PROJECT = "default"

LATEST_POINTER = "LATEST"

#: Slugs appear directly in storage keys and URLs, so they are deliberately
#: narrow: lowercase, no dots (which would allow ``..`` traversal), no slashes.
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

#: Version ids are timestamp-prefixed at microsecond resolution so that lexical
#: order is chronological order — listing a project's versions returns them
#: already sorted. Second resolution is not enough: two CI uploads land in the
#: same second easily, and the random suffix would then decide the order.
VERSION_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")


class InvalidKeyError(ValueError):
    """Raised when a caller-supplied slug or version id is not well formed."""


def new_version_id(now: datetime | None = None) -> str:
    """Generate a sortable, collision-resistant version id."""
    moment = now or datetime.now(timezone.utc)
    return f"{moment.strftime('%Y%m%dT%H%M%S%f')}Z-{secrets.token_hex(4)}"


def validate_slug(value: str, *, field: str) -> str:
    if not SLUG_PATTERN.match(value):
        raise InvalidKeyError(
            f"Invalid {field} '{value}': use 1-63 characters of a-z, 0-9, '-' or '_', "
            "starting with a letter or digit"
        )
    return value


def validate_version(value: str) -> str:
    if not VERSION_PATTERN.match(value):
        raise InvalidKeyError(f"Invalid version id '{value}'")
    return value


def project_prefix(org: str, project: str) -> str:
    validate_slug(org, field="org")
    validate_slug(project, field="project")
    return f"orgs/{org}/projects/{project}"


def versions_prefix(org: str, project: str) -> str:
    return f"{project_prefix(org, project)}/versions"


def version_prefix(org: str, project: str, version: str) -> str:
    validate_version(version)
    return f"{versions_prefix(org, project)}/{version}"


def doc_key(org: str, project: str, version: str, filename: str) -> str:
    return f"{version_prefix(org, project, version)}/{filename}"


def latest_pointer_key(org: str, project: str) -> str:
    return f"{project_prefix(org, project)}/{LATEST_POINTER}"


def version_from_key(key: str) -> str | None:
    """Extract the version id from a full doc key, or None if it has none."""
    parts = key.split("/")
    if len(parts) >= 6 and parts[4] == "versions":
        return parts[5]
    return None
