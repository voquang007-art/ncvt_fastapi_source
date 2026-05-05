from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, ROLE_ADMIN, ROLE_SUMMARY, ROLE_APPROVER


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if not user or not user.is_active or not user.is_approved:
        request.session.clear()
        return None
    return user


def login_required(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def admin_required(current_user: User = Depends(login_required)) -> User:
    if current_user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Không có quyền Admin.")
    return current_user


def summary_required(current_user: User = Depends(login_required)) -> User:
    if current_user.role not in {ROLE_ADMIN, ROLE_SUMMARY, ROLE_APPROVER}:
        raise HTTPException(status_code=403, detail="Không có quyền tổng hợp.")
    return current_user


def can_view_all(current_user: User) -> bool:
    return current_user.role in {ROLE_ADMIN, ROLE_SUMMARY, ROLE_APPROVER}


def can_edit_request_status(status: str) -> bool:
    return status in {"DRAFT", "RETURNED_FOR_EDIT"}
