# Backend + AI layer (FastAPI, retrieval models, ChromaDB, SQLite).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hf_cache \
    TRANSFORMERS_VERBOSITY=error \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    DATABASE_URL=sqlite:////app/data/db/hospital.db

WORKDIR /app
RUN mkdir -p /app/data/db

# CPU-only PyTorch first: the default wheel bundles CUDA and is ~2 GB bigger.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY ai ai
COPY backend backend
COPY data/docs data/docs
COPY data/seed data/seed

# Bake the embedding + reranker models and the vector index into the image,
# so the container starts fast and works without internet.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')" \
 && python -m ai.ingest

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready')" || exit 1

# SEED_ON_START=true (default) rebuilds the demo data on every start; set false to keep data in the volume.
CMD ["sh", "-c", "if [ \"${SEED_ON_START:-true}\" = \"true\" ] || [ ! -f /app/data/db/hospital.db ]; then python -m backend.app.seed --reset; fi && exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
