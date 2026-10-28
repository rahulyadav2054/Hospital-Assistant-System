import datetime as dt

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .config import settings
from .db import get_db
from .limiter import limiter
from .models import Patient, User

router = APIRouter(tags=["auth"])
bearer = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "patient_id": user.patient_id,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def get_current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """Identity comes ONLY from the signed token - never from the request body or the LLM."""
    try:
        p = jwt.decode(cred.credentials, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    return {"user_id": int(p["sub"]), "role": p["role"], "patient_id": p.get("patient_id")}


def require_staff(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "staff":
        raise HTTPException(403, "Staff only")
    return user


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


def public_user(db, user: User) -> dict:
    name = user.display_name
    if user.patient_id:
        name = db.get(Patient, user.patient_id).name
    return {"id": user.id, "username": user.username, "name": name, "role": user.role,
            "patient_id": user.patient_id}


@router.post("/auth/login")
@limiter.limit(settings.LOGIN_RATE)
def login(request: Request, body: LoginIn, db=Depends(get_db)):
    user = db.query(User).filter_by(username=body.username.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": create_token(user), "token_type": "bearer", "user": public_user(db, user)}
