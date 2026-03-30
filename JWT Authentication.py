from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any
from pydantic import BaseModel
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from blackbox.db.models import Client

SECRET_KEY = "neuroflow-super-secret-key-2024-change-in-prod"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

class TokenPayload(BaseModel):
    sub: str  # client_id
    scopes: list[str]

security = HTTPBearer()

async def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> TokenPayload:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
        return token_data
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(token: TokenPayload = Depends(verify_token)) -> TokenPayload:
    return token

def require_scope(required_scope: str):
    def scope_checker(current_user: TokenPayload = Depends(get_current_user)):
        if required_scope not in current_user.scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Scope '{required_scope}' required"
            )
        return current_user
    return scope_checker