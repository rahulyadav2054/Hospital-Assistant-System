"""Audit logger. Every request, tool call and action is recorded - with PHI masked.

Never log lab values, names, phone numbers, raw tokens or passwords. Log record IDs instead.
"""
import json
import logging
from datetime import datetime

from .db import db_session
from .models import AuditLog

log = logging.getLogger("audit")

# Argument values that are safe to keep verbatim (identifiers and filters, not health data).
SAFE_ARG_KEYS = {"status", "department", "order_type", "latest_only", "doc_type", "test_name",
                 "procedure_name", "procedure_code", "appointment_id", "slot_id", "doctor_id", "from_date",
                 "pending_action_id"}


def mask_args(args: dict | None) -> str | None:
    if not args:
        return None
    masked = {}
    for k, v in args.items():
        if k in SAFE_ARG_KEYS and isinstance(v, (str, int, float, bool)):
            masked[k] = v if not isinstance(v, str) else v[:60]
        else:
            # Free text (e.g. search queries) may contain names or symptoms - keep only its size.
            masked[k] = f"<masked:{len(str(v))} chars>"
    return json.dumps(masked)


def audit(user_ctx: dict | None, *, endpoint=None, intent=None, tool=None, args=None, outcome=None,
          latency_ms=None) -> None:
    """Write one audit row. Never raises - auditing must not break the request."""
    try:
        with db_session() as db:
            db.add(AuditLog(ts=datetime.now(), user_id=(user_ctx or {}).get("user_id"),
                            role=(user_ctx or {}).get("role"), endpoint=endpoint, intent=intent, tool_name=tool,
                            args_masked=mask_args(args), outcome=(str(outcome)[:100] if outcome else None),
                            latency_ms=latency_ms))
            db.commit()
    except Exception:  # pragma: no cover - logging only
        log.exception("audit write failed")
