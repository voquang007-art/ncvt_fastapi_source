import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import can_edit_request_status, can_view_all, login_required
from ..models import (
    ACTION_LABELS,
    DemandBalanceResult,
    DemandRequest,
    DemandRequestItem,
    DemandRequestLog,
    Material,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_SUMMARY,
    ROLE_UNIT_HEAD,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_LABELS,
    STATUS_RESUBMITTED,
    STATUS_RETURNED_FOR_EDIT,
    STATUS_SENT_TO_SUMMARY,
    STATUS_SUMMARIZED,
    STATUS_WAIT_UNIT_APPROVAL,
    Unit,
    User,
)
from ..reporting import build_request_pdf
from ..services import add_log, next_request_no, touch_request
from ..time_utils import vietnam_now

router = APIRouter(prefix="/requests", tags=["requests"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update(
    ROLE_LABELS=ROLE_LABELS,
    STATUS_LABELS=STATUS_LABELS,
    ACTION_LABELS=ACTION_LABELS,
    NAV_MONTH=date.today().month,
    NAV_YEAR=date.today().year,
)


def _json_ok(message: str, **kwargs) -> JSONResponse:
    payload = {"ok": True, "message": message}
    payload.update(kwargs)
    return JSONResponse(payload)


def _json_error(message: str, status_code: int = 400, **kwargs) -> JSONResponse:
    payload = {"ok": False, "message": message}
    payload.update(kwargs)
    return JSONResponse(payload, status_code=status_code)


def visible_request_query(db: Session, user: User):
    query = db.query(DemandRequest).filter(DemandRequest.is_cancelled == False)
    if not can_view_all(user):
        query = query.filter(DemandRequest.unit_id == user.unit_id)
    return query


def _get_units(db: Session):
    return db.query(Unit).filter(Unit.is_active == True).order_by(Unit.name).all()


def _get_materials(db: Session):
    return db.query(Material).filter(Material.is_active == True).order_by(Material.name).all()


def _safe_unit_id(unit_id: int | None, current_user: User) -> int | None:
    if can_view_all(current_user):
        return unit_id
    return current_user.unit_id


def _unit_defaults_map(units: list[Unit]) -> dict[int, str]:
    return {unit.id: unit.default_unit_head_name or "" for unit in units}


def _parse_qty(value: str | None) -> float:
    text = str(value or "").strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0

BALANCE_LOCKED_RETURN_MESSAGE = "Tháng này đã chốt/lưu cân đối tồn kho, không được trả phiếu về đơn vị sửa."
BALANCE_LOCKED_EDIT_MESSAGE = "Tháng này đã chốt/lưu cân đối tồn kho, không được sửa nội dung/số lượng phiếu."


def _is_balance_locked(db: Session, req: DemandRequest | None) -> bool:
    if not req:
        return False

    if req.status not in {STATUS_SUMMARIZED, STATUS_CLOSED}:
        return False

    return (
        db.query(DemandBalanceResult.id)
        .filter(
            DemandBalanceResult.month == req.month,
            DemandBalanceResult.year == req.year,
        )
        .first()
        is not None
    )


def _redirect_fresh(url: str) -> RedirectResponse:
    separator = "&" if "?" in url else "?"
    response = RedirectResponse(f"{url}{separator}_ts={int(vietnam_now().timestamp())}", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("", response_class=HTMLResponse)
def list_requests(
    request: Request,
    month: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    today = date.today()
    month = month or today.month
    year = year or today.year
    rows = (
        visible_request_query(db, current_user)
        .filter(DemandRequest.month == month, DemandRequest.year == year)
        .order_by(DemandRequest.created_at.desc())
        .all()
    )
    has_balance_result = (
        db.query(DemandBalanceResult.id)
        .filter(
            DemandBalanceResult.month == month,
            DemandBalanceResult.year == year,
        )
        .first()
        is not None
    )
    balance_locked_ids = {
        row.id
        for row in rows
        if has_balance_result and row.status in {STATUS_SUMMARIZED, STATUS_CLOSED}
    }
    return templates.TemplateResponse(
        "requests.html",
        {
            "request": request,
            "current_user": current_user,
            "rows": rows,
            "month": month,
            "year": year,
            "status_labels": STATUS_LABELS,
            "can_view_all": can_view_all(current_user),
            "balance_locked_ids": balance_locked_ids,
            "has_balance_result": has_balance_result,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_request_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    materials = _get_materials(db)
    units = _get_units(db)
    initial_unit_id = current_user.unit_id if not can_view_all(current_user) else (units[0].id if units else None)
    unit_head_default = ""
    if initial_unit_id:
        initial_unit = db.get(Unit, initial_unit_id)
        unit_head_default = initial_unit.default_unit_head_name or "" if initial_unit else ""

    return templates.TemplateResponse(
        "request_form.html",
        {
            "request": request,
            "current_user": current_user,
            "req": None,
            "items": [],
            "materials": materials,
            "units": units,
            "today": date.today(),
            "editable": True,
            "balance_locked": False,
            "unit_head_default": unit_head_default,
            "unit_defaults": _unit_defaults_map(units),
        },
    )


@router.get("/api/unit-head-default")
def unit_head_default_api(
    unit_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    safe_unit_id = _safe_unit_id(unit_id, current_user)
    unit = db.get(Unit, safe_unit_id) if safe_unit_id else None
    if not unit:
        return _json_error("Không tìm thấy đơn vị.", 404)
    return _json_ok("Đã tải thông tin phụ trách khoa/phòng.", unit_head_name=unit.default_unit_head_name or "")


@router.post("/unit-head-default/save")
def save_unit_head_default(
    unit_id: int = Form(...),
    unit_head_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    safe_unit_id = _safe_unit_id(unit_id, current_user)
    unit = db.get(Unit, safe_unit_id) if safe_unit_id else None
    if not unit:
        return _json_error("Không tìm thấy đơn vị.", 404)

    clean_name = unit_head_name.strip()
    if not clean_name:
        return _json_error("Vui lòng nhập tên phụ trách khoa/phòng trước khi lưu.")

    unit.default_unit_head_name = clean_name
    db.commit()
    return _json_ok("Đã lưu mặc định phụ trách khoa/phòng.", unit_head_name=clean_name)


@router.post("/unit-head-default/clear")
def clear_unit_head_default(
    unit_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    safe_unit_id = _safe_unit_id(unit_id, current_user)
    unit = db.get(Unit, safe_unit_id) if safe_unit_id else None
    if not unit:
        return _json_error("Không tìm thấy đơn vị.", 404)

    unit.default_unit_head_name = None
    db.commit()
    return _json_ok("Đã xóa mặc định phụ trách khoa/phòng.", unit_head_name="")


@router.post("/create")
def create_request(
    unit_id: int = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    request_date: str = Form(...),
    input_person_name: str = Form(...),
    unit_head_name: str = Form(""),
    note: str = Form(""),
    material_id: list[str] = Form([]),
    material_name: list[str] = Form([]),
    material_code: list[str] = Form([]),
    unit: list[str] = Form([]),
    quantity: list[str] = Form([]),
    category_name: list[str] = Form([]),
    specification: list[str] = Form([]),
    item_note: list[str] = Form([]),
    is_new_material: list[str] = Form([]),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    unit_id = _safe_unit_id(unit_id, current_user)

    existing = db.query(DemandRequest).filter(
        DemandRequest.unit_id == unit_id,
        DemandRequest.month == month,
        DemandRequest.year == year,
        DemandRequest.is_cancelled == False,
    ).first()
    if existing:
        return RedirectResponse(f"/requests/{existing.id}/edit", status_code=303)

    target_unit = db.get(Unit, unit_id)
    req = DemandRequest(
        request_no=next_request_no(db, target_unit, month, year),
        unit_id=unit_id,
        month=month,
        year=year,
        request_date=date.fromisoformat(request_date),
        input_person_name=input_person_name.strip(),
        unit_head_name=unit_head_name.strip() or None,
        note=note.strip() or None,
        status=STATUS_DRAFT,
        created_by=current_user.id,
    )
    db.add(req)
    db.flush()

    new_flags = set(is_new_material or [])
    for idx, name in enumerate(material_name):
        clean_name = (name or "").strip()
        if not clean_name:
            continue
        qty = _parse_qty(quantity[idx] if idx < len(quantity) else "0")
        if qty <= 0:
            continue
        mid = int(material_id[idx]) if idx < len(material_id) and str(material_id[idx]).isdigit() else None
        is_new = str(idx) in new_flags or not mid
        db.add(
            DemandRequestItem(
                request_id=req.id,
                material_id=mid,
                material_code=(material_code[idx].strip() if idx < len(material_code) and material_code[idx].strip() else None),
                material_name=clean_name,
                unit=(unit[idx].strip() if idx < len(unit) else ""),
                quantity=qty,
                category_name=(category_name[idx].strip() if idx < len(category_name) else ""),
                specification=(
                    specification[idx].strip()
                    if idx < len(specification) and specification[idx].strip()
                    else None
                ),
                note=(item_note[idx].strip() if idx < len(item_note) and item_note[idx].strip() else None),
                is_new_material=is_new,
                sort_order=idx + 1,
            )
        )

    add_log(db, req.id, current_user.id, "CREATE", "Tạo phiếu")
    db.commit()
    return RedirectResponse(f"/requests/{req.id}", status_code=303)


@router.get("/{request_id}", response_class=HTMLResponse)
def request_detail(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    req = visible_request_query(db, current_user).filter(DemandRequest.id == request_id).first()
    if not req:
        return RedirectResponse("/requests", status_code=303)
    balance_locked = _is_balance_locked(db, req)
    logs = (
        db.query(DemandRequestLog)
        .filter(DemandRequestLog.request_id == request_id)
        .order_by(DemandRequestLog.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "request_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "req": req,
            "logs": logs,
            "status_labels": STATUS_LABELS,
            "can_view_all": can_view_all(current_user),
            "action_labels": ACTION_LABELS,
            "balance_locked": balance_locked,
        },
    )


@router.get("/{request_id}/edit", response_class=HTMLResponse)
def edit_request_form(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    req = visible_request_query(db, current_user).filter(DemandRequest.id == request_id).first()
    if not req:
        return RedirectResponse("/requests", status_code=303)

    balance_locked = _is_balance_locked(db, req)
    editable = (can_edit_request_status(req.status) or can_view_all(current_user)) and not balance_locked
    materials = _get_materials(db)
    units = _get_units(db)
    unit_head_default = req.unit_head_name or (req.unit.default_unit_head_name or "")
    return templates.TemplateResponse(
        "request_form.html",
        {
            "request": request,
            "current_user": current_user,
            "req": req,
            "items": req.items,
            "materials": materials,
            "units": units,
            "today": date.today(),
            "editable": editable,
            "balance_locked": balance_locked,
            "unit_head_default": unit_head_default,
            "unit_defaults": _unit_defaults_map(units),
        },
    )


@router.post("/{request_id}/update")
def update_request(
    request_id: int,
    unit_id: int = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    request_date: str = Form(...),
    input_person_name: str = Form(...),
    unit_head_name: str = Form(""),
    note: str = Form(""),
    material_id: list[str] = Form([]),
    material_name: list[str] = Form([]),
    material_code: list[str] = Form([]),
    unit: list[str] = Form([]),
    quantity: list[str] = Form([]),
    category_name: list[str] = Form([]),
    specification: list[str] = Form([]),
    item_note: list[str] = Form([]),
    is_new_material: list[str] = Form([]),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    req = visible_request_query(db, current_user).filter(DemandRequest.id == request_id).first()
    if not req:
        return RedirectResponse("/requests", status_code=303)

    if _is_balance_locked(db, req):
        return _redirect_fresh(f"/requests/{req.id}?locked=balance_edit")

    if not (can_edit_request_status(req.status) or can_view_all(current_user)):
        return _redirect_fresh(f"/requests/{req.id}")

    if can_view_all(current_user):
        req.unit_id = unit_id
    req.month = month
    req.year = year
    req.request_date = date.fromisoformat(request_date)
    req.input_person_name = input_person_name.strip()
    req.unit_head_name = unit_head_name.strip() or None
    req.note = note.strip() or None

    req.items.clear()
    db.flush()
    new_flags = set(is_new_material or [])
    for idx, name in enumerate(material_name):
        clean_name = (name or "").strip()
        if not clean_name:
            continue
        qty = _parse_qty(quantity[idx] if idx < len(quantity) else "0")
        if qty <= 0:
            continue
        mid = int(material_id[idx]) if idx < len(material_id) and str(material_id[idx]).isdigit() else None
        req.items.append(
            DemandRequestItem(
                material_id=mid,
                material_code=(material_code[idx].strip() if idx < len(material_code) and material_code[idx].strip() else None),
                material_name=clean_name,
                unit=(unit[idx].strip() if idx < len(unit) else ""),
                quantity=qty,
                category_name=(category_name[idx].strip() if idx < len(category_name) else ""),
                specification=(
                    specification[idx].strip()
                    if idx < len(specification) and specification[idx].strip()
                    else None
                ),
                note=(item_note[idx].strip() if idx < len(item_note) and item_note[idx].strip() else None),
                is_new_material=(str(idx) in new_flags or not mid),
                sort_order=idx + 1,
            )
        )
    if req.status == STATUS_RETURNED_FOR_EDIT:
        req.status = STATUS_RESUBMITTED
        req.sent_to_summary_at = vietnam_now()
    touch_request(req)
    add_log(db, req.id, current_user.id, "UPDATE", "Cập nhật phiếu")
    db.commit()
    return _redirect_fresh(f"/requests/{req.id}")


@router.post("/{request_id}/submit-summary")
def submit_summary(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(login_required)):
    req = visible_request_query(db, current_user).filter(DemandRequest.id == request_id).first()
    if req and req.status in {STATUS_DRAFT, STATUS_WAIT_UNIT_APPROVAL, STATUS_RETURNED_FOR_EDIT, STATUS_RESUBMITTED}:
        req.status = STATUS_SENT_TO_SUMMARY if req.status != STATUS_RETURNED_FOR_EDIT else STATUS_RESUBMITTED
        req.sent_to_summary_at = vietnam_now()
        add_log(db, req.id, current_user.id, "SUBMIT_SUMMARY", "Gửi Bộ phận tổng hợp")
        db.commit()
    return _redirect_fresh(f"/requests/{request_id}")


@router.post("/{request_id}/submit-unit")
def submit_unit(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(login_required)):
    req = visible_request_query(db, current_user).filter(DemandRequest.id == request_id).first()
    if req and req.status == STATUS_DRAFT:
        req.status = STATUS_WAIT_UNIT_APPROVAL
        req.submitted_to_unit_head_at = vietnam_now()
        add_log(db, req.id, current_user.id, "SUBMIT_UNIT", "Chuyển Trưởng đơn vị phê duyệt")
        db.commit()
    return _redirect_fresh(f"/requests/{request_id}")


@router.post("/{request_id}/unit-approve")
def unit_approve(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(login_required)):
    req = visible_request_query(db, current_user).filter(DemandRequest.id == request_id).first()
    if req and req.status == STATUS_WAIT_UNIT_APPROVAL and current_user.role in {ROLE_UNIT_HEAD, ROLE_ADMIN}:
        req.status = STATUS_SENT_TO_SUMMARY
        req.unit_approved_by = current_user.id
        req.unit_approved_at = vietnam_now()
        req.sent_to_summary_at = vietnam_now()
        add_log(db, req.id, current_user.id, "UNIT_APPROVE", "Trưởng đơn vị phê duyệt và gửi Bộ phận tổng hợp")
        db.commit()
    return _redirect_fresh(f"/requests/{request_id}")


@router.post("/{request_id}/return-edit")
def return_edit(
    request_id: int,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    if not can_view_all(current_user):
        return _redirect_fresh(f"/requests/{request_id}")

    req = db.get(DemandRequest, request_id)
    if req and _is_balance_locked(db, req):
        return _redirect_fresh(f"/requests/{request_id}?locked=balance_return")

    if req and req.status not in {STATUS_CLOSED}:
        req.status = STATUS_RETURNED_FOR_EDIT
        req.return_reason = reason.strip() or None
        req.edit_unlock_reason = reason.strip() or None
        add_log(db, req.id, current_user.id, "RETURN_EDIT", reason.strip() or "Trả lại điều chỉnh")
        db.commit()

    return _redirect_fresh(f"/requests/{request_id}")


@router.post("/{request_id}/summarize")
def summarize_request(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(login_required)):
    if not can_view_all(current_user):
        return _redirect_fresh(f"/requests/{request_id}")

    req = db.get(DemandRequest, request_id)
    if req and req.status in {STATUS_SENT_TO_SUMMARY, STATUS_RESUBMITTED}:
        req.status = STATUS_SUMMARIZED
        req.summarized_by = current_user.id
        req.summarized_at = vietnam_now()
        add_log(
            db,
            req.id,
            current_user.id,
            "SUMMARIZE",
            "Đưa vào tổng hợp. Nếu tháng này đã từng chốt/lưu cân đối tồn kho, cần chốt/lưu cân đối lại để cập nhật số liệu.",
        )
        db.commit()

    return _redirect_fresh(f"/requests/{request_id}")


@router.post("/{request_id}/close")
def close_request(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(login_required)):
    if not can_view_all(current_user):
        return _redirect_fresh(f"/requests/{request_id}")
    req = db.get(DemandRequest, request_id)
    if req and req.status == STATUS_SUMMARIZED:
        req.status = STATUS_CLOSED
        req.closed_by = current_user.id
        req.closed_at = vietnam_now()
        add_log(db, req.id, current_user.id, "CLOSE", "Chốt phiếu")
        db.commit()
    return _redirect_fresh(f"/requests/{request_id}")


@router.post("/{request_id}/copy-next")
def copy_next(
    request_id: int,
    target_month: int = Form(...),
    target_year: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required),
):
    src = visible_request_query(db, current_user).filter(DemandRequest.id == request_id).first()
    if not src:
        return RedirectResponse("/requests", status_code=303)
    existing = db.query(DemandRequest).filter(
        DemandRequest.unit_id == src.unit_id,
        DemandRequest.month == target_month,
        DemandRequest.year == target_year,
        DemandRequest.is_cancelled == False,
    ).first()
    if existing:
        return RedirectResponse(f"/requests/{existing.id}/edit", status_code=303)
    req = DemandRequest(
        request_no=next_request_no(db, src.unit, target_month, target_year),
        unit_id=src.unit_id,
        month=target_month,
        year=target_year,
        request_date=date.today(),
        input_person_name=current_user.full_name,
        unit_head_name=src.unit_head_name or src.unit.default_unit_head_name,
        note=src.note,
        status=STATUS_DRAFT,
        created_by=current_user.id,
    )
    db.add(req)
    db.flush()
    for idx, item in enumerate(src.items, 1):
        db.add(
            DemandRequestItem(
                request_id=req.id,
                material_id=item.material_id,
                material_code=item.material_code,
                material_name=item.material_name,
                unit=item.unit,
                quantity=item.quantity,
                category_name=item.category_name,
                specification=item.specification,
                note=item.note,
                is_new_material=item.is_new_material,
                sort_order=idx,
            )
        )
    add_log(db, req.id, current_user.id, "COPY", f"Sao chép từ phiếu {src.request_no}")
    db.commit()
    return _redirect_fresh(f"/requests/{req.id}/edit")


@router.get("/{request_id}/pdf")
def export_pdf(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(login_required)):
    req = visible_request_query(db, current_user).filter(DemandRequest.id == request_id).first()
    if not req:
        return RedirectResponse("/requests", status_code=303)
    pdf = build_request_pdf(req)
    filename = f"{req.request_no}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
