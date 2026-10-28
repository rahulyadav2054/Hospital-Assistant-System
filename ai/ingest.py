"""Load hospital documents -> split by heading -> window long sections -> embed -> store in ChromaDB.

Usage:  python -m ai.ingest
"""
import re

import yaml

from . import config


def parse(path):
    raw = path.read_text(encoding="utf-8")
    _, fm, body = raw.split("---", 2)
    return yaml.safe_load(fm), body


def split_sections(body):
    """Yield (section_heading, text) for each ##/### heading, so citations keep their section number."""
    parts = re.split(r"^(#{2,3} .+)$", body, flags=re.M)
    heading = "Introduction"
    for p in parts:
        if re.match(r"^#{2,3} ", p):
            heading = p.lstrip("# ").strip()
            continue
        text = re.sub(r"^# .*$", "", p, flags=re.M).strip()  # drop the H1 document title line
        if text:
            yield heading, text


def window(text, size=400, overlap=60):
    words = text.split(" ")
    for i in range(0, max(len(words), 1), size - overlap):
        yield " ".join(words[i:i + size])
        if i + size >= len(words):
            break


def build_chunks():
    ids, texts, metas = [], [], []
    for path in sorted(config.DOCS_PATH.glob("*.md")):
        meta, body = parse(path)
        for s_idx, (section, text) in enumerate(split_sections(body)):
            for c_idx, chunk in enumerate(window(text)):
                ids.append(f"{meta['doc_id']}::{s_idx}::{c_idx}")
                # Prefix title + section so the embedding (and the reranker) know the context.
                texts.append(f"{meta['title']} — {section}\n{chunk}")
                metas.append({**{k: str(v) for k, v in meta.items()}, "section": section})
    return ids, texts, metas


def ingest(verbose: bool = True) -> int:
    from .retriever import get_client, get_embedder, reset_collection_cache

    client = get_client()
    try:
        client.delete_collection(config.COLLECTION)
    except Exception:
        pass  # collection did not exist yet
    col = client.create_collection(config.COLLECTION, metadata={"hnsw:space": "cosine"})
    ids, texts, metas = build_chunks()
    embeddings = get_embedder().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
    col.add(ids=ids, documents=texts, metadatas=metas, embeddings=embeddings)
    reset_collection_cache()
    if verbose:
        print(f"Ingested {len(ids)} chunks from {len(set(m['doc_id'] for m in metas))} documents")
    return len(ids)


if __name__ == "__main__":
    ingest()
