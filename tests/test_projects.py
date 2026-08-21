from tests.conftest import upload


def test_projects_are_isolated_from_each_other(client):
    upload(client, project="analytics", index=b"<html>analytics</html>")
    upload(client, project="finance", index=b"<html>finance</html>")

    assert client.get("/p/analytics/").text == "<html>analytics</html>"
    assert client.get("/p/finance/").text == "<html>finance</html>"


def test_default_routes_do_not_collide_with_named_projects(client):
    upload(client, index=b"<html>default</html>")
    upload(client, project="analytics", index=b"<html>analytics</html>")

    assert client.get("/").text == "<html>default</html>"
    assert client.get("/p/analytics/").text == "<html>analytics</html>"


def test_invalid_project_slug_is_rejected(client):
    response = upload(client, project="Not-A-Slug")
    assert response.status_code == 400


def test_unknown_project_is_404(client):
    assert client.get("/p/nosuchproject/").status_code == 404


def test_version_history_lists_newest_first(client):
    first = upload(client, project="analytics").json()["version"]
    second = upload(client, project="analytics").json()["version"]

    body = client.get("/api/v1/projects/analytics/versions").json()
    assert body["count"] == 2
    assert [v["version"] for v in body["versions"]] == [second, first]
    assert all(v["size_bytes"] > 0 for v in body["versions"])


def test_version_history_is_empty_for_unknown_project(client):
    body = client.get("/api/v1/projects/nosuchproject/versions").json()
    assert body == {"project": "nosuchproject", "count": 0, "versions": []}


def test_delete_version_removes_it_from_history(client):
    doomed = upload(client, project="analytics").json()["version"]
    kept = upload(client, project="analytics").json()["version"]

    response = client.delete(
        f"/api/v1/projects/analytics/versions/{doomed}", headers={"x-api-key": "test-api-key"}
    )
    assert response.status_code == 200
    assert response.json()["removed"] == 3

    remaining = client.get("/api/v1/projects/analytics/versions").json()
    assert [v["version"] for v in remaining["versions"]] == [kept]


def test_delete_requires_auth(client):
    version = upload(client, project="analytics").json()["version"]
    assert client.delete(f"/api/v1/projects/analytics/versions/{version}").status_code == 401


def test_delete_unknown_version_is_404(client):
    upload(client, project="analytics")
    response = client.delete(
        "/api/v1/projects/analytics/versions/20200101T000000000000Z-deadbeef",
        headers={"x-api-key": "test-api-key"},
    )
    assert response.status_code == 404


def test_everything_works_on_the_local_backend(local_client):
    upload(local_client, project="analytics", index=b"<html>local</html>")
    assert local_client.get("/p/analytics/").text == "<html>local</html>"
    assert local_client.get("/api/v1/projects/analytics/versions").json()["count"] == 1
