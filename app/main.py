from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .database import Base, SessionLocal, engine
from .models import ROLE_ADMIN, Unit, User
from .routers import admin, auth, inventory_balance, materials, requests, summary
from .security import hash_password


app = FastAPI(title="Đăng ký nhu cầu vật tư")
app.add_middleware(SessionMiddleware, secret_key="CHANGE_ME_NCVT_SECRET_KEY")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def no_cache_dynamic_pages(request: Request, call_next):
    response = await call_next(request)

    if not request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


def ensure_schema_updates() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()

        if "units" in tables:
            unit_columns = {col["name"] for col in inspector.get_columns("units")}
            if "default_unit_head_name" not in unit_columns:
                conn.execute(text("ALTER TABLE units ADD COLUMN default_unit_head_name VARCHAR(255)"))


def seed_data() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_updates()

    db: Session = SessionLocal()
    try:
        if not db.query(Unit).first():
            db.add(Unit(name="Đơn vị mặc định", is_active=True))
            db.commit()

        if not db.query(User).filter(User.username == "admin").first():
            unit = db.query(Unit).first()
            db.add(
                User(
                    username="admin",
                    full_name="Quản trị hệ thống",
                    password_hash=hash_password("Admin@123"),
                    role=ROLE_ADMIN,
                    unit_id=unit.id if unit else None,
                    is_approved=True,
                    is_active=True,
                )
            )
            db.commit()
    finally:
        db.close()


seed_data()

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(materials.router)
app.include_router(requests.router)
app.include_router(summary.router)
app.include_router(inventory_balance.router)


@app.get("/")
def index(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/requests", status_code=303)
    return RedirectResponse("/login", status_code=303)
