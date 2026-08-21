"""HEAD support.

FastAPI's ``@app.get`` registers only GET, unlike plain Starlette routes which
add HEAD automatically — so every read route used to answer 405. Monitors,
caches and link checkers all issue HEAD.
"""

import pytest

from tests.conftest import upload

READ_PATHS = [
    "/",
    "/manifest.json",
    "/catalog.json",
    "/p/default/",
    "/p/default/manifest.json",
]


@pytest.mark.parametrize("path", READ_PATHS)
def test_head_is_allowed_on_read_routes(client, path):
    upload(client)
    assert client.head(path).status_code == 200


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_head_is_allowed_on_ops_routes(client, path):
    assert client.head(path).status_code == 200


def test_head_returns_no_body(client):
    upload(client)
    assert client.head("/").content == b""


def test_head_headers_match_get(client):
    upload(client)
    head = client.head("/")
    get = client.get("/")

    assert head.headers["content-type"] == get.headers["content-type"]
    assert head.headers["etag"] == get.headers["etag"]
    assert head.headers["cache-control"] == get.headers["cache-control"]


def test_head_reports_the_real_content_length(client):
    body = b"<html>" + b"x" * 5000 + b"</html>"
    upload(client, index=body)

    head = client.head("/")
    assert head.headers["content-length"] == str(len(body))
    assert len(client.get("/").content) == len(body)


def test_head_does_not_fetch_the_object_body(client):
    """The whole point of answering from metadata: no pointless download."""
    upload(client)
    storage = client.app.state.storage

    fetched: list[str] = []
    original = storage.get_object

    def spy(key):
        fetched.append(key)
        return original(key)

    storage.get_object = spy
    try:
        client.head("/p/default/manifest.json")
        head_reads = list(fetched)

        fetched.clear()
        client.get("/p/default/manifest.json")
        get_reads = list(fetched)
    finally:
        storage.get_object = original

    assert not any(k.endswith("manifest.json") for k in head_reads)
    assert any(k.endswith("manifest.json") for k in get_reads)


def test_head_on_missing_docs_is_404(client):
    assert client.head("/").status_code == 404


def test_head_on_unknown_artifact_is_404(client):
    upload(client)
    assert client.head("/p/default/secrets.env").status_code == 404


def test_head_honours_conditional_requests(client):
    upload(client)
    etag = client.head("/").headers["etag"]
    assert client.head("/", headers={"If-None-Match": etag}).status_code == 304


def test_head_on_a_pinned_version(client):
    version_url = upload(client).json()["version_url"]
    response = client.head(version_url)
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


def test_publish_routes_still_reject_head(client):
    assert client.head("/upload").status_code == 405
