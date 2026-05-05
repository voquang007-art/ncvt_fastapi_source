from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ROLE_INPUTTER, ROLE_LABELS, Unit, User
from ..security import hash_password, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update(ROLE_LABELS=ROLE_LABELS, NAV_MONTH=date.today().month, NAV_YEAR=date.today().year)


def _is_ajax(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, message: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "message": message})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        message = "Sai tài khoản hoặc mật khẩu."
        if _is_ajax(request):
            return JSONResponse({"ok": False, "message": message}, status_code=400)
        return templates.TemplateResponse("login.html", {"request": request, "error": message, "message": ""})

    if not user.is_approved or not user.is_active:
        message = "Tài khoản chưa được duyệt hoặc đã bị khóa."
        if _is_ajax(request):
            return JSONResponse({"ok": False, "message": message}, status_code=400)
        return templates.TemplateResponse("login.html", {"request": request, "error": message, "message": ""})

    request.session["user_id"] = user.id
    if _is_ajax(request):
        return JSONResponse({"ok": True, "redirect": "/requests"})
    return RedirectResponse("/requests", status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, db: Session = Depends(get_db)):
    units = db.query(Unit).filter(Unit.is_active == True).order_by(Unit.name).all()
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "units": units, "error": None, "message": ""},
    )


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    unit_id: int = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip()
    full_name = full_name.strip()
    units = db.query(Unit).filter(Unit.is_active == True).order_by(Unit.name).all()
    selected_unit = db.query(Unit).filter(Unit.id == unit_id, Unit.is_active == True).first()

    if not username or not full_name:
        message = "Tên đăng nhập và họ tên không được để trống."
        if _is_ajax(request):
            return JSONResponse({"ok": False, "message": message}, status_code=400)
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "units": units, "error": message, "message": ""},
        )

    if not selected_unit:
        message = "Đơn vị đăng ký không hợp lệ hoặc đã ngưng sử dụng."
        if _is_ajax(request):
            return JSONResponse({"ok": False, "message": message}, status_code=400)
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "units": units, "error": message, "message": ""},
        )

    if db.query(User).filter(User.username == username).first():
        message = "Tên đăng nhập đã tồn tại."
        if _is_ajax(request):
            return JSONResponse({"ok": False, "message": message}, status_code=400)
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "units": units, "error": message, "message": ""},
        )

    db.add(
        User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            unit_id=selected_unit.id,
            role=ROLE_INPUTTER,
            is_approved=False,
            is_active=True,
        )
    )
    db.commit()
    success_message = "Đăng ký thành công. Vui lòng chờ Quản trị hệ thống xét duyệt tài khoản."
    if _is_ajax(request):
        return JSONResponse({"ok": True, "message": success_message, "redirect": f"/login?message={success_message}"})
    return RedirectResponse(f"/login?message={success_message}", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
