"""Database models.

Design notes for privacy/compliance (see DEPLOYMENT.md):
  * We store ONE face embedding per student (a 512-dim ArcFace vector), never
    long-term photos. Embeddings are one-way and cannot be reversed into a face.
  * Raw class photos live transiently on disk and are purged by the retention job.
  * Every automated match and every manual correction is written to audit_log.
  * Biometric consent is stored with timestamp and the admin who recorded it
    (DPDP Act 2023 §7 — explicit, informed, per-purpose consent required).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

EMBED_DIM = 512


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"


class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"


class AttendanceMethod(str, enum.Enum):
    auto = "auto"            # marked by face match
    manual = "manual"        # set/corrected by a teacher
    liveness_fail = "liveness_fail"  # face detected but failed anti-spoofing


class SessionState(str, enum.Enum):
    created = "created"        # session exists, no photo yet
    processing = "processing"  # photo queued/being matched
    review = "review"          # auto results ready, awaiting teacher confirm
    finalized = "finalized"    # teacher confirmed; record is authoritative
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.teacher)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sessions: Mapped[list["ClassSession"]] = relationship(back_populates="teacher")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roll_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    department: Mapped[str] = mapped_column(String(128), default="")

    # Consent is legally required before biometric processing (DPDP Act 2023).
    # We record not just the flag but who recorded it and when for the audit trail.
    biometric_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consent_recorded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    embedding: Mapped["FaceEmbedding | None"] = relationship(
        back_populates="student", uselist=False, cascade="all, delete-orphan"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    consent_recorder: Mapped["User | None"] = relationship(
        "User", foreign_keys=[consent_recorded_by]
    )


class FaceEmbedding(Base):
    """One enrolled face vector per student. Deleting this = 'forget my face'."""
    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), unique=True, index=True
    )
    vector: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utcnow
    )

    student: Mapped[Student] = relationship(back_populates="embedding")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    department: Mapped[str] = mapped_column(String(128), default="")

    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["ClassSession"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Enrollment(Base):
    """Roster: which students belong to which course. Scopes face matching."""
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "student_id", name="uq_course_student"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)

    course: Mapped[Course] = relationship(back_populates="enrollments")
    student: Mapped[Student] = relationship(back_populates="enrollments")


class ClassSession(Base):
    __tablename__ = "class_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    state: Mapped[SessionState] = mapped_column(Enum(SessionState), default=SessionState.created)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    photo_purged: Mapped[bool] = mapped_column(Boolean, default=False)
    faces_detected: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    course: Mapped[Course] = relationship(back_populates="sessions")
    teacher: Mapped["User | None"] = relationship(back_populates="sessions")
    records: Mapped[list["Attendance"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_session_student"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("class_sessions.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus), default=AttendanceStatus.absent
    )
    method: Mapped[AttendanceMethod] = mapped_column(
        Enum(AttendanceMethod), default=AttendanceMethod.auto
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    corrected_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utcnow
    )

    session: Mapped[ClassSession] = relationship(back_populates="records")
    student: Mapped[Student] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # user id or null (system)
    action: Mapped[str] = mapped_column(String(64))       # e.g. enroll, match, correct, purge
    entity: Mapped[str] = mapped_column(String(64))       # e.g. student, session, attendance
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
