from fastapi import Depends, Header, HTTPException, Query
from navbe_core.models import UserModel, get_db
from navbe_core.repository import WorkflowRepository
from sqlalchemy.orm import Session


def get_api_key(x_api_key: str | None = Header(None), api_key: str | None = Query(None)) -> str:
    """Accept the key via the x-api-key header (REST calls) or an api_key
    query param — EventSource (used for the SSE run stream) can't set custom
    headers, so the stream endpoint relies on the query param instead.
    """
    key = x_api_key or api_key
    if not key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return key


def get_current_user(
    api_key: str = Depends(get_api_key), db: Session = Depends(get_db)
) -> UserModel:
    user = WorkflowRepository(db).get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user
