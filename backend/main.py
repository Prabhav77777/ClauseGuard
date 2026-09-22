import asyncio
import logging
import time
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.config import settings

# Logging configuration
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Session store
sessions: dict[str, Any] = {}
sessions_lock = asyncio.Lock()

async def cleanup_sessions():
    """Background task to clean up expired sessions."""
    while True:
        try:
            await asyncio.sleep(600)  # run every 10 minutes
            now = time.time()
            async with sessions_lock:
                expired = [
                    sid for sid, data in sessions.items()
                    if now - data.get("last_accessed", now) > settings.SESSION_TTL_SECONDS
                ]
                for sid in expired:
                    del sessions[sid]
                if expired:
                    logger.info(f"Cleaned up {len(expired)} expired sessions.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in session cleanup: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting ClauseGuard API...")
    app.state.sessions = {}
    app.state.retrievers = {}
    cleanup_task = asyncio.create_task(cleanup_sessions())
    yield
    # Shutdown
    logger.info("Shutting down ClauseGuard API...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="ClauseGuard API",
    description="GenAI-powered legal document analysis tool API",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

from backend.api.documents import router as documents_router
from backend.api.chat import router as chat_router
from backend.api.compare import router as compare_router

app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(compare_router)
