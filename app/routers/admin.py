from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_required
from ..models import DemandRequest, DemandRequestLog, ROLE_LABELS, Unit, User

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update(ROLE_LABELS=ROLE_LABELS, NAV_MONTH=date.today().month, NAV_YEAR=date.today().year)


def _redirect_users(message: str = "") -> RedirectResponse:
    if message:
        return RedirectResponse(f"/admin/users?message={message}", status_code=303)
    return RedirectResponse("/admin/users", status_code=303)


def _is_ajax(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _user_has_history(db: Session, user_id: int) -> bool:
    request_count = db.query(DemandRequest).filter(
        or_(
            DemandRequest.created_by == user_id,
            DemandRequest.unit_approved_by == user_id,
            DemandRequest.summarized_by == user_id,
            DemandRequest.closed_by == user_id,
        )
    ).count()
    if request_count:
        return True

    log_count = db.query(DemandRequestLog).filter(DemandRequestLog.user_id == user_id).count()
    return log_count > 0


def _unit_has_history(db: Session, unit_id: int) -> bool:
    user_count = db.query(User).filter(User.unit_id == unit_id).count()
    if user_count:
        return True

    request_count = db.query(DemandRequest).filter(DemandRequest.unit_id == unit_id).count()
    return request_count > 0


def _serialize_unit(unit: Unit) -> dict:
    return {
        "id": unit.id,
        "name": unit.name,
        "is_active": bool(unit.is_active),
        "created_at": unit.created_at.strftime("%d/%m/%Y %H:%M") if unit.created_at else "",
    }


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "unit_name": user.unit.name if user.unit else "Chưa chọn đơn vị",
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "is_approved": bool(user.is_approved),
        "is_active": bool(user.is_active),
        "created_at": user.created_at.strftime("%d/%m/%Y %H:%M") if user.created_at else "",
    }


def _build_state(db: Session) -> dict:
    users = db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()
    units = db.query(Unit).order_by(Unit.name).all()
    return {
        "users": [_serialize_user(user) for user in users],
        "units": [_serialize_unit(unit) for unit in units],
        "role_labels": ROLE_LABELS,
    }


def _state_response(db: Session, message: str, status_code: int = 200) -> JSONResponse:
    payload = _build_state(db)
    payload.update({"ok": True, "message": message})
    return JSONResponse(payload, status_code=status_code)


def _error_response(db: Session, message: str, status_code: int = 400) -> JSONResponse:
    payload = _build_state(db)
    payload.update({"ok": False, "message": message})
    return JSONResponse(payload, status_code=status_code)


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    message: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    state = _build_state(db)
    return templates.TemplateResponse(
        "admin_users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": state["users"],
            "units": state["units"],
            "role_labels": ROLE_LABELS,
            "message": message,
        },
    )


@router.get("/api/state")
def users_state(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    return JSONResponse(_build_state(db))


@router.post("/users/{user_id}/update")
def update_user(
    request: Request,
    user_id: int,
    role: str = Form(""),
    is_approved: str | None = Form(None),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    user = db.get(User, user_id)
    if not user:
        if _is_ajax(request):
            return _error_response(db, "Không tìm thấy người dùng.", 404)
        return _redirect_users("Không tìm thấy người dùng.")

    clean_role = role.strip()
    if not clean_role or clean_role not in ROLE_LABELS:
        if _is_ajax(request):
            return _error_response(db, "Vai trò/quyền không hợp lệ. Vui lòng chọn lại vai trò người dùng.", 400)
        return _redirect_users("Vai trò/quyền không hợp lệ. Vui lòng chọn lại vai trò người dùng.")

    user.role = clean_role
    user.is_approved = is_approved == "on"
    user.is_active = is_active == "on"
    db.commit()

    if _is_ajax(request):
        return _state_response(db, "Đã lưu thông tin người dùng.")
    return _redirect_users("Đã lưu thông tin người dùng.")


@router.post("/users/{user_id}/delete")
def delete_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    user = db.get(User, user_id)
    if not user:
        if _is_ajax(request):
            return _error_response(db, "Không tìm thấy người dùng.", 404)
        return _redirect_users("Không tìm thấy người dùng.")

    if user.id == current_user.id:
        if _is_ajax(request):
            return _error_response(db, "Không được xóa chính tài khoản đang đăng nhập.", 400)
        return _redirect_users("Không được xóa chính tài khoản Admin đang đăng nhập.")

    if _user_has_history(db, user.id):
        user.is_active = False
        user.is_approved = False
        db.commit()
        message = "Người dùng đã có dữ liệu phát sinh nên hệ thống đã khóa tài khoản thay vì xóa cứng."
        if _is_ajax(request):
            return _state_response(db, message)
        return _redirect_users(message)

    db.delete(user)
    db.commit()
    if _is_ajax(request):
        return _state_response(db, "Đã xóa người dùng.")
    return _redirect_users("Đã xóa người dùng.")


@router.post("/units/create")
def create_unit(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    clean = name.strip()
    if not clean:
        if _is_ajax(request):
            return _error_response(db, "Tên đơn vị không được để trống.")
        return _redirect_users("Tên đơn vị không được để trống.")

    existing = db.query(Unit).filter(Unit.name == clean).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
            message = "Đơn vị đã tồn tại và đã được kích hoạt lại."
            if _is_ajax(request):
                return _state_response(db, message)
            return _redirect_users(message)
        if _is_ajax(request):
            return _error_response(db, "Tên đơn vị đã tồn tại.")
        return _redirect_users("Tên đơn vị đã tồn tại.")

    db.add(Unit(name=clean, is_active=True))
    db.commit()
    if _is_ajax(request):
        return _state_response(db, "Đã thêm đơn vị.")
    return _redirect_users("Đã thêm đơn vị.")


@router.post("/units/{unit_id}/update")
def update_unit(
    request: Request,
    unit_id: int,
    name: str = Form(...),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    unit = db.get(Unit, unit_id)
    if not unit:
        if _is_ajax(request):
            return _error_response(db, "Không tìm thấy đơn vị.", 404)
        return _redirect_users("Không tìm thấy đơn vị.")

    clean = name.strip()
    if not clean:
        if _is_ajax(request):
            return _error_response(db, "Tên đơn vị không được để trống.")
        return _redirect_users("Tên đơn vị không được để trống.")

    duplicated = db.query(Unit).filter(Unit.name == clean, Unit.id != unit_id).first()
    if duplicated:
        if _is_ajax(request):
            return _error_response(db, "Tên đơn vị đã tồn tại.")
        return _redirect_users("Tên đơn vị đã tồn tại.")

    unit.name = clean
    unit.is_active = is_active == "on"
    db.commit()
    if _is_ajax(request):
        return _state_response(db, "Đã cập nhật đơn vị.")
    return _redirect_users("Đã cập nhật đơn vị.")


@router.post("/units/{unit_id}/delete")
def delete_unit(
    request: Request,
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    unit = db.get(Unit, unit_id)
    if not unit:
        if _is_ajax(request):
            return _error_response(db, "Không tìm thấy đơn vị.", 404)
        return _redirect_users("Không tìm thấy đơn vị.")

    if _unit_has_history(db, unit.id):
        unit.is_active = False
        db.commit()
        message = "Đơn vị đã có người dùng/phiếu phát sinh nên hệ thống đã ngưng sử dụng thay vì xóa cứng."
        if _is_ajax(request):
            return _state_response(db, message)
        return _redirect_users(message)

    db.delete(unit)
    db.commit()
    if _is_ajax(request):
        return _state_response(db, "Đã xóa đơn vị.")
    return _redirect_users("Đã xóa đơn vị.")
