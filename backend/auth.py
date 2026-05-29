import bcrypt
import os
from datetime import datetime, timedelta
from jose import jwt
from fastapi import HTTPException, Cookie
from typing import Optional

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

def verify_password(plain: str) -> bool:
    stored_hash = os.getenv("APP_PASSWORD_HASH", "")
    if not stored_hash:
        # dev mode: ใช้ "research" เป็น default
        return plain == "research"
    return bcrypt.checkpw(plain.encode(), stored_hash.encode())

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def create_token() -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"exp": expire, "sub": "researcher"}, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: Optional[str] = Cookie(default=None)) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return token
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
