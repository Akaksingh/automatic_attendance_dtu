"""Pydantic request and response schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import AttendanceStatus, SessionState, UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    profile_image_url: str | None


class AuthResponse(BaseModel):
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AccountRegistration(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class StudentRegistration(AccountRegistration):
    roll_no: str = Field(min_length=1, max_length=64)


class TeacherCreate(AccountRegistration):
    pass


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    profile_image_url: str | None = Field(default=None, max_length=2048)
    current_password: str | None = Field(default=None, min_length=8, max_length=128)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class GroupUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    join_code: str
    owner_id: UUID
    archived_at: datetime | None
    created_at: datetime


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class GroupPage(BaseModel):
    items: list[GroupOut]
    meta: PageMeta


class JoinGroupRequest(BaseModel):
    join_code: str = Field(min_length=4, max_length=16)


class AddStudentRequest(BaseModel):
    roll_no: str = Field(min_length=1, max_length=64)


class GroupRosterResult(BaseModel):
    row: int
    roll_no: str | None = None
    status: str
    student_id: UUID | None = None
    error: str | None = None


class GroupRosterImportOut(BaseModel):
    added: int
    failed: int
    results: list[GroupRosterResult]


class GroupRosterStudentOut(BaseModel):
    student_id: UUID
    user_id: UUID
    roll_no: str
    full_name: str
    email: EmailStr
    profile_image_url: str | None
    joined_at: datetime


class GroupRosterPage(BaseModel):
    items: list[GroupRosterStudentOut]
    meta: PageMeta


class AttendanceOut(BaseModel):
    session_id: UUID
    group_id: UUID
    group_name: str
    status: AttendanceStatus
    marked_at: datetime


class AttendancePage(BaseModel):
    items: list[AttendanceOut]
    meta: PageMeta


class SessionPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    image_url: str
    expires_at: datetime
    processed_at: datetime | None
    error: str | None
    created_at: datetime


class SessionAttendanceOut(BaseModel):
    id: UUID
    student_id: UUID
    status: AttendanceStatus
    marked_at: datetime


class SessionOut(BaseModel):
    id: UUID
    group_id: UUID
    created_by_id: UUID
    state: SessionState
    started_at: datetime
    finalized_at: datetime | None
    processing_total: int
    processing_completed: int
    processing_message: str | None
    photos: list[SessionPhotoOut]
    attendance: list[SessionAttendanceOut]


class SessionPage(BaseModel):
    items: list[SessionOut]
    meta: PageMeta


class AttendanceStatusUpdate(BaseModel):
    status: AttendanceStatus


class StudentPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    image_url: str | None
    similarity_to_previous: float | None
    is_profile: bool
    created_at: datetime


class PhotoJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    similarity_to_previous: float | None
    error: str | None
    photo_id: UUID | None
    created_at: datetime
    completed_at: datetime | None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    roll_no: str
    full_name: str
    profile_image_url: str | None
    photo_count: int
    photos: list[StudentPhotoOut]


class StudentPage(BaseModel):
    items: list[StudentOut]
    meta: PageMeta


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: str
    status: str
    total: int
    processed: int
    succeeded: int
    failed: int
    error: str | None
    error_file_url: str | None = None
    created_at: datetime
    completed_at: datetime | None


class StudentProvisionOut(BaseModel):
    student: StudentOut
    photo_job: PhotoJobOut | None = None
    temporary_password: str | None = None


class BulkStudentResult(BaseModel):
    row: int
    email: EmailStr | None = None
    roll_no: str | None = None
    status: str
    student_id: UUID | None = None
    photo_job_id: UUID | None = None
    temporary_password: str | None = None
    error: str | None = None


class BulkStudentImportOut(BaseModel):
    created: int
    failed: int
    results: list[BulkStudentResult]
