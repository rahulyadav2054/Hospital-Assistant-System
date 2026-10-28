from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))  # patient | staff
    patient_id: Mapped[Optional[str]] = mapped_column(ForeignKey("patients.id"), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class InsurancePlan(Base):
    __tablename__ = "insurance_plans"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    annual_limit: Mapped[int] = mapped_column(Integer)
    deductible: Mapped[int] = mapped_column(Integer)
    doc_ref: Mapped[str] = mapped_column(String(50))


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    dob: Mapped[date] = mapped_column(Date)
    phone: Mapped[str] = mapped_column(String(30))
    plan_id: Mapped[str] = mapped_column(ForeignKey("insurance_plans.id"))
    plan_member_id: Mapped[str] = mapped_column(String(30))
    # Policy validity is per member (a plan product can be active while one member's policy has lapsed).
    coverage_start: Mapped[date] = mapped_column(Date)
    coverage_end: Mapped[date] = mapped_column(Date)


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(30))
    hours: Mapped[str] = mapped_column(String(50))
    keywords: Mapped[str] = mapped_column(Text, default="[]")  # JSON list


class Doctor(Base):
    __tablename__ = "doctors"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    specialty: Mapped[str] = mapped_column(String(100))


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"))
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20))  # scheduled | completed | cancelled


class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)


class LabResult(Base):
    __tablename__ = "lab_results"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    test_name: Mapped[str] = mapped_column(String(100))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    ref_low: Mapped[float] = mapped_column(Float)
    ref_high: Mapped[float] = mapped_column(Float)
    flag: Mapped[str] = mapped_column(String(10))  # low | normal | high
    collected_at: Mapped[datetime] = mapped_column(DateTime)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    order_type: Mapped[str] = mapped_column(String(20))  # procedure | pre_op | imaging | lab
    description: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))  # pending | completed
    ordered_by: Mapped[str] = mapped_column(ForeignKey("doctors.id"))
    linked_procedure: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Set when a test is booked into a diagnostic slot (still "pending" until it is done).
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scheduled_slot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("diagnostic_slots.id"), nullable=True)


class DiagnosticSlot(Base):
    """Bookable slots for tests that need an appointment (ECG, X-ray, MRI). Blood tests are walk-in."""
    __tablename__ = "diagnostic_slots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(50), index=True)
    location: Mapped[str] = mapped_column(String(100))
    start_time: Mapped[datetime] = mapped_column(DateTime)
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)


class PriorAuthRequest(Base):
    __tablename__ = "prior_auth_requests"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    procedure_code: Mapped[str] = mapped_column(ForeignKey("procedures.code"))
    plan_id: Mapped[str] = mapped_column(ForeignKey("insurance_plans.id"))
    order_id: Mapped[Optional[str]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # submitted | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Procedure(Base):
    __tablename__ = "procedures"
    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    aliases: Mapped[str] = mapped_column(Text)  # JSON list
    base_cost: Mapped[int] = mapped_column(Integer)


class CoverageRule(Base):
    __tablename__ = "coverage_rules"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("insurance_plans.id"))
    procedure_code: Mapped[str] = mapped_column(ForeignKey("procedures.code"))
    covered: Mapped[bool] = mapped_column(Boolean)
    coverage_pct: Mapped[int] = mapped_column(Integer)
    prior_auth_required: Mapped[bool] = mapped_column(Boolean)
    waiting_period_days: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str] = mapped_column(String(20))
    exclusion_note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)


class PendingAction(Base):
    __tablename__ = "pending_actions"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action_type: Mapped[str] = mapped_column(String(30))
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # pending | done | cancelled | expired
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    endpoint: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    args_masked: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
