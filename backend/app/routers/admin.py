from fastapi import APIRouter, Depends, Query

from ..auth import require_staff
from ..db import get_db
from ..models import AuditLog

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit")
def audit_log(limit: int = Query(50, ge=1, le=500), user=Depends(require_staff), db=Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [{"id": r.id, "ts": r.ts.isoformat(timespec="seconds"), "user_id": r.user_id, "role": r.role,
             "endpoint": r.endpoint, "intent": r.intent, "tool": r.tool_name, "args": r.args_masked,
             "outcome": r.outcome, "latency_ms": r.latency_ms} for r in rows]
