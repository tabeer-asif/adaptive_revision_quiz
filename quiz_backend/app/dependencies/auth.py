# app/dependencies/auth.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.supabase_client import supabase_auth

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verifies the Supabase JWT sent in the Authorization header.
    Expects: "Bearer <access_token>"
    """
    token = credentials.credentials

    try:
        user_resp = supabase_auth.auth.get_user(token)
        if user_resp.user is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_resp.user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")