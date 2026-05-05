from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import summary_required
from ..models import (
    DemandRequest,
    DemandRequestItem,
    ROLE_LABELS,
    STATUS_CLOSED,
    STATUS_RESUBMITTED,
    STATUS_SENT_TO_SUMMARY,
    STATUS_SUMMARIZED,
    User,
)
from ..reporting import build_summary_excel

router = APIRouter(prefix="/summary", tags=["summary"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update(ROLE_LABELS=ROLE_LABELS, NAV_MONTH=date.today().month, NAV_YEAR=date.today().year)

def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _fmt_qty(value: float) -> str:
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _build_spec_note(spec_quantities: dict[str, float]) -> str:
    parts = []
    for spec, qty in sorted(spec_quantities.items(), key=lambda item: item[0].lower()):
        clean_spec = _clean_text(spec)
        if clean_spec:
            parts.append(f"{_fmt_qty(qty)} {clean_spec}")
    return "; ".join(parts)

def collect_summary(db: Session, month: int, year: int):
    reqs = db.query(DemandRequest).filter(
        DemandRequest.month == month,
        DemandRequest.year == year,
        DemandRequest.status.in_([STATUS_SUMMARIZED, STATUS_CLOSED]),
        DemandRequest.is_cancelled == False,
    ).all()
    req_ids = [r.id for r in reqs]
    if not req_ids:
        return [], [], []
    unit_by_req = {r.id: r.unit.name for r in reqs}
    items = db.query(DemandRequestItem).filter(DemandRequestItem.request_id.in_(req_ids)).all()

    grouped = {}
    unit_sets = defaultdict(set)
    details = []
    new_materials = []

    for item in items:
        key = (
            item.material_code or "Ngoài danh mục",
            item.material_name,
            item.category_name,
            item.unit,
        )
        if key not in grouped:
            grouped[key] = {
                "material_code": key[0],
                "material_name": key[1],
                "category_name": key[2],
                "unit": key[3],
                "total_quantity": 0,
                "unit_count": 0,
                "spec_quantities": defaultdict(float),
                "note": "",
            }

        quantity_value = float(item.quantity or 0)
        grouped[key]["total_quantity"] += quantity_value

        spec_note = _clean_text(item.specification or item.note)
        if spec_note:
            grouped[key]["spec_quantities"][spec_note] += quantity_value

        unit_name = unit_by_req.get(item.request_id, "")
        unit_sets[key].add(unit_name)

        detail = {
            "unit_name": unit_name,
            "material_code": item.material_code or "Ngoài danh mục",
            "material_name": item.material_name,
            "category_name": item.category_name,
            "unit": item.unit,
            "quantity": item.quantity,
            "note": _clean_text(item.specification or item.note),
        }
        details.append(detail)
        if item.is_new_material:
            new_materials.append(detail)

    rows = []
    for key, row in grouped.items():
        row["unit_count"] = len(unit_sets[key])
        row["note"] = _build_spec_note(row.pop("spec_quantities", {}))
        rows.append(row)
    rows.sort(key=lambda x: (x["category_name"], x["material_name"]))
    details.sort(key=lambda x: (x["unit_name"], x["category_name"], x["material_name"]))
    new_materials.sort(key=lambda x: (x["unit_name"], x["material_name"]))
    return rows, details, new_materials


@router.get("", response_class=HTMLResponse)
def summary_page(
    request: Request,
    month: int,
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(summary_required),
):
    rows, details, new_materials = collect_summary(db, month, year)
    pending_requests = (
        db.query(DemandRequest)
        .filter(
            DemandRequest.month == month,
            DemandRequest.year == year,
            DemandRequest.status.in_([STATUS_SENT_TO_SUMMARY, STATUS_RESUBMITTED]),
            DemandRequest.is_cancelled == False,
        )
        .order_by(DemandRequest.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "summary.html",
        {
            "request": request,
            "current_user": current_user,
            "month": month,
            "year": year,
            "rows": rows,
            "details": details,
            "new_materials": new_materials,
            "pending_requests": pending_requests,
        },
    )


@router.get("/export.xlsx")
def summary_excel(month: int, year: int, db: Session = Depends(get_db), current_user: User = Depends(summary_required)):
    rows, details, new_materials = collect_summary(db, month, year)
    content = build_summary_excel(rows, details, new_materials)
    filename = f"tong_hop_nhu_cau_vat_tu_{year}_{month:02d}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
