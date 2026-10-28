from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import audit
from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..tools.scheduling import ActionError, cancel_action, confirm_action

router = APIRouter(prefix="/actions", tags=["actions"])


class ActionIn(BaseModel):
    pending_action_id: str = Field(min_length=1, max_length=30)
    # Care plans only: indexes of the items the patient ticked (default: all).
    selected: list[int] | None = Field(default=None, max_length=10)


@router.post("/confirm")
def confirm(body: ActionIn, user=Depends(get_current_user), db=Depends(get_db)):
    if settings.MOCK_AI and body.pending_action_id == "PA-MOCK":
        return {"status": "done", "message": "Rescheduled (mock)."}
    try:
        result = confirm_action(db, user, body.pending_action_id, body.selected)
    except ActionError as e:
        audit(user, endpoint="/actions/confirm", args={"pending_action_id": body.pending_action_id},
              outcome=f"failed {e.status_code}")
        raise HTTPException(e.status_code, e.detail)
    audit(user, endpoint="/actions/confirm", args={"pending_action_id": body.pending_action_id},
          outcome="plan approved" if "results" in result else "rescheduled")
    return result


@router.post("/cancel")
def cancel(body: ActionIn, user=Depends(get_current_user), db=Depends(get_db)):
    if settings.MOCK_AI and body.pending_action_id == "PA-MOCK":
        return {"status": "cancelled"}
    try:
        result = cancel_action(db, user, body.pending_action_id)
    except ActionError as e:
        raise HTTPException(e.status_code, e.detail)
    audit(user, endpoint="/actions/cancel", args=body.model_dump(), outcome="cancelled")
    return result
