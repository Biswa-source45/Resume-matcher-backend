from fastapi import Request, HTTPException, Response, Depends
import jwt
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

JWT_SECRET = os.getenv("JWT_SECRET", "secret-key-change-in-production")
JWT_ALGO = "HS256"

def create_jwt(payload: dict, expires_in_days: int = 7) -> str:
    """Create a JWT token with expiration"""
    payload = payload.copy()
    payload["exp"] = datetime.utcnow() + timedelta(days=expires_in_days)
    payload["iat"] = datetime.utcnow()
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    return token

def verify_jwt_cookie(request: Request) -> Dict[str, Any]:
    """Verify JWT token from cookie"""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return decoded
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def set_auth_cookie(response: Response, token: str, max_age: int = 60 * 60 * 24 * 7):
    """Set HTTP-only cookie with authentication token"""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="Lax",
        secure=False,  # Set to True in production with HTTPS
        max_age=max_age,
        path="/"
    )

def clear_auth_cookie(response: Response):
    """Clear authentication cookie"""
    response.delete_cookie(key="access_token", path="/")