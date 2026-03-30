from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from blackbox.db.session import get_db
from blackbox.db.models import Client
from blackbox.security.auth import create_access_token, TokenPayload

router = APIRouter(prefix="/auth", tags=["auth"])

class TokenRequest(BaseModel):
    client_id: str
    client_secret: str

@router.post("/token")
async def login_for_access_token(
    form_data: TokenRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    # Verify client credentials
    client = await db.execute(
        select(Client).where(
            Client.client_id == form_data.client_id,
            Client.client_secret == form_data.client_secret  # In prod: hash this
        )
    )
    client = client.scalar_one_or_none()
    
    if not client:
        raise HTTPException(
            status_code=401,
            detail="Incorrect client_id or client_secret",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    scopes = client.scopes.split(',') if client.scopes else ['query']
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = await create_access_token(
        data={"sub": client.client_id, "scopes": scopes},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "client_id": client.client_id,
        "scopes": scopes,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }