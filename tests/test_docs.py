def _upload(client, api_key="test-api-key"):
    files = {
        "index_html": ("index.html", b"<html>docs</html>", "text/html"),
        "manifest_json": ("manifest.json", b'{"nodes": {}}', "application/json"),
        "catalog_json": ("catalog.json", b'{"nodes": {}}', "application/json"),
    }
    return client.post("/upload", files=files, headers={"x-api-key": api_key})


def test_serving_before_upload_returns_404(client):
    response = client.get("/")
    assert response.status_code == 404


def test_upload_requires_valid_api_key(client):
    response = _upload(client, api_key="wrong-key")
    assert response.status_code == 401


def test_upload_and_serve_docs(client):
    upload_response = _upload(client)
    assert upload_response.status_code == 200
    assert set(upload_response.json()["files"]) == {"index.html", "manifest.json", "catalog.json"}

    index_response = client.get("/")
    assert index_response.status_code == 200
    assert index_response.text == "<html>docs</html>"
    assert index_response.headers["content-type"].startswith("text/html")

    manifest_response = client.get("/manifest.json")
    assert manifest_response.status_code == 200
    assert manifest_response.json() == {"nodes": {}}

    catalog_response = client.get("/catalog.json")
    assert catalog_response.status_code == 200
    assert catalog_response.json() == {"nodes": {}}
