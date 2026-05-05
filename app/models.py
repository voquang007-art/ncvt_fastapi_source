from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .time_utils import vietnam_now


ROLE_ADMIN = "ADMIN"
ROLE_INPUTTER = "INPUTTER"
ROLE_UNIT_HEAD = "UNIT_HEAD"
ROLE_SUMMARY = "SUMMARY"
ROLE_APPROVER = "APPROVER"
ROLE_VIEWER = "VIEWER"

STATUS_DRAFT = "DRAFT"
STATUS_WAIT_UNIT_APPROVAL = "WAIT_UNIT_APPROVAL"
STATUS_SENT_TO_SUMMARY = "SENT_TO_SUMMARY"
STATUS_RETURNED_FOR_EDIT = "RETURNED_FOR_EDIT"
STATUS_RESUBMITTED = "RESUBMITTED"
STATUS_SUMMARIZED = "SUMMARIZED"
STATUS_APPROVED = "APPROVED"
STATUS_CLOSED = "CLOSED"
STATUS_CANCELLED = "CANCELLED"

STATUS_LABELS = {
    STATUS_DRAFT: "Nháp",
    STATUS_WAIT_UNIT_APPROVAL: "Chờ Trưởng đơn vị phê duyệt",
    STATUS_SENT_TO_SUMMARY: "Đã gửi Bộ phận tổng hợp",
    STATUS_RETURNED_FOR_EDIT: "Trả lại điều chỉnh",
    STATUS_RESUBMITTED: "Đã gửi lại sau điều chỉnh",
    STATUS_SUMMARIZED: "Đã tổng hợp",
    STATUS_APPROVED: "Đã duyệt",
    STATUS_CLOSED: "Đã chốt",
    STATUS_CANCELLED: "Đã hủy",
}

ROLE_LABELS = {
    ROLE_ADMIN: "Quản trị hệ thống",
    ROLE_INPUTTER: "Người lập phiếu",
    ROLE_UNIT_HEAD: "Trưởng đơn vị",
    ROLE_SUMMARY: "Bộ phận tổng hợp",
    ROLE_APPROVER: "Người duyệt/chốt",
    ROLE_VIEWER: "Người xem",
}

ACTION_LABELS = {
    "CREATE": "Tạo phiếu",
    "UPDATE": "Cập nhật phiếu",
    "SUBMIT_SUMMARY": "Gửi Bộ phận tổng hợp",
    "SUBMIT_UNIT": "Chuyển Trưởng đơn vị phê duyệt",
    "UNIT_APPROVE": "Trưởng đơn vị phê duyệt",
    "RETURN_EDIT": "Trả lại điều chỉnh",
    "SUMMARIZE": "Đưa vào tổng hợp",
    "CLOSE": "Chốt phiếu",
    "COPY": "Sao chép phiếu",
}


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    default_unit_head_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)

    users = relationship("User", back_populates="unit")
    requests = relationship("DemandRequest", back_populates="unit")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default=ROLE_INPUTTER)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)

    unit = relationship("Unit", back_populates="users")


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    category_name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    specification: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)


class DemandRequest(Base):
    __tablename__ = "demand_requests"
    __table_args__ = (
        UniqueConstraint("unit_id", "month", "year", "is_cancelled", name="uq_request_unit_month_year_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_no: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    request_date: Mapped[date] = mapped_column(Date, default=date.today)
    title: Mapped[str] = mapped_column(String(500), default="PHIẾU ĐĂNG KÝ NHU CẦU VẬT TƯ")
    input_person_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_head_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=STATUS_DRAFT, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    edit_unlock_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_to_unit_head_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    unit_approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    unit_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_to_summary_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summarized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    summarized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)

    unit = relationship("Unit", back_populates="requests")
    items = relationship(
        "DemandRequestItem",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="DemandRequestItem.sort_order",
    )


class DemandRequestItem(Base):
    __tablename__ = "demand_request_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("demand_requests.id"), nullable=False)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"), nullable=True)
    material_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    material_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    category_name: Mapped[str] = mapped_column(String(255), nullable=False)
    specification: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_new_material: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    request = relationship("DemandRequest", back_populates="items")
    material = relationship("Material")


class DemandRequestLog(Base):
    __tablename__ = "demand_request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("demand_requests.id"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    old_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)

    items = relationship("InventorySnapshotItem", back_populates="snapshot", cascade="all, delete-orphan")


class InventorySnapshotItem(Base):
    __tablename__ = "inventory_snapshot_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("inventory_snapshots.id"), nullable=False, index=True)
    material_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    material_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stock_qty: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshot = relationship("InventorySnapshot", back_populates="items")


class DemandBalanceResult(Base):
    __tablename__ = "demand_balance_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    material_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    material_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_demand_qty: Mapped[float] = mapped_column(Float, default=0)
    stock_qty: Mapped[float] = mapped_column(Float, default=0)
    shortage_qty: Mapped[float] = mapped_column(Float, default=0)
    surplus_qty: Mapped[float] = mapped_column(Float, default=0)
    suggested_purchase_qty: Mapped[float] = mapped_column(Float, default=0)
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_snapshots.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=vietnam_now)
