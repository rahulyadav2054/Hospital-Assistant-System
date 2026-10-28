from fastapi import APIRouter, Depends, HTTPException

from ai.retriever import get_chunk

from ..auth import get_current_user

router = APIRouter(tags=["sources"])


@router.get("/sources/{chunk_id:path}")
def source(chunk_id: str, user=Depends(get_current_user)):
    """Exact text of a cited document chunk (hospital documents only - never patient records)."""
    chunk = get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(404, "Source not found")
    return chunk
