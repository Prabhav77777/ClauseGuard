"""
MODULE: Application entry point, FastAPI initialization, lifespan management, middleware, and background session cleanup.

@level-one-validation: Central app entry point. Min-heap session cleanup and lifespan handlers are solid, but in-memory session store is single-process bound. Verified by test_api.py and test_security.py.

#Scope-Of-Improvement: Migrate in-memory session dictionary and min-heap to Redis for distributed multi-worker production deployments.
"""

import asyncio
import heapq
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.api.chat import router as chat_router
from backend.api.compare import router as compare_router
from backend.api.documents import router as documents_router
from backend.config import settings
from backend.core.limiter import limiter

# Logging configuration
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# @risk-area: In-memory session store is lost on process restart and cannot be shared across multiple worker processes.
# Session store & Efficiency min-heap for O(1) peek / O(log N) session expiration
sessions: dict[str, Any] = {}
sessions_heap: list[tuple[float, str]] = []  # tuple of (expiry_timestamp, session_id)
sessions_lock = asyncio.Lock()


# #What: Pushes a session entry into the min-heap ordered by expiry timestamp
def push_session_expiry(session_id: str, last_accessed: float | None = None):
    """Push a session entry into the min-heap ordered by expiry timestamp."""
    ts = last_accessed if last_accessed is not None else time.time()
    expiry = ts + settings.SESSION_TTL_SECONDS
    heapq.heappush(sessions_heap, (expiry, session_id))


# #What: Background async loop purging expired sessions based on TTL
async def cleanup_sessions():
    """Background task to clean up expired sessions using a min-heap."""
    while True:
        try:
            await asyncio.sleep(600)  # run every 10 minutes
            now = time.time()
            async with sessions_lock:
                expired_count = 0
                while sessions_heap and sessions_heap[0][0] <= now:
                    expiry, sid = heapq.heappop(sessions_heap)
                    data = sessions.get(sid)
                    if data is None:
                        continue

                    # Verify actual expiry timestamp from DocumentSession instance
                    last_accessed = getattr(data, "last_accessed", now) if not isinstance(data, dict) else data.get("last_accessed", now)

                    actual_expiry = last_accessed + settings.SESSION_TTL_SECONDS
                    if actual_expiry <= now:
                        del sessions[sid]
                        if hasattr(app.state, "retrievers") and sid in app.state.retrievers:
                            del app.state.retrievers[sid]
                        expired_count += 1
                    else:
                        # Session was refreshed; re-push updated expiry to heap
                        heapq.heappush(sessions_heap, (actual_expiry, sid))

                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired sessions.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in session cleanup: {e}")


# #What: Manages FastAPI lifecycle startup and cleanup tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting ClauseGuard API...")
    app.state.sessions = sessions
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

# Response Compression Middleware for Network Bandwidth Efficiency
app.add_middleware(GZipMiddleware, minimum_size=500)


# Security Response Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https:;"
    return response


# Security: CORS Middleware
# Production: Set CORS_ORIGINS in .env to explicit frontend domain list (e.g. ["https://clauseguard.vercel.app"])
# Development fallback: Defaults to local origins with restrictive methods for API security.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Rate limiter exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


# #Business-Intent: Generic unhandled exception handler masks internal stack traces from client responses to satisfy production API security requirements.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )


@app.get("/")
@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "ClauseGuard API"}


app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(compare_router)
