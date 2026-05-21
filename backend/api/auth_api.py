"""
API Authentification & Gestion Utilisateurs
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import jwt
from loguru import logger
from backend.database import get_db
from backend.models.user import User, UserRole
from backend.services.email_service import send_account_created, send_password_changed
from backend.config import settings

router = APIRouter(prefix="/auth", tags=["Auth"])
users_router = APIRouter(prefix="/users", tags=["Users"])

# ── Crypto ────────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=24)
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


# ── Schemas ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.user

class ChangePasswordRequest(BaseModel):
    email: EmailStr
    old_password: str
    new_password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    # Mettre à jour last_login
    await db.execute(
        update(User).where(User.id == user.id)
        .values(last_login=datetime.now(timezone.utc))
    )
    await db.commit()

    token = create_token({"sub": str(user.id), "email": user.email, "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        }
    }


# ── Créer un utilisateur (admin) ──────────────────────────────────────────────
@users_router.post("/", response_model=UserResponse)
async def create_user(req: CreateUserRequest, db: AsyncSession = Depends(get_db)):
    # Vérifier si l'email existe déjà
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    user = User(
        email=req.email,
        full_name=req.full_name,
        hashed_password=hash_password(req.password),
        role=req.role,
        must_change_password=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Envoyer email de bienvenue
    await send_account_created(req.email, req.full_name, req.password)
    logger.info(f"[Auth] Utilisateur créé : {req.email}")

    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
    )


# ── Lister les utilisateurs ───────────────────────────────────────────────────
@users_router.get("/")
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "must_change_password": u.must_change_password,
            "created_at": u.created_at,
            "last_login": u.last_login,
        }
        for u in users
    ]


# ── Changer mot de passe ──────────────────────────────────────────────────────
@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.old_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")

    await db.execute(
        update(User).where(User.id == user.id).values(
            hashed_password=hash_password(req.new_password),
            must_change_password=False,
        )
    )
    await db.commit()

    await send_password_changed(req.email, user.full_name or req.email)
    return {"message": "Mot de passe modifié avec succès"}


# ── Activer / Désactiver ──────────────────────────────────────────────────────
@users_router.patch("/{user_id}/toggle")
async def toggle_user(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    await db.execute(
        update(User).where(User.id == user.id).values(is_active=not user.is_active)
    )
    await db.commit()
    return {"message": f"Compte {'activé' if not user.is_active else 'désactivé'}"}