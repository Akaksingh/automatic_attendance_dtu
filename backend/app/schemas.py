"""Pydantic request/response models."""
from datetime import datetime
from typing import Optional

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


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[Role] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


# ---- Students ----
class StudentCreate(BaseModel):
    roll_no: str
    full_name: str
    department: str = ""
    biometric_consent: bool = False


class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None
    biometric_consent: Optional[bool] = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    roll_no: str
    full_name: str
    department: str
    biometric_consent: bool
    consent_recorded_at: Optional[datetime] = None
    has_embedding: bool = False
    created_at: datetime


class ConsentRequest(BaseModel):
    granted: bool = True


# ---- Courses / enrollment ----
class CourseCreate(BaseModel):
    code: str
    name: str
    department: str = ""


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    department: str


class CourseDetail(CourseOut):
    """Course with roster count for the admin UI."""
    enrolled_count: int = 0


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
    liveness_score: float | None = None  # None = not checked; 0-1 when ONNX model is active


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


class SessionListItem(BaseModel):
    """Lightweight session row for the history list — no attendance records."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    course_code: str
    course_name: str
    state: SessionState
    started_at: datetime
    faces_detected: int
    teacher_name: str


class CorrectionItem(BaseModel):
    student_id: int
    status: AttendanceStatus


class CorrectionRequest(BaseModel):
    corrections: list[CorrectionItem]


# ---- Reports ----
class StudentAttendanceSummary(BaseModel):
    student_id: int
    roll_no: str
    full_name: str
    total_sessions: int
    attended: int
    percentage: float


class CourseAttendanceReport(BaseModel):
    course_id: int
    course_code: str
    course_name: str
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    total_sessions: int
    students: list[StudentAttendanceSummary]
