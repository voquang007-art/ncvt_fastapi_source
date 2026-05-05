from sqlalchemy.orm import Session

from .models import DemandRequest, DemandRequestLog, Unit
from .time_utils import vietnam_now


def next_request_no(db: Session, unit: Unit, month: int, year: int) -> str:
    prefix = f"NCVT-{year}-{month:02d}"
    count = db.query(DemandRequest).filter(DemandRequest.year == year, DemandRequest.month == month).count() + 1
    return f"{prefix}-{count:03d}"


def add_log(db: Session, request_id: int, user_id: int | None, action: str, note: str | None = None, old_data: str | None = None, new_data: str | None = None):
    db.add(DemandRequestLog(
        request_id=request_id,
        user_id=user_id,
        action=action,
        note=note,
        old_data=old_data,
        new_data=new_data,
    ))


def touch_request(req: DemandRequest):
    req.updated_at = vietnam_now()
