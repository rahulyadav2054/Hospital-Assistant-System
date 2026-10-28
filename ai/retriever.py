"""Vector search + cross-encoder rerank + not-found threshold.

An empty result means "not found" - the assistant must then give a grounded not-found reply.
"""
import threading

from . import config

DOC_TYPES = {"policy", "procedure", "insurance", "directory", "clinical_protocol"}

_lock = threading.RLock()  # re-entrant: get_collection() may ingest, which loads the embedder
_client = _embedder = _reranker = _collection = None
_ready = threading.Event()


def get_client():
    global _client
    with _lock:
        if _client is None:
            import chromadb
            from chromadb.config import Settings

            config.CHROMA_PATH.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(config.CHROMA_PATH),
                                                settings=Settings(anonymized_telemetry=False))
        return _client


def _load_model(cls, name):
    """Use the local cache first (fast, works without internet); download only if it is missing."""
    try:
        return cls(name, local_files_only=True)
    except Exception:
        return cls(name)


def get_embedder():
    global _embedder
    with _lock:
        if _embedder is None:
            from sentence_transformers import SentenceTransformer

            _embedder = _load_model(SentenceTransformer, config.EMBED_MODEL)
        return _embedder


def get_reranker():
    global _reranker
    with _lock:
        if _reranker is None:
            from sentence_transformers import CrossEncoder

            _reranker = _load_model(CrossEncoder, config.RERANK_MODEL)
        return _reranker


def warm_up() -> None:
    """Load models + collection and run one query, so the first real question is fast."""
    search("ICU visiting hours")
    _ready.set()


def is_ready() -> bool:
    return _ready.is_set()


def reset_collection_cache():
    global _collection
    _collection = None


def get_collection():
    """Open the collection, building it from data/docs on first use."""
    global _collection
    with _lock:
        if _collection is None:
            try:
                col = get_client().get_collection(config.COLLECTION)
                if col.count() == 0:
                    raise ValueError("empty collection")
            except Exception:
                from .ingest import ingest

                ingest(verbose=False)
                col = get_client().get_collection(config.COLLECTION)
            _collection = col
        return _collection


def _body(text: str) -> str:
    # Stored documents are "Title — Section\n<body>"; return just the body.
    return text.split("\n", 1)[1] if "\n" in text else text


def search(query: str, doc_type: str | None = None, k: int = 12, top_n: int = 4) -> list[dict]:
    if not query or not query.strip():
        return []
    col = get_collection()
    where = {"doc_type": doc_type} if doc_type in DOC_TYPES else None
    n = min(k, col.count())
    res = col.query(query_embeddings=get_embedder().encode([query], normalize_embeddings=True,
                                                           show_progress_bar=False).tolist(),
                    n_results=n, where=where)
    cands = [{"chunk_id": i, "_text": d, **m}
             for i, d, m in zip(res["ids"][0], res["documents"][0], res["metadatas"][0])]
    if not cands:
        return []
    scores = get_reranker().predict([(query, c["_text"]) for c in cands], show_progress_bar=False)
    for c, s in zip(cands, scores):
        c["score"] = round(float(s), 3)
    cands.sort(key=lambda c: c["score"], reverse=True)
    out = []
    for c in cands[:top_n]:
        if c["score"] < config.RERANK_THRESHOLD:
            continue
        out.append({"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "title": c["title"], "section": c["section"],
                    "doc_type": c["doc_type"], "effective_date": c["effective_date"], "text": _body(c["_text"]),
                    "score": c["score"]})
    return out


def get_chunk(chunk_id: str) -> dict | None:
    """Used by GET /sources/{chunk_id} to show the exact cited text."""
    r = get_collection().get(ids=[chunk_id])
    if not r["ids"]:
        return None
    m = r["metadatas"][0]
    return {"chunk_id": chunk_id, "doc_id": m["doc_id"], "title": m["title"], "section": m["section"],
            "doc_type": m["doc_type"], "effective_date": m["effective_date"], "version": m.get("version"),
            "text": _body(r["documents"][0])}
