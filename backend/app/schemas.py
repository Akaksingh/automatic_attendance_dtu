"""Pydantic request/response models."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import (
    AttendanceMethod,
    AttendanceStatus,
    Role,
    SessionState,
)


# ---- Auth ----
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = ""
    password: str = Field(min_length=8)
    role: Role = Role.teacher


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool


# ---- Students ----
class StudentCreate(BaseModel):
    roll_no: str
    full_name: str
    department: str = ""
    biometric_consent: bool = False


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    roll_no: str
    full_name: str
    department: str
    biometric_consent: bool
    has_embedding: bool = False


# ---- Courses / enrollment ----
class CourseCreate(BaseModel):
    code: str
    name: str
    department: str = ""


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    department: str


class EnrollRequest(BaseModel):
    roll_nos: list[str]


# ---- Sessions / attendance ----
class SessionCreate(BaseModel):
    course_id: int


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    student_id: int
    status: AttendanceStatus
    method: AttendanceMethod
    confidence: float | None = None


class AttendanceRow(BaseModel):
    """Enriched row for the teacher review UI."""
    student_id: int
    roll_no: str
    full_name: str
    status: AttendanceStatus
    method: AttendanceMethod
    confidence: float | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    state: SessionState
    started_at: datetime
    faces_detected: int
    error: str | None = None


class SessionDetail(SessionOut):
    records: list[AttendanceRow] = []


class CorrectionItem(BaseModel):
    student_id: int
    status: AttendanceStatus


class CorrectionRequest(BaseModel):
    corrections: list[CorrectionItem]
