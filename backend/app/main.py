import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from ai import retriever
from ai.config import ai_mode

from . import auth
from .config import settings
from .db import Base, engine
from .limiter import limiter
from .routers import actions, admin, chat, me, sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpx2", "huggingface_hub", "sentence_transformers"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("app")


def _warm_up():
    try:
        retriever.warm_up()
        log.info("Retrieval models loaded - ready")
    except Exception:
        log.exception("Warm-up failed; models will load on the first question")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading the embedding + reranker models takes several seconds; do it before the first question.
    threading.Thread(target=_warm_up, name="warm-up", daemon=True).start()
    yield


app = FastAPI(title="City Care Hospital - Patient Services Assistant API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

Base.metadata.create_all(engine)

for r in (auth.router, chat.router, actions.router, me.router, sources.router, admin.router):
    app.include_router(r)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "ai_mode": "mock" if settings.MOCK_AI else ai_mode(), "models_ready": retriever.is_ready()}


@app.get("/ready", tags=["meta"])
def ready():
    """503 until the retrieval models are loaded (used by the E2E runner and deploy health checks)."""
    if not retriever.is_ready():
        return JSONResponse({"ready": False}, status_code=503)
    return {"ready": True}
