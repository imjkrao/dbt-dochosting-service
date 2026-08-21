from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings


def verify_upload_api_key(
    x_api_key: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_api_key != settings.upload_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
