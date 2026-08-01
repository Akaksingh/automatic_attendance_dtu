"""Database models for ClassLens identity, groups, and attendance."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(StrEnum):
    admin = "admin"
    teacher = "teacher"
    student = "student"


class AttendanceStatus(StrEnum):
    present = "present"
    absent = "absent"


class SessionState(StrEnum):
    created = "created"
    processing = "processing"
    review = "review"
    finalized = "finalized"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    profile_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owned_groups: Mapped[list[Group]] = relationship(back_populates="owner")
    memberships: Mapped[list[GroupMembership]] = relationship(back_populates="student")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")
    created_sessions: Mapped[list[ClassSession]] = relationship(back_populates="created_by", foreign_keys="ClassSession.created_by_id")
    student_profile: Mapped[Student | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Student(Base):
    """Student identity data and the approved photo enrollment history."""
    __tablename__ = "students"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    roll_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    profile_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="student_profile")
    photos: Mapped[list[StudentPhoto]] = relationship(back_populates="student", cascade="all, delete-orphan")


class StudentPhoto(Base):
    """An approved reference photo retained for future face matching."""
    __tablename__ = "student_photos"
    __table_args__ = (Index("ix_student_photos_storage_key", "storage_key", unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100))
    embedding_json: Mapped[str] = mapped_column(Text)
    similarity_to_previous: Mapped[float | None] = mapped_column(nullable=True)
    is_profile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped[Student] = relationship(back_populates="photos")


class PhotoJobStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"


class ImportJobStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ImportJob(Base):
    """Durable asynchronous Excel/ZIP import and error-report job."""
    __tablename__ = "import_jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[ImportJobStatus] = mapped_column(Enum(ImportJobStatus), default=ImportJobStatus.pending, index=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True)
    spreadsheet_key: Mapped[str] = mapped_column(String(512))
    images_zip_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_file_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    total: Mapped[int] = mapped_column(default=0, nullable=False)
    processed: Mapped[int] = mapped_column(default=0, nullable=False)
    succeeded: Mapped[int] = mapped_column(default=0, nullable=False)
    failed: Mapped[int] = mapped_column(default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PhotoProcessingJob(Base):
    """Durable queue record for asynchronous face verification."""
    __tablename__ = "photo_processing_jobs"
    __table_args__ = (Index("ix_photo_processing_jobs_storage_key", "storage_key", unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[PhotoJobStatus] = mapped_column(Enum(PhotoJobStatus), default=PhotoJobStatus.pending, index=True)
    similarity_to_previous: Mapped[float | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[UUID | None] = mapped_column(ForeignKey("student_photos.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    student: Mapped[Student] = relationship()
    photo: Mapped[StudentPhoto | None] = relationship()


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    join_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[User] = relationship(back_populates="owned_groups")
    memberships: Mapped[list[GroupMembership]] = relationship(back_populates="group", cascade="all, delete-orphan")
    sessions: Mapped[list[ClassSession]] = relationship(back_populates="group", cascade="all, delete-orphan")


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("group_id", "student_id", name="uq_group_membership"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id"), index=True)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    group: Mapped[Group] = relationship(back_populates="memberships")
    student: Mapped[User] = relationship(back_populates="memberships")


class ClassSession(Base):
    __tablename__ = "class_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id"), index=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    state: Mapped[SessionState] = mapped_column(Enum(SessionState), default=SessionState.created, index=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_total: Mapped[int] = mapped_column(default=0, nullable=False)
    processing_completed: Mapped[int] = mapped_column(default=0, nullable=False)
    processing_message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    group: Mapped[Group] = relationship(back_populates="sessions")
    created_by: Mapped[User] = relationship(back_populates="created_sessions", foreign_keys=[created_by_id])
    attendance_records: Mapped[list[AttendanceRecord]] = relationship(back_populates="session", cascade="all, delete-orphan")
    photos: Mapped[list[SessionPhoto]] = relationship(back_populates="session", cascade="all, delete-orphan")


class SessionPhoto(Base):
    """Classroom image retained only for the session's seven-day review window."""
    __tablename__ = "session_photos"
    __table_args__ = (Index("ix_session_photos_storage_key", "storage_key", unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("class_sessions.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ClassSession] = relationship(back_populates="photos")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_session_attendance"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("class_sessions.id"), index=True)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[AttendanceStatus] = mapped_column(Enum(AttendanceStatus))
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ClassSession] = relationship(back_populates="attendance_records")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class AuditLog(Base):
    """Immutable record of security-sensitive administrative actions."""
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
