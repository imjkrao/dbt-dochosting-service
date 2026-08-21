from tests.conftest import upload


def test_serving_before_upload_returns_404(client):
    assert client.get("/").status_code == 404


def test_upload_requires_valid_api_key(client):
    assert upload(client, api_key="wrong-key").status_code == 401


def test_upload_without_api_key_header_is_401_not_422(client):
    files = {
        "index_html": ("index.html", b"x", "text/html"),
        "manifest_json": ("manifest.json", b"{}", "application/json"),
        "catalog_json": ("catalog.json", b"{}", "application/json"),
    }
    assert client.post("/upload", files=files).status_code == 401


def test_upload_and_serve_docs(client):
    response = upload(client)
    assert response.status_code == 200

    body = response.json()
    assert set(body["files"]) == {"index.html", "manifest.json", "catalog.json"}
    assert body["project"] == "default"
    assert body["version"]

    index = client.get("/")
    assert index.status_code == 200
    assert index.text == "<html>docs</html>"
    assert index.headers["content-type"].startswith("text/html")

    assert client.get("/manifest.json").json() == {"nodes": {}}
    assert client.get("/catalog.json").json() == {"nodes": {}}


def test_run_results_is_uploadable_and_servable(client):
    response = upload(client, run_results=True)
    assert "run_results.json" in response.json()["files"]
    assert client.get("/run_results.json").json() == {"results": []}


def test_upload_returns_a_usable_version_url(client):
    version_url = upload(client).json()["version_url"]
    assert client.get(version_url).text == "<html>docs</html>"


def test_latest_reflects_the_newest_upload(client):
    upload(client, index=b"<html>first</html>")
    first = client.get("/").text

    upload(client, index=b"<html>second</html>")
    assert first == "<html>first</html>"
    assert client.get("/").text == "<html>second</html>"


def test_old_versions_stay_readable_after_a_new_upload(client):
    first_url = upload(client, index=b"<html>first</html>").json()["version_url"]
    upload(client, index=b"<html>second</html>")

    assert client.get(first_url).text == "<html>first</html>"
    assert client.get("/").text == "<html>second</html>"


def test_conditional_get_returns_304(client):
    upload(client)
    first = client.get("/")
    etag = first.headers["etag"]

    again = client.get("/", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_pinned_versions_are_cached_immutably(client):
    version_url = upload(client).json()["version_url"]
    assert "immutable" in client.get(version_url).headers["cache-control"]
    assert "immutable" not in client.get("/").headers["cache-control"]


def test_unknown_artifact_is_404(client):
    upload(client)
    assert client.get("/p/default/secrets.env").status_code == 404


def test_upload_over_the_size_cap_is_rejected(settings):
    import boto3
    from fastapi.testclient import TestClient
    from moto import mock_aws

    from app.main import create_app
    from tests.conftest import make_settings

    small = make_settings(max_upload_bytes=64)
    with mock_aws():
        boto3.client("s3", region_name=small.s3_region).create_bucket(Bucket=small.s3_bucket)
        client = TestClient(create_app(small))
        response = upload(client, index=b"x" * 500)
    assert response.status_code == 413


def test_requests_carry_a_request_id(client):
    assert client.get("/healthz").headers["x-request-id"]
