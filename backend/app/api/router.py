from fastapi import APIRouter

from app.api import artifacts, chat, health, sessions

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(sessions.router)
api_router.include_router(artifacts.router)
