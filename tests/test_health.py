def test_healthz_does_not_touch_storage(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_the_backend(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "backend": "s3"}


def test_readyz_is_503_when_storage_is_unreachable(client, monkeypatch):
    def boom():
        raise RuntimeError("bucket gone")

    monkeypatch.setattr(client.app.state.storage, "health_check", boom)

    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["detail"] == "Storage backend unreachable"
