import hmac

from fastapi import HTTPException, Request, status


def verify_upload_api_key(request: Request) -> None:
    """Authenticate a publishing client.

    Settings come from app state rather than the process-wide env cache, so a
    test app (or, later, a per-tenant one) authenticates against its own key.

    A missing header is a 401 like any other failed credential, rather than the
    422 FastAPI would raise for a required header. The comparison is
    constant-time so a wrong key leaks nothing about the right one.
    """
    provided = request.headers.get("x-api-key")
    expected = request.app.state.settings.upload_api_key
    if provided is None or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
